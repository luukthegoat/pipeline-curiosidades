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
ORDEN = ["jason", "lucia", "pareja", "vicecity", "cal", "raul", "cayos", "boobie", "trailer", "grassrivers", "brian",
         "vintage", "drequan", "portgellhorn", "realdimez", "ambrosia", "ultimate", "kalaga"]

PROMPT = """Eres guionista de un canal español de YouTube Shorts sobre GTA 6 (Grand Theft Auto VI). Escribe un Short de
20-25 segundos sobre {nombre} ({tipo}), usando SOLO lo que dice el MATERIAL OFICIAL de Rockstar Games: no inventes
nada del juego (ni misiones, ni escenas, ni relaciones, ni detalles que no estén en el material).
- 4 o 5 escenas; en total, entre 52 y 70 palabras. Frases cortas y fáciles de decir en voz alta, en español de España,
  con el tono de un fan que cuenta algo que poca gente sabe.
- La PRIMERA frase (12 palabras como mucho) engancha con lo más llamativo. No empieces por «En GTA 6…» ni por el
  nombre a secas.
- Si te paso CAPTURAS con su descripción, elige para cada escena la que mejor acompañe lo que se dice ("captura": su
  número), sin repetir si puedes.
- Di «GTA 6» al menos una vez (así lo busca la gente).
- Respeta QUIÉN hace cada cosa y A QUIÉN, tal como lo dice el material (si dice que A deja vivir gratis a B a cambio
  de algo, no escribas que B trabaja gratis para A). Ante la duda, usa casi las mismas palabras del material.
- El título y el gancho también salen del material: nada de apodos ni cargos que no estén en él.
- Si el material habla de drogas, atracos o clubes, cuéntalo como lo cuenta el material, sin recrearte ni presentarlo
  como algo bueno.
- La última escena es SOLO una pregunta al espectador para que comente (termina en «?»).
- Las frases del personaje se citan tal cual, sin decir a quién se las dice si el material no lo dice.
Responde SOLO con JSON: {{"titulo": "título con gancho que incluya «GTA 6» (máx. 60 caracteres)",
"gancho": "texto grande del primer segundo (3 a 6 palabras)", "escenas": [{{"narracion": "…", "captura": 1}}],
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
    con_texto = [f for f in fotos if f.stem in descripciones]
    lista_capturas = ("\n\nCAPTURAS:\n" + "\n".join(f"{i}. {descripciones[f.stem]}" for i, f in enumerate(con_texto, 1))
                      if con_texto else "")
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("falta GROQ_API_KEY en el archivo .env")
    modelo = os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO
    for intento in range(1, 4):
        try:
            g = json.loads(paso1_guiones.llamar_groq(
                api_key, modelo, PROMPT.format(nombre=p["nombre"], tipo=TIPOS_TEMA.get(p.get("tipo"), "un tema")),
                f"MATERIAL OFICIAL:\n{texto_material}{lista_capturas}"))
            escenas = [{"narracion": _limpio(e.get("narracion", "")), "captura": e.get("captura")}
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
    if 1 in malas:
        print(f"  título sin respaldo («{titulo}»): se usa uno seguro")
        titulo = (f"Quién es {p['nombre']} en GTA 6" if p.get("tipo") == "personaje"
                  else f"Así es {p['nombre']} en GTA 6")
    if 2 in malas:
        print(f"  gancho sin respaldo («{gancho}»): se usa uno seguro")
        gancho = f"{p['nombre']} en GTA 6"
    # La captura de cada escena: la que eligió la IA por su descripción y, si no, la siguiente sin usar
    usadas, elegidas = set(), []
    for e in escenas:
        try:
            foto = con_texto[int(e.get("captura")) - 1]
        except (TypeError, ValueError, IndexError):
            foto = None
        if foto is None or foto in usadas:
            foto = next((f for f in fotos if f not in usadas), fotos[len(elegidas) % len(fotos)] if fotos else None)
        usadas.add(foto)
        elegidas.append(foto)
    escenas = [{"numero": i, "narracion": e["narracion"], "visual": foto.name if foto else ""}
               for i, (e, foto) in enumerate(zip(escenas, elegidas), start=1)]
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
        "credito": "Imágenes: Rockstar Games (material oficial de prensa)", "estilo": "fotos",
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
    for e in guion["escenas"]:
        imagen = fotos.get(e["visual"]) or next(iter(fotos.values()))
        plano(imagen, carpeta / f"escena_{e['numero']:02d}.mp4", duraciones[e["numero"]] + 1.0, e["numero"] % 2 == 1)
        print(f"  plano {e['numero']}: {imagen.name}")


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
    lista = hechos()
    lista[clave] = {"fecha": date.today().isoformat(), "guion": ruta.stem}
    HECHOS.parent.mkdir(parents=True, exist_ok=True)
    HECHOS.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Shorts de GTA 6 con el material oficial de Rockstar Games")
    parser.add_argument("--personaje", choices=ORDEN)
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
    if args.lista:
        for clave in ORDEN:
            print(f"{clave:10} {material()['temas'][clave]['nombre']:16} {hecho.get(clave, {}).get('fecha', '—')}")
        return 0
    clave = args.personaje or next((c for c in ORDEN if c not in hecho), None)
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
