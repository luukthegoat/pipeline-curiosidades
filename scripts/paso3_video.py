"""Paso 3: monta el vídeo vertical (1080x1920) con imágenes, voz, subtítulos y música.

Lee salida/audio/<guion>/escenas.json (paso 2) y crea una carpeta por tema en salida/videos/:
  - Guerra-civil/Guerra-civil_pt3.mp4            : vídeo listo para Shorts / TikTok / Reels
  - Guerra-civil/Guerra-civil_pt3.txt            : qué poner al publicar en TikTok y en YouTube Shorts
  - Guerra-civil/Guerra-civil_pt3.jpg            : miniatura con el gancho en grande
  - Guerra-civil/guiones/Guerra-civil_pt3.txt    : el texto del guion
  («_pt3» solo en las series; los vídeos que no están en español llevan el idioma: «_EN»)

Imágenes: las de los artículos de Wikipedia del guion y una búsqueda en Wikimedia Commons
(con su autor y licencia). A cada escena se le asigna la que mejor encaja con su texto,
salvo que la hayas elegido a mano en el menú. Llevan un zoom lento (efecto Ken Burns).
Subtítulos: grandes, resaltando la palabra que suena. Al empezar, el gancho en grande.
Música: la del guion ("musica": epico, misterio, triste, neutro, una tuya o "ninguna"),
que baja de volumen sola cuando habla la voz.

Cada escena se guarda en caché (salida/_trabajo): al cambiar una imagen o una frase solo
se rehace esa escena. Las escenas se montan en paralelo.

Uso:
    python scripts/paso3_video.py                    # todos los guiones con audio
    python scripts/paso3_video.py salida/audio/X     # solo uno
    python scripts/paso3_video.py --solo-verificados
    python scripts/paso3_video.py --forzar           # rehace aunque ya exista el vídeo
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import imageio_ffmpeg
import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

import cierre
import musica
import pexels  # planos de ambiente (mar, humo, mapas…) para las escenas sin vídeo de archivo
import wikimedia  # acceso a Wikimedia con caché y ritmo controlado (evita que te pongan en espera)

load_dotenv()

CARPETA_AUDIO = Path("salida/audio")
CARPETA_VIDEOS = Path("salida/videos")
CARPETA_GUIONES = Path("salida/guiones")
CARPETA_TRABAJO = Path("salida/_trabajo")      # escenas en caché, candidatas e imágenes elegidas
CARPETA_CACHE = Path("salida/cache_imagenes")  # cada imagen se descarga una sola vez
CARPETA_PROPIAS = Path("salida/imagenes_propias")  # imágenes que subes desde el menú
ANCHO_DESCARGA = 1280  # tamaño estándar de Wikimedia: los no estándar tienen límites mucho más estrictos
PUNTUACION_MINIMA = 0.45  # por debajo, la imagen apenas tiene que ver con la escena: se repite una buena
MAX_COMMONS = 25       # imágenes extra buscadas en Wikimedia Commons
MAX_VIDEOS_COMMONS = 20         # vídeos buscados en Wikimedia Commons (en español y en inglés)
MAX_CLIPS_POR_VIDEO = 2         # clips de vídeo libres por vídeo: se reservan antes que las fotos (1-2 por vídeo)
PUNTUACION_MINIMA_VIDEO = 0.8   # un vídeo tiene que encajar mejor que una foto para usarse
VENTAJA_VIDEO = 0.6             # los clips libres van primero: ganan a una foto que encaje algo mejor
MAX_AMBIENTE_POR_VIDEO = 2      # planos de ambiente de Pexels como mucho (son genéricos: solo rellenan)
PUNTUACION_AMBIENTE = 0.8       # si la mejor foto nueva encaja menos que esto, mejor un plano de ambiente
DURACION_CLIP = 12.0            # s que se descargan de cada vídeo (las escenas duran menos)
DURACION_MAXIMA_VIDEO = 1200    # s; más largos suelen ser grabaciones enteras de un acto
TAMANO_MAXIMO_VIDEO = 60        # MB de la versión ligera: se descarga entera para recortarla
CARPETA_CLIPS = Path("salida/cache_clips")  # trozos de vídeo ya descargados
# Discursos, telediarios, entrevistas…: una persona hablando a cámara no sirve de imagen de una escena.
EXCLUIR_VIDEO = re.compile(
    r"address|remarks|speech|speaks|statement|interview|press conference|briefing|hearing|lecture|podcast|"
    r"news in|webinar|discurso|entrevista|rueda de prensa|declaraci|conferencia|audio|subtitles|trailer|"
    r"remember|testimon|oral history|tribute|ceremony|commentary|story|recuerd|homenaje|testimonio|"
    r"president|presidente|minister|ministro|senator|senador|secretary|secretario|governor|mayor|alcalde|"
    r"hall of fame|oral|keynote|panel|q&a|wrap up|vlog|"
    r"^\d+\.\s",  # «4. Apellido, Nombre (lugar, año)»: series de entrevistas
    re.I)

ANCHO, ALTO, FPS = 1080, 1920, 30
ALTO_IMAGEN = 0.54    # fracción de la altura que ocupa la imagen
CENTRO_IMAGEN = 0.48  # posición vertical de su centro (0 arriba, 1 abajo)
ZOOM_FINAL = 1.08               # zoom lento a lo largo de cada escena
COLA_TRAS_ULTIMA_PALABRA = 0.2  # s de audio que se dejan tras la última palabra (recorta el silencio final)
PAUSA_ENTRE_ESCENAS = 0.15      # s
DURACION_GANCHO = 2.2           # s que el gancho se ve en grande al empezar
DURACION_TITULO = 3.0           # s del título arriba (solo si el guion no tiene gancho)
VOLUMEN_MUSICA = 0.22           # volumen de la música bajo la voz (además baja sola cuando se habla)
HILOS = max(1, min(4, (os.cpu_count() or 2) // 2))  # escenas que se montan a la vez
VERSION_ESCENA = "3"            # cámbiala si cambia el aspecto de las escenas: invalida la caché

PALABRAS_POR_SUBTITULO = 3
CORTE_POR_SILENCIO = 0.35

URL_WIKI_API = "https://es.wikipedia.org/w/api.php"
URL_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MIMES_VALIDOS = ("image/jpeg", "image/png")
TAMANO_MINIMO = 500
EXCLUIR = re.compile(r"logo|icon|icono|signature|firma|coat of arms|escudo|flag|bandera|seal|sello|\.svg", re.I)

PALABRAS_VACIAS = set(
    "el la los las un una unos unas de del al y o en que por para con sin su sus se lo le les es fue era "
    "como mas pero este esta estos estas ese esa eso muy ya hoy dia the of and a an in on at to for with "
    "from by his her their was were is are it its this that as into who which "
    "archivo file jpg jpeg png".split()
)


# --- Imágenes candidatas -------------------------------------------------------------

def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", texto)


def palabras_clave(texto: str) -> set:
    return {p for p in normalizar(texto).split() if len(p) > 2 and p not in PALABRAS_VACIAS}


def limpiar_html(valor: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", valor or ""))).strip()


def titulo_desde_url(url: str) -> str:
    return unquote(urlparse(url).path.rsplit("/", 1)[-1]).replace("_", " ")


def _imagenes(url_api: str, parametros: dict, origen: str) -> list:
    """Consulta imágenes a una API de Wikimedia y devuelve las válidas con URL, autor y licencia."""
    parametros = {
        **parametros,
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": ANCHO_DESCARGA,
        "iiextmetadatafilter": "Artist|LicenseShortName|ImageDescription",
        "format": "json", "formatversion": 2,
    }
    imagenes = []
    for pagina in wikimedia.json_api(url_api, parametros).get("query", {}).get("pages", []):
        info = (pagina.get("imageinfo") or [{}])[0]
        nombre = pagina.get("title", "")
        if (
            info.get("mime") not in MIMES_VALIDOS
            or min(info.get("width", 0), info.get("height", 0)) < TAMANO_MINIMO
            or EXCLUIR.search(nombre)
        ):
            continue
        meta = info.get("extmetadata")
        meta = meta if isinstance(meta, dict) else {}  # Wikimedia devuelve [] cuando no hay metadatos
        descripcion = limpiar_html(meta.get("ImageDescription", {}).get("value", ""))
        # Años en el nombre o la descripción (la época que muestra; la fecha de la foto no sirve:
        # una foto de 2012 de un objeto de 1810 es válida).
        anios = [int(a) for a in re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", f"{nombre} {descripcion[:300]}")]
        # Las imágenes cuyo ancho ya es estándar se sirven tal cual (si es menor que 1280, sin miniatura).
        url = info.get("thumburl") if info.get("width", 0) > ANCHO_DESCARGA else info.get("url")
        imagenes.append(
            {
                "archivo": nombre.split(":", 1)[-1],
                "url": url or info.get("url"),
                "anio": min(anios) if anios else None,
                "articulo": origen,
                "pagina": info.get("descriptionurl", ""),
                "autor": limpiar_html(meta.get("Artist", {}).get("value", "")) or "Autor desconocido",
                "licencia": meta.get("LicenseShortName", {}).get("value", "") or "ver página del archivo",
                "descripcion": descripcion[:200],
                "claves": sorted(palabras_clave(f"{nombre} {descripcion[:300]}")),
            }
        )
    return imagenes


def imagenes_de_articulo(titulo: str) -> list:
    parametros = {"action": "query", "generator": "images", "titles": titulo, "gimlimit": 50, "redirects": 1}
    return _imagenes(URL_WIKI_API, parametros, titulo)


def imagenes_de_commons(busqueda: str) -> list:
    """Búsqueda de imágenes en Wikimedia Commons (amplía las opciones más allá del artículo)."""
    parametros = {
        "action": "query", "generator": "search", "gsrsearch": f"{busqueda} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": MAX_COMMONS,
    }
    return _imagenes(URL_COMMONS_API, parametros, "Wikimedia Commons")


def _videos(url_api: str, parametros: dict, origen: str) -> list:
    """Vídeos (con su versión ligera para descargar) de una consulta a una API de Wikimedia."""
    parametros = {
        **parametros,
        "prop": "videoinfo", "viprop": "url|size|mime|extmetadata|derivatives", "viurlwidth": 640,
        "viextmetadatafilter": "Artist|LicenseShortName|ImageDescription",
        "format": "json", "formatversion": 2,
    }
    videos = []
    for pagina in wikimedia.json_api(url_api, parametros).get("query", {}).get("pages", []):
        info = (pagina.get("videoinfo") or [{}])[0]
        nombre = pagina.get("title", "")
        duracion = info.get("duration") or 0
        # La versión ligera de 480p (o la más cercana) basta para la franja central del vídeo vertical.
        # Solo versiones convertidas por Commons (no el archivo original, que puede pesar gigas) y en .webm.
        versiones = sorted((d for d in info.get("derivatives", []) if d.get("transcodekey", "").endswith(".webm")
                            and d.get("height") and d.get("bandwidth")
                            and d["bandwidth"] * duracion / 8e6 <= TAMANO_MAXIMO_VIDEO),
                           key=lambda d: (abs(d["height"] - 480), -d["height"]))
        if (not info.get("width") or not versiones or not 3 <= duracion <= DURACION_MAXIMA_VIDEO
                or EXCLUIR_VIDEO.search(nombre)):
            continue  # sin imagen (solo audio), sin versión ligera, demasiado corto o largo, o alguien hablando
        meta = info.get("extmetadata")
        meta = meta if isinstance(meta, dict) else {}
        descripcion = limpiar_html(meta.get("ImageDescription", {}).get("value", ""))
        if EXCLUIR_VIDEO.search(descripcion[:200]):
            continue
        anios = [int(a) for a in re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", f"{nombre} {descripcion[:300]}")]
        videos.append({
            "archivo": nombre.split(":", 1)[-1],
            "url": versiones[0]["src"],
            "miniatura": info.get("thumburl", ""),
            "video": True,
            "duracion": round(duracion, 1),
            "anio": min(anios) if anios else None,
            "articulo": origen,
            "pagina": info.get("descriptionurl", ""),
            "autor": limpiar_html(meta.get("Artist", {}).get("value", "")) or "Autor desconocido",
            "licencia": meta.get("LicenseShortName", {}).get("value", "") or "ver página del archivo",
            "descripcion": descripcion[:200],
            "claves": sorted(palabras_clave(f"{nombre} {descripcion[:300]}")),
        })
    return videos


def videos_de_articulo(titulo: str, url_api: str = URL_WIKI_API) -> list:
    """Vídeos que los editores de Wikipedia han puesto en el artículo: pocos, pero del tema seguro."""
    parametros = {"action": "query", "generator": "images", "titles": titulo, "gimlimit": 200, "redirects": 1}
    return [{**v, "del_articulo": True} for v in _videos(url_api, parametros, f"{titulo} (vídeo)")]


def videos_de_commons(busqueda: str) -> list:
    """Búsqueda de vídeos en Wikimedia Commons (noticiarios, archivos públicos…): más, pero menos seguros."""
    parametros = {"action": "query", "generator": "search", "gsrsearch": f"{busqueda} filetype:video",
                  "gsrnamespace": 6, "gsrlimit": MAX_VIDEOS_COMMONS}
    return _videos(URL_COMMONS_API, parametros, "Wikimedia Commons (vídeo)")


# --- Museos (imágenes de dominio público, buscan en inglés) ------------------------------

URL_MET = "https://collectionapi.metmuseum.org/public/collection"
URL_AIC = "https://api.artic.edu/api/v1/artworks/search"
MAX_MUSEO = 12  # obras que se consultan en cada museo
UN_MES = 30 * 24 * 3600


def tema_en_ingles(datos: dict) -> str:
    """Título en inglés del artículo fuente (los museos buscan mejor en inglés)."""
    fuente = (datos.get("fuentes") or [{}])[0]
    titulo = fuente.get("titulo") or titulo_desde_url(fuente.get("url", ""))
    if titulo:
        parametros = {"action": "query", "prop": "langlinks", "lllang": "en", "titles": titulo,
                      "redirects": 1, "format": "json", "formatversion": 2}
        paginas = wikimedia.json_api(URL_WIKI_API, parametros, caducidad=UN_MES).get("query", {}).get("pages", [])
        enlaces = paginas[0].get("langlinks", []) if paginas else []
        if enlaces:
            return enlaces[0]["title"]
    return nombre_corto(datos)


# «Fall of Constantinople» → «Constantinople»: los museos buscan por palabras sueltas y
# «Fall» trae «The Fall of Icarus», «Fall of Man»…
GENERICAS = re.compile(
    r"^(the )?(fall|siege|sack|sinking|battle|history|death|assassination|execution|conquest|founding|"
    r"invasion|discovery|independence|war|revolution|reign|life|trial|burning|destruction)"
    r"( of| for| in| on)?( the)? ",
    re.I,
)


def busqueda_museos(titulo_en: str) -> str:
    esencial = GENERICAS.sub("", titulo_en.strip())
    return re.sub(r"\s*\(.*?\)", "", esencial).strip() or titulo_en  # sin aclaraciones entre paréntesis


def _anio(valor):
    return valor if isinstance(valor, int) and -3000 < valor < 2100 and valor != 0 else None


def imagenes_del_met(busqueda: str) -> list:
    """Obras de dominio público del Metropolitan Museum of Art (Nueva York)."""
    ids = wikimedia.json_api(f"{URL_MET}/v1.1/search",
                             {"q": busqueda, "hasImages": "true", "limit": MAX_MUSEO}).get("objectIDs") or []
    imagenes = []
    for id_obra in ids[:MAX_MUSEO]:
        obra = wikimedia.json_api(f"{URL_MET}/v1/objects/{id_obra}", caducidad=UN_MES)
        url = obra.get("primaryImageSmall") or obra.get("primaryImage")
        if not obra.get("isPublicDomain") or not url:
            continue
        titulo = obra.get("title") or "Obra"
        texto = " ".join(str(obra.get(k) or "") for k in ("title", "artistDisplayName", "culture", "objectName", "period"))
        imagenes.append({
            "archivo": f"Met {id_obra} - {titulo[:80]}",
            "url": url,
            "anio": _anio(obra.get("objectBeginDate")),
            "articulo": "The Met",
            "pagina": obra.get("objectURL", ""),
            "autor": obra.get("artistDisplayName") or "The Metropolitan Museum of Art",
            "licencia": "Dominio público (CC0)",
            "descripcion": f"{titulo} ({obra.get('objectDate', '')})"[:200],
            "claves": sorted(palabras_clave(texto)),
        })
    return imagenes


def imagenes_del_art_institute(busqueda: str) -> list:
    """Obras de dominio público del Art Institute of Chicago."""
    campos = "id,title,artist_display,date_start,date_display,image_id,is_public_domain,place_of_origin,medium_display"
    datos = wikimedia.json_api(URL_AIC, {"q": busqueda, "limit": MAX_MUSEO, "fields": campos})
    iiif = (datos.get("config") or {}).get("iiif_url", "https://www.artic.edu/iiif/2")
    imagenes = []
    for obra in datos.get("data", []):
        if not obra.get("is_public_domain") or not obra.get("image_id"):
            continue
        titulo = obra.get("title") or "Obra"
        texto = " ".join(str(obra.get(k) or "") for k in ("title", "artist_display", "place_of_origin", "medium_display"))
        imagenes.append({
            "archivo": f"AIC {obra['id']} - {titulo[:80]}",
            "url": f"{iiif}/{obra['image_id']}/full/843,/0/default.jpg",  # 843 px: el tamaño que recomiendan
            "anio": _anio(obra.get("date_start")),
            "articulo": "Art Institute of Chicago",
            "pagina": f"https://www.artic.edu/artworks/{obra['id']}",
            "autor": (obra.get("artist_display") or "Art Institute of Chicago").split("\n")[0],
            "licencia": "Dominio público (CC0)",
            "descripcion": f"{titulo} ({obra.get('date_display', '')})"[:200],
            "claves": sorted(palabras_clave(texto)),
        })
    return imagenes


VERSION_CANDIDATAS = 11  # súbela si cambian las fuentes de imágenes: se vuelven a buscar


def candidatas(nombre: str, datos: dict, renovar: bool = False) -> list:
    """Imágenes posibles para un guion (artículos fuente, Commons y museos), guardadas en caché."""
    ruta = CARPETA_TRABAJO / nombre / "candidatas.json"
    if ruta.exists() and not renovar:
        guardadas = json.loads(ruta.read_text(encoding="utf-8"))
        if isinstance(guardadas, dict) and guardadas.get("version") == VERSION_CANDIDATAS:
            return guardadas["imagenes"]
    if datos.get("actualidad"):
        imagenes = imagenes_de_archivo(datos)
        imagenes = list({i["archivo"]: i for i in reversed(imagenes)}.values())[::-1]
        if imagenes:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps({"version": VERSION_CANDIDATAS, "imagenes": imagenes}, ensure_ascii=False,
                                       indent=2), encoding="utf-8")
        return imagenes
    imagenes = []
    articulos = [fuente.get("titulo") or titulo_desde_url(fuente["url"]) for fuente in datos.get("fuentes", [])]
    for fuente in datos.get("fuentes", []):
        try:
            imagenes += imagenes_de_articulo(fuente.get("titulo") or titulo_desde_url(fuente["url"]))
        except wikimedia.WikimediaEnEspera:
            raise  # sin la lista completa no se guarda nada: se reintenta cuando acabe la espera
        except requests.RequestException:
            print(f"  aviso: no se pudieron leer las imágenes de {fuente.get('titulo')}")
    busqueda = ((datos.get("diario") or {}).get("personaje") or (datos.get("serie") or {}).get("tema")
                or nombre_corto(datos))
    en_ingles = tema_en_ingles(datos)
    # Lo que salga de Commons tiene que nombrar el tema (los artículos fuente y su título en inglés): una búsqueda
    # por «11S» trae también la proteína «11S proteasome».
    tema = set().union(*(palabras_clave(t) for t in [*articulos, en_ingles, (datos.get("serie") or {}).get("tema", "")]))
    del_tema = lambda lista: [i for i in lista if datos.get("diario") or set(i["claves"]) & tema]  # noqa: E731
    try:
        encontradas = imagenes_de_commons(busqueda)
        imagenes += del_tema(encontradas)
        if len(del_tema(encontradas)) < len(encontradas):
            print(f"  Commons: {len(encontradas) - len(del_tema(encontradas))} imágenes descartadas por no ser del tema")
    except wikimedia.WikimediaEnEspera:
        raise
    except requests.RequestException:
        print("  aviso: no se pudo buscar en Wikimedia Commons")
    # Vídeo real de archivo (no en los diarios, que van con imágenes de IA): primero los de los artículos de
    # Wikipedia (en español y en inglés); después, una búsqueda en Commons, solo con los que nombren bien el tema
    # (dos palabras suyas: «Francisco Franco» no debe traer vídeos de «Marielle Franco»).
    if not datos.get("diario"):
        busquedas = [(videos_de_articulo, (t,), "artículo") for t in articulos[:2]]
        if en_ingles not in articulos:
            busquedas.append((videos_de_articulo, (en_ingles, URL_WIKI_API.replace("es.", "en.")), "artículo en inglés"))
        busquedas.append((videos_de_commons, (en_ingles,), "Commons"))
        for buscar, argumentos, donde in busquedas:
            try:
                encontrados = buscar(*argumentos)
            except wikimedia.WikimediaEnEspera:
                raise
            except requests.RequestException:
                print(f"  aviso: no se pudieron buscar vídeos en {donde}")
                continue
            if buscar is videos_de_commons:
                encontrados = [{**v, "del_tema": True} for v in encontrados
                               if len(set(v["claves"]) & tema) >= min(2, len(tema))]
            imagenes += encontrados
            print(f"  {donde}: {len(encontrados)} vídeos de «{argumentos[0]}»")
    # Planos de ambiente de Pexels (mar, humo, mapas…) para lo que pidan las escenas: solo rellenan huecos.
    # No en las noticias (un plano de fuego o humo junto a un suceso real confundiría) ni en los diarios.
    if not datos.get("diario") and pexels.clave():
        for busqueda in pexels.busquedas_para([e.get("visual", "") for e in datos.get("escenas", [])]):
            try:
                encontrados = pexels.buscar(busqueda)
            except (requests.RequestException, ValueError) as error:
                print(f"  aviso: no se pudo buscar en Pexels ({type(error).__name__})")
                break
            imagenes += encontrados
            print(f"  Pexels: {len(encontrados)} planos de ambiente para «{busqueda}»")
    # Museos: si fallan, se sigue sin ellos (no dependen de Wikimedia).
    en_ingles = busqueda_museos(en_ingles)
    for museo, buscar in (("The Met", imagenes_del_met), ("Art Institute of Chicago", imagenes_del_art_institute)):
        try:
            encontradas = buscar(en_ingles)
            imagenes += encontradas
            print(f"  {museo}: {len(encontradas)} obras de dominio público para «{en_ingles}»")
        except (requests.RequestException, ValueError, KeyError) as error:
            print(f"  aviso: no se pudo buscar en {museo} ({type(error).__name__})")
    imagenes = list({i["archivo"]: i for i in reversed(imagenes)}.values())[::-1]  # sin repetidas
    if imagenes:  # una lista vacía (fallo puntual) no se guarda, para volver a buscar la próxima vez
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"version": VERSION_CANDIDATAS, "imagenes": imagenes}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return imagenes


def imagenes_de_archivo(datos: dict) -> list:
    """Noticias: fotos de ARCHIVO de los lugares e instituciones (nunca fotos de prensa del suceso, que tienen
    derechos). Se buscan en Wikimedia Commons con las búsquedas que propuso el guion."""
    busquedas = (datos.get("actualidad") or {}).get("busquedas_imagenes") or [nombre_corto(datos)]
    imagenes = []
    # Clips con licencia libre de Commons: del propio suceso (por si alguien lo grabó y lo compartió con licencia
    # libre) y de los lugares de la noticia. Nunca vídeo de televisiones o agencias: tiene derechos.
    tema = (datos.get("actualidad") or {}).get("tema") or ""
    for busqueda in [b for b in dict.fromkeys([tema, *busquedas[:5]]) if b]:
        try:
            encontrados = [{**v, "del_tema": True} for v in videos_de_commons(busqueda)
                           if set(v["claves"]) & palabras_clave(busqueda)]
            print(f"  Commons: {len(encontrados)} vídeos libres para «{busqueda}»")
            imagenes += encontrados
        except wikimedia.WikimediaEnEspera:
            raise
        except requests.RequestException:
            print(f"  aviso: no se pudieron buscar vídeos de «{busqueda}» en Wikimedia Commons")
    for busqueda in busquedas[:5]:
        try:
            encontradas = imagenes_de_commons(busqueda)
            print(f"  Commons (archivo): {len(encontradas)} imágenes para «{busqueda}»")
            imagenes += encontradas
        except wikimedia.WikimediaEnEspera:
            raise
        except requests.RequestException:
            print(f"  aviso: no se pudo buscar «{busqueda}» en Wikimedia Commons")
    return imagenes


def miniatura_url(imagen: dict) -> str:
    """URL pequeña para mostrar la imagen en el menú (330 px en Wikimedia, 400 px en el Art Institute)."""
    if imagen.get("video"):
        return imagen.get("miniatura", "")
    url = imagen.get("url", "")
    if "/thumb/" in url:
        return re.sub(r"/\d+px-", "/330px-", url)
    if "/iiif/" in url:
        return url.replace("/full/843,/", "/full/400,/")
    return url


class SelectorImagenes:
    """Elige y descarga la imagen de cada escena para un guion."""

    def __init__(self, imagenes: list, evento: str, anio_evento):
        self.imagenes = imagenes
        self.claves = [set(i["claves"]) for i in imagenes]
        self.claves_evento = palabras_clave(evento)
        self.anio_evento = anio_evento if isinstance(anio_evento, int) else None
        self.articulos = list(dict.fromkeys(i["articulo"] for i in imagenes))
        # Palabras que salen en muchas imágenes (p. ej. "colombia") distinguen poco: pesan menos.
        frecuencia = {}
        for claves in self.claves:
            for clave in claves:
                frecuencia[clave] = frecuencia.get(clave, 0) + 1
        self.peso = {c: 1 / (1 + n) ** 0.5 for c, n in frecuencia.items()}
        self.usadas, self.fallidas, self.descargadas = set(), set(), {}
        self.bloqueados = set()  # grupos de servidores que nos han pedido esperar
        self.anterior = None  # para no repetir la misma imagen en dos escenas seguidas
        self.reservadas = set()  # clips apartados para una escena concreta (reservar_clips)
        self.epoca_maxima = None  # temas anteriores al 2000: sin clips de búsqueda grabados después (ver montar)

    def puntuacion(self, indice: int, claves: set) -> float:
        imagen = self.imagenes[indice]
        puntos = sum(self.peso.get(c, 0) for c in self.claves[indice] & claves)
        if self.anio_evento and imagen["anio"] and not (
            self.anio_evento - 150 <= imagen["anio"] <= self.anio_evento + 60
        ):
            puntos -= 1.5  # de una época muy distinta a la del evento
        puntos -= 0.1 * self.articulos.index(imagen["articulo"])  # desempate: artículo principal primero
        return puntos

    def _vale(self, indice: int, claves: set) -> bool:
        """¿Encaja lo bastante con la escena? A los vídeos se les pide más (y hay un máximo por vídeo).

        Los planos de ambiente no compiten aquí: solo entran en `para_escena` cuando no hay nada mejor."""
        if self.imagenes[indice].get("ambiente"):
            return False
        if self.imagenes[indice].get("video"):
            return False  # los clips solo entran reservados (reservar_clips_con_ia): escena a escena, nunca
        return self.puntuacion(indice, claves) >= PUNTUACION_MINIMA

    def ranking(self, escena: dict) -> list:
        """Índices de las imágenes de mejor a peor para la escena."""
        claves = palabras_clave(f"{escena['narracion']} {escena.get('visual', '')}") | self.claves_evento
        return sorted(range(len(self.imagenes)), reverse=True,
                      key=lambda i: self.puntuacion(i, claves) + (VENTAJA_VIDEO if self.imagenes[i].get("video") else 0))

    def marcar_usada(self, imagen: dict) -> None:
        """Una imagen elegida a mano no se vuelve a proponer para otra escena."""
        for i, candidata in enumerate(self.imagenes):
            if candidata["archivo"] == imagen.get("archivo"):
                self.usadas.add(i)

    def _grupo(self, indice: int) -> str:
        return wikimedia.grupo(urlparse(self.imagenes[indice].get("url", "")).hostname or "")

    def _bloqueada(self, indice: int) -> bool:
        """Su servidor nos ha pedido esperar y no la tenemos ya descargada."""
        return self._grupo(indice) in self.bloqueados and not ruta_en_cache(self.imagenes[indice]).exists()

    def _descargar(self, indice: int):
        try:
            self.descargadas[indice] = descargar(self.imagenes[indice])
            self.usadas.add(indice)
            self.anterior = indice
            return self.imagenes[indice], self.descargadas[indice]
        except WikimediaBloqueado as aviso:
            print(f"    {aviso} Mientras, uso imágenes de otras fuentes o ya descargadas.")
            self.bloqueados.add(self._grupo(indice))
        except requests.RequestException:
            print(f"    no se pudo descargar {self.imagenes[indice]['archivo'][:50]}; pruebo otra")
            self.fallidas.add(indice)
        return None

    def _fuera_de_epoca(self, indice: int) -> bool:
        imagen = self.imagenes[indice]
        return bool(self.epoca_maxima and not imagen.get("del_articulo") and imagen.get("anio")
                    and imagen["anio"] > self.epoca_maxima)

    def clips_posibles(self, escenas: list, maximo: int = 14) -> list:
        """Índices de los clips que podrían ir en alguna escena (los que mejor encajan primero)."""
        mejores = {}
        for escena in escenas:
            if escena.get("imagen"):
                continue
            claves = palabras_clave(f"{escena['narracion']} {escena.get('visual', '')}") | self.claves_evento
            for indice, imagen in enumerate(self.imagenes):
                if (imagen.get("video") and not imagen.get("ambiente") and indice not in self.usadas
                        and not self._fuera_de_epoca(indice)):
                    mejores[indice] = max(mejores.get(indice, -9), self.puntuacion(indice, claves))
        return sorted(mejores, key=mejores.get, reverse=True)[:maximo]

    def apartar(self, reservas: dict) -> dict:
        """Deja apartados los clips de `reservas` ({escena: índice}) para que ninguna otra escena los coja."""
        clips_ya = sum(1 for i in self.usadas if self.imagenes[i].get("video"))
        reservas = dict(list(reservas.items())[:max(0, MAX_CLIPS_POR_VIDEO - clips_ya)])
        self.reservadas = set(reservas.values())
        return reservas

    def reservar_clips(self, escenas: list) -> dict:
        """{número de escena: índice del clip}: hasta MAX_CLIPS_POR_VIDEO clips, cada uno en la escena donde mejor
        encaja, decididos antes que las fotos para que siempre que haya un clip que encaje, salga."""
        libres = [e for e in escenas if not e.get("imagen")]
        clips_ya = sum(1 for i in self.usadas if self.imagenes[i].get("video"))  # elegidos a mano
        parejas = []
        for escena in libres:
            claves = palabras_clave(f"{escena['narracion']} {escena.get('visual', '')}") | self.claves_evento
            for indice, imagen in enumerate(self.imagenes):
                if not imagen.get("video") or imagen.get("ambiente") or indice in self.usadas:
                    continue
                # Los del artículo (los eligieron sus editores) valen con que tengan algo que ver con la escena; los
                # de una búsqueda del tema, con la relevancia de una foto; los demás, la exigencia normal de los vídeos.
                if self._fuera_de_epoca(indice):
                    continue
                puntos = self.puntuacion(indice, claves)
                if ((imagen.get("del_articulo") and puntos > 0) or (imagen.get("del_tema") and puntos >= PUNTUACION_MINIMA)
                        or puntos >= PUNTUACION_MINIMA_VIDEO):
                    parejas.append((self.puntuacion(indice, claves), -escena["numero"], indice))
        reservas = {}
        for _, numero, indice in sorted(parejas, reverse=True):  # a igualdad, la escena más temprana
            numero = -numero
            if len(reservas) + clips_ya >= MAX_CLIPS_POR_VIDEO:
                break
            if numero not in reservas and indice not in reservas.values():
                reservas[numero] = indice
        self.reservadas = set(reservas.values())  # nadie más los coge
        return reservas

    def usar(self, indice: int):
        """Descarga una candidata concreta (p. ej. un clip reservado); None si no se puede."""
        return self._descargar(indice)

    def _ambiente(self, escena: dict):
        """Un plano de ambiente de Pexels de lo que pide el «visual» de la escena (fuego, mar, mapa…), si queda cupo."""
        if sum(1 for i in self.usadas if self.imagenes[i].get("ambiente")) >= MAX_AMBIENTE_POR_VIDEO:
            return None
        busquedas = pexels.busquedas_para([escena.get("visual", "")])
        for indice, imagen in enumerate(self.imagenes):
            if (imagen.get("ambiente") and imagen.get("busqueda") in busquedas and indice not in self.usadas
                    and indice not in self.fallidas):
                if resultado := self._descargar(indice):
                    return resultado
        return None

    def para_escena(self, escena: dict):
        """Devuelve (imagen, ruta) de la mejor imagen disponible, o (None, None)."""
        claves = palabras_clave(f"{escena['narracion']} {escena.get('visual', '')}") | self.claves_evento
        ranking = self.ranking(escena)
        nuevas = [i for i in ranking if i not in self.usadas and i not in self.fallidas and i not in self.reservadas
                  and self._vale(i, claves)]
        nuevas = [i for i in nuevas if not self._bloqueada(i)]
        if not nuevas or self.puntuacion(nuevas[0], claves) < PUNTUACION_AMBIENTE:
            if resultado := self._ambiente(escena):  # nada que encaje bien: un plano de ambiente de lo que se cuenta
                return resultado
        for indice in nuevas[:5]:
            if resultado := self._descargar(indice):
                return resultado
        # Sin imagen nueva relevante: mejor repetir una buena (sin repetir la de la escena anterior).
        repetibles = [i for i in ranking if i in self.descargadas and not self.imagenes[i].get("video")]
        for indice in [i for i in repetibles if i != self.anterior] or repetibles:
            self.anterior = indice
            return self.imagenes[indice], self.descargadas[indice]
        # Aún no hay ninguna descargada (p. ej. primera escena sin coincidencias): la mejor disponible.
        for indice in [i for i in ranking if i not in self.fallidas and not self._bloqueada(i)
                       and not self.imagenes[i].get("video")][:5]:
            if resultado := self._descargar(indice):
                return resultado
        return None, None


PROMPT_CLIPS = """Eres el montador de un canal de Shorts de historia y actualidad. Te paso las escenas de un vídeo y
unos clips de vídeo de archivo con licencia libre (título, descripción, año y origen). Decide qué clips encajan.

Un clip SOLO vale para una escena si:
- muestra algo coherente con lo que cuenta la escena (el lugar, el hecho, la época), no solo comparte una palabra;
- es de la época de lo que se cuenta: nada de vídeo moderno (misiones, huracanes, protestas, eventos de 2000 en adelante)
  en un tema histórico, salvo un lugar o paisaje que no delate la época (un timelapse de la ciudad, el mar, una montaña);
- no es una persona hablando a cámara (entrevista, discurso, conferencia, rueda de prensa) ni un vídeo de otro suceso.

Los clips retienen más que las fotos: si alguno encaja razonablemente, pon AL MENOS UNO. Elige como mucho {maximo},
cada clip en una sola escena y cada escena con un solo clip. Si ninguno encaja de verdad, no elijas ninguno: es mejor
una foto que un clip que no pega.
Responde SOLO con JSON: {{"asignaciones": [{{"escena": 3, "clip": 2, "motivo": "…"}}]}}"""


def reservar_clips_con_ia(selector, datos: dict, trabajo: Path) -> dict:
    """{escena: índice de clip}: la IA decide qué clips de archivo encajan de verdad (como mucho MAX_CLIPS_POR_VIDEO).

    La respuesta se guarda (clips_ia.json) para no volver a preguntar al rehacer el mismo vídeo. Sin IA disponible,
    solo los clips del propio artículo de Wikipedia (los eligieron sus editores), con la regla de palabras clave.
    """
    escenas = datos["escenas"]
    posibles = selector.clips_posibles(escenas)
    if not posibles:
        return {}
    libres = [e for e in escenas if not e.get("imagen")]
    clips = [{"clip": n, "titulo": selector.imagenes[i]["archivo"], "descripcion": selector.imagenes[i].get("descripcion", "")[:200],
              "anio": selector.imagenes[i].get("anio"), "segundos": selector.imagenes[i].get("duracion"),
              "origen": selector.imagenes[i].get("articulo", "")} for n, i in enumerate(posibles, 1)]
    pedido = json.dumps({"tema": datos.get("titulo", ""), "evento": datos.get("evento", ""),
                         "escenas": [{"escena": e["numero"], "texto": e["narracion"], "idea_visual": e.get("visual", "")}
                                     for e in libres],
                         "clips": clips}, ensure_ascii=False)
    guardado = trabajo / "clips_ia.json"
    firma = huella(pedido, MAX_CLIPS_POR_VIDEO)
    respuesta = None
    if guardado.exists():
        anterior = json.loads(guardado.read_text(encoding="utf-8"))
        respuesta = anterior.get("respuesta") if anterior.get("firma") == firma else None
    if respuesta is None:
        try:
            import paso1_guiones
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                raise RuntimeError("sin GROQ_API_KEY")
            texto = paso1_guiones.llamar_groq(api_key, paso1_guiones.MODELO_VERIFICADOR,
                                              PROMPT_CLIPS.format(maximo=MAX_CLIPS_POR_VIDEO), pedido)
            respuesta = json.loads(texto).get("asignaciones", [])
            guardado.write_text(json.dumps({"firma": firma, "respuesta": respuesta}, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        except Exception as error:  # noqa: BLE001 — sin IA: solo los clips seguros (los del artículo)
            print(f"  aviso: la IA no ha podido elegir clips ({type(error).__name__}); solo uso los del artículo")
            reservas = selector.reservar_clips(escenas)
            return selector.apartar({n: i for n, i in reservas.items() if selector.imagenes[i].get("del_articulo")})
    validas = {e["numero"] for e in libres}
    reservas = {}
    for a in respuesta if isinstance(respuesta, list) else []:
        try:
            numero, indice = int(a["escena"]), posibles[int(a["clip"]) - 1]
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        if numero in validas and numero not in reservas and indice not in reservas.values():
            reservas[numero] = indice
            print(f"  clip para la escena {numero}: {selector.imagenes[indice]['archivo'][:50]} ({a.get('motivo', '')[:70]})")
    if not reservas:
        print(f"  ningún clip de los {len(posibles)} encaja de verdad: van fotos")
    return selector.apartar(reservas)


# Wikimedia pide esperar demasiado: no se descargan más imágenes en esta ejecución.
WikimediaBloqueado = wikimedia.WikimediaEnEspera


def normalizar_nombre(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def ruta_en_cache(imagen: dict) -> Path:
    nombre = re.sub(r"[^\w.-]+", "_", normalizar_nombre(imagen["archivo"]))[:120]
    extension = ".png" if nombre.lower().endswith(".png") else ".jpg"
    return CARPETA_CACHE / f"{Path(nombre).stem}_{ANCHO_DESCARGA}{extension}"


def descargar(imagen: dict) -> Path:
    """Descarga (o reutiliza de la caché) la imagen, al ritmo que permite Wikimedia."""
    if imagen.get("ruta"):  # imagen propia subida desde el menú
        return Path(imagen["ruta"])
    if imagen.get("video"):
        # Un trozo desde el 20 % del vídeo (al principio suele haber títulos o carta de ajuste).
        duracion = float(imagen.get("duracion") or DURACION_CLIP)
        inicio = max(0.0, min(duracion * 0.2, duracion - DURACION_CLIP))
        nombre = re.sub(r"[^\w.-]+", "_", normalizar_nombre(imagen["archivo"]))[:100]
        return wikimedia.fragmento_video(imagen["url"], CARPETA_CLIPS / f"{Path(nombre).stem}_{inicio:.0f}.mp4",
                                         inicio, DURACION_CLIP)
    return wikimedia.archivo(imagen["url"], ruta_en_cache(imagen))


def componer_fotograma(ruta_imagen, destino: Path, etiqueta: str = "") -> Path:
    """Imagen completa centrada sobre un fondo de la misma imagen desenfocada (formato vertical).

    `etiqueta` (p. ej. «IMAGEN DE ARCHIVO») se pinta en la esquina de la imagen."""
    if ruta_imagen is None:  # sin imagen: degradado oscuro
        fondo = Image.linear_gradient("L").resize((ANCHO, ALTO)).convert("RGB")
        ImageEnhance.Brightness(ImageOps.colorize(fondo.convert("L"), "#0b1a2e", "#3a2a14")).enhance(0.9).save(destino)
        return destino
    imagen = ImageOps.exif_transpose(Image.open(ruta_imagen)).convert("RGB")
    fondo = ImageOps.fit(imagen, (ANCHO, ALTO)).filter(ImageFilter.GaussianBlur(40))
    fondo = ImageEnhance.Brightness(fondo).enhance(0.45)
    # La imagen ocupa la franja central: arriba queda sitio para el título y abajo para los subtítulos.
    alto_maximo = int(ALTO * ALTO_IMAGEN)
    frente = imagen.copy()
    frente.thumbnail((ANCHO, alto_maximo), Image.LANCZOS)
    if frente.width < ANCHO * 0.85:  # imágenes pequeñas: se amplían para llenar el ancho
        frente = imagen.resize((ANCHO, int(imagen.height * ANCHO / imagen.width)), Image.LANCZOS)
        if frente.height > alto_maximo:
            frente = ImageOps.fit(frente, (ANCHO, alto_maximo))
    x = (ANCHO - frente.width) // 2
    y = int(ALTO * CENTRO_IMAGEN) - frente.height // 2
    fondo.paste(frente, (x, y))
    if etiqueta:
        poner_etiqueta(fondo, etiqueta, x + 24, y + 24)
    fondo.save(destino)
    return destino


def capa_etiqueta(tamano: tuple, texto: str, x: int, y: int) -> Image.Image:
    """Capa transparente con el rótulo: texto blanco en una pastilla oscura, legible sobre cualquier imagen."""
    try:
        fuente = ImageFont.truetype("arialbd.ttf", 30)
    except OSError:
        fuente = ImageFont.load_default()
    capa = Image.new("RGBA", tamano, (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(capa)
    caja = dibujo.textbbox((0, 0), texto, font=fuente)
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    dibujo.rounded_rectangle((x, y, x + ancho + 32, y + alto + 22), radius=12, fill=(0, 0, 0, 170))
    dibujo.text((x + 16, y + 11 - caja[1]), texto, font=fuente, fill=(255, 255, 255, 235))
    return capa


def poner_etiqueta(imagen, texto: str, x: int, y: int) -> None:
    """Rótulo pequeño y legible sobre cualquier foto."""
    imagen.paste(Image.alpha_composite(imagen.convert("RGBA"), capa_etiqueta(imagen.size, texto, x, y)).convert("RGB"))


# --- Subtítulos (ASS) -----------------------------------------------------------

def tiempo_ass(segundos: float) -> str:
    centesimas = round(max(segundos, 0) * 100)
    horas, resto = divmod(centesimas, 360_000)
    minutos, resto = divmod(resto, 6000)
    segs, cs = divmod(resto, 100)
    return f"{horas}:{minutos:02d}:{segs:02d}.{cs:02d}"


def escapar_ass(texto: str) -> str:
    return texto.replace("\\", "").replace("{", "(").replace("}", ")")


CABECERA_ASS = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {ANCHO}
PlayResY: {ALTO}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Arial Black,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,2,2,70,70,430,1
Style: Titulo,Arial Black,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,3,16,0,8,80,80,120,1
Style: Gancho,Arial Black,160,&H0000D7FF,&H0000D7FF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,10,4,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
AMARILLO = r"{\c&H00D7FF&}"  # BGR: amarillo dorado para la palabra que suena
BLANCO = r"{\c&HFFFFFF&}"


def bloques_de_palabras(palabras: list) -> list:
    bloques, actual = [], []
    for palabra in palabras:
        if actual and (
            len(actual) >= PALABRAS_POR_SUBTITULO or palabra["inicio_s"] - actual[-1]["fin_s"] > CORTE_POR_SILENCIO
        ):
            bloques.append(actual)
            actual = []
        actual.append(palabra)
    if actual:
        bloques.append(actual)
    return bloques


def _es_clave(palabra: str, claves: set) -> bool:
    return normalizar(palabra).strip() in claves


def texto_ass(palabras: list, total: float, gancho: str = "", titulo: str = "", claves=()) -> str:
    """Subtítulos de una escena (tiempos relativos a su inicio). En la primera, el gancho o el título.

    Las `claves` (palabras graciosas o importantes) salen siempre en mayúsculas, doradas y algo más grandes.
    """
    # «tabla de madera» → «tabla», «madera»: las palabras vacías («de», «la»…) nunca se resaltan.
    claves = {p for c in claves for p in normalizar(c).split() if len(p) > 2 and p not in PALABRAS_VACIAS}
    eventos = []
    if gancho:  # aparece con un pequeño «salto» y se desvanece
        fin = min(DURACION_GANCHO, total - 0.05)
        eventos.append(
            f"Dialogue: 1,{tiempo_ass(0)},{tiempo_ass(fin)},Gancho,,0,0,0,,"
            rf"{{\fad(80,300)\fscx70\fscy70\t(0,180,\fscx100\fscy100)}}{escapar_ass(gancho)}"
        )
    elif titulo:
        fin = min(DURACION_TITULO, total - 0.05)
        eventos.append(
            f"Dialogue: 1,{tiempo_ass(0)},{tiempo_ass(fin)},Titulo,,0,0,0,,{{\\fad(200,400)}}{escapar_ass(titulo)}"
        )
    for bloque in bloques_de_palabras(palabras):
        for i, palabra in enumerate(bloque):
            inicio = palabra["inicio_s"]
            fin = bloque[i + 1]["inicio_s"] if i + 1 < len(bloque) else min(palabra["fin_s"] + 0.15, total)
            partes = []
            for j, p in enumerate(bloque):
                texto_palabra = escapar_ass(p["texto"])
                if _es_clave(p["texto"], claves):  # palabra clave: siempre destacada
                    partes.append(rf"{AMARILLO}{{\fscx118\fscy118}}{texto_palabra.upper()}{{\fscx100\fscy100}}{BLANCO}")
                elif j == i:
                    partes.append(f"{AMARILLO}{texto_palabra}{BLANCO}")
                else:
                    partes.append(texto_palabra)
            texto = " ".join(partes)
            eventos.append(f"Dialogue: 0,{tiempo_ass(inicio)},{tiempo_ass(fin)},Sub,,0,0,0,,{texto}")
    return CABECERA_ASS + "\n".join(eventos) + "\n"


# --- Vídeo -------------------------------------------------------------------------

def ffmpeg(argumentos: list, cwd: Path) -> None:
    comando = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *argumentos]
    resultado = subprocess.run(
        comando, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {resultado.stderr.strip()[-500:]}")


def huella(*partes) -> str:
    return hashlib.sha1(json.dumps(partes, sort_keys=True, default=str).encode()).hexdigest()


def info_archivo(ruta) -> list:
    ruta = Path(ruta) if ruta else None
    if not ruta or not ruta.exists():
        return [str(ruta)]
    estado = ruta.stat()
    return [str(ruta), estado.st_size, int(estado.st_mtime)]


def segmento_escena(trabajo: Path, numero: int, ruta_imagen, audio: Path, util: float, total: float,
                    subtitulos: str, etiqueta: str = "") -> Path:
    """Vídeo de una escena (imagen con zoom lento + su audio + subtítulos ya grabados), con caché."""
    salida = trabajo / f"seg_{numero:02d}.mp4"
    clave = trabajo / f"seg_{numero:02d}.clave"
    firma = huella(VERSION_ESCENA, info_archivo(ruta_imagen), info_archivo(audio), round(util, 3),
                   round(total, 3), subtitulos, etiqueta)
    if salida.exists() and clave.exists() and clave.read_text() == firma:
        return salida  # nada ha cambiado en esta escena

    fotograma = componer_fotograma(ruta_imagen, trabajo / f"frame_{numero:02d}.png", etiqueta)
    (trabajo / f"sub_{numero:02d}.ass").write_text(subtitulos, encoding="utf-8")
    fotogramas = max(1, round(total * FPS))
    zoom = f"min(1+{ZOOM_FINAL - 1:.3f}*on/{fotogramas},{ZOOM_FINAL})"
    filtro_video = (
        f"scale={ANCHO * 2}:{ALTO * 2},"
        f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fotogramas}:s={ANCHO}x{ALTO}:fps={FPS},"
        f"ass=sub_{numero:02d}.ass,format=yuv420p"
    )
    ffmpeg(
        [
            "-i", fotograma.name, "-i", str(audio.resolve()),
            "-filter_complex", f"[0:v]{filtro_video}[v];[1:a]atrim=0:{util:.3f},apad=whole_dur={total:.3f}[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            salida.name,
        ],
        trabajo,
    )
    clave.write_text(firma)
    return salida


def _filtro_clip_vertical(entrada: str, salida: str) -> str:
    """El clip en la franja central, sobre el mismo clip desenfocado y oscurecido (como las fotos)."""
    alto_maximo = int(ALTO * ALTO_IMAGEN)
    return (
        f"[{entrada}]fps={FPS},split[cf][cd];"
        f"[cf]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},"
        f"boxblur=24:2,eq=brightness=-0.3[fondo];"
        f"[cd]scale={ANCHO}:{alto_maximo}:force_original_aspect_ratio=decrease[frente];"
        f"[fondo][frente]overlay=(W-w)/2:{int(ALTO * CENTRO_IMAGEN)}-h/2,setsar=1[{salida}]"
    )


def segmento_video(trabajo: Path, numero: int, clip, audio: Path, util: float, total: float,
                   subtitulos: str, etiqueta: str = "") -> Path:
    """Escena con un clip de vídeo real: en movimiento, sin su sonido, con la voz y los subtítulos."""
    salida = trabajo / f"seg_{numero:02d}.mp4"
    clave = trabajo / f"seg_{numero:02d}.clave"
    firma = huella(VERSION_ESCENA, "video", info_archivo(clip), info_archivo(audio), round(util, 3),
                   round(total, 3), subtitulos, etiqueta)
    if salida.exists() and clave.exists() and clave.read_text() == firma:
        return salida
    (trabajo / f"sub_{numero:02d}.ass").write_text(subtitulos, encoding="utf-8")
    entradas, rotulo = [], ""
    if etiqueta:  # «IMÁGENES DE ARCHIVO»…: en la esquina del clip, como en las fotos
        ancho, alto = dimensiones_video(clip)
        escala = min(ANCHO / ancho, int(ALTO * ALTO_IMAGEN) / alto)
        x = (ANCHO - int(ancho * escala)) // 2
        y = int(ALTO * CENTRO_IMAGEN) - int(alto * escala) // 2
        capa_etiqueta((ANCHO, ALTO), etiqueta, x + 24, y + 24).save(trabajo / f"rotulo_{numero:02d}.png")
        entradas = ["-i", f"rotulo_{numero:02d}.png"]
        rotulo = "[vc][2:v]overlay=0:0[vc];"
    # Si el clip es más corto que la escena, se queda congelado en su último fotograma.
    video = (f"{_filtro_clip_vertical('0:v', 'vc')};{rotulo}"
             f"[vc]tpad=stop_mode=clone:stop_duration={total:.3f},ass=sub_{numero:02d}.ass,format=yuv420p[v]")
    ffmpeg(
        [
            "-i", str(Path(clip).resolve()), "-i", str(audio.resolve()), *entradas,
            "-filter_complex", f"{video};[1:a]atrim=0:{util:.3f},apad=whole_dur={total:.3f}[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            salida.name,
        ],
        trabajo,
    )
    clave.write_text(firma)
    return salida


def dimensiones_video(clip) -> tuple:
    """(ancho, alto) de un vídeo, leídos de lo que dice ffmpeg al abrirlo."""
    salida = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(Path(clip).resolve())],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    medida = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", salida)
    return (int(medida[1]), int(medida[2])) if medida else (ANCHO, int(ALTO * ALTO_IMAGEN))


def fotograma_de_video(clip, destino: Path) -> Path:
    """Un fotograma del clip ya compuesto en vertical (para la miniatura si la primera escena es un vídeo)."""
    ffmpeg(["-ss", "0.5", "-i", str(Path(clip).resolve()), "-filter_complex", _filtro_clip_vertical("0:v", "v"),
            "-map", "[v]", "-frames:v", "1", destino.name], destino.parent)
    return destino


def unir(trabajo: Path, segmentos: list, destino: Path, pista, duracion: float) -> None:
    """Une las escenas sin recodificar el vídeo y mezcla la música (que baja cuando habla la voz)."""
    (trabajo / "lista.txt").write_text("".join(f"file '{s.name}'\n" for s in segmentos), encoding="utf-8")
    if pista is None:
        argumentos = ["-f", "concat", "-safe", "0", "-i", "lista.txt", "-c", "copy"]
    else:
        fundido = max(0.0, duracion - 1.5)
        filtro = (
            f"[1:a]volume={VOLUMEN_MUSICA},afade=t=in:d=1,afade=t=out:st={fundido:.2f}:d=1.5,"
            "aformat=sample_rates=44100:channel_layouts=stereo[musica];"
            "[0:a]asplit=2[voz][guia];"
            "[musica][guia]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=350[fondo];"
            "[voz][fondo]amix=inputs=2:duration=first:normalize=0[a]"
        )
        argumentos = [
            "-f", "concat", "-safe", "0", "-i", "lista.txt",
            "-stream_loop", "-1", "-i", str(Path(pista).resolve()),
            "-filter_complex", filtro, "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duracion:.3f}",
        ]
    ffmpeg([*argumentos, "-movflags", "+faststart", "final.mp4"], trabajo)
    shutil.move(str(trabajo / "final.mp4"), destino)


def crear_miniatura(fotograma: Path, texto: str, destino: Path, parte: str = "") -> None:
    """Portada 1080x1920: la imagen de la primera escena con el gancho en grande."""
    imagen = ImageEnhance.Brightness(Image.open(fotograma).convert("RGB")).enhance(0.8)
    dibujo = ImageDraw.Draw(imagen)
    texto = re.sub(r"\s*\((Parte|Part) \d+/\d+\)\s*$", "", texto)  # la parte ya va en la etiqueta

    def partir(fuente) -> list:
        lineas, actual = [], ""
        for palabra in texto.split():
            prueba = f"{actual} {palabra}".strip()
            if actual and dibujo.textlength(prueba, font=fuente) > ANCHO - 120:
                lineas.append(actual)
                actual = palabra
            else:
                actual = prueba
        return lineas + [actual]

    # La letra más grande con la que el texto cabe a lo ancho en 4 líneas como mucho.
    try:
        fuente_parte = ImageFont.truetype("ariblk.ttf", 70)
        for tamano in range(150, 60, -10):
            fuente = ImageFont.truetype("ariblk.ttf", tamano)
            lineas = partir(fuente)
            if len(lineas) <= 4 and all(dibujo.textlength(l, font=fuente) <= ANCHO - 80 for l in lineas):
                break
    except OSError:
        fuente = fuente_parte = ImageFont.load_default()
        tamano, lineas = 40, partir(fuente)
    alto_linea = int(tamano * 1.1)
    y = int(ALTO * 0.2)
    for linea in lineas[:4]:
        ancho = dibujo.textlength(linea, font=fuente)
        dibujo.text(((ANCHO - ancho) / 2, y), linea, font=fuente, fill=(255, 215, 0),
                    stroke_width=max(4, tamano // 15), stroke_fill=(0, 0, 0))
        y += alto_linea
    if parte:
        ancho = dibujo.textlength(parte, font=fuente_parte)
        dibujo.rounded_rectangle(((ANCHO - ancho) / 2 - 30, ALTO - 360, (ANCHO + ancho) / 2 + 30, ALTO - 250),
                                 radius=24, fill=(181, 86, 43))
        dibujo.text(((ANCHO - ancho) / 2, ALTO - 352), parte, font=fuente_parte, fill=(255, 255, 255))
    imagen.save(destino, quality=90)


# --- Nombres y carpetas de los vídeos ---------------------------------------------------
# salida/videos/Guerra-civil/
#     Guerra-civil_pt1.mp4   el vídeo
#     Guerra-civil_pt1.txt   lo que poner al publicar (TikTok y YouTube Shorts)
#     Guerra-civil_pt1.jpg   la miniatura
#     guiones/Guerra-civil_pt1.txt   el texto del guion
# («_ptN» solo en las series; los vídeos que no están en español llevan el idioma: «_EN»)

PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')  # caracteres no válidos en nombres de Windows
ARTICULOS = {"el", "la", "los", "las", "lo", "un", "una", "the", "a", "an"}


def nombre_corto(datos: dict) -> str:
    """Nombre corto del tema (p. ej. «Guerra civil»), seguro para usarlo como nombre de archivo."""
    # Hasta la primera coma y 4 palabras como mucho (por si la IA devolvió el tema entero).
    nombre = " ".join(re.split(r"[,:;(]", str(datos.get("nombre_corto") or ""))[0].split()[:4])
    if not nombre:  # guiones antiguos: primeras palabras del tema o del evento
        base = (datos.get("serie") or {}).get("tema") or datos.get("evento") or datos.get("titulo") or "Vídeo"
        palabras = base.split()
        while len(palabras) > 1 and palabras[0].lower() in ARTICULOS:
            palabras.pop(0)
        nombre = " ".join(palabras[:3])
    nombre = PROHIBIDOS.sub("", nombre).strip(" .")[:40].strip(" .") or "Video"
    return nombre[0].upper() + nombre[1:]


def ruta_guion_de(nombre: str) -> Path:
    return CARPETA_GUIONES / f"{nombre}.json"


def nombre_archivo(datos: dict) -> str:
    """«Guerra civil» → «Guerra-civil»: sin espacios, para nombres de archivo cortos."""
    return re.sub(r"\s+", "-", nombre_corto(datos))


def ruta_esperada(datos: dict) -> Path:
    """Ruta que le corresponde a un vídeo según su nombre corto (sin comprobar si ya existe)."""
    corto = nombre_archivo(datos)
    serie = datos.get("serie") or {}
    base = f"{corto}_pt{serie['parte']}" if serie.get("total", 1) > 1 else corto
    if datos.get("diario"):  # «Diario-soldado-romano_dia4»
        base = f"{corto}_dia{datos['diario']['dia']}"
    if datos.get("idioma", "es") != "es":  # p. ej. «Pancho-Villa_EN» junto a «Pancho-Villa»
        base += f"_{datos['idioma'].upper()}"
    return CARPETA_VIDEOS / corto / f"{base}.mp4"


def destino_nuevo(datos: dict) -> Path:
    """Ruta que le toca a un vídeo nuevo, sin pisar la de otro guion."""
    esperada = ruta_esperada(datos)
    candidato, numero = esperada, 2
    while candidato.exists():  # otro vídeo ya usa ese nombre
        candidato = esperada.with_name(f"{esperada.stem}_{numero}.mp4")
        numero += 1
    return candidato


def destino_video(nombre: str, datos: dict) -> Path:
    """Ruta del vídeo de un guion: la que ya tenía guardada o una nueva."""
    if datos.get("video"):
        return Path(datos["video"])
    return destino_nuevo(datos)


def ruta_descripcion(video: Path) -> Path:
    return video.with_suffix(".txt")


def ruta_miniatura(video: Path) -> Path:
    return video.with_suffix(".jpg")


def ruta_guion_texto(video: Path) -> Path:
    return video.parent / "guiones" / f"{video.stem}.txt"


def guardar_ruta_video(nombre: str, video: Path) -> None:
    """Apunta en el guion dónde quedó su vídeo (lo usan el menú y las siguientes ejecuciones)."""
    ruta = ruta_guion_de(nombre)
    if not ruta.exists():
        return
    guion = json.loads(ruta.read_text(encoding="utf-8"))
    guion["video"] = video.as_posix()
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")


def _creditos_antiguos(descripcion: Path) -> list:
    """Créditos de imágenes de una descripción de las versiones anteriores (líneas «- …» tras «Imágenes»)."""
    if not descripcion.exists():
        return []
    creditos, dentro = [], False
    for linea in descripcion.read_text(encoding="utf-8").splitlines():
        if linea.strip().rstrip(":").lower().startswith(("imágenes", "images")):
            dentro = True
        elif dentro and linea.startswith("- "):
            creditos.append(linea[2:].strip())
        elif dentro and not linea.strip():
            break
    return creditos


def _creditos_guardados(nombre: str) -> list:
    """Créditos de las imágenes que se usaron la última vez que se montó el vídeo."""
    ruta = elegidas_path(nombre)
    if not ruta.exists():
        return []
    creditos = []
    for eleccion in json.loads(ruta.read_text(encoding="utf-8")).values():
        imagen = eleccion.get("imagen")
        if imagen and imagen["archivo"] not in [c["archivo"] for c in creditos]:
            creditos.append(imagen)
    return creditos


def migrar_videos_antiguos() -> None:
    """Pasa los vídeos de formatos anteriores al actual (Tema/Tema_ptN.mp4 + .txt + .jpg + guiones/)."""
    # 1. Formato más antiguo: salida/videos/<guion>.mp4 sueltos.
    for antiguo in CARPETA_VIDEOS.glob("*.mp4"):
        if ruta_guion_de(antiguo.stem).exists():
            guion = json.loads(ruta_guion_de(antiguo.stem).read_text(encoding="utf-8"))
            if not guion.get("video"):
                guardar_ruta_video(antiguo.stem, antiguo)
    # 2. Cualquier vídeo cuyo nombre no siga el formato actual.
    for ruta in CARPETA_GUIONES.glob("*.json"):
        guion = json.loads(ruta.read_text(encoding="utf-8"))
        actual = Path(guion["video"]) if guion.get("video") else None
        if not actual or not actual.exists():
            continue
        descripcion_vieja = next((p for p in (actual.with_name(f"{actual.stem} - descripcion.txt"),
                                              actual.with_name(f"{actual.stem}_descripcion.txt")) if p.exists()), None)
        miniatura_vieja = actual.with_name(f"{actual.stem} - miniatura.jpg")
        esperada = ruta_esperada(guion)
        if not descripcion_vieja and not miniatura_vieja.exists() and actual.parent == esperada.parent:
            continue  # ya está en el formato actual
        if actual.resolve() == esperada.resolve():
            nuevo = actual  # el nombre ya vale: solo cambian sus textos
        else:
            nuevo = esperada if not esperada.exists() else destino_nuevo(guion)
            nuevo.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(actual), nuevo)
        if miniatura_vieja.exists():
            shutil.move(str(miniatura_vieja), ruta_miniatura(nuevo))
        creditos = _creditos_guardados(ruta.stem) or (_creditos_antiguos(descripcion_vieja) if descripcion_vieja else [])
        if descripcion_vieja:
            descripcion_vieja.unlink()
        datos = leer_datos(CARPETA_AUDIO / ruta.stem) if (CARPETA_AUDIO / ruta.stem / "escenas.json").exists() else guion
        # Los vídeos montados con la versión con música tienen «elegidas.json»; los anteriores, no.
        pista = guion.get("musica", "neutro") if elegidas_path(ruta.stem).exists() else ""
        escribir_textos(nuevo, ruta.stem, datos, creditos, pista)
        guardar_ruta_video(ruta.stem, nuevo)
        print(f"Formato nuevo: {actual} → {nuevo}")
        if actual.parent != nuevo.parent and actual.parent.exists() and not any(actual.parent.iterdir()):
            actual.parent.rmdir()  # la carpeta antigua del tema quedó vacía


# --- Montaje ---------------------------------------------------------------------

def leer_datos(carpeta_audio: Path) -> dict:
    """Tiempos del audio (paso 2) + lo último del guion: título, gancho, música e imágenes elegidas."""
    datos = json.loads((carpeta_audio / "escenas.json").read_text(encoding="utf-8"))
    ruta = ruta_guion_de(carpeta_audio.name)
    if not ruta.exists():
        return datos
    guion = json.loads(ruta.read_text(encoding="utf-8"))
    elegidas = {e.get("numero"): e.get("imagen") for e in guion.get("escenas", []) if e.get("imagen")}
    escenas = [{**e, "imagen": elegidas.get(e["numero"])} for e in datos["escenas"]]
    return {**datos, **{k: v for k, v in guion.items() if k != "escenas"}, "escenas": escenas}


def elegidas_path(nombre: str) -> Path:
    return CARPETA_TRABAJO / nombre / "elegidas.json"


def montar(carpeta_audio: Path, forzar: bool) -> Path:
    nombre = carpeta_audio.name
    datos = leer_datos(carpeta_audio)
    ruta_video = destino_video(nombre, datos)
    if ruta_video.exists() and not forzar:
        print(f"  ya tiene vídeo: {ruta_video} (usa --forzar para rehacerlo)")
        return ruta_video
    ruta_video.parent.mkdir(parents=True, exist_ok=True)
    trabajo = CARPETA_TRABAJO / nombre
    trabajo.mkdir(parents=True, exist_ok=True)

    if datos.get("video_ia"):  # clips generados con una IA de vídeo en vez de imágenes
        return montar_clips(carpeta_audio, datos, nombre, ruta_video, trabajo)

    # 1. Imagen de cada escena: la elegida a mano o la que mejor encaja
    imagenes = candidatas(nombre, datos)
    print(f"  {len(imagenes)} imágenes candidatas")
    selector = SelectorImagenes(imagenes, datos.get("evento", ""), datos.get("anio_evento"))
    anios = [int(a) for e in datos["escenas"] for a in re.findall(r"(1[0-9]{3}|20[0-9]{2})", e["narracion"])]
    if not datos.get("actualidad") and anios and max(anios) < 2000:
        selector.epoca_maxima = 1999  # nada de huracanes de 2024 en un vídeo sobre la colonia
    for escena in datos["escenas"]:
        if escena.get("imagen"):
            selector.marcar_usada(escena["imagen"])
    elegidas, creditos = {}, []
    reservas = reservar_clips_con_ia(selector, datos, trabajo)  # 1-2 clips de vídeo libres, si encajan de verdad
    for escena in datos["escenas"]:
        imagen, ruta = escena.get("imagen"), None
        if imagen:
            try:
                ruta = descargar(imagen)
            except (WikimediaBloqueado, requests.RequestException):
                print(f"    no se pudo descargar la imagen elegida de la escena {escena['numero']}; elijo otra")
                imagen = None
        if not imagen and escena["numero"] in reservas:
            imagen, ruta = selector.usar(reservas[escena["numero"]]) or (None, None)
        if not imagen:
            imagen, ruta = selector.para_escena(escena)
        elegidas[escena["numero"]] = {"imagen": imagen, "ruta": str(ruta) if ruta else None,
                                      "a_mano": bool(escena.get("imagen")) and imagen is escena.get("imagen")}
        if imagen and imagen["archivo"] not in [c["archivo"] for c in creditos]:
            creditos.append(imagen)
        if ruta is None and selector.bloqueados:
            # Mejor esperar que montar un vídeo con escenas sin imagen.
            raise wikimedia.WikimediaEnEspera(wikimedia.en_espera_hasta() or time.time() + 120)
    elegidas_path(nombre).write_text(json.dumps(elegidas, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Un segmento por escena (en paralelo y con caché), con la línea de tiempo ya recortada
    gancho = str(datos.get("gancho") or "").strip()
    trabajos, cursor = [], 0.0
    for indice, escena in enumerate(datos["escenas"]):
        tiempos = escena.get("palabras_tiempos", [])
        ultima = (tiempos[-1]["fin_s"] - escena["inicio_s"]) if tiempos else escena["duracion_s"]
        util = min(escena["duracion_s"], ultima + COLA_TRAS_ULTIMA_PALABRA)
        total = util + PAUSA_ENTRE_ESCENAS
        relativas = [{"texto": p["texto"], "inicio_s": p["inicio_s"] - escena["inicio_s"],
                      "fin_s": p["fin_s"] - escena["inicio_s"]} for p in tiempos]
        subtitulos = texto_ass(relativas, total, gancho if indice == 0 else "",
                               datos.get("titulo", "") if indice == 0 else "", datos.get("palabras_clave", []))
        eleccion = elegidas[escena["numero"]]
        etiqueta = ""
        if datos.get("actualidad") and eleccion["ruta"] and not (eleccion["imagen"] or {}).get("ruta"):
            # Foto de este año (puede ser del propio suceso, con licencia libre): se dice de dónde es.
            # Si es anterior, se avisa de que es de archivo y no muestra los hechos.
            ingles = datos.get("idioma") == "en"
            es_video = (eleccion["imagen"] or {}).get("video")
            if (eleccion["imagen"] or {}).get("anio") == datetime.now().year:
                etiqueta = ("VIDEO" if es_video else "PHOTO" if ingles else "FOTO") + ": WIKIMEDIA COMMONS"
                etiqueta = etiqueta.replace("VIDEO", "VÍDEO") if es_video and not ingles else etiqueta
            elif es_video:
                etiqueta = "ARCHIVE FOOTAGE" if ingles else "IMÁGENES DE ARCHIVO"
            else:
                etiqueta = "ARCHIVE IMAGE" if ingles else "IMAGEN DE ARCHIVO"
        imagen = eleccion["imagen"]
        hacer = segmento_video if (imagen or {}).get("video") and eleccion["ruta"] else segmento_escena
        trabajos.append((hacer, trabajo, escena["numero"], eleccion["ruta"], carpeta_audio / escena["audio"],
                         util, total, subtitulos, etiqueta))
        marca = (" (generada con IA)" if (imagen or {}).get("ia") else " (elegida a mano)") if eleccion["a_mano"] else ""
        marca += " [vídeo]" if hacer is segmento_video else ""
        print(f"  escena {escena['numero']}: {total:.2f} s · {imagen['archivo'][:55] if imagen else 'sin imagen'}{marca}")
        cursor += total

    inicio = time.time()
    with ThreadPoolExecutor(max_workers=HILOS) as hilos:
        segmentos = list(hilos.map(lambda t: t[0](*t[1:]), trabajos))
    print(f"  escenas listas en {time.time() - inicio:.0f} s ({HILOS} a la vez; las que no cambiaron, de la caché)")

    # Toma final: «¿Quieres la parte 2? Dale a like y suscríbete» (sobria en los vídeos de tono triste)
    segmento_cierre, duracion_cierre = cierre.crear(datos, trabajo, huella)
    segmentos.append(segmento_cierre)
    cursor += duracion_cierre
    print(f"  cierre: «{cierre.textos(datos)['voz']}» ({duracion_cierre:.1f} s)")

    # 3. Unir, música, descripción y miniatura
    pista = musica.ruta_pista(datos.get("musica", "neutro"))
    unir(trabajo, segmentos, ruta_video, pista, cursor)
    escribir_textos(ruta_video, nombre, datos, creditos, datos.get("musica", "neutro") if pista else "")
    serie = datos.get("serie") or {}
    etiqueta = ""
    if serie.get("total", 1) > 1:
        etiqueta = f"{'PART' if datos.get('idioma') == 'en' else 'PARTE'} {serie['parte']}/{serie['total']}"
    primera = trabajo / f"frame_{datos['escenas'][0]['numero']:02d}.png"
    eleccion = elegidas[datos["escenas"][0]["numero"]]
    if (eleccion["imagen"] or {}).get("video") and eleccion["ruta"]:
        fotograma_de_video(eleccion["ruta"], primera)  # la primera escena es un vídeo: su fotograma
    elif not primera.exists():
        componer_fotograma(eleccion["ruta"], primera)
    crear_miniatura(primera, gancho or datos.get("titulo", ""), ruta_miniatura(ruta_video), etiqueta)
    guardar_ruta_video(nombre, ruta_video)
    print(f"  duración: {cursor:.1f} s · música: {datos.get('musica', 'neutro') if pista else 'ninguna'}")
    return ruta_video


def segmento_clip(trabajo: Path, numero: int, clip: Path, audio: Path, util: float, total: float,
                  subtitulos: str, voz_del_clip: bool) -> Path:
    """Escena hecha con un clip de IA: recortado a vertical, en bucle si es más corto que la escena, con subtítulos.

    Con la voz del clip, el audio es el del propio clip; si narra la app, va su voz con el sonido del clip de fondo."""
    import video_ia
    salida = trabajo / f"seg_{numero:02d}.mp4"
    clave = trabajo / f"seg_{numero:02d}.clave"
    firma = huella(VERSION_ESCENA, "clip", info_archivo(clip), info_archivo(audio), round(util, 3), round(total, 3),
                   subtitulos, voz_del_clip)
    if salida.exists() and clave.exists() and clave.read_text() == firma:
        return salida
    (trabajo / f"sub_{numero:02d}.ass").write_text(subtitulos, encoding="utf-8")
    bucle = ["-stream_loop", "-1"] if video_ia.duracion(clip) < total - 0.05 else []
    video = (f"[0:v]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},setsar=1,fps={FPS},"
             f"ass=sub_{numero:02d}.ass,format=yuv420p[v]")
    voz = f"[1:a]atrim=0:{util:.3f},apad=whole_dur={total:.3f}"
    if not voz_del_clip and video_ia.tiene_audio(clip):  # narración de la app con el ambiente del clip bajito
        sonido = (f"{voz}[voz];[0:a]volume=0.15,apad,atrim=0:{total:.3f}[ambiente];"
                  f"[voz][ambiente]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        sonido = f"{voz}[a]"
    ffmpeg(
        [
            *bucle, "-i", str(clip.resolve()), "-i", str(audio.resolve()),
            "-filter_complex", f"{video};{sonido}",
            "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            salida.name,
        ],
        trabajo,
    )
    clave.write_text(firma)
    return salida


def montar_clips(carpeta_audio: Path, datos: dict, nombre: str, ruta_video: Path, trabajo: Path) -> Path:
    """Monta un «Vídeo con IA»: un clip por escena, subtítulos, gancho, música, cierre, miniatura y textos."""
    import video_ia
    faltan = video_ia.faltan(nombre, datos["escenas"])
    if faltan:
        raise ValueError(f"faltan los clips de las escenas {', '.join(map(str, faltan))}: súbelos en la página del guion")
    ia = datos["video_ia"]
    voz_del_clip = ia.get("voz") == "ia"
    print(f"  vídeo con IA ({video_ia.herramienta(ia.get('herramienta', ''))['nombre']}) · "
          f"voz {'de los clips' if voz_del_clip else 'de la app'}")
    gancho = str(datos.get("gancho") or "").strip()
    trabajos, cursor = [], 0.0
    for indice, escena in enumerate(datos["escenas"]):
        tiempos = escena.get("palabras_tiempos", [])
        ultima = (tiempos[-1]["fin_s"] - escena["inicio_s"]) if tiempos else escena["duracion_s"]
        util = min(escena["duracion_s"], ultima + COLA_TRAS_ULTIMA_PALABRA)
        total = util + PAUSA_ENTRE_ESCENAS
        relativas = [{"texto": p["texto"], "inicio_s": p["inicio_s"] - escena["inicio_s"],
                      "fin_s": p["fin_s"] - escena["inicio_s"]} for p in tiempos]
        subtitulos = texto_ass(relativas, total, gancho if indice == 0 else "",
                               datos.get("titulo", "") if indice == 0 else "", datos.get("palabras_clave", []))
        clip = video_ia.ruta_clip(nombre, escena["numero"])
        trabajos.append((trabajo, escena["numero"], clip, carpeta_audio / escena["audio"], util, total, subtitulos,
                         voz_del_clip))
        print(f"  escena {escena['numero']}: {total:.2f} s · clip {clip.name} ({video_ia.duracion(clip):.1f} s)")
        cursor += total

    inicio = time.time()
    with ThreadPoolExecutor(max_workers=HILOS) as hilos:
        segmentos = list(hilos.map(lambda argumentos: segmento_clip(*argumentos), trabajos))
    print(f"  escenas listas en {time.time() - inicio:.0f} s")

    segmento_cierre, duracion_cierre = cierre.crear(datos, trabajo, huella)
    segmentos.append(segmento_cierre)
    cursor += duracion_cierre
    print(f"  cierre: «{cierre.textos(datos)['voz']}» ({duracion_cierre:.1f} s)")

    pista = musica.ruta_pista(datos.get("musica", "neutro"))
    unir(trabajo, segmentos, ruta_video, pista, cursor)
    elegidas_path(nombre).write_text("{}", encoding="utf-8")  # sin imágenes ni créditos de terceros
    escribir_textos(ruta_video, nombre, datos, [], datos.get("musica", "neutro") if pista else "")
    # Miniatura: un fotograma del primer clip (a pantalla completa) con el gancho
    portada = trabajo / "portada_clip.png"
    ffmpeg(["-ss", "1", "-i", str(video_ia.ruta_clip(nombre, datos["escenas"][0]["numero"]).resolve()),
            "-frames:v", "1", "-vf", f"scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO}",
            portada.name], trabajo)
    crear_miniatura(portada, gancho or datos.get("titulo", ""), ruta_miniatura(ruta_video))
    guardar_ruta_video(nombre, ruta_video)
    print(f"  duración: {cursor:.1f} s · música: {datos.get('musica', 'neutro') if pista else 'ninguna'}")
    return ruta_video


# --- Textos para publicar ----------------------------------------------------------

LIMITE_TITULO_YT = 100
SEPARADOR = "=" * 60


def _linea_credito(c, ingles: bool) -> str:
    if isinstance(c, str):  # crédito copiado de una descripción antigua
        return f"- {c}"
    if c.get("ia"):
        return f"- {c['archivo']} — {'AI-generated image (Pollinations)' if ingles else 'imagen generada con IA (Pollinations)'}"
    if c.get("ruta"):
        return f"- {c['archivo']} — {'own image' if ingles else 'imagen propia'}"
    tipo = ("(video) " if ingles else "(vídeo) ") if c.get("video") else ""
    return f"- {tipo}{c['archivo']} — {c['autor']} — {c['licencia']} — {c['pagina']}"


def _hashtags(datos: dict, maximo: int) -> str:
    """Los del guion + uno genérico del canal, sin repetir."""
    extra = ["#didyouknow", "#facts"] if datos.get("idioma") == "en" else ["#curiosidades", "#sabiasque"]
    etiquetas = []
    for h in [*datos.get("hashtags", []), *extra]:
        h = "#" + re.sub(r"[^\w]", "", str(h).lstrip("#"))
        if len(h) > 1 and h.lower() not in [e.lower() for e in etiquetas]:
            etiquetas.append(h)
    return " ".join(etiquetas[:maximo])


def _linea_diario(datos: dict, donde_es: str, donde_en: str) -> str:
    """«📓 Día 4 · El día 5, pronto en mi perfil» para los vídeos del formato diario ("" si no lo es)."""
    diario = datos.get("diario")
    if not diario:
        return ""
    dia = diario["dia"]
    if datos.get("idioma") == "en":
        return f"📓 Day {dia} · Day {dia + 1} coming soon {donde_en}"
    return f"📓 Día {dia} · El día {dia + 1}, pronto {donde_es}"


def _linea_video_ia(datos: dict) -> str:
    """Aviso obligatorio en los vídeos hechos con una IA de vídeo."""
    import video_ia
    ia = datos["video_ia"]
    nombre = video_ia.herramienta(ia.get("herramienta", ""))["nombre"]
    if datos.get("idioma") == "en":
        return f"🎬 AI-generated video ({nombre})" + (" with AI voices." if ia.get("voz") == "ia" else "; synthetic voice.")
    return f"🎬 Vídeo generado con IA ({nombre})" + (" con voces de IA." if ia.get("voz") == "ia" else "; voz sintética.")


def texto_publicacion(datos: dict, creditos: list, pista: str) -> str:
    """Lo que hay que pegar al subir el vídeo: un bloque para TikTok y otro para YouTube Shorts."""
    ingles = datos.get("idioma") == "en"
    titulo = datos.get("titulo", "").strip()
    titulo_sin_parte = re.sub(r"\s*\((Parte|Part) \d+/\d+\)\s*$", "", titulo)
    escenas = datos.get("escenas", [])
    entrada = escenas[0]["narracion"].strip() if escenas else ""
    serie = datos.get("serie") or {}
    linea_serie = ""
    if serie.get("total", 1) > 1:
        parte, total = serie["parte"], serie["total"]
        if ingles:
            linea_serie = f"📺 Part {parte}/{total}" + (f" · Part {parte + 1} on my profile" if parte < total else " · Final part")
        else:
            linea_serie = f"📺 Parte {parte}/{total}" + (f" · La parte {parte + 1}, en mi perfil" if parte < total
                                                        else " · Parte final")
    linea_serie = linea_serie or _linea_diario(datos, "en mi perfil", "on my profile")
    # TikTok: corto y directo. Los enlaces no son clicables, así que se nombran las fuentes.
    tiktok = [titulo_sin_parte, "", entrada]
    if linea_serie:
        tiktok += ["", linea_serie]
    pregunta = str(datos.get("pregunta") or "").strip()  # la del final del vídeo: da más comentarios que una genérica
    tiktok += ["", f"💬 {pregunta}" if pregunta else
               ("💬 Did you know? Tell me in the comments." if ingles else "💬 ¿Lo sabías? Te leo en comentarios."), ""]
    nombres_fuentes = ", ".join(f["titulo"] for f in datos.get("fuentes", []))
    if datos.get("actualidad"):
        medios = ", ".join(dict.fromkeys(f.get("medio") or f["titulo"] for f in datos.get("fuentes", [])))
        fecha_datos = datos["actualidad"].get("fecha_datos", "")
        tiktok.append(f"{'Sources' if ingles else 'Fuentes'}: {medios}"
                      + (f" ({'as of' if ingles else 'datos a'} {fecha_datos})" if fecha_datos else ""))
        tiktok.append("Images from Wikimedia Commons; those marked as archive do not show the events." if ingles
                      else "Imágenes de Wikimedia Commons; las marcadas como de archivo no muestran los hechos.")
    elif datos.get("video_ia"):
        tiktok.append(_linea_video_ia(datos))
    else:
        tiktok.append(f"{'Source' if ingles else 'Fuente'}: Wikipedia ({nombres_fuentes})" if nombres_fuentes else "")
    autores = set()
    for c in creditos:
        if isinstance(c, str):  # «archivo — autor — licencia — página»
            partes = c.split(" — ")
            autores.add(partes[1].strip() if len(partes) > 1 else "")
        else:
            autores.add(str(c.get("autor", "")).strip())
    autores = sorted(a for a in autores - {"", "Propia", "Autor desconocido", "Generada con IA (Pollinations)"}
                     if len(a) < 60)
    if any(isinstance(c, dict) and c.get("ia") for c in creditos):
        tiktok.append("Images: AI-generated (Pollinations)." if ingles else "Imágenes: generadas con IA (Pollinations).")
    elif creditos:
        tiktok.append(f"{'Images' if ingles else 'Imágenes'}: Wikimedia Commons / museos"
                      + (f" ({', '.join(autores[:6])})" if autores else "")
                      + (". Full credits on YouTube." if ingles else ". Créditos completos en YouTube."))
    tiktok += ["", _hashtags(datos, 5)]

    youtube = publicacion_youtube(datos, creditos, pista)

    aviso = ("Before publishing: check the facts and tick the AI-generated content label if the platform asks."
             if ingles else
             "Antes de publicar: comprueba los datos y marca la etiqueta de «contenido generado con IA» si la plataforma la pide.")
    return "\n".join([
        f"⚠ {aviso}", "",
        SEPARADOR, "TIKTOK — copy everything below as the caption" if ingles else "TIKTOK — copia todo esto en la descripción",
        SEPARADOR, *tiktok, "", "",
        SEPARADOR, "YOUTUBE SHORTS", SEPARADOR,
        "TITLE (paste in «Title»):" if ingles else "TÍTULO (pégalo en «Título»):", youtube["titulo"], "",
        "DESCRIPTION (paste in «Description»):" if ingles else "DESCRIPCIÓN (pégala en «Descripción»):",
        youtube["descripcion"],
    ]) + "\n"


def publicacion_youtube(datos: dict, creditos: list, pista: str) -> dict:
    """Título (máx. 100 caracteres, con #Shorts), descripción y etiquetas para YouTube Shorts.

    Lo usan el .txt de cada vídeo y la subida automática (subir_youtube.py): así son idénticos.
    """
    ingles = datos.get("idioma") == "en"
    titulo = datos.get("titulo", "").strip()
    escenas = datos.get("escenas", [])
    lineas = [escenas[0]["narracion"].strip() if escenas else ""]
    if str(datos.get("pregunta") or "").strip():
        lineas += ["", f"💬 {datos['pregunta'].strip()}"]
    serie = datos.get("serie") or {}
    if serie.get("total", 1) > 1:
        parte, total = serie["parte"], serie["total"]
        if ingles:
            lineas += ["", f"📺 Part {parte}/{total}" + (f" · Part {parte + 1} on my channel" if parte < total else " · Final part")]
        else:
            lineas += ["", f"📺 Parte {parte}/{total}" + (f" · La parte {parte + 1}, en mi canal" if parte < total
                                                           else " · Parte final")]
    if datos.get("diario"):
        lineas += ["", _linea_diario(datos, "en mi canal", "on my channel")]
    if datos.get("fuentes"):
        lineas += ["", "Sources:" if ingles else "Fuentes:", *[f"- {f['titulo']}: {f['url']}" for f in datos["fuentes"]]]
    if datos.get("actualidad"):
        fecha_datos = datos["actualidad"].get("fecha_datos", "")
        lineas += ["", (f"Information as of {fecha_datos}: the situation may change. Images from Wikimedia Commons; "
                        "those marked as archive do not show the events." if ingles else
                        f"Información a {fecha_datos}: la situación puede cambiar. Imágenes de Wikimedia Commons; las "
                        "marcadas como de archivo no muestran los hechos.")]
    if creditos:
        lineas += ["", "Images:" if ingles else "Imágenes:", *[_linea_credito(c, ingles) for c in creditos]]
    lineas.append("")
    if pista in musica.TONOS:
        lineas.append("Music: generated, royalty-free." if ingles else "Música: generada, sin derechos de autor.")
    elif pista:
        lineas.append(f"{'Music' if ingles else 'Música'}: {pista}")
    lineas += [_linea_video_ia(datos) if datos.get("video_ia") else ("Synthetic voice (AI)." if ingles
                                                                       else "Voz sintética (IA)."),
               "", _hashtags(datos, 8)]
    # YouTube rechaza «<» y «>» en título y descripción, y corta la descripción a 5.000 caracteres.
    descripcion = "\n".join(lineas).replace("<", "‹").replace(">", "›")[:4900]
    etiquetas, largo = [], 0
    for h in _hashtags(datos, 15).split():
        etiqueta = h.lstrip("#")
        if largo + len(etiqueta) + 1 > 450:  # las etiquetas suman 500 caracteres como mucho
            break
        etiquetas.append(etiqueta)
        largo += len(etiqueta) + 1
    titulo_yt = titulo.replace("<", "‹").replace(">", "›")[: LIMITE_TITULO_YT - len(" #Shorts")].rstrip() + " #Shorts"
    return {"titulo": titulo_yt, "descripcion": descripcion, "etiquetas": etiquetas}


def texto_guion(datos: dict, elegidas: dict = None) -> str:
    """El guion en texto legible: escenas, imagen de cada una, dudas y fuentes."""
    elegidas = elegidas or {}
    duracion = (datos.get("audio") or {}).get("duracion_total_s")
    lineas = [datos.get("titulo", ""), "=" * len(datos.get("titulo", "") or "x")]
    if datos.get("gancho"):
        lineas.append(f"Gancho: {datos['gancho']}")
    detalles = [f"idioma: {datos.get('idioma', '?')}", f"verificado: {'sí' if datos.get('verificado') else 'NO'}"]
    if duracion:
        detalles.append(f"duración: {duracion:.0f} s")
    if datos.get("modelo"):
        detalles.append(f"escrito con: {datos['modelo']}")
    lineas += [" · ".join(detalles), ""]
    for escena in datos.get("escenas", []):
        lineas.append(f"[{escena.get('numero')}] {escena.get('narracion', '').strip()}")
        eleccion = elegidas.get(escena.get("numero")) or elegidas.get(str(escena.get("numero"))) or {}
        imagen = (eleccion.get("imagen") or {}).get("archivo") if isinstance(eleccion, dict) else None
        lineas.append(f"    imagen: {imagen or escena.get('visual', '')}")
        lineas.append("")
    dudas = datos.get("sin_respaldo", [])
    if dudas:
        lineas.append("FRASES A REVISAR (el verificador no las encontró en las fuentes):")
        lineas += [f"- escena {d.get('escena')}: «{d.get('frase')}» → {d.get('motivo')}" for d in dudas]
        lineas.append("")
    lineas.append("Fuentes:")
    lineas += [f"- {f['titulo']}: {f['url']}" for f in datos.get("fuentes", [])]
    return "\n".join(lineas) + "\n"


def escribir_textos(video: Path, nombre: str, datos: dict, creditos: list, pista: str) -> None:
    """Junto al vídeo: <video>.txt (para publicar) y guiones/<video>.txt (el guion)."""
    ruta_descripcion(video).write_text(texto_publicacion(datos, creditos, pista), encoding="utf-8")
    ruta = ruta_guion_texto(video)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    elegidas = json.loads(elegidas_path(nombre).read_text(encoding="utf-8")) if elegidas_path(nombre).exists() else {}
    ruta.write_text(texto_guion(datos, elegidas), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Monta el vídeo vertical de cada guion con audio")
    parser.add_argument("carpetas", nargs="*", type=Path, help="carpetas de salida/audio (por defecto, todas)")
    parser.add_argument("--solo-verificados", action="store_true", help='omite guiones sin "verificado": true')
    parser.add_argument("--forzar", action="store_true", help="rehace el vídeo aunque ya exista")
    args = parser.parse_args(argv)

    musica.asegurar_pistas()
    migrar_videos_antiguos()
    carpetas = args.carpetas or sorted(p.parent for p in CARPETA_AUDIO.glob("*/escenas.json"))
    if not carpetas:
        print(f"[error] No hay audio en {CARPETA_AUDIO}. Ejecuta antes paso2_audio.py", file=sys.stderr)
        return 1

    hechos = omitidos = fallidos = 0
    for carpeta in carpetas:
        print(f"\n· {carpeta.name}")
        try:
            datos = leer_datos(carpeta)
            if not datos.get("verificado"):
                if args.solo_verificados:
                    print("  omitido: no está verificado")
                    omitidos += 1
                    continue
                print("  aviso: guion sin verificar; revísalo antes de publicar")
            print(f"  → {montar(carpeta, args.forzar)}")
            hechos += 1
        except (ValueError, KeyError, RuntimeError, OSError, requests.RequestException) as error:
            print(f"  error: {error}", file=sys.stderr)
            fallidos += 1
        except Exception as error:  # un fallo inesperado en un vídeo no debe parar los demás
            print(f"  error inesperado ({type(error).__name__}): {error}", file=sys.stderr)
            fallidos += 1

    print(f"\nVídeos: {hechos} · Omitidos: {omitidos} · Con error: {fallidos}")
    return 0 if fallidos == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
