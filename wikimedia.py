"""Acceso a Wikipedia, Wikimedia Commons y los museos sin que te pongan en espera.

Todas las peticiones del programa (salvo las de Groq) pasan por aquí:
  - Caché en disco (salida/cache_wikipedia): lo ya consultado no se vuelve a pedir en 7 días.
  - Ritmo controlado: una pausa mínima entre peticiones al mismo servidor, compartida por
    todos los pasos y el menú (aunque se ejecuten a la vez).
  - Respeto a los avisos: ante un 429/503 se espera lo que pida el servidor; si pide demasiado,
    se apunta la hora hasta la que hay que esperar y no se insiste (el menú lo muestra).
  - Identificación con contacto (WIKIMEDIA_CONTACTO en .env), como exige Wikimedia.
"""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

CARPETA = Path("salida/cache_wikipedia")
CADUCIDAD = 7 * 24 * 3600   # s que vale una respuesta guardada
ESPERA_MAXIMA = 60          # s; si el servidor pide esperar más, se para y se avisa
INTENTOS = 5
# Pausa mínima entre peticiones a cada servidor (una por segundo, como pide Wikimedia a los programas).
# El Met permite muchas más (80/s): con él vamos algo más rápido, pero con margen.
INTERVALO = {"collectionapi.metmuseum.org": 0.25, "images.metmuseum.org": 0.5}
INTERVALO_POR_DEFECTO = 1.0
_turno = threading.Lock()  # el menú atiende varias peticiones a la vez: que hagan cola

CONTACTO = os.getenv("WIKIMEDIA_CONTACTO") or "sin contacto"
CABECERAS = {
    "User-Agent": f"pipeline-curiosidades/0.2 ({CONTACTO}) python-requests/{requests.__version__}",
    "AIC-User-Agent": f"pipeline-curiosidades ({CONTACTO})",  # el Art Institute pide identificarse así
    "Accept-Encoding": "gzip",
}
_sesion = requests.Session()  # reutiliza la conexión: menos carga para el servidor
_sesion.headers.update(CABECERAS)


class WikimediaEnEspera(requests.RequestException):
    """Wikimedia ha pedido esperar. `hasta` es la hora (timestamp) a partir de la que reintentar."""

    def __init__(self, hasta: float, servidores: str = "wikimedia"):
        self.hasta = hasta
        quien = "Wikipedia/Wikimedia" if servidores == "wikimedia" else servidores
        super().__init__(f"{quien} nos ha pedido esperar hasta las {time.strftime('%H:%M', time.localtime(hasta))}. "
                         "Vuelve a intentarlo a esa hora (lo ya descargado está guardado).")


# --- Espera compartida entre procesos ----------------------------------------------

def grupo(host: str) -> str:
    """Servidores que comparten límite: todo Wikimedia junto; cada museo por su cuenta."""
    if host.endswith(("wikipedia.org", "wikimedia.org", "wikidata.org")):
        return "wikimedia"
    return host


def _archivo_bloqueo(nombre_grupo: str) -> Path:
    return CARPETA / ("_espera.json" if nombre_grupo == "wikimedia" else f"_espera_{nombre_grupo}.json")


def en_espera_hasta(nombre_grupo: str = "wikimedia") -> float:
    """Hora (timestamp) hasta la que hay que esperar con ese grupo de servidores, o 0 si se puede consultar."""
    try:
        hasta = json.loads(_archivo_bloqueo(nombre_grupo).read_text(encoding="utf-8"))["hasta"]
    except (OSError, ValueError, KeyError):
        return 0.0
    return hasta if hasta > time.time() else 0.0


def _apuntar_espera(nombre_grupo: str, segundos: float) -> float:
    hasta = max(time.time() + segundos, en_espera_hasta(nombre_grupo))
    CARPETA.mkdir(parents=True, exist_ok=True)
    _archivo_bloqueo(nombre_grupo).write_text(json.dumps({"hasta": hasta}), encoding="utf-8")
    return hasta


def _esperar_turno(host: str) -> None:
    """Respeta la pausa mínima desde la última petición a este servidor (de cualquier proceso)."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    marca = CARPETA / f"_ultima_{host}.txt"
    intervalo = INTERVALO.get(host, INTERVALO_POR_DEFECTO)
    with _turno:
        try:
            ultima = float(marca.read_text())
        except (OSError, ValueError):
            ultima = 0.0
        pausa = ultima + intervalo - time.time()
        if pausa > 0:
            if pausa > 5:
                print(f"    esperando {pausa:.0f} s (límite de {host})…", flush=True)
            time.sleep(min(pausa, intervalo))
        marca.write_text(str(time.time()))


def _segundos_de_espera(respuesta, intento: int) -> float:
    try:
        return float(respuesta.headers.get("retry-after", ""))
    except ValueError:
        pass
    pista = re.search(r"[Rr]etry after (\d+)\s*s", respuesta.text[:500])  # p. ej. Pollinations lo dice en el texto
    return float(pista.group(1)) + 2 if pista else 5.0 * 2 ** intento  # 5, 10, 20, 40… s


# --- Caché -----------------------------------------------------------------------

def _ruta_cache(url: str, parametros: dict, extension: str) -> Path:
    clave = hashlib.sha1(json.dumps([url, sorted((parametros or {}).items())], default=str).encode()).hexdigest()
    return CARPETA / clave[:2] / f"{clave}{extension}"


def _fresca(ruta: Path, caducidad: float) -> bool:
    return ruta.exists() and time.time() - ruta.stat().st_mtime < caducidad


# --- Peticiones --------------------------------------------------------------------

def _pedir(url: str, parametros: dict) -> requests.Response:
    host = urlparse(url).hostname or ""
    servidores = grupo(host)
    hasta = en_espera_hasta(servidores)
    if hasta:
        raise WikimediaEnEspera(hasta, servidores)
    parametros = dict(parametros or {})
    if url.endswith("/w/api.php"):
        parametros.setdefault("maxlag", 5)  # cortesía: si los servidores van cargados, nos piden esperar
    for intento in range(INTENTOS):
        _esperar_turno(host)
        respuesta = _sesion.get(url, params=parametros, timeout=60)
        saturado = respuesta.status_code in (429, 503) or (
            respuesta.status_code == 402 and "FREE_LIMIT" in respuesta.text  # límite gratuito de Pollinations
        )
        if not saturado and "json" in respuesta.headers.get("content-type", ""):
            try:
                saturado = (respuesta.json().get("error") or {}).get("code") == "maxlag"
            except (ValueError, AttributeError):
                pass
        if not saturado:
            respuesta.raise_for_status()
            return respuesta
        espera = _segundos_de_espera(respuesta, intento)
        if espera > ESPERA_MAXIMA:
            raise WikimediaEnEspera(_apuntar_espera(servidores, espera), servidores)
        print(f"    {host} pide esperar {espera:.0f} s…", flush=True)
        time.sleep(espera)
    # sigue saturado: mejor parar un par de minutos
    raise WikimediaEnEspera(_apuntar_espera(servidores, 120), servidores)


def json_api(url: str, parametros: dict = None, caducidad: float = CADUCIDAD) -> dict:
    """GET que devuelve JSON, con caché en disco."""
    ruta = _ruta_cache(url, parametros, ".json")
    if _fresca(ruta, caducidad):
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except ValueError:
            pass
    datos = _pedir(url, parametros).json()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return datos


def archivo(url: str, destino: Path) -> Path:
    """Descarga un archivo (p. ej. una imagen) a `destino`, salvo que ya exista."""
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    contenido = _pedir(url, {}).content
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return destino


def fragmento_video(url: str, destino: Path, inicio: float, duracion: float) -> Path:
    """Trozo de `duracion` segundos de un vídeo desde `inicio` (sin sonido, en .mp4), salvo que ya exista.

    El vídeo (su versión ligera) se descarga entero en una sola petición, con el mismo ritmo que el resto, y se
    recorta aquí: pedirle a ffmpeg que salte por el archivo en el servidor hace decenas de peticiones y Wikimedia
    lo bloquea por exceso. Después se borra y solo se guarda el trozo.
    """
    if destino.exists() and destino.stat().st_size > 1000:
        return destino
    import subprocess
    import imageio_ffmpeg
    completo = archivo(url, destino.with_name(destino.stem + ".completo" + Path(urlparse(url).path).suffix))
    temporal = destino.with_suffix(".parcial.mp4")
    try:
        resultado = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{inicio:.2f}", "-i", str(completo), "-t", f"{duracion:.2f}",
             "-an", "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", str(temporal)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if resultado.returncode != 0 or not temporal.exists() or temporal.stat().st_size <= 1000:
            raise requests.RequestException(f"no se pudo recortar el vídeo: {resultado.stderr.strip()[-200:]}")
        temporal.replace(destino)
    finally:
        temporal.unlink(missing_ok=True)
        completo.unlink(missing_ok=True)
    return destino
