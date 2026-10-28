"""Sube a YouTube Shorts los vídeos verificados, con su título, descripción y etiquetas.

Usa la API oficial de YouTube. Configuración, una sola vez (guía completa en menu/LEEME.txt):
  1. Crea un proyecto en Google Cloud, activa «YouTube Data API v3» y descarga las credenciales
     de tipo «App de escritorio» como  credenciales/client_secret.json
  2. Conecta tu canal:  python scripts/subir_youtube.py --conectar   (o desde el menú)
     Se abre Google en el navegador: inicias sesión TÚ y autorizas. Se guarda
     credenciales/token_youtube.json para no tener que repetirlo.

Solo se suben guiones marcados como verificados, y nunca dos veces el mismo (salvo --forzar).

Uso:
    python scripts/subir_youtube.py --conectar
    python scripts/subir_youtube.py <guion> [<guion> …]          # nombre del guion (sin .json) o su ruta
    python scripts/subir_youtube.py --pendientes                  # todos los verificados aún sin subir
    python scripts/subir_youtube.py <guion> --privacidad public   # private (por defecto) | unlisted | public
    python scripts/subir_youtube.py <guion> --publicar-el 2026-10-25T18:00   # programado (hora local)
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import paso3_video

load_dotenv()
for _flujo in (sys.stdout, sys.stderr):  # un «✔» en una consola que no es UTF-8 no debe romper nada
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(errors="replace")

CARPETA_CREDENCIALES = Path("credenciales")
CLIENTE = CARPETA_CREDENCIALES / "client_secret.json"
TOKEN = CARPETA_CREDENCIALES / "token_youtube.json"
PERMISOS = [
    "https://www.googleapis.com/auth/youtube.upload",    # subir vídeos y miniaturas
    "https://www.googleapis.com/auth/youtube.readonly",  # ver el nombre del canal conectado
    "https://www.googleapis.com/auth/youtube",           # cambiar la descripción del canal (--perfil)
]
# Retención (cuánta gente se queda y cuánto ve de cada vídeo). Se pide al conectar; las conexiones de antes no lo
# tienen y siguen subiendo igual: solo hace falta volver a conectar para ver la retención.
ANALITICA = "https://www.googleapis.com/auth/yt-analytics.readonly"
DESCRIPCION_CANAL = Path("marca/descripcion_youtube.txt")
PALABRAS_CLAVE_CANAL = Path("marca/palabras_clave_youtube.txt")
CATEGORIA_EDUCACION = "27"
PRIVACIDADES = ("private", "unlisted", "public")
TROZO = 8 * 1024 * 1024  # la subida va por partes de 8 MB (se puede reanudar si falla la red)
ESPERA_RED = 180  # segundos sin respuesta de YouTube antes de dar la conexión por perdida (antes: sin límite)


class SinConexion(Exception):
    """El canal no está conectado o faltan las credenciales."""


# --- Conexión con el canal -----------------------------------------------------------

def credenciales(interactivo: bool = False, nueva: bool = False) -> Credentials:
    """Credenciales guardadas (renovándolas si hace falta). Con `interactivo`, abre Google para autorizar.

    Con `nueva`, ignora la autorización guardada y vuelve a preguntar (para cambiar de canal o de cuenta).
    """
    permisos = PERMISOS + [ANALITICA] if tiene_analitica() else PERMISOS  # al renovar se conservan todos
    creds = Credentials.from_authorized_user_file(str(TOKEN), permisos) if TOKEN.exists() and not nueva else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except RefreshError:
            creds = None  # el permiso se retiró o caducó: hay que volver a conectar
    if not interactivo:
        raise SinConexion("El canal de YouTube no está conectado. Conéctalo en el menú (Ajustes → YouTube) "
                          "o con: python scripts/subir_youtube.py --conectar")
    if not CLIENTE.exists():
        raise SinConexion(f"Falta {CLIENTE}: descárgalo de Google Cloud (mira la guía en menu/LEEME.txt).")
    flujo = InstalledAppFlow.from_client_secrets_file(str(CLIENTE), PERMISOS + [ANALITICA])
    print("Se abre Google en tu navegador: inicia sesión con la cuenta del canal y autoriza el acceso.", flush=True)
    creds = flujo.run_local_server(
        # «select_account»: Google siempre pregunta qué cuenta usar (ahí aparecen los canales de marca).
        port=0, open_browser=True, prompt="select_account consent",
        authorization_prompt_message="Si no se abre solo, entra en esta dirección: {url}",
        success_message="Canal conectado. Ya puedes cerrar esta pestaña y volver al menú.",
    )
    CARPETA_CREDENCIALES.mkdir(exist_ok=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def tiene_analitica() -> bool:
    """¿La conexión guardada incluye el permiso de ver la retención?"""
    try:
        return ANALITICA in json.loads(TOKEN.read_text(encoding="utf-8")).get("scopes", [])
    except (OSError, ValueError):
        return False


AVISO_SIN_CANAL = ("La cuenta autorizada no tiene canal de YouTube. Crea el canal en youtube.com (foto de perfil → "
                   "«Crear un canal») o, si tu canal es una cuenta de marca, vuelve a conectar y elige el canal "
                   "(no tu cuenta personal) cuando Google pregunte qué cuenta usar.")


def canal_conectado():
    """{"id", "nombre"} del canal conectado; {"id": None} si la cuenta no tiene canal; None si no hay conexión."""
    try:
        youtube = build("youtube", "v3", credentials=credenciales(), cache_discovery=False)
        elementos = youtube.channels().list(part="snippet", mine=True).execute().get("items", [])
    except (SinConexion, HttpError, OSError):
        return None
    if not elementos:
        return {"id": None, "nombre": None}
    return {"id": elementos[0]["id"], "nombre": elementos[0]["snippet"]["title"]}


def actualizar_perfil() -> str:
    """Pone en el canal la descripción y las palabras clave de la carpeta marca/. Devuelve el nombre del canal.

    La foto de perfil NO se puede cambiar por la API de YouTube: se cambia en YouTube Studio.
    """
    descripcion = DESCRIPCION_CANAL.read_text(encoding="utf-8").strip()
    palabras = PALABRAS_CLAVE_CANAL.read_text(encoding="utf-8").strip() if PALABRAS_CLAVE_CANAL.exists() else ""
    youtube = build("youtube", "v3", credentials=credenciales(), cache_discovery=False)
    elementos = youtube.channels().list(part="brandingSettings,snippet", mine=True).execute().get("items", [])
    if not elementos:
        raise SinConexion(AVISO_SIN_CANAL)
    canal = elementos[0]
    ajustes = canal.get("brandingSettings", {})  # se reenvía lo que ya tenía para no borrar nada más
    ajustes.setdefault("channel", {})
    ajustes["channel"]["description"] = descripcion.replace("<", "‹").replace(">", "›")[:1000]
    if palabras:
        ajustes["channel"]["keywords"] = palabras[:500]
    ajustes["channel"].setdefault("defaultLanguage", "es")
    youtube.channels().update(part="brandingSettings", body={"id": canal["id"], "brandingSettings": ajustes}).execute()
    return canal["snippet"]["title"]


def desconectar() -> None:
    if TOKEN.exists():
        TOKEN.unlink()


# --- Subida ---------------------------------------------------------------------------

def _ruta_guion(guion: str) -> Path:
    ruta = Path(guion)
    if ruta.suffix != ".json":
        ruta = paso3_video.ruta_guion_de(guion)
    if not ruta.exists():
        raise ValueError(f"no existe el guion {ruta}")
    return ruta


def _hora_utc(texto: str) -> str:
    """«2026-10-25T18:00» (hora local) → «2026-10-25T16:00:00Z» (lo que pide YouTube)."""
    local = datetime.fromisoformat(texto)
    if local.tzinfo is None:
        local = local.astimezone()  # zona horaria del ordenador
    if local <= datetime.now(timezone.utc):
        raise ValueError("la fecha de publicación tiene que ser futura")
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _youtube_con_limite():
    """Cliente de YouTube que no se queda colgado para siempre si la conexión se queda muda."""
    import google_auth_httplib2
    from googleapiclient.http import build_http
    # build_http, y no un httplib2.Http a secas: YouTube contesta 308 a cada trozo de una subida reanudable y
    # build_http hace que no se tome como redirección. Sin eso, el vídeo se queda a medias y «procesándose» para siempre.
    conexion = build_http()
    conexion.timeout = ESPERA_RED
    http = google_auth_httplib2.AuthorizedHttp(credenciales(), http=conexion)
    return build("youtube", "v3", http=http, cache_discovery=False)


def _buscar_recien_subido(titulo: str, desde: datetime):
    """Id del vídeo con ese título subido después de `desde`, o None.

    Sirve cuando la conexión se corta justo al terminar: YouTube puede haber creado el vídeo aunque no nos
    haya llegado la respuesta, y volver a subirlo dejaría un duplicado.
    """
    import time
    for intento in range(4):  # el vídeo tarda unos segundos en aparecer en la lista del canal
        if intento:
            time.sleep(15)
        try:
            youtube = _youtube_con_limite()
            canal = youtube.channels().list(part="contentDetails", mine=True).execute()
            lista = canal["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            elementos = youtube.playlistItems().list(part="snippet", playlistId=lista, maxResults=10).execute()
        except Exception:  # noqa: BLE001 — sin conexión todavía: se reintenta
            continue
        for e in elementos.get("items", []):
            subido = datetime.fromisoformat(e["snippet"]["publishedAt"].replace("Z", "+00:00"))
            if e["snippet"]["title"] == titulo and subido >= desde - timedelta(minutes=2):
                return e["snippet"]["resourceId"]["videoId"]
    return None


def _explicar(error: HttpError) -> str:
    """Mensajes de error de YouTube en cristiano."""
    motivo = ""
    try:
        motivo = json.loads(error.content.decode())["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError):
        pass
    explicaciones = {
        "quotaExceeded": "se ha gastado el cupo diario gratuito de la API (unos 6 vídeos al día). Vuelve a probar mañana.",
        "uploadLimitExceeded": "YouTube ha limitado las subidas de tu canal por hoy. Vuelve a probar mañana.",
        "forbidden": "YouTube no permite esta acción con tu cuenta (¿canal sin verificar por teléfono?).",
        "youtubeSignupRequired": "esta cuenta de Google no tiene canal de YouTube: créalo primero en youtube.com.",
        "invalidTitle": "el título no es válido.",
        "invalidDescription": "la descripción no es válida.",
    }
    return explicaciones.get(motivo, f"YouTube respondió {error.resp.status} ({motivo or 'sin detalle'}).")


def subir(guion: str, privacidad: str = "private", publicar_el: str = "", forzar: bool = False,
          borrador: bool = False) -> dict:
    """Sube el vídeo de un guion verificado y apunta en el guion el enlace. Devuelve {"id", "url", …}.

    Con `borrador` se puede subir sin verificar, pero siempre en privado y sin programar:
    queda en YouTube Studio para revisarlo antes de publicarlo.
    """
    ruta = _ruta_guion(guion)
    nombre = ruta.stem
    datos_guion = json.loads(ruta.read_text(encoding="utf-8"))
    if borrador and not datos_guion.get("verificado"):
        privacidad, publicar_el = "private", ""
        print("  borrador: sin verificar, se sube en PRIVADO para revisarlo en YouTube Studio")
    elif not datos_guion.get("verificado"):
        raise ValueError("el guion no está verificado: revísalo y márcalo como verificado antes de subirlo")
    if datos_guion.get("youtube") and not forzar:
        print(f"  ya estaba subido: {datos_guion['youtube']['url']} (usa --forzar para subirlo otra vez)")
        return datos_guion["youtube"]
    video = Path(datos_guion.get("video") or "-")
    if not video.exists():
        raise ValueError("todavía no tiene vídeo: genera primero el audio y el vídeo")

    audio = paso3_video.CARPETA_AUDIO / nombre
    datos = paso3_video.leer_datos(audio) if (audio / "escenas.json").exists() else datos_guion
    creditos = paso3_video._creditos_guardados(nombre)
    pista = datos_guion.get("musica", "neutro") if paso3_video.elegidas_path(nombre).exists() else ""
    publicacion = paso3_video.publicacion_youtube(datos, creditos, pista)

    estado = {
        "privacyStatus": "private" if publicar_el else privacidad,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,  # voz e imágenes montadas con IA: YouTube pide declararlo
    }
    if publicar_el:
        estado["publishAt"] = _hora_utc(publicar_el)  # se hace público solo a esa hora
    idioma = datos_guion.get("idioma", "es")
    cuerpo = {
        "snippet": {
            "title": publicacion["titulo"],
            "description": publicacion["descripcion"],
            "tags": publicacion["etiquetas"],
            "categoryId": CATEGORIA_EDUCACION,
            "defaultLanguage": idioma,
            "defaultAudioLanguage": idioma,
        },
        "status": estado,
    }

    youtube = _youtube_con_limite()
    print(f"  subiendo {video.name} ({video.stat().st_size // (1024 * 1024)} MB)…", flush=True)
    peticion = youtube.videos().insert(
        part="snippet,status", body=cuerpo,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=TROZO, resumable=True),
    )
    inicio = datetime.now(timezone.utc)
    respuesta = None
    try:
        while respuesta is None:
            progreso, respuesta = peticion.next_chunk()
            if progreso:
                print(f"  {progreso.progress():.0%}", flush=True)
    except HttpError:
        raise  # YouTube ha contestado que no: no hay vídeo
    except Exception as error:  # conexión cortada o muda: ¿llegó a crearse?
        encontrado = _buscar_recien_subido(cuerpo["snippet"]["title"], inicio)
        if not encontrado:
            raise
        print(f"  la conexión se cortó al terminar ({error}), pero el vídeo sí llegó a YouTube", flush=True)
        respuesta = {"id": encontrado, "status": {"privacyStatus": estado["privacyStatus"]}}
    id_video = respuesta["id"]
    privacidad_final = respuesta.get("status", {}).get("privacyStatus", estado["privacyStatus"])
    # Lo primero, apuntarlo: si algo falla a partir de aquí (miniatura, un mensaje…), el vídeo YA está en YouTube
    # y no debe volver a subirse.
    resultado = {
        "id": id_video,
        "url": f"https://youtube.com/shorts/{id_video}",
        "privacidad": privacidad_final,
        "publicar_el": publicar_el or None,
        "subido": datetime.now().isoformat(timespec="seconds"),
        "borrador_sin_verificar": not datos_guion.get("verificado"),
    }
    datos_guion = json.loads(ruta.read_text(encoding="utf-8"))  # releer por si cambió mientras subía
    datos_guion["youtube"] = resultado
    ruta.write_text(json.dumps(datos_guion, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✔ subido: https://youtube.com/shorts/{id_video} ({privacidad_final})")
    if privacidad_final != estado["privacyStatus"]:
        print("  aviso: YouTube lo ha dejado en privado porque tu proyecto de Google Cloud aún no está verificado. "
              "Cámbialo a público en YouTube Studio (o solicita la verificación del proyecto).")

    miniatura = paso3_video.ruta_miniatura(video)
    if miniatura.exists():
        try:
            youtube.thumbnails().set(videoId=id_video, media_body=MediaFileUpload(str(miniatura))).execute()
            print("  miniatura puesta")
        except HttpError:
            # En los Shorts la portada se elige desde la app; la API solo deja si el canal está verificado.
            print("  aviso: YouTube no ha aceptado la miniatura (normal en Shorts o en canales sin verificar)")

    return resultado


def cambiar_publicacion(id_video: str, privacidad: str = "public", publicar_el: str = "") -> dict:
    """Cambia cuándo y cómo se publica un vídeo ya subido.

    - con `publicar_el` (hora local): queda privado y YouTube lo publica solo a esa hora;
    - sin ella: pasa ya a `privacidad` (public = publicarlo ahora, private = retirarlo).
    Devuelve el estado nuevo. Se reenvían los demás ajustes de estado tal cual: si no, YouTube los reinicia.
    """
    youtube = build("youtube", "v3", credentials=credenciales(), cache_discovery=False)
    respuesta = youtube.videos().list(part="status", id=id_video).execute()
    if not respuesta.get("items"):
        raise ValueError("ese vídeo ya no está en tu canal de YouTube")
    actual = respuesta["items"][0]["status"]
    editables = ("embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids", "containsSyntheticMedia")
    estado = {k: actual[k] for k in editables if k in actual}
    if publicar_el:
        estado.update(privacyStatus="private", publishAt=_hora_utc(publicar_el))
    else:
        estado["privacyStatus"] = privacidad
    return youtube.videos().update(part="status", body={"id": id_video, "status": estado}).execute()["status"]


ESTADISTICAS = Path("salida/estadisticas_youtube.json")


def actualizar_estadisticas() -> dict:
    """Pide a YouTube las vistas, «me gusta» y comentarios de todos los vídeos subidos (1 unidad de cuota por
    cada 50) y los guarda en salida/estadisticas_youtube.json. Devuelve {id: {vistas, me_gusta, comentarios}}."""
    ids = []
    for ruta in paso3_video.CARPETA_GUIONES.glob("*.json"):
        try:
            id_video = (json.loads(ruta.read_text(encoding="utf-8")).get("youtube") or {}).get("id")
        except (OSError, ValueError):
            continue
        if id_video:
            ids.append(id_video)
    if not ids:
        return {}
    youtube = build("youtube", "v3", credentials=credenciales(), cache_discovery=False)
    estadisticas = {}
    for i in range(0, len(ids), 50):
        respuesta = youtube.videos().list(part="statistics", id=",".join(ids[i:i + 50])).execute()
        for video in respuesta.get("items", []):
            datos = video.get("statistics", {})
            estadisticas[video["id"]] = {"vistas": int(datos.get("viewCount", 0)),
                                         "me_gusta": int(datos.get("likeCount", 0)),
                                         "comentarios": int(datos.get("commentCount", 0))}
    ESTADISTICAS.parent.mkdir(parents=True, exist_ok=True)
    ESTADISTICAS.write_text(json.dumps({"actualizado": datetime.now().isoformat(timespec="seconds"),
                                        "videos": estadisticas}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        actualizar_retencion()  # cada pocas horas como mucho
    except Exception as error:  # noqa: BLE001 — la retención es un extra: que no impida tener las vistas
        print(f"  aviso: no se ha podido traer la retención: {error}")
    return estadisticas


RETENCION = Path("salida/retencion_youtube.json")
HORAS_RETENCION = 6  # YouTube Analytics va con uno o dos días de retraso: no hace falta pedirla más a menudo


def actualizar_retencion(forzar: bool = False) -> dict:
    """Pide a YouTube Analytics, por vídeo, cuánta gente se queda a verlo (frente a la que desliza) y cuánto ve de
    media. Lo guarda en salida/retencion_youtube.json. Sin el permiso, apunta que hay que volver a conectar."""
    anterior = retencion()
    if not forzar and anterior.get("actualizado") and datetime.now() - datetime.fromisoformat(
            anterior["actualizado"]) < timedelta(hours=HORAS_RETENCION):
        return anterior
    resultado = {"actualizado": datetime.now().isoformat(timespec="seconds"), "videos": anterior.get("videos", {})}
    if not tiene_analitica():
        resultado["error"] = "sin_permiso"
    else:
        analitica = build("youtubeAnalytics", "v2", credentials=credenciales(), cache_discovery=False)
        consulta = dict(ids="channel==MINE", startDate="2020-01-01", endDate=datetime.now().strftime("%Y-%m-%d"),
                        dimensions="video", sort="-views", maxResults=200)
        try:
            # engagedViews: vistas en las que no se deslizó al empezar (lo que Studio llama «se quedaron a verlo»).
            respuesta = analitica.reports().query(
                metrics="views,engagedViews,averageViewDuration,averageViewPercentage", **consulta).execute()
        except HttpError as error:
            if "accessNotConfigured" in str(error) or "has not been used" in str(error):
                resultado["error"] = "api_apagada"
                respuesta = None
            else:  # por si la métrica engagedViews no está disponible: sin ella
                respuesta = analitica.reports().query(
                    metrics="views,averageViewDuration,averageViewPercentage", **consulta).execute()
        if respuesta is not None:
            columnas = [c["name"] for c in respuesta.get("columnHeaders", [])]
            videos = {}
            for fila in respuesta.get("rows", []):
                d = dict(zip(columnas, fila))
                vistas = int(d.get("views") or 0)
                videos[d["video"]] = {
                    "vistas": vistas,
                    "se_quedan": round(100 * d["engagedViews"] / vistas) if vistas and "engagedViews" in d else None,
                    "visto_pct": round(d.get("averageViewPercentage") or 0),
                    "segundos": round(d.get("averageViewDuration") or 0),
                }
            resultado["videos"] = videos
    RETENCION.parent.mkdir(parents=True, exist_ok=True)
    RETENCION.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return resultado


def retencion() -> dict:
    """La última retención guardada: {"actualizado", "videos": {id: {se_quedan, visto_pct, segundos}}, "error"?}."""
    try:
        return json.loads(RETENCION.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"actualizado": "", "videos": {}}


def estadisticas() -> dict:
    """Las últimas estadísticas guardadas: {"actualizado": «…», "videos": {id: {…}}} (vacío si aún no hay).

    Cada vídeo lleva también su retención, si se tiene: «se_quedan» (%), «visto_pct» (%) y «segundos» de media.
    """
    try:
        datos = json.loads(ESTADISTICAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"actualizado": "", "videos": {}}
    for id_video, ret in retencion().get("videos", {}).items():
        if id_video in datos["videos"]:
            # «vistas_analitica»: las vistas de las que YouTube ya tiene retención (van con días de retraso)
            datos["videos"][id_video].update({k: v for k, v in ret.items() if k != "vistas"},
                                             vistas_analitica=ret.get("vistas", 0))
    return datos


def pendientes() -> list:
    """Guiones verificados, con vídeo y aún sin subir."""
    lista = []
    for ruta in sorted(paso3_video.CARPETA_GUIONES.glob("*.json")):
        guion = json.loads(ruta.read_text(encoding="utf-8"))
        if guion.get("verificado") and not guion.get("youtube") and Path(guion.get("video") or "-").exists():
            lista.append(ruta.stem)
    return lista


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sube a YouTube Shorts los vídeos verificados")
    parser.add_argument("guiones", nargs="*", help="nombres de guion (sin .json) o rutas")
    parser.add_argument("--conectar", action="store_true", help="conecta (o reconecta) tu canal de YouTube")
    parser.add_argument("--pendientes", action="store_true", help="sube todos los verificados aún sin subir")
    parser.add_argument("--privacidad", choices=PRIVACIDADES, default=os.getenv("YT_PRIVACIDAD") or "private")
    parser.add_argument("--publicar-el", default="", help="AAAA-MM-DDTHH:MM (hora local) para programarlo")
    parser.add_argument("--cada", type=float, default=0,
                        help="con varios guiones y --publicar-el: horas entre la publicación de uno y el siguiente")
    parser.add_argument("--forzar", action="store_true", help="súbelo aunque ya se hubiera subido")
    parser.add_argument("--perfil", action="store_true",
                        help="pone en el canal la descripción y palabras clave de la carpeta marca/")
    parser.add_argument("--borrador", action="store_true",
                        help="permite subir sin verificar, siempre en privado (para revisarlo en YouTube Studio)")
    args = parser.parse_args(argv)

    try:
        if args.conectar:
            credenciales(interactivo=True, nueva=True)  # siempre abre Google: así se puede cambiar de canal
            info = canal_conectado()
            if info and info["id"]:
                print(f"✔ Canal conectado: {info['nombre']}")
                return 0
            print(f"⚠ {AVISO_SIN_CANAL}" if info else "⚠ Conectado, pero no he podido comprobar el canal.")
            return 2
        if args.perfil:
            try:
                nombre = actualizar_perfil()
            except HttpError as error:
                if error.resp.status == 403:  # autorización antigua sin el permiso de gestionar el canal
                    print("Hace falta un permiso más: se abre Google para autorizarlo (elige el canal).", flush=True)
                    credenciales(interactivo=True, nueva=True)
                    nombre = actualizar_perfil()
                else:
                    raise
            print(f"✔ Descripción y palabras clave puestas en el canal «{nombre}».")
            print("  La foto de perfil se cambia en YouTube Studio → Personalización → Imagen de marca.")
            return 0
        canal = canal_conectado()
        if canal and not canal["id"]:
            raise SinConexion(AVISO_SIN_CANAL)
        guiones = args.guiones or (pendientes() if args.pendientes else [])
        if not guiones:
            print("No hay nada que subir (indica un guion o usa --pendientes).")
            return 0
        credenciales()  # comprueba la conexión antes de empezar
    except SinConexion as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1

    subidos = fallidos = 0
    for orden, guion in enumerate(guiones):
        publicar_el = args.publicar_el
        if publicar_el and args.cada:  # escalonados y en el orden dado: el primero a esa hora, luego uno cada X h
            hora = datetime.fromisoformat(publicar_el) + timedelta(hours=args.cada * orden)
            publicar_el = hora.strftime("%Y-%m-%dT%H:%M")
        print(f"\n· {guion}" + (f"  (se publica el {publicar_el.replace('T', ' a las ')})" if publicar_el else ""))
        try:
            subir(guion, args.privacidad, publicar_el, args.forzar, args.borrador)
            subidos += 1
        except HttpError as error:
            print(f"  error: {_explicar(error)}", file=sys.stderr)
            fallidos += 1
            if "cupo" in _explicar(error) or "limitado" in _explicar(error):
                break  # no tiene sentido seguir hoy
        except (ValueError, SinConexion, OSError) as error:
            print(f"  error: {error}", file=sys.stderr)
            fallidos += 1

    print(f"\nSubidos: {subidos} · Con error: {fallidos}")
    return 0 if fallidos == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
