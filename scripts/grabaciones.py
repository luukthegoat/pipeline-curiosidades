"""Tus grabaciones de partidas convertidas en Shorts, dentro de la app.

Dos formas:
  1. CLIPS: la app busca sola los mejores momentos de la grabación (donde sube el sonido y hay más movimiento), una IA
     con visión mira cada uno y otra elige los mejores y les pone título y gancho. Cada clip sale en vertical: la
     partida en grande, el fondo desenfocado y el gancho arriba. Con el sonido del juego o con la música del canal.
  2. SHORT NARRADO: le dices en una línea qué has grabado («el easter egg del caimán en Grassrivers»); la IA mira el
     trozo, escribe un guion corto y Álvaro lo cuenta sobre tu partida, con subtítulos y el sonido del juego de fondo.

No hay una IA de edición con API gratis (Opus Clip, Vizard o Klap son de pago), así que esto se hace con Groq (gratis:
la IA que ve imágenes y la que escribe) y ffmpeg. Los vídeos quedan como guiones normales: se revisan y se programan
desde «Vídeos» como los demás.

Uso:
    python scripts/grabaciones.py clips partida.mp4 --cantidad 3 --duracion 25 --sonido juego
    python scripts/grabaciones.py narrado partida.mp4 --nota "el easter egg del caimán" [--desde 1:20 --hasta 2:05]
    python scripts/grabaciones.py rehacer salida/guiones/<guion>.json
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
import paso3_video
import video_ia

load_dotenv()

CARPETA = Path("salida/grabaciones")
TRABAJO = Path("salida/_trabajo/grabaciones")
EXTENSIONES = (".mp4", ".mov", ".mkv", ".webm", ".m4v")
ANCHO, ALTO, FPS = 1080, 1920, 30
ALTO_PARTIDA = 1440   # la partida ocupa el centro (3:4); arriba queda sitio para el gancho
MAX_CANDIDATOS = 8    # momentos que se enseñan a la IA (cada uno gasta una imagen del cupo diario de visión)
SIN_VENTANA = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

PROMPT_FOTOGRAMA = """Es un fotograma de una partida grabada del videojuego JUEGO. Responde SOLO con JSON:
{"descripcion": "qué pasa, en una frase en español (personajes, vehículos, lugar, acción)",
 "interes": de 1 a 5 (5 = momento espectacular, gracioso o raro que engancha: persecución, accidente, salto,
            explosión, algo absurdo o un lugar secreto; 1 = menú, pantalla de carga, conducir sin más, negro),
 "menu": true si es un menú, un mapa, una pantalla de carga, un logo o un rótulo,
 "sexual": true si hay desnudez o contenido sexual}"""

PROMPT_ELEGIR = """Eres el editor de un canal español de Shorts de videojuegos ({juego}). Te paso MOMENTOS candidatos de
una partida grabada por el autor del canal, con lo que se ve en cada uno y lo «movido» que es (0 a 1). Elige los
{cantidad} mejores para Shorts: los que más enganchan (acción, algo gracioso o raro); nunca menús, logos ni pantallas
de carga, ni nada vulgar o sexual. Responde SOLO con JSON: {{"elegidos": [3, 1]}} (los números, el mejor primero)."""

# Título y gancho de UN momento, solo con su descripción (si van todos juntos, la IA a veces los cruza)
PROMPT_TITULO = """Eres el editor de un canal español de Shorts de videojuegos ({juego}), apto para todos los públicos.
Con lo que se ve en este MOMENTO de una partida, escribe:
- "titulo": máx. 60 caracteres, con gancho y con «{juego}» si encaja. Solo lo que pasa en el momento: no inventes
  misiones, lugares ni nombres. Nada vulgar ni sexual (si lo que se ve lo es, quédate con la acción: «derrape»,
  «persecución», «fiesta»…).
- "gancho": 2 a 6 palabras para el texto grande de arriba («¿Esto es legal?», «No me lo esperaba»).
- "descripcion": una frase para la descripción del vídeo.
- "pregunta": una pregunta corta al espectador para los comentarios.
Responde SOLO con JSON: {{"titulo": "…", "gancho": "…", "descripcion": "…", "pregunta": "…"}}"""

PROMPT_NARRADO = """Eres guionista de un canal español de Shorts de videojuegos. El autor del canal ha grabado una
partida de {juego} y te dice qué ha grabado (NOTA DEL AUTOR); también tienes lo que se ve en varios momentos del trozo
(FOTOGRAMAS, en orden). Escribe un Short de 20-25 segundos que cuente lo que enseña la grabación, como un jugador que
comparte un secreto, un truco o un momentazo con sus seguidores.
- 4 o 5 escenas que siguen el orden de los fotogramas; en total, entre 45 y 65 palabras, en español de España, frases
  cortas y fáciles de decir en voz alta.
- La PRIMERA frase (12 palabras como mucho) engancha con lo más llamativo.
- Cuenta SOLO lo que dice la NOTA y lo que se ve en los fotogramas: no inventes datos del juego (recompensas,
  nombres, sitios, cómo se consigue) que no estén ahí.
- Cuenta la JUGADA, no describas la imagen: nada de listar ropa, colores o posturas («con gafas y camiseta verde»).
  Lo importante es la NOTA; los fotogramas solo sirven para seguir el orden de lo que pasa.
- La última escena es SOLO una pregunta al espectador (termina en «?»).
Responde SOLO con JSON: {{"titulo": "título con gancho, con «{juego}» (máx. 60 caracteres)",
"gancho": "texto grande del primer segundo (3 a 6 palabras)", "escenas": [{{"narracion": "…"}}],
"pregunta": "la pregunta final", "musica": "epico, misterio o neutro"}}"""


# --- Información de las grabaciones -------------------------------------------------------------

def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def info(video: Path) -> dict:
    """Duración, tamaño de imagen y si tiene sonido (leyendo solo la cabecera: es rápido aunque pese GB)."""
    salida = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(video)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", creationflags=SIN_VENTANA).stderr
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", salida)
    tam = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", salida)
    return {"duracion": int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3]) if dur else 0.0,
            "ancho": int(tam[1]) if tam else 1920, "alto": int(tam[2]) if tam else 1080,
            "sonido": "Audio:" in salida}


def lista() -> list:
    """Las grabaciones de la carpeta, la más reciente primero."""
    if not CARPETA.exists():
        return []
    return sorted((p for p in CARPETA.iterdir() if p.suffix.lower() in EXTENSIONES),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def ruta_grabacion(archivo: str) -> Path:
    ruta = (CARPETA / Path(archivo).name).resolve()
    if ruta.parent != CARPETA.resolve() or not ruta.exists():
        raise ValueError(f"no encuentro la grabación «{archivo}» en {CARPETA}")
    return ruta


def portada(video: Path) -> Path:
    """Un fotograma pequeño para la lista de la app (se hace una vez)."""
    destino = TRABAJO / video.stem / "portada.jpg"
    if not destino.exists() or destino.stat().st_mtime < video.stat().st_mtime:
        destino.parent.mkdir(parents=True, exist_ok=True)
        momento = min(10.0, info(video)["duracion"] / 3)
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{momento:.1f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=480:-2", str(destino)], creationflags=SIN_VENTANA)
    return destino


def fotograma(video: Path, segundo: float, destino: Path, ancho: int = 640) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{max(0.0, segundo):.2f}", "-i", str(video),
                    "-frames:v", "1", "-vf", f"scale={ancho}:-2", str(destino)], check=True, creationflags=SIN_VENTANA)
    return destino


def segundos(texto: str):
    """«1:20» → 80.0; «95» → 95.0; vacío → None."""
    texto = str(texto or "").strip()
    if not texto:
        return None
    partes = [float(p) for p in texto.replace(",", ".").split(":")]
    total = 0.0
    for p in partes:
        total = total * 60 + p
    return total


# --- Dónde están los mejores momentos ---------------------------------------------------------------

def _por_segundo(salida: str, clave: str) -> dict:
    """{segundo: valor} de las líneas «pts_time:X» + «clave=valor» que imprime ffmpeg con ametadata/metadata."""
    valores, momento = {}, None
    for linea in salida.splitlines():
        t = re.search(r"pts_time:([\d.]+)", linea)
        if t:
            momento = float(t[1])
            continue
        v = re.search(re.escape(clave) + r"=(-?[\d.]+|-?inf)", linea)
        if v and momento is not None:
            numero = float(v[1]) if "inf" not in v[1] else -90.0
            segundo = int(momento)
            valores[segundo] = max(valores.get(segundo, numero), numero)
    return valores


def analizar(video: Path) -> dict:
    """Sonido (RMS) y movimiento (cambio de imagen entre fotogramas clave) de cada segundo. Se guarda por si se
    vuelve a usar la misma grabación."""
    guardado = TRABAJO / video.stem / "analisis.json"
    firma = [video.stat().st_size, int(video.stat().st_mtime)]
    if guardado.exists():
        datos = json.loads(guardado.read_text(encoding="utf-8"))
        if datos.get("firma") == firma:
            return datos
    datos_video = info(video)
    print(f"  analizando {video.name} ({datos_video['duracion'] / 60:.1f} min)…", flush=True)
    sonido = {}
    if datos_video["sonido"]:
        salida = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-i", str(video), "-vn", "-af",
             "aresample=8000,asetnsamples=n=8000:p=0,astats=metadata=1:reset=1,"
             "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SIN_VENTANA).stderr
        sonido = _por_segundo(salida, "lavfi.astats.Overall.RMS_level")
    salida = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-skip_frame", "nokey", "-i", str(video), "-an", "-vf",
         "scale=160:-2,select='gte(scene,0)',metadata=mode=print:key=lavfi.scene_score", "-vsync", "0",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SIN_VENTANA).stderr
    movimiento = _por_segundo(salida, "lavfi.scene_score")
    datos = {"firma": firma, **datos_video,
             "sonido_rms": {str(k): v for k, v in sonido.items()},
             "movimiento": {str(k): v for k, v in movimiento.items()}}
    guardado.parent.mkdir(parents=True, exist_ok=True)
    guardado.write_text(json.dumps(datos), encoding="utf-8")
    return datos


def _normalizado(valores: list) -> list:
    ordenados = sorted(valores)
    if not ordenados:
        return []
    bajo = ordenados[int(len(ordenados) * 0.05)]
    alto = ordenados[min(len(ordenados) - 1, int(len(ordenados) * 0.95))]
    rango = (alto - bajo) or 1.0
    return [min(1.0, max(0.0, (v - bajo) / rango)) for v in valores]


def puntuaciones(datos: dict) -> list:
    """Lo «movido» de cada segundo (0 a 1): sobre todo el sonido (golpes, choques, gritos) y también el movimiento."""
    total = max(1, int(datos["duracion"]))
    rms = [max(-60.0, float(datos["sonido_rms"].get(str(s), -60.0))) for s in range(total)]
    mov, ultimo = [], 0.0
    for s in range(total):  # los fotogramas clave van cada 1-2 s: los huecos se rellenan con el último valor
        ultimo = float(datos["movimiento"].get(str(s), ultimo))
        mov.append(ultimo)
    peso_sonido = 0.6 if datos.get("sonido") else 0.0
    return [peso_sonido * a + (1 - peso_sonido) * b for a, b in zip(_normalizado(rms), _normalizado(mov))]


def momentos(datos: dict, duracion: float, cantidad: int = MAX_CANDIDATOS) -> list:
    """Los trozos de `duracion` segundos más movidos, sin solaparse: [{"inicio", "fin", "puntuacion", "pico"}].
    El momento más fuerte de cada trozo queda hacia el principio: lo primero que se ve tiene que enganchar."""
    total = datos["duracion"]
    if total <= duracion + 2:
        return [{"inicio": 0.0, "fin": total, "puntuacion": 1.0, "pico": total / 2}]
    nota = puntuaciones(datos)
    largo = int(duracion)
    acumulado = [0.0]
    for valor in nota:
        acumulado.append(acumulado[-1] + valor)
    ventanas = []
    for inicio in range(3, max(4, len(nota) - largo - 2)):  # ni el principio ni el final (menús, cargas)
        ventanas.append(((acumulado[inicio + largo] - acumulado[inicio]) / largo, inicio))
    ventanas.sort(reverse=True)
    elegidos = []
    for puntuacion, inicio in ventanas:
        pico = max(range(inicio, inicio + largo), key=lambda s: nota[s])
        comienzo = min(max(0.0, pico - 0.3 * duracion), total - duracion)
        if all(comienzo + duracion <= e["inicio"] or comienzo >= e["fin"] for e in elegidos):
            elegidos.append({"inicio": round(comienzo, 1), "fin": round(comienzo + duracion, 1),
                             "puntuacion": round(puntuacion, 3), "pico": float(pico)})
        if len(elegidos) >= cantidad:
            break
    return elegidos


def ver(video: Path, segundo: float, juego: str, nombre: str) -> dict:
    """Lo que la IA con visión ve en ese momento ({} si no hay cupo)."""
    import gta6_trailers
    imagen = fotograma(video, segundo, TRABAJO / video.stem / f"{nombre}.jpg")
    try:
        return gta6_trailers.describir(imagen, PROMPT_FOTOGRAMA.replace("JUEGO", juego))
    except gta6_trailers.SinCupo:
        print("  aviso: se ha gastado el cupo diario de la IA que ve imágenes; elijo solo por sonido y movimiento")
        return {}
    except Exception as error:  # noqa: BLE001
        print(f"  aviso: la IA no ha podido ver el fotograma ({type(error).__name__})")
        return {}


# --- Montaje en vertical ------------------------------------------------------------------------------

def _filtro_vertical(ancho: int, alto: int, texto_ass: str = "") -> str:
    """La partida en grande en el centro, el fondo con la misma imagen desenfocada y, si hay, el texto de arriba."""
    if ancho / alto >= 0.75:  # grabación horizontal: se recorta el centro a 3:4
        frente = f"crop=ih*3/4:ih,scale={ANCHO}:{ALTO_PARTIDA},setsar=1"
        posicion = f"0:{(ALTO - ALTO_PARTIDA) // 2}"
    else:  # ya es vertical (p. ej. grabada con el móvil)
        frente = f"scale={ANCHO}:{ALTO}:force_original_aspect_ratio=decrease,setsar=1"
        posicion = "(W-w)/2:(H-h)/2"
    texto = f",ass={texto_ass}" if texto_ass else ""
    return (f"[0:v]split=2[f][b];[b]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},"
            f"boxblur=24:3,eq=brightness=-0.12[fondo];[f]{frente}[frente];"
            f"[fondo][frente]overlay={posicion},fps={FPS}{texto},format=yuv420p[v]")


def _ass_arriba(texto: str, duracion: float) -> str:
    fin = paso3_video.tiempo_ass(duracion)
    return ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            "Style: Arriba,Arial Black,78,&H0000D7FF,&H0000D7FF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,7,3,8,"
            "60,60,45,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,{fin},Arriba,,0,0,0,,{{\\fad(150,0)}}{paso3_video.escapar_ass(texto.upper())}\n")


def recortar(video: Path, inicio: float, duracion: float, destino: Path, texto: str = "", sonido: str = "juego",
             pista: str = "") -> None:
    """El trozo en vertical (1080x1920). sonido: «juego» (el de la grabación), «musica» (la pista) o «nada»."""
    datos = info(video)
    trabajo = destino.parent
    trabajo.mkdir(parents=True, exist_ok=True)
    nombre_ass = f"{destino.stem}.ass"
    if texto:
        (trabajo / nombre_ass).write_text(_ass_arriba(texto, duracion), encoding="utf-8")
    entradas = ["-ss", f"{inicio:.2f}", "-t", f"{duracion:.2f}", "-i", str(video.resolve())]
    filtro = _filtro_vertical(datos["ancho"], datos["alto"], nombre_ass if texto else "")
    ruta_pista = paso3_video.musica.ruta_pista(pista) if sonido == "musica" and pista else None
    fundido = f"afade=t=in:d=0.2,afade=t=out:st={max(0.0, duracion - 0.5):.2f}:d=0.5"
    if sonido == "juego" and datos["sonido"]:
        filtro += f";[0:a]{fundido}[a]"
    elif ruta_pista:
        entradas += ["-stream_loop", "-1", "-i", str(Path(ruta_pista).resolve())]
        filtro += f";[1:a]volume=0.6,atrim=0:{duracion:.2f},{fundido}[a]"
    else:
        entradas += ["-f", "lavfi", "-t", f"{duracion:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filtro += ";[1:a]anull[a]"
    paso3_video.ffmpeg([*entradas, "-filter_complex", filtro, "-map", "[v]", "-map", "[a]", "-t", f"{duracion:.2f}",
                        *paso3_video.opciones_video(), "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                        "-ac", "2", "-movflags", "+faststart", destino.name], trabajo)


# --- Guiones -----------------------------------------------------------------------------------------

def hashtags(juego: str) -> list:
    base = "".join(c for c in juego if c.isalnum())  # «GTA 6» → «GTA6» (sin cambiar mayúsculas)
    extra = ["#GTAVI", "#GTA"] if base.lower() in ("gta6", "gtavi") else []
    return [f"#{base}", *extra, "#gaming"][:4]


def _nombre_libre(base: str) -> str:
    n = 1
    while (paso1_guiones.CARPETA_SALIDA / f"{base}_{n:02d}_es.json").exists():
        n += 1
    return f"{base}_{n:02d}_es"


def _guardar(nombre: str, guion: dict) -> Path:
    ruta = paso1_guiones.CARPETA_SALIDA / f"{nombre}.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def _llamar(sistema: str, usuario: str) -> dict:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("falta GROQ_API_KEY en el archivo .env")
    texto = paso1_guiones.llamar_groq(api_key, os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO,
                                      sistema, usuario)
    datos = json.loads(texto)
    return datos if isinstance(datos, dict) else {}


def _limpio(texto) -> str:
    texto = str(texto or "")
    for raro, normal in (("‑", "-"), ("‐", "-"), (" ", " "), (" ", " ")):
        texto = texto.replace(raro, normal)
    return " ".join(texto.split())


def montar_clip(ruta_guion: Path) -> Path:
    """Hace (o rehace) el vídeo de un clip con su título y gancho actuales."""
    nombre = ruta_guion.stem
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    g = guion["grabacion"]
    video = ruta_grabacion(g["origen"])
    destino = paso3_video.destino_video(nombre, guion)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = TRABAJO / video.stem / f"{nombre}.mp4"
    pista = guion.get("musica", "neutro") if g.get("sonido") == "musica" else ""
    recortar(video, g["inicio"], g["duracion"], temporal, guion.get("gancho", ""), g.get("sonido", "juego"), pista)
    temporal.replace(destino)
    portada_clip = fotograma(destino, min(1.0, g["duracion"] / 3), TRABAJO / video.stem / f"{nombre}_portada.jpg",
                             ancho=ANCHO)
    paso3_video.crear_miniatura(portada_clip, guion.get("gancho") or guion.get("titulo", ""),
                                paso3_video.ruta_miniatura(destino))
    paso3_video.guardar_ruta_video(nombre, destino)
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    paso3_video.escribir_textos(destino, nombre, guion, [], pista)
    return destino


def crear_clips(archivo: str, cantidad: int = 3, duracion: float = 25, sonido: str = "juego",
                juego: str = "GTA 6") -> list:
    video = ruta_grabacion(archivo)
    datos = analizar(video)
    candidatos = momentos(datos, duracion)
    print(f"  {len(candidatos)} momentos candidatos; la IA los mira…", flush=True)
    for i, c in enumerate(candidatos, 1):
        c.update(ver(video, c["pico"], juego, f"candidato_{i:02d}"))
        print(f"    {i}. {c['inicio']:.0f}-{c['fin']:.0f} s · movido {c['puntuacion']:.2f} · "
              f"{c.get('descripcion', '(sin ver)')[:80]}", flush=True)
    # Fuera menús y desnudez (YouTube restringe por edad y quita anuncios)
    utiles = [c for c in candidatos if not c.get("menu") and not c.get("sexual")] or \
             [c for c in candidatos if not c.get("sexual")]
    if not utiles:
        raise RuntimeError("no hay momentos que se puedan publicar en esta grabación")
    lista_ia = "\n".join(f"{i}. ({c['inicio']:.0f}-{c['fin']:.0f} s, movido {c['puntuacion']:.2f}, interés "
                         f"{c.get('interes', '?')}) {c.get('descripcion', 'sin descripción')}"
                         for i, c in enumerate(utiles, 1))
    try:
        numeros = _llamar(PROMPT_ELEGIR.format(juego=juego, cantidad=cantidad), f"MOMENTOS:\n{lista_ia}").get("elegidos", [])
    except Exception as error:  # noqa: BLE001 — sin IA: los más movidos
        print(f"  aviso: la IA no ha podido elegir ({type(error).__name__}); van los más movidos")
        numeros = []
    orden = []
    for n in [*numeros, *range(1, len(utiles) + 1)]:  # los que elija la IA y, si faltan, los más movidos
        try:
            c = utiles[int(n) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        if c not in orden:
            orden.append(c)
    rutas = []
    base = f"{date.today().isoformat()}_grabacion_{paso1_guiones.slug(video.stem)[:30]}"
    for c in orden[:cantidad]:
        try:
            e = _llamar(PROMPT_TITULO.format(juego=juego),
                        f"MOMENTO: {c.get('descripcion') or 'una jugada con mucha acción'}")
        except Exception:  # noqa: BLE001
            e = {}
        e = {"gancho": "Mira esto", "pregunta": "¿Te ha pasado algo así?", **{k: v for k, v in e.items() if v}}
        titulo = _limpio(e.get("titulo")) or f"Momentazo en {juego}"
        nombre = _nombre_libre(base)
        guion = {
            "fecha": date.today().isoformat(), "anio_evento": None, "evento": f"Clip de {video.name}", "idioma": "es",
            "titulo": titulo[:70], "gancho": _limpio(e.get("gancho"))[:40],
            "escenas": [{"numero": 1, "narracion": _limpio(e.get("descripcion")) or titulo,
                         "visual": "grabación propia"}],
            "palabras": 0, "nombre_corto": f"{juego} clip", "musica": "neutro" if sonido == "musica" else "ninguna",
            "hashtags": hashtags(juego), "pregunta": _limpio(e.get("pregunta")), "palabras_clave": [],
            "fuentes": [], "sin_respaldo": [], "verificado": False,
            "grabacion": {"origen": video.name, "modo": "clips", "inicio": c["inicio"],
                          "duracion": round(c["fin"] - c["inicio"], 2), "sonido": sonido, "juego": juego},
        }
        ruta = _guardar(nombre, guion)
        print(f"  clip {len(rutas) + 1}: {c['inicio']:.0f}-{c['fin']:.0f} s · «{titulo}»", flush=True)
        print(f"    → {montar_clip(ruta)}", flush=True)
        rutas.append(ruta)
    return rutas


# --- Short narrado -------------------------------------------------------------------------------------

def preparar_planos(ruta_guion: Path) -> None:
    """Un trozo vertical de la grabación por escena, seguidos y de la duración de su voz (con el sonido del juego,
    que el montaje pone de fondo, bajito)."""
    nombre = ruta_guion.stem
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    g = guion["grabacion"]
    video = ruta_grabacion(g["origen"])
    audio = json.loads((paso3_video.CARPETA_AUDIO / nombre / "escenas.json").read_text(encoding="utf-8"))
    duraciones = [e["duracion_s"] for e in audio["escenas"]]
    tramo = max(1.0, g["fin"] - g["inicio"])
    carpeta = video_ia.carpeta_clips(nombre)
    carpeta.mkdir(parents=True, exist_ok=True)
    for viejo in carpeta.glob("escena_*"):
        viejo.unlink()
    cursor = g["inicio"]
    for escena, dur in zip(audio["escenas"], duraciones):
        # Si la voz dura más que el trozo grabado, cada escena avanza en proporción; si no, la partida va seguida
        paso = dur * min(1.0, tramo / sum(duraciones))
        recortar(video, cursor, dur + 1.0, carpeta / f"escena_{escena['numero']:02d}.mp4", "", "juego")
        cursor += paso


def montar_narrado(ruta_guion: Path) -> None:
    """Voz, planos y montaje (con subtítulos, gancho, música y cierre, como los demás Shorts)."""
    _ejecutar("paso2_audio.py", str(ruta_guion))
    preparar_planos(ruta_guion)
    _ejecutar("paso3_video.py", str(paso3_video.CARPETA_AUDIO / ruta_guion.stem), "--forzar")


def _ejecutar(script: str, *argumentos: str) -> None:
    resultado = subprocess.run([sys.executable, str(Path(__file__).parent / script), *argumentos],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               creationflags=SIN_VENTANA)
    salida = (resultado.stdout + resultado.stderr).strip()
    print("\n".join("    " + linea for linea in salida.splitlines()[-5:]), flush=True)
    if resultado.returncode:
        raise RuntimeError(f"{script} ha fallado")


def crear_narrado(archivo: str, nota: str, desde=None, hasta=None, juego: str = "GTA 6") -> Path:
    video = ruta_grabacion(archivo)
    total = info(video)["duracion"]
    if desde is None:  # sin trozo elegido: el más movido de unos 40 s
        mejor = momentos(analizar(video), min(40.0, total), 1)[0]
        desde, hasta = mejor["inicio"], mejor["fin"]
    hasta = min(total, hasta if hasta is not None else desde + 40)
    if hasta - desde < 5:
        raise ValueError("el trozo es demasiado corto: elige al menos 5 segundos")
    print(f"  trozo: {desde:.0f}-{hasta:.0f} s; la IA lo mira…", flush=True)
    vistas = []
    for i in range(5):
        momento = desde + (hasta - desde) * (i + 0.5) / 5
        d = ver(video, momento, juego, f"narrado_{i + 1}")
        vistas.append(d.get("descripcion") or "(sin ver)")
        if d.get("sexual"):
            print(f"  ⚠ en el segundo {momento:.0f} hay desnudez o contenido sexual: YouTube restringirá el vídeo por "
                  "edad. Mejor elige otro trozo.", flush=True)
        print(f"    {momento:.0f} s · {vistas[-1][:90]}", flush=True)
    fotogramas = "\n".join(f"{i}. {t}" for i, t in enumerate(vistas, 1))
    for intento in range(1, 4):
        g = _llamar(PROMPT_NARRADO.format(juego=juego),
                    f"NOTA DEL AUTOR: {nota}\n\nFOTOGRAMAS:\n{fotogramas}")
        escenas = [{"narracion": _limpio(e.get("narracion"))} for e in g.get("escenas", [])
                   if isinstance(e, dict) and _limpio(e.get("narracion"))]
        pregunta = _limpio(g.get("pregunta"))
        if escenas and not escenas[-1]["narracion"].rstrip(" »\"").endswith("?") and pregunta.endswith("?"):
            escenas.append({"narracion": pregunta})
        palabras = sum(len(e["narracion"].split()) for e in escenas)
        if 3 <= len(escenas) <= 6 and 35 <= palabras <= 85:
            break
        print(f"  intento {intento}: {len(escenas)} escenas y {palabras} palabras; se pide otra vez")
    else:
        raise RuntimeError("la IA no ha dado un guion válido en 3 intentos")
    escenas = [{"numero": i, "narracion": e["narracion"], "visual": "grabación propia"}
               for i, e in enumerate(escenas, start=1)]
    nombre = _nombre_libre(f"{date.today().isoformat()}_grabacion_{paso1_guiones.slug(video.stem)[:30]}_narrado")
    guion = {
        "fecha": date.today().isoformat(), "anio_evento": None, "evento": f"Short narrado de {video.name}",
        "idioma": "es", "titulo": (_limpio(g.get("titulo")) or f"Lo que encontré en {juego}")[:70],
        "gancho": _limpio(g.get("gancho"))[:40], "escenas": escenas, "palabras": paso1_guiones.contar_palabras(escenas),
        "nombre_corto": f"{juego} jugada",
        "musica": g.get("musica") if g.get("musica") in ("epico", "misterio", "neutro") else "epico",
        "hashtags": hashtags(juego), "pregunta": pregunta, "palabras_clave": [], "fuentes": [],
        "sin_respaldo": [], "verificado": False, "estilo": "fotos",
        "clips_propios": {"origen": "grabación propia"},
        "grabacion": {"origen": video.name, "modo": "narrado", "inicio": round(desde, 2), "fin": round(hasta, 2),
                      "nota": nota, "juego": juego},
    }
    ruta = _guardar(nombre, guion)
    print(f"  guion: «{guion['titulo']}»", flush=True)
    for e in escenas:
        print(f"    {e['numero']}. {e['narracion']}", flush=True)
    montar_narrado(ruta)
    return ruta


def rehacer(ruta_guion: Path) -> None:
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    if (guion.get("grabacion") or {}).get("modo") == "narrado":
        montar_narrado(ruta_guion)
    else:
        print(f"  → {montar_clip(ruta_guion)}")


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Shorts a partir de tus grabaciones de partidas")
    sub = parser.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("clips")
    p.add_argument("archivo")
    p.add_argument("--cantidad", type=int, default=3)
    p.add_argument("--duracion", type=float, default=25)
    p.add_argument("--sonido", choices=("juego", "musica"), default="juego")
    p.add_argument("--juego", default="GTA 6")
    p = sub.add_parser("narrado")
    p.add_argument("archivo")
    p.add_argument("--nota", required=True)
    p.add_argument("--desde", default="")
    p.add_argument("--hasta", default="")
    p.add_argument("--juego", default="GTA 6")
    p = sub.add_parser("rehacer")
    p.add_argument("guion", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.orden == "clips":
            rutas = crear_clips(args.archivo, max(1, min(args.cantidad, 5)), max(10.0, min(args.duracion, 60.0)),
                                args.sonido, args.juego.strip() or "GTA 6")
            print(f"Clips hechos: {len(rutas)}")
            return 0 if rutas else 1
        if args.orden == "narrado":
            ruta = crear_narrado(args.archivo, args.nota.strip(), segundos(args.desde), segundos(args.hasta),
                                 args.juego.strip() or "GTA 6")
            print(f"Short narrado hecho: {ruta.stem}")
            return 0
        rehacer(args.guion)
        return 0
    except Exception as error:  # noqa: BLE001
        print(f"[error] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
