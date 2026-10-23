"""Borra un vídeo y todo lo que se generó para él (a la Papelera de reciclaje de Windows, para poder recuperarlo).

Lo que se borra de un guion:
  - el guion (salida/guiones/<nombre>.json)
  - la voz y los subtítulos (salida/audio/<nombre>/)
  - las escenas montadas, las imágenes candidatas y las elegidas (salida/_trabajo/<nombre>/)
  - las imágenes generadas con IA (salida/imagenes_ia/<nombre>/) y las que subiste tú (salida/imagenes_propias/)
  - el vídeo, su texto para publicar, su miniatura y el texto del guion (salida/videos/<Tema>/…);
    si la carpeta del tema se queda vacía, también la carpeta
  - su entrada en «Programados» y en los recordatorios de TikTok
Las cachés compartidas (imágenes descargadas, Wikipedia) no se tocan: las usan otros vídeos.

En YouTube solo se borra si se pide expresamente (no se puede deshacer).

Uso:
    python borrar.py <guion> [--youtube]
"""
import json
import sys
from pathlib import Path

from send2trash import send2trash

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "salida"
GUIONES = SALIDA / "guiones"
TIKTOK = SALIDA / "_trabajo" / "tiktok_pendientes.json"


def _guion(nombre: str) -> dict:
    ruta = (GUIONES / f"{nombre}.json").resolve()
    if ruta.parent != GUIONES.resolve() or not ruta.exists():
        raise ValueError("ese guion no existe")
    return json.loads(ruta.read_text(encoding="utf-8"))


def archivos(nombre: str) -> list:
    """Archivos y carpetas de un guion que existen ahora mismo (lo que se borraría)."""
    guion = _guion(nombre)
    rutas = [
        GUIONES / f"{nombre}.json",
        SALIDA / "audio" / nombre,
        SALIDA / "_trabajo" / nombre,
        SALIDA / "imagenes_ia" / nombre,
        *sorted((SALIDA / "imagenes_propias").glob(f"{nombre}_escena*")),
    ]
    if guion.get("video"):
        video = (RAIZ / guion["video"]).resolve()
        if (SALIDA / "videos").resolve() in video.parents:  # nunca fuera de la carpeta de vídeos
            rutas += [video, video.with_suffix(".txt"), video.with_suffix(".jpg"),
                      video.parent / "guiones" / f"{video.stem}.txt"]
    return [r for r in rutas if r.exists()]


def resumen(nombre: str) -> dict:
    """Lo que hay que saber antes de borrar: archivos, estado en YouTube y en la cola."""
    import programados
    guion = _guion(nombre)
    en_cola = programados.buscar(programados.leer(), nombre)
    yt = guion.get("youtube") or {}
    youtube_id = yt.get("id") or (en_cola or {}).get("youtube_id")
    hora = (en_cola or {}).get("hora") or yt.get("publicar_el")
    from datetime import datetime
    pendiente_de_publicar = bool(youtube_id and hora and datetime.fromisoformat(hora[:16]) > datetime.now())
    return {
        "titulo": guion.get("titulo", nombre),
        "archivos": [r.relative_to(RAIZ).as_posix() + ("/" if r.is_dir() else "") for r in archivos(nombre)],
        "youtube_id": youtube_id,
        "youtube_url": yt.get("url") or (en_cola or {}).get("url"),
        "programado": bool(en_cola),
        "subiendo": bool(en_cola and en_cola["estado"] == "subiendo"),
        # Programado en YouTube y aún sin publicar: si no se borra allí, se publicaría igualmente.
        "pendiente_de_publicar": pendiente_de_publicar,
    }


def borrar(nombre: str, de_youtube: bool = False) -> str:
    """Borra el guion y todo lo suyo. Devuelve un resumen de lo hecho."""
    import programados
    info = resumen(nombre)
    if info["subiendo"]:
        raise ValueError("se está subiendo a YouTube ahora mismo: espera a que termine")

    hecho = []
    if de_youtube and info["youtube_id"]:
        import subir_youtube
        from googleapiclient.errors import HttpError
        youtube = subir_youtube.build("youtube", "v3", credentials=subir_youtube.credenciales(),
                                      cache_discovery=False)
        try:
            youtube.videos().delete(id=info["youtube_id"]).execute()
            hecho.append("borrado de YouTube")
        except HttpError as error:
            if error.resp.status != 404:  # 404: ya no estaba
                raise ValueError(f"YouTube no ha dejado borrarlo: {subir_youtube._explicar(error)}") from error

    # Fuera de la cola de programados y de los recordatorios de TikTok
    datos = programados.leer()
    if programados.buscar(datos, nombre):
        datos["videos"] = [v for v in datos["videos"] if v["nombre"] != nombre]
        programados._guardar_y_reprogramar(datos)
        hecho.append("quitado de Programados")
    if TIKTOK.exists():
        pendientes = json.loads(TIKTOK.read_text(encoding="utf-8"))
        quedan = [p for p in pendientes if p.get("nombre") != nombre]
        if len(quedan) != len(pendientes):
            TIKTOK.write_text(json.dumps(quedan, ensure_ascii=False, indent=2), encoding="utf-8")

    # Archivos a la papelera (el guion el último: si algo falla, se puede volver a intentar)
    rutas = archivos(nombre)
    guion = GUIONES / f"{nombre}.json"
    carpetas_video = {r.parent for r in rutas if r.suffix == ".mp4"}
    for ruta in [r for r in rutas if r != guion] + [guion]:
        send2trash(str(ruta))
    for carpeta in carpetas_video:  # carpeta del tema vacía (o solo con su subcarpeta «guiones» vacía)
        subcarpeta = carpeta / "guiones"
        if subcarpeta.is_dir() and not any(subcarpeta.iterdir()):
            subcarpeta.rmdir()
        if carpeta.is_dir() and not any(carpeta.iterdir()):
            carpeta.rmdir()
    hecho.insert(0, f"{len(rutas)} archivo(s) y carpeta(s) a la Papelera de reciclaje")
    return f"«{info['titulo']}» borrado: " + ", ".join(hecho) + "."


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    print(borrar(sys.argv[1], de_youtube="--youtube" in sys.argv))
