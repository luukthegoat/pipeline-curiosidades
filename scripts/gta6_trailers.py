"""Planos de los tráileres oficiales de GTA 6 para los Shorts (scripts/gta6.py).

Rockstar ofrece los tráileres para descargar en https://www.rockstargames.com/VI/media/videos; se guardan en
salida/gta6/trailers. Este script los corta en planos (cada cambio de cámara), saca un fotograma de cada uno y una IA
con visión lo describe y descarta lo que no sirve (rótulos, logos, negro, desnudez). El resultado, en
salida/gta6/planos.json, lo usa gta6.py para elegir el plano que acompaña cada frase.

Los planos se usan SIN el audio del tráiler: sus canciones son de otros artistas y harían saltar Content ID.

Uso:
    python scripts/gta6_trailers.py            # prepara los tráileres nuevos (los ya hechos no se repiten)
"""
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

CARPETA = Path("salida/gta6")
TRAILERS = CARPETA / "trailers"
PLANOS = CARPETA / "planos.json"
FOTOGRAMAS = CARPETA / "fotogramas"
MODELO_VISION = os.getenv("MODELO_VISION") or "qwen/qwen3.8-27b"
UMBRAL_CORTE = 0.30      # cuánto tiene que cambiar la imagen para contar como otro plano
PLANO_MIN_S = 1.0        # los planos más cortos son destellos: no se usan
MARGEN_FINAL_S = 12      # el final de cada tráiler son rótulos y logos

PROMPT = """Es un fotograma del tráiler oficial del videojuego GTA 6. Responde SOLO con JSON:
{"descripcion": "qué se ve, en una frase en español (personas, vehículos, lugar, acción)",
 "util": true o false (false si es sobre todo texto, un logo, un rótulo, pantalla negra o está borroso),
 "accion": true si hay movimiento o acción llamativa (persecución, salto, explosión, fiesta, velocidad),
 "violento": true si se ve sangre, un disparo o alguien herido,
 "sexual": true si hay desnudez o contenido sexual}"""


def ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def duracion(video: Path) -> float:
    return float(imageio_ffmpeg.count_frames_and_secs(str(video))[1])


def cortes(video: Path) -> list:
    """Los segundos en los que cambia el plano."""
    salida = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(video), "-an", "-vf",
                             f"scale=320:-2,select='gt(scene,{UMBRAL_CORTE})',showinfo", "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", salida)]


def fotograma(video: Path, segundo: float, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{segundo:.2f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=640:-2", str(destino)], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def describir(imagen: Path, prompt: str = None) -> dict:
    img = Image.open(imagen)
    img.thumbnail((384, 384))  # Groq da 8.000 tokens por minuto: a este tamaño caben unas 12 imágenes por minuto
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    contenido = [{"type": "text", "text": (prompt or PROMPT) + " /no_think"},
                 {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}]
    for intento in range(6):
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY', '')}"},
                          json={"model": MODELO_VISION, "max_tokens": 300, "temperature": 0.2,
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "user", "content": contenido}]}, timeout=90)
        if r.status_code == 429:
            espera = float(r.headers.get("retry-after", 10) or 10)
            if espera > 90:  # el límite del día (200.000 tokens): se sigue en la próxima pasada
                raise SinCupo(espera)
            time.sleep(espera + 1)  # el límite por minuto: se espera un poco
            continue
        if r.status_code >= 500:  # Groq saturado un momento
            time.sleep(5 * (intento + 1))
            continue
        r.raise_for_status()
        texto = r.json()["choices"][0]["message"]["content"]
        texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()
        try:
            return json.loads(re.sub(r"^```(?:json)?|```$", "", texto).strip())
        except ValueError:
            continue
    raise SinCupo(60)  # no ha salido: se reintentará en la próxima pasada


class SinCupo(Exception):
    """Groq no deja describir más imágenes por ahora."""


def planos_de(video: Path, hechos: list) -> list:
    """Los planos del tráiler. Se guardan uno a uno en `hechos` (y en planos.json): si se corta, sigue donde iba."""
    ya = {p["id"] for p in hechos}
    total = duracion(video)
    limites = [0.0, *[t for t in cortes(video) if t < total - MARGEN_FINAL_S], total - MARGEN_FINAL_S]
    clave = re.sub(r"^GTAVI_", "", video.stem)
    planos = []
    for n, (inicio, fin) in enumerate(zip(limites, limites[1:]), start=1):
        if fin - inicio < PLANO_MIN_S or inicio < 2:  # los primeros segundos suelen ser el logo de Rockstar
            continue
        ident = f"{clave}_{n:03d}"
        if ident in ya:
            continue
        imagen = FOTOGRAMAS / f"{ident}.jpg"
        fotograma(video, (inicio + fin) / 2, imagen)
        info = describir(imagen)
        if re.search(r"\blogo|\btexto\b|r[oó]tulo|t[ií]tulo|letras|pantalla negra|fundido", str(info.get("descripcion", "")),
                     re.I):
            info["util"] = False  # a veces la IA da por bueno un plano que es casi todo logo o texto
        planos.append({"id": ident, "video": str(video), "inicio": round(inicio, 2), "fin": round(fin, 2),
                       "descripcion": " ".join(str(info.get("descripcion", "")).split())[:200],
                       "util": bool(info.get("util")) and not info.get("sexual"),
                       "accion": bool(info.get("accion")), "violento": bool(info.get("violento")),
                       "sexual": bool(info.get("sexual"))})
        print(f"  {ident} {fin - inicio:4.1f} s {'✔' if planos[-1]['util'] else '✗'} {planos[-1]['descripcion'][:90]}",
              flush=True)
        hechos.append(planos[-1])
        PLANOS.write_text(json.dumps(hechos, ensure_ascii=False, indent=2), encoding="utf-8")
    hechos.append({"id": f"{clave}_completo", "video": str(video), "util": False, "completo": True,
                   "inicio": 0, "fin": 0, "descripcion": ""})  # marca: este tráiler ya está entero
    PLANOS.write_text(json.dumps(hechos, ensure_ascii=False, indent=2), encoding="utf-8")
    return planos


def cargar() -> list:
    try:
        return json.loads(PLANOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")
    hechos = cargar()
    completos = {p["video"] for p in hechos if p.get("completo")}
    for video in sorted(TRAILERS.glob("*.mp4")):
        if str(video) in completos:
            continue
        print(f"· {video.name}", flush=True)
        try:
            planos_de(video, hechos)
        except SinCupo as cupo:
            print(f"Groq no deja describir más imágenes ahora (unos {cupo.args[0] / 60:.0f} min): sigo en la próxima "
                  "pasada desde donde lo dejo.")
            break
    utiles = [p for p in hechos if p["util"]]
    print(f"Planos: {len(hechos)} · útiles: {len(utiles)} · con acción: {sum(p['accion'] for p in utiles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
