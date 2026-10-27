"""Publicar los vídeos como Reels en Instagram (API de Instagram con inicio de sesión de Facebook).

Requisitos (una vez): cuenta de Instagram profesional, conectada a una página de Facebook, y una app de Meta con los
permisos instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement y business_management.

Conexión: el identificador y la clave secreta de la app y un token de usuario (del Explorador de la API Graph). El
token se cambia por uno de larga duración y, con él, por el de la página, que no caduca: es el que se guarda.

Publicar: se crea un contenedor de Reel con subida reanudable, se manda el archivo a rupload.facebook.com (no hace falta
servidor público), se espera a que Instagram lo procese y se publica. Instagram no deja programar por la API: la hora la
pone la cola de Programados.

Uso a mano:
    python scripts\\instagram.py --estado
    python scripts\\instagram.py --publicar NOMBRE_DEL_GUION
"""
import json
import sys
import time
from pathlib import Path

import requests

VERSION = "v21.0"
GRAPH = f"https://graph.facebook.com/{VERSION}"
RUPLOAD = f"https://rupload.facebook.com/ig-api-upload/{VERSION}"
CONFIG = Path("credenciales/instagram.json")  # credenciales/ nunca va al repositorio
LIMITE_TEXTO = 2200       # caracteres de la descripción de un Reel
LIMITE_HASHTAGS = 30
ESPERA_PROCESADO = 600    # s como mucho esperando a que Instagram procese el vídeo


class ErrorInstagram(Exception):
    pass


def _json(respuesta: requests.Response) -> dict:
    try:
        datos = respuesta.json()
    except ValueError:
        raise ErrorInstagram(f"respuesta inesperada de Meta ({respuesta.status_code})")
    if respuesta.status_code >= 400 or "error" in datos:
        error = datos.get("error") or {}
        raise ErrorInstagram(error.get("error_user_msg") or error.get("message") or f"error {respuesta.status_code}")
    return datos


def leer_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_config(datos: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def conectado() -> bool:
    c = leer_config()
    return bool(c.get("token_pagina") and c.get("ig_id"))


def guardar_app(app_id: str, app_secreto: str) -> None:
    """Identificador y clave de la app de Meta (la clave solo se cambia si se escribe una nueva)."""
    c = leer_config()
    if app_id.strip():
        c["app_id"] = app_id.strip()
    if app_secreto.strip():
        c["app_secreto"] = app_secreto.strip()
    _guardar_config(c)


def conectar(token_usuario: str) -> dict:
    """Cambia el token de usuario (corto) por el de la página con Instagram (no caduca) y lo guarda."""
    c = leer_config()
    if not c.get("app_id") or not c.get("app_secreto"):
        raise ErrorInstagram("primero guarda el identificador y la clave secreta de la app de Meta")
    largo = _json(requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": c["app_id"], "client_secret": c["app_secreto"],
        "fb_exchange_token": token_usuario.strip()}, timeout=30))["access_token"]
    paginas = _json(requests.get(f"{GRAPH}/me/accounts", params={
        "fields": "name,access_token,instagram_business_account{id,username}", "access_token": largo},
        timeout=30)).get("data", [])
    con_instagram = [p for p in paginas if p.get("instagram_business_account")]
    if not con_instagram:
        nombres = ", ".join(p.get("name", "?") for p in paginas) or "ninguna"
        raise ErrorInstagram(f"ninguna de tus páginas de Facebook ({nombres}) tiene una cuenta de Instagram profesional "
                             "conectada, o no diste permiso a la página al generar el token")
    pagina = con_instagram[0]
    cuenta = pagina["instagram_business_account"]
    c.update(token_pagina=pagina["access_token"], pagina=pagina.get("name", ""), ig_id=cuenta["id"],
             usuario=cuenta.get("username", ""), conectado=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _guardar_config(c)
    return {"usuario": c["usuario"], "pagina": c["pagina"]}


def desconectar() -> None:
    c = leer_config()
    for clave in ("token_pagina", "ig_id", "usuario", "pagina", "conectado"):
        c.pop(clave, None)
    _guardar_config(c)


def cuenta() -> dict:
    """Nombre, seguidores y publicaciones de la cuenta conectada (para Ajustes)."""
    c = leer_config()
    return _json(requests.get(f"{GRAPH}/{c['ig_id']}", params={
        "fields": "username,followers_count,media_count", "access_token": c["token_pagina"]}, timeout=30))


def texto_desde_txt(ruta_txt: Path) -> str:
    """La descripción del Reel: el bloque de TikTok del .txt del vídeo (texto, fuentes y hashtags)."""
    try:
        texto = ruta_txt.read_text(encoding="utf-8")
    except OSError:
        return ""
    trozos = texto.split("=" * 60)
    # [aviso, «TIKTOK — …», bloque de TikTok, «YOUTUBE SHORTS», bloque de YouTube…]
    bloque = trozos[2].strip() if len(trozos) > 2 else texto.strip()
    # Los créditos de las imágenes se quedan (la licencia obliga a citar a los autores); sobra la referencia a YouTube.
    bloque = bloque.replace(" Créditos completos en YouTube.", "").replace(" Full credits on YouTube.", "")
    # Instagram admite como mucho 30 hashtags y 2200 caracteres.
    vistos, palabras = 0, []
    for palabra in bloque.split(" "):
        if palabra.startswith("#"):
            vistos += 1
            if vistos > LIMITE_HASHTAGS:
                continue
        palabras.append(palabra)
    return " ".join(palabras)[:LIMITE_TEXTO]


def publicar_reel(video: Path, texto: str) -> dict:
    """Sube y publica un Reel. Devuelve {"id", "url"}."""
    c = leer_config()
    if not conectado():
        raise ErrorInstagram("Instagram no está conectado (Ajustes → Instagram)")
    token, ig = c["token_pagina"], c["ig_id"]
    contenedor = _json(requests.post(f"{GRAPH}/{ig}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": texto, "share_to_feed": "true",
        "access_token": token}, timeout=60))["id"]
    tamano = video.stat().st_size
    with open(video, "rb") as archivo:
        _json(requests.post(f"{RUPLOAD}/{contenedor}", data=archivo, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(tamano)}))
    inicio = time.time()
    while True:
        estado = _json(requests.get(f"{GRAPH}/{contenedor}", params={
            "fields": "status_code,status", "access_token": token}, timeout=30))
        if estado.get("status_code") == "FINISHED":
            break
        if estado.get("status_code") in ("ERROR", "EXPIRED"):
            raise ErrorInstagram(f"Instagram no ha podido procesar el vídeo: {estado.get('status', estado['status_code'])}")
        if time.time() - inicio > ESPERA_PROCESADO:
            raise ErrorInstagram("Instagram está tardando demasiado en procesar el vídeo; se reintentará")
        time.sleep(15)
    publicado = _json(requests.post(f"{GRAPH}/{ig}/media_publish", data={
        "creation_id": contenedor, "access_token": token}, timeout=60))["id"]
    enlace = _json(requests.get(f"{GRAPH}/{publicado}", params={
        "fields": "permalink", "access_token": token}, timeout=30)).get("permalink", "")
    return {"id": publicado, "url": enlace}


def publicar_guion(nombre: str) -> dict:
    """Publica en Instagram el vídeo de un guion (con el texto de su .txt) y lo apunta en el guion."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import paso3_video
    ruta = paso3_video.CARPETA_GUIONES / f"{nombre}.json"
    guion = json.loads(ruta.read_text(encoding="utf-8"))
    if (guion.get("instagram") or {}).get("id"):
        return guion["instagram"]  # ya publicado: no se repite
    video = Path(guion.get("video") or "-")
    if not video.exists():
        raise ErrorInstagram("el guion no tiene vídeo")
    resultado = publicar_reel(video, texto_desde_txt(paso3_video.ruta_descripcion(video)))
    guion = json.loads(ruta.read_text(encoding="utf-8"))  # releer por si cambió mientras subía
    guion["instagram"] = {**resultado, "publicado": time.strftime("%Y-%m-%dT%H:%M:%S")}
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    return guion["instagram"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--publicar" in sys.argv:
        print(publicar_guion(sys.argv[sys.argv.index("--publicar") + 1]))
    else:
        c = leer_config()
        print("conectado:", conectado(), "·", c.get("usuario", ""), "·", c.get("pagina", ""))
