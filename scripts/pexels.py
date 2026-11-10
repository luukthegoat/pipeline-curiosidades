"""Planos de ambiente de Pexels y Pixabay (mar, humo, mapas antiguos, ruinas…) para las escenas sin vídeo de archivo.

Pexels y Pixabay son bancos de vídeo gratuitos (uso libre, sin atribución obligatoria, aunque se agradece).
Es metraje actual, así que solo se buscan cosas que no delatan la época: naturaleza, fuego, cielo, papel antiguo,
piedra… Nunca personas, ciudades ni vehículos, que en un vídeo de historia quedarían fuera de lugar.

Hace falta una clave gratuita de al menos uno: pexels.com/api (PEXELS_API_KEY) o pixabay.com/api/docs
(PIXABAY_API_KEY). Con las dos, se buscan en ambos y hay más donde elegir.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

URL_API = "https://api.pexels.com/videos/search"
CARPETA_CACHE = Path("salida/cache_pexels")
CADUCIDAD = 30 * 24 * 3600  # las búsquedas se repiten poco: un mes en caché
POR_BUSQUEDA = 4            # vídeos que se piden por cada búsqueda
MAX_BUSQUEDAS = 4           # búsquedas por guion (la API gratuita da 200 por hora)
DURACION = (5, 60)          # s: ni planos de un segundo ni grabaciones largas

# Palabra que aparece en el «visual» de la escena (en inglés) → búsqueda en Pexels. Solo cosas sin época.
AMBIENTES = {
    "sea": "ocean waves", "ocean": "ocean waves", "waves": "ocean waves", "coast": "rocky coast waves",
    "storm": "storm clouds", "rain": "rain drops", "lightning": "lightning storm", "thunder": "lightning storm",
    "clouds": "dark clouds timelapse", "sky": "dramatic sky clouds", "sunset": "sunset sky", "sunrise": "sunrise sky",
    "night": "night sky stars", "stars": "night sky stars", "moon": "full moon night",
    "fire": "fire flames", "flames": "fire flames", "burning": "fire flames", "smoke": "smoke dark",
    "fog": "fog forest", "mist": "fog forest", "snow": "snow falling", "winter": "snow falling", "ice": "ice frozen",
    "desert": "desert sand dunes", "sand": "desert sand dunes", "mountains": "mountains aerial",
    "mountain": "mountains aerial", "forest": "forest trees", "river": "river flowing", "lake": "lake calm water",
    "volcano": "volcano lava", "lava": "volcano lava", "earthquake": "cracked ground", "candle": "candle flame dark",
    "candlelight": "candle flame dark", "map": "old map", "maps": "old map", "parchment": "old paper parchment",
    "manuscript": "old book pages", "book": "old book pages", "letter": "old letter paper", "ink": "ink quill writing",
    "quill": "ink quill writing", "coins": "gold coins", "gold": "gold coins", "treasure": "gold coins",
    "sword": "sword steel", "ruins": "ancient ruins", "castle": "medieval castle", "fortress": "medieval castle",
    "cathedral": "cathedral interior", "church": "church interior candles", "temple": "ancient temple",
    "hourglass": "hourglass sand", "clock": "old clock ticking", "chains": "chains metal", "prison": "prison bars",
    "battlefield": "smoke battlefield", "ashes": "embers ashes", "embers": "embers ashes", "grave": "cemetery fog",
    "cemetery": "cemetery fog",
}


URL_PIXABAY = "https://pixabay.com/api/videos/"


class SinClave(Exception):
    """No hay clave ni de Pexels ni de Pixabay."""


def clave_pexels() -> str:
    return os.getenv("PEXELS_API_KEY", "").strip()


def clave_pixabay() -> str:
    return os.getenv("PIXABAY_API_KEY", "").strip()


def clave() -> str:
    """Alguna clave (de Pexels o de Pixabay): sin ninguna no hay planos de ambiente."""
    return clave_pexels() or clave_pixabay()


def _en_cache(nombre: str, pedir) -> dict:
    """La respuesta guardada de una búsqueda (un mes) o una nueva."""
    CARPETA_CACHE.mkdir(parents=True, exist_ok=True)
    cache = CARPETA_CACHE / f"{hashlib.sha1(nombre.encode()).hexdigest()[:16]}.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < CADUCIDAD:
        return json.loads(cache.read_text(encoding="utf-8"))
    respuesta = pedir()
    respuesta.raise_for_status()
    datos = respuesta.json()
    cache.write_text(json.dumps(datos), encoding="utf-8")
    return datos


def busquedas_para(visuales: list) -> list:
    """Las búsquedas de ambiente que piden las escenas, en orden de aparición y sin repetir."""
    vistas = []
    for visual in visuales:
        for palabra in re.findall(r"[a-z]+", (visual or "").lower()):
            busqueda = AMBIENTES.get(palabra)
            if busqueda and busqueda not in vistas:
                vistas.append(busqueda)
    return vistas[:MAX_BUSQUEDAS]


def _version_ligera(archivos: list) -> dict:
    """El archivo .mp4 más cercano a 720 p de alto (la franja central del vídeo vertical no pide más)."""
    validos = [a for a in archivos if a.get("file_type") == "video/mp4" and a.get("height") and a.get("link")]
    return min(validos, key=lambda a: (abs(min(a["height"], a["width"] or a["height"]) - 720), a["height"]),
               default={})


def buscar(busqueda: str) -> list:
    """Vídeos de Pexels y Pixabay para una búsqueda, con el mismo formato que los de Wikimedia (ver paso3_video)."""
    if not clave():
        raise SinClave("falta PEXELS_API_KEY o PIXABAY_API_KEY")
    videos = []
    for nombre, buscar_en, hay_clave in (("Pexels", buscar_pexels, clave_pexels()),
                                         ("Pixabay", buscar_pixabay, clave_pixabay())):
        if not hay_clave:
            continue
        try:
            videos += buscar_en(busqueda)
        except (requests.RequestException, ValueError) as error:
            if len([c for c in (clave_pexels(), clave_pixabay()) if c]) == 1:
                raise  # era la única fuente: que se vea el fallo
            print(f"  aviso: no se pudo buscar en {nombre} ({type(error).__name__}); sigo con la otra")
    return videos


def _version_pixabay(tamanos: dict) -> dict:
    """El tamaño más cercano a 720 p (la franja central del vídeo vertical no pide más)."""
    validos = [t for t in tamanos.values() if isinstance(t, dict) and t.get("url") and t.get("height")]
    return min(validos, key=lambda t: (abs(min(t["height"], t.get("width") or t["height"]) - 720), t["height"]),
               default={})


def buscar_pixabay(busqueda: str) -> list:
    """Vídeos de Pixabay (licencia de contenido de Pixabay: uso libre, sin atribución obligatoria)."""
    datos = _en_cache(f"pixabay|{busqueda}", lambda: requests.get(
        URL_PIXABAY, timeout=30, params={"key": clave_pixabay(), "q": busqueda, "per_page": max(3, POR_BUSQUEDA * 2),
                                         "safesearch": "true", "video_type": "film"}))
    videos = []
    for video in datos.get("hits", []):
        archivo = _version_pixabay(video.get("videos") or {})
        if not archivo or not DURACION[0] <= (video.get("duration") or 0) <= DURACION[1]:
            continue
        descripcion = (video.get("tags") or busqueda).replace(",", "")
        videos.append({
            "archivo": f"Pixabay {video['id']} - {descripcion[:60]}",
            "url": archivo["url"],
            "miniatura": archivo.get("thumbnail", ""),
            "video": True,
            "ambiente": True,
            "busqueda": busqueda,
            "duracion": float(video.get("duration") or 0),
            "anio": None,
            "articulo": "Pixabay (ambiente)",
            "pagina": video.get("pageURL", ""),
            "autor": video.get("user") or "Pixabay",
            "licencia": "Pixabay Content License",
            "descripcion": descripcion[:200],
            "claves": sorted(set(busqueda.split()) | set(descripcion.lower().split())),
        })
        if len(videos) >= POR_BUSQUEDA:
            break
    return videos


def buscar_pexels(busqueda: str) -> list:
    """Vídeos de Pexels (licencia Pexels: uso libre, sin atribución obligatoria)."""
    datos = _en_cache(busqueda, lambda: requests.get(
        URL_API, headers={"Authorization": clave_pexels()}, timeout=30,
        params={"query": busqueda, "per_page": POR_BUSQUEDA * 2, "size": "medium"}))
    videos = []
    for video in datos.get("videos", []):
        archivo = _version_ligera(video.get("video_files", []))
        if not archivo or not DURACION[0] <= (video.get("duration") or 0) <= DURACION[1]:
            continue
        pagina = video.get("url", "")
        # La URL lleva la descripción: «…/video/waves-crashing-on-rocks-1234567/»
        descripcion = " ".join(re.findall(r"[a-z]+", pagina.rstrip("/").rsplit("/", 1)[-1])) or busqueda
        videos.append({
            "archivo": f"Pexels {video['id']} - {descripcion[:60]}",
            "url": archivo["link"],
            "miniatura": video.get("image", ""),
            "video": True,
            "ambiente": True,
            "busqueda": busqueda,
            "duracion": float(video.get("duration") or 0),
            "anio": None,
            "articulo": "Pexels (ambiente)",
            "pagina": pagina,
            "autor": (video.get("user") or {}).get("name") or "Pexels",
            "licencia": "Pexels License",
            "descripcion": descripcion[:200],
            "claves": sorted(set(busqueda.split()) | set(descripcion.split())),
        })
        if len(videos) >= POR_BUSQUEDA:
            break
    return videos
