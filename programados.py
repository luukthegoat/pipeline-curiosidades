"""Publicaciones programadas: la cola la lleva el programa y YouTube publica a la hora exacta.

Modo mixto:
  - Programar un vídeo solo lo apunta en la cola (salida/_trabajo/programados.json).
  - Entre ANTELACION_H y unos minutos antes de su hora, el programa lo sube a YouTube ya programado
    (privado + publishAt). Desde ese momento YouTube lo publica a su hora aunque el ordenador esté apagado.
  - Nunca sube más de MAX_SUBIDAS_DIA vídeos en 24 h (contando también los subidos a mano), para no chocar
    con el límite de subidas de YouTube; lo que no cabe, espera a la siguiente oportunidad.
  - Si a la hora de subirlo ya ha pasado su hora (ordenador apagado muchos días), se publica al subirlo.

Quién lo ejecuta:
  - El menú, cada minuto, mientras está abierto.
  - Una tarea de Windows («Mente Inquieta - publicar programados») que se reprograma sola para la próxima
    subida y también se lanza al iniciar sesión (si el ordenador estaba apagado, en cuanto se encienda).

Uso:
    python programados.py            # sube lo que toque ahora y reprograma la tarea de Windows
    python programados.py --estado   # muestra la cola
"""
import json
import msvcrt
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
os.chdir(RAIZ)  # las credenciales y las carpetas de salida van con rutas relativas

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")

ARCHIVO = RAIZ / "salida" / "_trabajo" / "programados.json"
CERROJO = RAIZ / "salida" / "_trabajo" / "programados.lock"
REGISTRO = RAIZ / "salida" / "_trabajo" / "programados.log"
GUIONES = RAIZ / "salida" / "guiones"
TAREA = "Mente Inquieta - publicar programados"
ANTELACION_H = float(os.getenv("PROGRAMADOS_ANTELACION_H") or 48)  # cuánto antes de su hora se sube
MAX_SUBIDAS_DIA = int(os.getenv("PROGRAMADOS_MAX_DIA") or 3)        # subidas como mucho en 24 h
MARGEN_MIN = 15  # YouTube necesita que la hora de publicación sea futura: por debajo de esto, se publica ya
FORMATO = "%Y-%m-%dT%H:%M"

# estado de cada vídeo de la cola:
#   en_cola     → aún en el ordenador; se subirá cuando entre en la ventana de ANTELACION_H
#   subiendo    → subiéndose ahora mismo
#   en_youtube  → subido y programado en YouTube (o ya publicado, si su hora pasó)
#   error       → falló la subida (ver «mensaje»); se puede reintentar


# --- Datos -------------------------------------------------------------------------

def _hora(texto: str) -> datetime:
    return datetime.strptime(texto[:16], FORMATO)


def leer() -> dict:
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    datos.setdefault("videos", [])
    datos.setdefault("siguiente_intento", None)
    return datos


def guardar(datos: dict) -> None:
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    temporal = ARCHIVO.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ARCHIVO)


def buscar(datos: dict, nombre: str):
    return next((v for v in datos["videos"] if v["nombre"] == nombre), None)


def _guion(nombre: str) -> dict:
    return json.loads((GUIONES / f"{nombre}.json").read_text(encoding="utf-8"))


def momento_de_subida(video: dict) -> datetime:
    """Desde cuándo se puede subir a YouTube."""
    return _hora(video["hora"]) - timedelta(hours=ANTELACION_H)


def subidas_ultimas_24h() -> int:
    """Vídeos subidos a YouTube en las últimas 24 h (por la cola o a mano), según los guiones."""
    limite = datetime.now() - timedelta(hours=24)
    total = 0
    for ruta in GUIONES.glob("*.json"):
        try:
            subido = (json.loads(ruta.read_text(encoding="utf-8")).get("youtube") or {}).get("subido")
            if subido and datetime.fromisoformat(subido) > limite:
                total += 1
        except (OSError, ValueError):
            continue
    return total


def proxima_subida_libre() -> datetime:
    """Cuándo vuelve a haber hueco si ya se ha llegado al máximo de subidas en 24 h."""
    horas = []
    for ruta in GUIONES.glob("*.json"):
        try:
            subido = (json.loads(ruta.read_text(encoding="utf-8")).get("youtube") or {}).get("subido")
            if subido:
                horas.append(datetime.fromisoformat(subido))
        except (OSError, ValueError):
            continue
    recientes = sorted(h for h in horas if h > datetime.now() - timedelta(hours=24))
    if len(recientes) < MAX_SUBIDAS_DIA:
        return datetime.now()
    return recientes[len(recientes) - MAX_SUBIDAS_DIA] + timedelta(hours=24, minutes=1)


# --- Cambios desde el menú ------------------------------------------------------------

_cerrojo_tarea = threading.Lock()


def proxima_revision():
    """Cuándo hay que volver a mirar la cola: la primera subida pendiente (o None si no queda nada)."""
    pendientes = [v for v in leer()["videos"] if v["estado"] == "en_cola"]
    return max(min(momento_de_subida(v) for v in pendientes), datetime.now()) if pendientes else None


def _reprogramar_tarea() -> None:
    # Se calcula al ejecutarse (no al pedirlo): con varios cambios seguidos, gana siempre el estado final.
    with _cerrojo_tarea:
        programar_tarea_windows(proxima_revision())


def _guardar_y_reprogramar(datos: dict) -> None:
    """Guarda la cola y, en segundo plano (PowerShell tarda unos segundos), deja lista la tarea de Windows."""
    datos["siguiente_intento"] = None  # que el menú lo revise ya
    guardar(datos)
    threading.Thread(target=_reprogramar_tarea, name="tarea-programados").start()


def anadir(nombre: str, hora: str) -> None:
    """Apunta (o vuelve a apuntar) un guion en la cola para publicarse a `hora` (AAAA-MM-DDTHH:MM, hora local)."""
    hora = _hora(hora).strftime(FORMATO)
    datos = leer()
    video = buscar(datos, nombre)
    if video and video["estado"] in ("subiendo", "en_youtube"):
        raise ValueError("ya está subido a YouTube: cambia su hora desde «Programados»")
    datos["videos"] = [v for v in datos["videos"] if v["nombre"] != nombre]
    guion = _guion(nombre)
    datos["videos"].append({
        "nombre": nombre, "titulo": guion.get("titulo", nombre), "hora": hora, "estado": "en_cola",
        "mensaje": "", "anadido": datetime.now().isoformat(timespec="seconds"),
    })
    _guardar_y_reprogramar(datos)


def quitar(nombre: str) -> str:
    """Saca un vídeo de la cola. Si ya estaba programado en YouTube, lo deja allí en privado (no lo borra)."""
    datos = leer()
    video = buscar(datos, nombre)
    if not video:
        return "Ese vídeo no estaba programado."
    mensaje = "Quitado de la cola."
    if video["estado"] == "en_youtube" and _hora(video["hora"]) > datetime.now():
        import subir_youtube
        subir_youtube.cambiar_publicacion(video["youtube_id"], privacidad="private")
        _apuntar_en_guion(nombre, privacidad="private", publicar_el=None)
        mensaje = "Quitado de la cola. En YouTube queda en privado: no se publicará (puedes borrarlo en YouTube Studio)."
    datos["videos"] = [v for v in datos["videos"] if v["nombre"] != nombre]
    _guardar_y_reprogramar(datos)
    return mensaje


def cambiar_hora(nombre: str, hora: str) -> str:
    hora = _hora(hora).strftime(FORMATO)
    if _hora(hora) <= datetime.now() + timedelta(minutes=MARGEN_MIN):
        raise ValueError(f"la hora tiene que ser al menos {MARGEN_MIN} minutos en el futuro (o usa «Publicar ya»)")
    datos = leer()
    video = buscar(datos, nombre)
    if not video:
        raise ValueError("ese vídeo no está programado")
    if video["estado"] == "en_youtube":
        import subir_youtube
        subir_youtube.cambiar_publicacion(video["youtube_id"], publicar_el=hora)
        _apuntar_en_guion(nombre, privacidad="private", publicar_el=hora)
    elif video["estado"] == "error":
        video["estado"], video["mensaje"] = "en_cola", ""
    video["hora"] = hora
    _guardar_y_reprogramar(datos)
    return f"Nueva hora: {formato_bonito(hora)}."


def publicar_ya(nombre: str) -> str:
    """Si ya está en YouTube, lo publica al momento; si no, lo deja listo para subirse en la próxima revisión."""
    datos = leer()
    video = buscar(datos, nombre)
    if not video:
        raise ValueError("ese vídeo no está programado")
    ahora = datetime.now().strftime(FORMATO)
    if video["estado"] == "en_youtube":
        import subir_youtube
        subir_youtube.cambiar_publicacion(video["youtube_id"], privacidad="public")
        _apuntar_en_guion(nombre, privacidad="public", publicar_el=None)
        mensaje = "Publicado en YouTube."
    else:
        video["estado"], video["mensaje"] = "en_cola", ""
        mensaje = "Se sube y se publica en cuanto se pueda (en menos de un minuto si el menú está abierto)."
    video["hora"] = ahora
    _guardar_y_reprogramar(datos)
    return mensaje


def limpiar_historial() -> None:
    datos = leer()
    datos["videos"] = [v for v in datos["videos"]
                       if not (v["estado"] == "en_youtube" and _hora(v["hora"]) <= datetime.now())]
    guardar(datos)


def _apuntar_en_guion(nombre: str, **cambios) -> None:
    ruta = GUIONES / f"{nombre}.json"
    guion = json.loads(ruta.read_text(encoding="utf-8"))
    if guion.get("youtube"):
        guion["youtube"].update(cambios)
        ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Lo que se ve en el menú ----------------------------------------------------------

DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def formato_bonito(hora: str) -> str:
    h = _hora(hora)
    return f"{DIAS[h.weekday()]} {h.day} {MESES[h.month - 1]} · {h:%H:%M}"


def relativo(hora: datetime) -> str:
    """«en 3 h», «en 2 días», «hace 20 min»…"""
    segundos = (hora - datetime.now()).total_seconds()
    cantidad = abs(segundos)
    if cantidad < 3600:
        texto = f"{max(1, round(cantidad / 60))} min"
    elif cantidad < 48 * 3600:
        horas, minutos = divmod(round(cantidad / 60), 60)
        texto = f"{horas} h" + (f" {minutos} min" if minutos and horas < 10 else "")
    else:
        texto = f"{round(cantidad / 86400)} días"
    return f"en {texto}" if segundos > 0 else f"hace {texto}"


def para_mostrar() -> dict:
    """La cola preparada para la página «Programados»: próximos (por hora) e historial."""
    ahora = datetime.now()
    proximos, historial = [], []
    for v in leer()["videos"]:
        hora = _hora(v["hora"])
        v = {**v, "bonita": formato_bonito(v["hora"]), "pasada": hora <= ahora, "relativo": relativo(hora),
             "dia": hora.day, "mes": MESES[hora.month - 1], "dia_semana": DIAS[hora.weekday()], "hhmm": f"{hora:%H:%M}",
             "sube_desde": formato_bonito(momento_de_subida(v).strftime(FORMATO)),
             "en_ventana": momento_de_subida(v) <= ahora}
        (historial if v["estado"] == "en_youtube" and v["pasada"] else proximos).append(v)
    proximos.sort(key=lambda v: v["hora"])
    historial.sort(key=lambda v: v["hora"], reverse=True)
    return {"proximos": proximos, "historial": historial[:30]}


def por_guion() -> dict:
    """{nombre: vídeo} de los que aún no se han publicado (para marcar los guiones en el inicio)."""
    ahora = datetime.now()
    return {v["nombre"]: {**v, "bonita": formato_bonito(v["hora"])} for v in leer()["videos"]
            if not (v["estado"] == "en_youtube" and _hora(v["hora"]) <= ahora)}


def toca_revisar() -> bool:
    """¿Hay algo que subir ya? (lo usa el menú cada minuto para no lanzar el proceso sin motivo)."""
    datos = leer()
    if datos["siguiente_intento"] and datetime.fromisoformat(datos["siguiente_intento"]) > datetime.now():
        return False
    return any(v["estado"] in ("en_cola", "subiendo") and momento_de_subida(v) <= datetime.now()
               for v in datos["videos"])


# --- Subida -----------------------------------------------------------------------------

def _log(texto: str) -> None:
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {texto}"
    print(linea, flush=True)
    try:
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def _cerrojo():
    """Impide que dos procesos (el menú y la tarea de Windows) suban a la vez. None si ya hay otro."""
    CERROJO.parent.mkdir(parents=True, exist_ok=True)
    archivo = open(CERROJO, "a+")
    try:
        msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
        return archivo
    except OSError:
        archivo.close()
        return None


def revisar() -> int:
    """Sube lo que toque y reprograma la tarea de Windows. Devuelve cuántos vídeos ha subido."""
    cerrojo = _cerrojo()
    if not cerrojo:
        _log("otro proceso ya está subiendo vídeos programados")
        return 0
    try:
        return _revisar()
    finally:
        cerrojo.close()


def _actualizar(nombre: str, **cambios):
    """Cambia un vídeo releyendo antes la cola (el menú puede haberla tocado mientras se subía otro)."""
    datos = leer()
    video = buscar(datos, nombre)
    if video:
        video.update(cambios)
        guardar(datos)
    return video


def _revisar() -> int:
    import subir_youtube
    from googleapiclient.errors import HttpError

    for v in leer()["videos"]:  # restos de una ejecución que se cortó a medias
        if v["estado"] == "subiendo":
            ruta = GUIONES / f"{v['nombre']}.json"
            yt = (json.loads(ruta.read_text(encoding="utf-8")).get("youtube") or {}) if ruta.exists() else {}
            if yt.get("id"):
                _actualizar(v["nombre"], estado="en_youtube", youtube_id=yt["id"], url=yt["url"])
            else:
                _actualizar(v["nombre"], estado="en_cola")

    subidos, bloqueado = 0, ""
    for nombre in [v["nombre"] for v in sorted(leer()["videos"], key=lambda v: v["hora"])]:
        v = buscar(leer(), nombre)  # estado actual: puede haberse quitado o cambiado de hora
        if not v or v["estado"] != "en_cola" or momento_de_subida(v) > datetime.now():
            continue
        if subidas_ultimas_24h() >= MAX_SUBIDAS_DIA:
            bloqueado = f"máximo de {MAX_SUBIDAS_DIA} subidas en 24 h alcanzado"
            break
        ruta = GUIONES / f"{nombre}.json"
        if not ruta.exists():
            _actualizar(nombre, estado="error", mensaje="el guion ya no existe")
            continue
        guion = json.loads(ruta.read_text(encoding="utf-8"))
        if guion.get("youtube"):  # se subió por otro lado mientras esperaba
            _actualizar(nombre, estado="en_youtube", youtube_id=guion["youtube"]["id"], url=guion["youtube"]["url"],
                        mensaje="ya estaba subido")
            continue

        a_tiempo = _hora(v["hora"]) > datetime.now() + timedelta(minutes=MARGEN_MIN)
        _actualizar(nombre, estado="subiendo", mensaje="")
        _log(f"subiendo «{v['titulo']}» para el {formato_bonito(v['hora'])}")
        try:
            resultado = subir_youtube.subir(nombre, privacidad="public", publicar_el=v["hora"] if a_tiempo else "")
        except HttpError as error:
            motivo = subir_youtube._explicar(error)
            if "cupo" in motivo or "limitado" in motivo:
                _actualizar(nombre, estado="en_cola", mensaje=f"YouTube no deja subir más por hoy: se reintentará solo. ({motivo})")
                bloqueado = motivo
                _log(f"  {motivo}")
                break
            fallo = motivo
        except Exception as error:  # noqa: BLE001 — se apunta y se sigue con el resto
            fallo = str(error)
        else:
            subidos += 1
            mensaje = "" if a_tiempo else "se subió tarde (el ordenador estaba apagado) y se publicó al subirlo"
            if resultado.get("privacidad") == "private" and not a_tiempo:
                mensaje = "subido, pero YouTube lo ha dejado en privado: hazlo público en YouTube Studio"
            _actualizar(nombre, estado="en_youtube", youtube_id=resultado["id"], url=resultado["url"],
                        subido=datetime.now().isoformat(timespec="seconds"), mensaje=mensaje)
            _log(f"  ✔ {resultado['url']}")
            _avisar("Vídeo programado en YouTube" if a_tiempo else "Vídeo publicado en YouTube",
                    f"«{v['titulo']}»" + (f" se publicará el {formato_bonito(v['hora'])}." if a_tiempo else "."))
            continue
        _actualizar(nombre, estado="error", mensaje=fallo)
        _log(f"  error: {fallo}")
        _avisar("No se ha podido subir un vídeo programado", f"«{v['titulo']}»: {fallo}")

    # Cuándo volver a mirar: la próxima subida posible (o en 1 h si YouTube nos ha frenado).
    datos = leer()
    pendientes = [v for v in datos["videos"] if v["estado"] == "en_cola"]
    siguiente = None
    if pendientes:
        if bloqueado:
            libre = proxima_subida_libre() if "máximo" in bloqueado else datetime.now() + timedelta(hours=1)
            siguiente = max(libre, datetime.now() + timedelta(minutes=5))
        else:
            siguiente = max(min(momento_de_subida(v) for v in pendientes), datetime.now() + timedelta(minutes=1))
    datos["siguiente_intento"] = siguiente.isoformat(timespec="seconds") if siguiente else None
    guardar(datos)
    programar_tarea_windows(siguiente)
    if bloqueado:
        _log(f"en espera: {bloqueado}; siguiente intento {siguiente:%d/%m %H:%M}" if siguiente else f"en espera: {bloqueado}")
    return subidos


def _avisar(titulo: str, texto: str) -> None:
    try:
        import avisos
        avisos.notificar(titulo, texto)
    except Exception:  # noqa: BLE001 — una notificación que falla no es grave
        pass


# --- Tarea de Windows -----------------------------------------------------------------------

_REGISTRAR = r"""
$accion = New-ScheduledTaskAction -Execute $env:T_EXE -Argument ('"' + $env:T_SCRIPT + '"') -WorkingDirectory $env:T_DIR
$disparadores = @((New-ScheduledTaskTrigger -Once -At ([datetime]$env:T_HORA)), (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME))
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $env:T_NOMBRE -Action $accion -Trigger $disparadores -Settings $ajustes -Description $env:T_DESC -Force | Out-Null
"""


def programar_tarea_windows(cuando) -> None:
    """Deja la tarea de Windows lista para la próxima subida (o la quita si no queda nada en la cola)."""
    import programador
    if cuando is None:
        programador._powershell(programador._BORRAR, T_NOMBRE=TAREA)
        return
    ejecutable = programador.PYTHONW if programador.PYTHONW.exists() else Path(sys.executable)
    resultado = programador._powershell(
        _REGISTRAR, T_EXE=ejecutable, T_SCRIPT=RAIZ / "programados.py", T_DIR=RAIZ,
        T_HORA=cuando.strftime("%Y-%m-%dT%H:%M:%S"), T_NOMBRE=TAREA,
        T_DESC="Sube a YouTube los vídeos programados de Mente Inquieta (se reprograma sola).")
    if resultado.returncode != 0:
        _log(f"no he podido programar la tarea de Windows: {resultado.stderr.strip()[-300:]}")


def estado_tarea_windows() -> dict:
    import programador
    return programador.estado_tarea(TAREA)


if __name__ == "__main__":
    if "--estado" in sys.argv:
        print(json.dumps(para_mostrar(), ensure_ascii=False, indent=2))
    else:
        revisar()
