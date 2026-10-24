"""Formato «Vídeo con IA»: la app escribe el guion y un prompt de vídeo por escena; tú generas cada clip en una IA
de vídeo (Veo, Sora, Runway, Kling…) y lo subes desde el menú; la app lo monta con subtítulos, música y cierre.

Dos formas de poner la voz:
  - "ia":  la propia IA genera el clip con voz (el prompt incluye lo que dice el personaje); se conserva su audio.
  - "app": los clips son mudos o solo con ambiente; narra la voz de la app (edge-tts), como en el resto de vídeos.
"""
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

CARPETA_CLIPS = Path("salida/clips_ia")
EXTENSIONES_CLIP = (".mp4", ".mov", ".webm", ".m4v")

# Las IAs del desplegable. «segundos»: duración típica de un clip; «voz»: si genera el vídeo con voz y diálogo.
HERRAMIENTAS = {
    "veo": {
        "nombre": "Google Veo 3", "url": "https://labs.google/fx/tools/flow", "voz": True, "segundos": 8,
        "consejo": "Se usa en Flow (labs.google) o en la app de Gemini. Genera el vídeo con sonido y diálogo a la vez: "
                   "el personaje dice la frase del prompt con la boca sincronizada. Clips de unos 8 s.",
    },
    "sora": {
        "nombre": "Sora (OpenAI)", "url": "https://sora.com", "voz": True, "segundos": 10,
        "consejo": "Sora 2 genera el vídeo con sonido y diálogo. Elige formato vertical y clips de unos 10 s.",
    },
    "runway": {
        "nombre": "Runway", "url": "https://app.runwayml.com", "voz": False, "segundos": 10,
        "consejo": "Genera el vídeo sin voz: la narración la pone la app. Elige formato vertical (9:16) y 10 s.",
    },
    "kling": {
        "nombre": "Kling AI", "url": "https://klingai.com", "voz": False, "segundos": 10,
        "consejo": "Genera el vídeo sin voz (como mucho, efectos de sonido): la narración la pone la app. "
                   "Elige formato 9:16 y clips de 10 s.",
    },
}

ESTILOS = {
    "cine": "cinematic, photorealistic, shallow depth of field, natural film lighting",
    "documental": "historical documentary style, realistic, handheld camera, natural light",
    "animacion": "3D animated film style, expressive characters, soft global illumination",
    "anime": "anime style, hand-drawn look, vibrant colors",
    "pintura": "oil painting style come to life, painterly textures, dramatic light",
}
NOMBRES_ESTILOS = {"cine": "Cine realista", "documental": "Documental histórico", "animacion": "Animación 3D",
                   "anime": "Anime", "pintura": "Cuadro que cobra vida"}


def herramienta(clave: str) -> dict:
    return HERRAMIENTAS.get(clave) or HERRAMIENTAS["veo"]


def prompt_completo(datos_ia: dict, escena: dict, idioma: str) -> str:
    """El prompt que se copia a la IA: formato, estilo y personaje fijos (para que salga igual en todos los clips),
    la acción de la escena y, si la IA pone la voz, la frase exacta que dice el personaje."""
    h = herramienta(datos_ia.get("herramienta", ""))
    segundos = datos_ia.get("segundos") or h["segundos"]
    partes = [
        f"Vertical 9:16 video, {segundos} seconds.",
        f"Style: {datos_ia.get('estilo_visual') or ESTILOS['cine']}.",
        f"Main character (keep exactly the same look in every shot): {datos_ia.get('personaje', '').rstrip('.')}.",
        f"Scene: {str(escena.get('accion') or escena.get('visual') or '').rstrip('.')}.",
    ]
    if datos_ia.get("voz") == "ia":
        lengua = "Spanish (Spain)" if idioma == "es" else "English"
        frase = escena["narracion"].replace('"', "'")
        partes.append(f'The character speaks in {lengua}, looking at the camera, saying: "{frase}" '
                      "Lip-synced speech, natural ambient sound, no background music.")
    else:
        partes.append("No dialogue, nobody speaks. Natural ambient sound only, no music.")
    partes.append("No subtitles, no captions, no on-screen text, no watermark.")
    return " ".join(partes)


# --- Clips subidos -------------------------------------------------------------------------

def carpeta_clips(nombre: str) -> Path:
    return CARPETA_CLIPS / nombre


def ruta_clip(nombre: str, numero: int):
    """El clip subido para una escena (o None)."""
    for ruta in sorted(carpeta_clips(nombre).glob(f"escena_{numero:02d}.*")):
        if ruta.suffix.lower() in EXTENSIONES_CLIP:
            return ruta
    return None


def clips(nombre: str, escenas: list) -> dict:
    return {e["numero"]: ruta_clip(nombre, e["numero"]) for e in escenas}


def faltan(nombre: str, escenas: list) -> list:
    return [n for n, r in clips(nombre, escenas).items() if r is None]


def duracion(ruta: Path) -> float:
    return float(imageio_ffmpeg.count_frames_and_secs(str(ruta))[1])


def tiene_audio(ruta: Path) -> bool:
    salida = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(ruta)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    return bool(re.search(r"Stream #\S+.*Audio:", salida))


def extraer_audio(clip: Path, destino: Path, segundos: float) -> None:
    """Audio del clip a .m4a (o silencio, si el clip no tiene sonido), para montarlo como la voz de la escena."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if tiene_audio(clip):
        orden = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip), "-vn",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", str(destino)]
    else:
        orden = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                 "anullsrc=r=44100:cl=stereo", "-t", f"{segundos:.3f}", "-c:a", "aac", str(destino)]
    subprocess.run(orden, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
