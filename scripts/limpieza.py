"""Libera espacio: borra del ordenador lo que ya no hace falta de los vídeos antiguos.

De cada Short PUBLICADO en YouTube hace más de N días (7 por defecto) se borran el vídeo, su miniatura, la voz, los
archivos de montaje y los clips e imágenes propios. El vídeo sigue en YouTube. De los que no se han publicado solo se
borran los archivos de montaje (se rehacen solos si un día lo montas otra vez): el vídeo y la voz se quedan.

No se tocan nunca: los guiones (pesan poco y hacen falta para las estadísticas y para no repetir temas), los vídeos
largos, lo que está en la cola de Programados ni lo que espera publicarse en Instagram.
También se borran de las cachés las imágenes y los clips descargados que llevan N días sin usarse.

Se borra de verdad (no a la Papelera: no liberaría espacio). Lo lanza el piloto automático cada día.

Uso:
    python scripts/limpieza.py              # borra lo de más de 7 días
    python scripts/limpieza.py --dias 14
    python scripts/limpieza.py --simular    # solo dice lo que borraría
"""
import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "salida"
GUIONES = SALIDA / "guiones"
CACHES = ("cache_imagenes", "cache_clips", "cache_pexels", "cache_wikipedia", "cache_miniaturas", "muestras_voz")


def _peso(ruta: Path) -> int:
    if ruta.is_file():
        return ruta.stat().st_size
    return sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file())


def _publicado_el(guion: dict):
    """Cuándo salió (o saldrá) en YouTube; None si no está subido."""
    yt = guion.get("youtube") or {}
    if not yt.get("id"):
        return None
    for clave in ("publicar_el", "subido"):
        try:
            return datetime.fromisoformat(str(yt.get(clave))[:16])
        except (TypeError, ValueError):
            continue
    return None


def candidatos(dias: int) -> list:
    """[(ruta, motivo)] de lo que toca borrar."""
    import programados
    limite = datetime.now() - timedelta(days=dias)
    cola = {v["nombre"]: v for v in programados.leer()["videos"]}
    config_ig = programados.instagram_activo()
    lista = []
    for ruta_guion in sorted(GUIONES.glob("*.json")):
        nombre = ruta_guion.stem
        try:
            guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        en_cola = cola.get(nombre)
        if en_cola and (en_cola["estado"] != "en_youtube" or programados.pendiente_instagram(en_cola, config_ig)):
            continue  # aún tiene que subirse (a YouTube o a Instagram): hace falta el archivo
        montaje = SALIDA / "_trabajo" / nombre
        publicado = _publicado_el(guion)
        if publicado and publicado < limite:
            rutas = [montaje, SALIDA / "audio" / nombre, SALIDA / "clips_ia" / nombre, SALIDA / "imagenes_ia" / nombre,
                     *(SALIDA / "imagenes_propias").glob(f"{nombre}_escena*")]
            if guion.get("video"):
                video = (RAIZ / guion["video"]).resolve()
                if (SALIDA / "videos").resolve() in video.parents:  # nunca fuera de la carpeta de vídeos
                    rutas += [video, video.with_suffix(".jpg")]
            lista += [(r, f"publicado el {publicado:%d/%m}") for r in rutas if r.exists()]
        elif not publicado and montaje.exists() and datetime.fromtimestamp(ruta_guion.stat().st_mtime) < limite:
            lista.append((montaje, "sin publicar: solo el montaje"))
    # Carpetas de montaje de guiones que ya no existen. Solo las que tienen nombre de guion («2026-11-10_…»): en
    # _trabajo hay más cosas que no son de ningún vídeo (los datos de la ventana de la app, las búsquedas de noticias).
    trabajo = SALIDA / "_trabajo"
    for carpeta in trabajo.iterdir() if trabajo.exists() else []:
        if (carpeta.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}_", carpeta.name)
                and not (GUIONES / f"{carpeta.name}.json").exists()
                and datetime.fromtimestamp(carpeta.stat().st_mtime) < limite):
            lista.append((carpeta, "su guion ya no existe"))
    # Cachés: lo descargado que lleva días sin usarse (se vuelve a bajar si hiciera falta)
    corte = time.time() - dias * 86400
    for nombre in CACHES:
        carpeta = SALIDA / nombre
        for archivo in carpeta.rglob("*") if carpeta.exists() else []:
            if archivo.is_file() and max(archivo.stat().st_mtime, archivo.stat().st_atime) < corte:
                lista.append((archivo, "caché sin usar"))
    return lista


def limpiar(dias: int = 7, simular: bool = False) -> dict:
    """Borra lo que toca. Devuelve {"archivos", "megas", "videos"}."""
    if dias <= 0:
        return {"archivos": 0, "megas": 0, "videos": 0}
    total = archivos = videos = 0
    carpetas_video = set()
    for ruta, _ in candidatos(dias):
        if SALIDA.resolve() not in ruta.resolve().parents:
            continue  # por si acaso: nada fuera de «salida»
        try:
            peso = _peso(ruta)
            if not simular:
                if ruta.is_dir():
                    shutil.rmtree(ruta)
                else:
                    ruta.unlink()
        except OSError:
            continue  # abierto en otro programa: se borrará otro día
        total += peso
        archivos += 1
        if ruta.suffix == ".mp4" and (SALIDA / "videos").resolve() in ruta.resolve().parents:
            videos += 1
            carpetas_video.add(ruta.parent)
    for carpeta in carpetas_video:  # la carpeta del tema, si ya no queda ningún vídeo dentro
        if not simular and carpeta.is_dir() and not any(carpeta.rglob("*.mp4")):
            shutil.rmtree(carpeta, ignore_errors=True)
    return {"archivos": archivos, "megas": round(total / 1_048_576), "videos": videos}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Borra del ordenador lo que ya no hace falta de los vídeos antiguos")
    parser.add_argument("--dias", type=int, default=7)
    parser.add_argument("--simular", action="store_true", help="solo dice lo que borraría")
    args = parser.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if args.simular:
        por_motivo = {}
        for ruta, motivo in candidatos(args.dias):
            clave = "publicados hace más de una semana" if motivo.startswith("publicado") else motivo
            por_motivo.setdefault(clave, [0, 0])
            por_motivo[clave][0] += 1
            por_motivo[clave][1] += _peso(ruta)
        for motivo, (n, peso) in por_motivo.items():
            print(f"  {motivo}: {n} archivo(s)/carpeta(s), {peso / 1_048_576:.0f} MB")
    r = limpiar(args.dias, args.simular)
    print(f"{'Se borrarían' if args.simular else 'Borrados'} {r['archivos']} archivos y carpetas "
          f"({r['videos']} vídeos): {r['megas']} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
