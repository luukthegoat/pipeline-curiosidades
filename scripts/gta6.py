"""Shorts de GTA 6 con el material oficial de prensa de Rockstar Games (capturas y textos).

Rockstar publica en https://www.rockstargames.com/VI/media sus capturas y vídeos para «descargar y compartir»; aquí
se usan las capturas descargadas en salida/gta6/capturas y los textos oficiales de salida/gta6/material.json (no van
en el repositorio). El guion lo escribe la IA SOLO con ese material y lo comprueba el verificador; cada captura se
convierte en un plano vertical que se desliza poco a poco, con la voz y los subtítulos encima.

Uso:
    python scripts/gta6.py --personaje cal      # vídeo de un personaje
    python scripts/gta6.py --siguiente          # el siguiente personaje que aún no tenga vídeo
    python scripts/gta6.py --lista              # personajes y si ya tienen vídeo
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv

import paso1_guiones
import video_ia

load_dotenv()

CARPETA = Path("salida/gta6")
MATERIAL = CARPETA / "material.json"
CAPTURAS = CARPETA / "capturas"
HECHOS = Path("salida/_trabajo/gta6.json")
ANCHO, ALTO, FPS = 1080, 1920, 30
# Primero los protagonistas; después, alternando personajes, zonas del mapa y novedades
ORDEN = ["lanzamiento", "album", "radio1", "festival", "radio2", "justice",  # los del día del lanzamiento, antes
         "jason", "lucia", "pareja", "vicecity", "cal", "raul", "cayos", "boobie", "trailer", "grassrivers", "brian",
         "vintage", "drequan", "portgellhorn", "realdimez", "ambrosia", "ultimate", "kalaga"]

PROMPT = """Eres guionista de un canal español de YouTube Shorts sobre GTA 6 (Grand Theft Auto VI). Escribe un Short de
20-25 segundos sobre {nombre} ({tipo}), usando SOLO lo que dice el MATERIAL OFICIAL de Rockstar Games: no inventes
nada del juego (ni misiones, ni escenas, ni relaciones, ni detalles que no estén en el material).
- 4 o 5 escenas; en total, entre 52 y 70 palabras. Frases cortas y fáciles de decir en voz alta, en español de España,
  con el tono de un fan que cuenta algo que poca gente sabe.
- La PRIMERA frase (12 palabras como mucho) engancha con lo más llamativo. No empieces por «En GTA 6…» ni por el
  nombre a secas.
- Para cada escena elige de la lista de IMÁGENES la que mejor acompañe lo que se dice ("visual": su código), sin
  repetir. Las «T…» son planos en movimiento de los tráileres (enganchan más); las «F…», capturas del tema.
  La escena 1 lleva SIEMPRE un plano «T» con acción. Usa al menos 2 «T» y, si hay «F», al menos 1 «F».
- Di «GTA 6» al menos una vez (así lo busca la gente).
- Respeta QUIÉN hace cada cosa y A QUIÉN, tal como lo dice el material (si dice que A deja vivir gratis a B a cambio
  de algo, no escribas que B trabaja gratis para A). Ante la duda, usa casi las mismas palabras del material.
- El título y el gancho también salen del material: nada de apodos ni cargos que no estén en él.
- Si el material habla de drogas, atracos o clubes, cuéntalo como lo cuenta el material, sin recrearte ni presentarlo
  como algo bueno.
- La última escena es SOLO una pregunta al espectador para que comente (termina en «?»).
- Las frases del personaje se citan tal cual, sin decir a quién se las dice si el material no lo dice.
Responde SOLO con JSON: {{"titulo": "título con gancho que incluya «GTA 6» (máx. 60 caracteres)",
"gancho": "texto grande del primer segundo (3 a 6 palabras)", "escenas": [{{"narracion": "…", "visual": "T3"}}],
"pregunta": "la pregunta final", "musica": "epico, misterio o neutro"}}"""


def material() -> dict:
    if not MATERIAL.exists():
        raise RuntimeError(f"falta {MATERIAL}: el material oficial de Rockstar Games")
    return json.loads(MATERIAL.read_text(encoding="utf-8"))


def hechos() -> dict:
    try:
        return json.loads(HECHOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def capturas(tema: dict) -> list:
    """Las capturas del tema, sin las excluidas (desnudez o contenido sexual: YouTube limita los anuncios)."""
    fuera = set(material().get("excluidas", []))
    rutas = []
    for carpeta in tema["capturas"]:
        rutas += sorted(p for p in (CAPTURAS / carpeta).glob("*")
                        if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.stem not in fuera)
    return rutas


USADOS = Path("salida/_trabajo/gta6_planos_usados.json")
PLANOS_A_ELEGIR = 30  # planos de tráiler que se ofrecen a la IA en cada guion (no caben todos)


def planos() -> dict:
    """{id: plano} de los planos útiles de los tráileres (los prepara gta6_trailers.py)."""
    try:
        lista = json.loads((CARPETA / "planos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {pl["id"]: pl for pl in lista if pl.get("util") and not pl.get("sexual") and Path(pl["video"]).exists()}


def planos_para_elegir() -> list:
    """Unos cuantos planos para este guion: primero los que aún no han salido en ningún vídeo (y, de ellos, los de
    acción), en orden al azar para que cada vídeo sea distinto."""
    import random
    try:
        usados = set(json.loads(USADOS.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        usados = set()
    # Sin sangre ni disparos: YouTube quita anuncios si hay violencia gráfica al principio, y así no hay que mirarlo
    todos = [pl for pl in planos().values() if not pl.get("violento")]
    random.shuffle(todos)
    todos.sort(key=lambda pl: (pl["id"] in usados, not pl["accion"]))
    return todos[:PLANOS_A_ELEGIR]


def apuntar_planos(ruta_guion: Path) -> None:
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    try:
        usados = json.loads(USADOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        usados = []
    usados += [e["visual"].split(":", 1)[1] for e in guion["escenas"] if str(e.get("visual", "")).startswith("trailer:")]
    USADOS.parent.mkdir(parents=True, exist_ok=True)
    USADOS.write_text(json.dumps(sorted(set(usados))), encoding="utf-8")


TIPOS_TEMA = {"personaje": "un personaje del juego", "lugar": "una zona del mapa del juego", "extra": "una novedad"}


def _limpio(texto) -> str:
    """Sin espacios de más ni los guiones y espacios «raros» que a veces pone la IA (no salen en todas las fuentes)."""
    texto = str(texto or "")
    for raro, normal in (("‑", "-"), ("‐", "-"), (" ", " "), (" ", " ")):
        texto = texto.replace(raro, normal)
    return " ".join(texto.split())


def escribir_guion(clave: str) -> Path:
    datos = material()
    p = datos["temas"][clave]
    texto_material = f"GENERAL: {datos['general']}\n\n{p['nombre'].upper()}: {p['texto']}"
    fotos = capturas(p)
    descripciones = datos.get("descripciones", {})
    # Lo que se puede ver en cada escena: capturas del tema (F) y planos de los tráileres (T), con su descripción
    opciones = {f"F{i}": {"captura": f.name, "texto": descripciones.get(f.stem, f"captura oficial de {p['nombre']}")}
                for i, f in enumerate(fotos[:12], 1)}
    opciones.update({f"T{i}": {"plano": pl["id"], "texto": pl["descripcion"] + (" (acción)" if pl["accion"] else "")}
                     for i, pl in enumerate(planos_para_elegir(), 1)})
    lista_capturas = "\n\nIMÁGENES:\n" + "\n".join(f"{c}. {o['texto']}" for c, o in opciones.items())
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("falta GROQ_API_KEY en el archivo .env")
    modelo = os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO
    for intento in range(1, 4):
        try:
            g = json.loads(paso1_guiones.llamar_groq(
                api_key, modelo, PROMPT.format(nombre=p["nombre"], tipo=TIPOS_TEMA.get(p.get("tipo"), "un tema")),
                f"MATERIAL OFICIAL:\n{texto_material}{lista_capturas}"))
            escenas = [{"narracion": _limpio(e.get("narracion", "")), "elegido": str(e.get("visual", "")).strip().upper()}
                       for e in g.get("escenas", []) if isinstance(e, dict) and str(e.get("narracion", "")).strip()]
        except (ValueError, AttributeError) as error:
            print(f"  intento {intento}: respuesta inservible ({error})")
            continue
        palabras = sum(len(e["narracion"].split()) for e in escenas)
        pregunta = _limpio(g.get("pregunta", ""))
        if escenas and not escenas[-1]["narracion"].rstrip(" »\"").endswith("?") and pregunta.endswith("?"):
            escenas.append({"narracion": pregunta})  # la deja en su campo aparte: se dice al final
            if len(escenas) > 5:
                escenas[-2:] = [{"narracion": f"{escenas[-2]['narracion']} {pregunta}"}]
        pregunta_final = bool(escenas) and escenas[-1]["narracion"].rstrip(" »\"").endswith("?")
        if (4 <= len(escenas) <= 5 and 45 <= palabras <= 80 and "gta" in str(g.get("titulo", "")).lower()
                and pregunta_final):
            break
        print(f"  intento {intento}: {len(escenas)} escenas, {palabras} palabras"
              f"{'' if pregunta_final else ', sin pregunta al final'}; se pide otra vez")
    else:
        raise RuntimeError("la IA no ha dado un guion válido en 3 intentos")

    titulo = _limpio(g["titulo"])[:70]
    gancho = _limpio(g.get("gancho", ""))
    # El verificador compara con el material; lo que no cuadre se reescribe una vez y se vuelve a mirar
    dudas = paso1_guiones.verificar_guion(api_key, paso1_guiones.MODELO_VERIFICADOR, texto_material, escenas)
    if dudas:
        print(f"  el verificador marca {len(dudas)} frase(s); se corrigen")
        corregidas = paso1_guiones.corregir_dudas(api_key, modelo, texto_material, escenas, dudas, "es")
        if corregidas:
            escenas = [{**anterior, "narracion": _limpio(e["narracion"])} for anterior, e in zip(escenas, corregidas)]
            dudas = paso1_guiones.verificar_guion(api_key, paso1_guiones.MODELO_VERIFICADOR, texto_material, escenas)
    # El título y el gancho salen en pantalla: si el verificador no los respalda, se cambian por unos seguros
    extra = paso1_guiones.verificar_guion(api_key, paso1_guiones.MODELO_VERIFICADOR, texto_material,
                                          [{"narracion": titulo}, {"narracion": gancho or "-"}])
    malas = {d.get("escena") for d in extra}
    # Los de reserva: sin repetir «GTA 6» si el nombre del tema ya lo lleva («el lanzamiento de GTA 6 en GTA 6»)
    con_juego = p["nombre"] if "GTA 6" in p["nombre"] else f"{p['nombre']} en GTA 6"
    if 1 in malas:
        print(f"  título sin respaldo («{titulo}»): se usa uno seguro")
        titulo = f"Quién es {con_juego}" if p.get("tipo") == "personaje" else f"Así es {con_juego}"
    if 2 in malas:
        print(f"  gancho sin respaldo («{gancho}»): se usa uno seguro")
        gancho = con_juego[0].upper() + con_juego[1:]
    # Lo que se ve en cada escena: lo que eligió la IA y, si no vale o se repite, lo siguiente sin usar. La primera
    # escena, siempre un plano de tráiler (el movimiento del primer segundo es lo que frena el dedo).
    planos_t = [c for c in opciones if c.startswith("T")]
    capturas_f = [c for c in opciones if c.startswith("F")]
    usadas, elegidas = set(), []
    for n, e in enumerate(escenas):
        codigo = e.get("elegido", "")
        if codigo not in opciones or codigo in usadas or (n == 0 and not codigo.startswith("T") and planos_t):
            reserva = (planos_t if n == 0 or n % 2 == 0 else capturas_f) or planos_t or capturas_f
            codigo = next((c for c in reserva if c not in usadas), "")
        usadas.add(codigo)
        elegidas.append(opciones.get(codigo, {}))
    escenas = [{"numero": i, "narracion": e["narracion"],
                "visual": f"trailer:{o['plano']}" if o.get("plano") else o.get("captura", "")}
               for i, (e, o) in enumerate(zip(escenas, elegidas), start=1)]
    hoy = date.today().isoformat()
    sin_articulo = re.sub(r"^(el|la|los|las)\s+|\s+de GTA 6$", "", p["nombre"], flags=re.I)
    sin_espacios = "".join(c for c in sin_articulo.title() if c.isalnum())
    guion = {
        "fecha": hoy, "anio_evento": None, "evento": f"GTA 6: {p['nombre']}", "idioma": "es",
        "titulo": titulo, "palabras": paso1_guiones.contar_palabras(escenas),
        "escenas": escenas, "nombre_corto": f"GTA6 {p['nombre']}", "gancho": gancho,
        "musica": g.get("musica") if g.get("musica") in ("epico", "misterio", "neutro") else "epico",
        "hashtags": ["#GTA6", "#GTAVI", "#GTA", f"#{sin_espacios}"],
        "pregunta": " ".join(str(g.get("pregunta", "")).split()), "palabras_clave": [],
        "fuentes": [datos["fuente"]], "sin_respaldo": dudas, "verificado": not dudas, "modelo": modelo,
        "clips_propios": {"origen": "capturas oficiales de Rockstar Games", "personaje": clave},
        "credito": "Imágenes y tráileres: Rockstar Games (material oficial de prensa)", "estilo": "fotos",
    }
    ruta = paso1_guiones.CARPETA_SALIDA / f"{hoy}_gta6_{clave}_es.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  guion: {ruta} · «{guion['titulo']}»" + (f" · {len(dudas)} frase(s) para revisar" if dudas else ""))
    return ruta


def plano(imagen: Path, destino: Path, segundos: float, hacia_la_derecha: bool) -> None:
    """Una captura horizontal a pantalla completa en vertical, deslizándose despacio de un lado al otro."""
    from PIL import Image
    ancho, alto = Image.open(imagen).size
    escala = 2  # se trabaja al doble y se reduce al final: así el movimiento no da saltitos
    w = round(ancho * ALTO * escala / alto)
    margen = max(0, w - ANCHO * escala)
    a, b = 0.3 * margen, 0.7 * margen
    if not hacia_la_derecha:
        a, b = b, a
    filtro = (f"scale={w}:{ALTO * escala},crop={ANCHO * escala}:{ALTO * escala}:x='{a:.1f}+({b - a:.1f})*t/{segundos:.3f}':y=0,"
              f"scale={ANCHO}:{ALTO},setsar=1,format=yuv420p")
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS),
                    "-t", f"{segundos:.3f}", "-i", str(imagen), "-vf", filtro, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-an", str(destino)], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def preparar_planos(ruta_guion: Path) -> None:
    """Un plano por escena, de la duración de su audio, en la carpeta de clips que usa el montaje."""
    nombre = ruta_guion.stem
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    p = material()["temas"][guion["clips_propios"]["personaje"]]
    fotos = {f.name: f for f in capturas(p)}
    audio = json.loads((Path("salida/audio") / nombre / "escenas.json").read_text(encoding="utf-8"))
    duraciones = {e["numero"]: e["duracion_s"] for e in audio["escenas"]}
    carpeta = video_ia.carpeta_clips(nombre)
    for viejo in carpeta.glob("escena_*"):
        viejo.unlink()
    de_trailer = planos()
    for e in guion["escenas"]:
        destino, segundos = carpeta / f"escena_{e['numero']:02d}.mp4", duraciones[e["numero"]] + 1.0
        ident = str(e.get("visual", "")).split("trailer:", 1)[-1] if str(e.get("visual", "")).startswith("trailer:") else ""
        if ident in de_trailer:
            trozo_de_trailer(de_trailer[ident], destino, segundos, de_trailer)
            print(f"  plano {e['numero']}: tráiler {ident}")
            continue
        imagen = fotos.get(e["visual"]) or next(iter(fotos.values()))
        plano(imagen, destino, segundos, e["numero"] % 2 == 1)
        print(f"  plano {e['numero']}: {imagen.name}")


RECORTES = CARPETA / "recortes.json"


def area_con_imagen(video: str) -> tuple:
    """(ancho, alto, x, y) de la parte del tráiler con imagen, sin las franjas negras de cine. Se mira una vez por
    tráiler (con cropdetect de ffmpeg en varios momentos) y se guarda."""
    try:
        guardados = json.loads(RECORTES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        guardados = {}
    if video in guardados:
        return tuple(guardados[video])
    medidas = []
    for segundo in (20, 45, 70, 95):
        salida = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-ss", str(segundo), "-t", "2",
                                 "-i", video, "-an", "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
        encontradas = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", salida)
        if encontradas:
            medidas.append(tuple(map(int, encontradas[-1])))
    if not medidas:
        return (3840, 2160, 0, 0)
    # La mayor zona con imagen de las medidas (en una escena oscura, cropdetect puede quedarse corto)
    area = max(medidas, key=lambda m: m[0] * m[1])
    guardados[video] = area
    RECORTES.write_text(json.dumps(guardados, indent=2), encoding="utf-8")
    return area


def trozo_de_trailer(pl: dict, destino: Path, segundos: float, todos: dict) -> None:
    """El trozo del tráiler desde el principio de ese plano, recortado a vertical por el centro y SIN su audio (las
    canciones de los tráileres son de otros artistas: harían saltar Content ID). Si el plano es más corto que la
    frase, sigue con los planos siguientes del tráiler, como en el original."""
    final_seguro = max(p["fin"] for p in todos.values() if p["video"] == pl["video"])
    inicio = max(0.0, min(pl["inicio"], final_seguro - segundos))
    w, h, x, y = area_con_imagen(pl["video"])
    ancho = round(h * 9 / 16 / 2) * 2
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{inicio:.2f}", "-t",
                    f"{segundos:.3f}", "-i", pl["video"], "-an", "-vf",
                    f"crop={ancho}:{h}:{x + (w - ancho) // 2}:{y},scale={ANCHO}:{ALTO},setsar=1,fps={FPS},format=yuv420p",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(destino)], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def ejecutar(script: str, *argumentos: str) -> None:
    resultado = subprocess.run([sys.executable, str(Path(__file__).parent / script), *argumentos],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    salida = (resultado.stdout + resultado.stderr).strip()
    print("\n".join("    " + l for l in salida.splitlines()[-6:]))
    if resultado.returncode:
        raise RuntimeError(f"{script} ha fallado")


def montar(ruta: Path) -> None:
    """Voz, un plano por escena (de la duración de su voz) y el vídeo. También sirve para rehacer uno ya hecho."""
    ejecutar("paso2_audio.py", str(ruta), "--forzar")
    preparar_planos(ruta)
    ejecutar("paso3_video.py", str(Path("salida/audio") / ruta.stem), "--forzar")


def crear(clave: str) -> Path:
    print(f"· GTA 6: {material()['temas'][clave]['nombre']}")
    ruta = escribir_guion(clave)
    montar(ruta)
    apuntar_planos(ruta)  # para que el siguiente vídeo use otros planos de los tráileres
    lista = hechos()
    lista[clave] = {"fecha": date.today().isoformat(), "guion": ruta.stem}
    HECHOS.parent.mkdir(parents=True, exist_ok=True)
    HECHOS.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Shorts de GTA 6 con el material oficial de Rockstar Games")
    parser.add_argument("--personaje", help="clave del tema (python scripts/gta6.py --lista)")
    parser.add_argument("--siguiente", action="store_true", help="el siguiente personaje sin vídeo")
    parser.add_argument("--lista", action="store_true")
    parser.add_argument("--rehacer", type=Path, help="rehace voz, planos y vídeo de ese guion (tras cambiar el texto)")
    args = parser.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")
    if args.rehacer:
        try:
            montar(args.rehacer)
            return 0
        except Exception as error:  # noqa: BLE001
            print(f"[error] {error}", file=sys.stderr)
            return 1
    hecho = hechos()
    # Los temas de ORDEN primero y, detrás, los que se añadan al material (salen solos, sin tocar este archivo)
    temas = material()["temas"]
    orden = [c for c in ORDEN if c in temas] + [c for c in temas if c not in ORDEN]
    if args.lista:
        for clave in orden:
            print(f"{clave:12} {temas[clave]['nombre'][:40]:40} {hecho.get(clave, {}).get('fecha', '—')}")
        return 0
    if args.personaje and args.personaje not in temas:
        print(f"[error] no hay ningún tema «{args.personaje}»; mira --lista", file=sys.stderr)
        return 1
    clave = args.personaje or next((c for c in orden if c not in hecho), None)
    if not clave:
        print("Ya tienen vídeo todos los temas.")
        return 0
    try:
        crear(clave)
    except Exception as error:  # noqa: BLE001
        print(f"[error] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
