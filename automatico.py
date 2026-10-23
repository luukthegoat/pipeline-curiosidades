"""Piloto automático: crea un vídeo al día, lo programa en YouTube y deja el recordatorio de TikTok.

Cada ejecución:
  1. Elige qué toca, rotando entre los tipos activos: efemérides del día, el siguiente día de un
     diario (rotando personajes) o el siguiente tema de la lista.
  2. Escribe el guion (paso 1), genera imágenes con IA si es un diario, la voz (paso 2) y el vídeo (paso 3).
  3. Lo deja en «Programados» (la cola del programa, que lo sube a YouTube antes de su hora sin pasarse del
     límite diario) a la hora recomendada para su tipo o a la hora fija de la configuración. Salvaguarda: si el
     verificador encontró frases sin respaldo, NO se programa: queda en «Pendientes» y te avisa (desactivable).
  4. Apunta el recordatorio para subirlo a mano a TikTok y te avisa con una notificación de Windows.

La configuración está en automatico.json (se edita desde el menú → Piloto automático).
Lo ejecuta Windows cada día (Programador de tareas) o tú con «Ejecutar ahora» (funciona aunque esté desactivado).

Uso:
    python automatico.py                 # crea el vídeo que toca (si el piloto está activado)
    python automatico.py --ahora         # lo crea aunque el piloto esté desactivado
    python automatico.py --tipo diario   # fuerza un tipo (efemerides, diario o tema)
"""
import argparse
import json
import subprocess
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
import os  # noqa: E402

os.chdir(RAIZ)  # los pasos usan rutas relativas a la carpeta principal

import avisos  # noqa: E402
import paso3_video  # noqa: E402

CONFIG = Path("automatico.json")
ESTADO = Path("salida/_trabajo/automatico_estado.json")
PENDIENTES_TIKTOK = Path("salida/_trabajo/tiktok_pendientes.json")
REGISTRO = Path("salida/_trabajo/automatico.log")
TIPOS = ("efemerides", "diario", "tema")

CONFIG_INICIAL = {
    "activo": True,
    "tipos": ["efemerides", "diario", "tema"],
    "idioma": "es",
    "hora_creacion": "10:00",
    "hora_youtube": "20:00",
    "hora_tiktok": "21:00",
    "imagenes_ia_en_diarios": True,
    "solo_publicar_sin_dudas": True,
    "hora_recomendada": True,  # publicar a la hora recomendada para su tipo (si no, a «hora_youtube»)
    "personajes": [
        "soldado romano en Vindolanda",
        "médico de la peste en Venecia",
        "escriba en el antiguo Egipto",
        "marinero en la primera vuelta al mundo de Magallanes",
    ],
    "temas": [
        "La Guerra de los Emús",
        "La epidemia de baile de 1518",
        "El Gran Hedor de Londres",
        "La tregua de Navidad de 1914",
        "El maratón olímpico de 1904",
        "El incendio de Roma del año 64",
    ],
}


# --- Configuración y estado ---------------------------------------------------------------

def leer_json(ruta: Path, por_defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return por_defecto


def escribir_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def configuracion() -> dict:
    if not CONFIG.exists():
        escribir_json(CONFIG, CONFIG_INICIAL)
    return {**CONFIG_INICIAL, **leer_json(CONFIG, {})}


def registrar(texto: str) -> None:
    linea = f"[{datetime.now():%Y-%m-%d %H:%M}] {texto}"
    print(linea, flush=True)
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRO.open("a", encoding="utf-8") as archivo:
        archivo.write(linea + "\n")


# --- Qué toca hoy ------------------------------------------------------------------------

def elegir_trabajo(config: dict, estado: dict, forzar_tipo: str = "") -> tuple:
    """Devuelve (tipo, argumentos para paso1_guiones.py, descripción). Avanza la rotación en `estado`."""
    tipos = [t for t in config["tipos"] if t in TIPOS] or ["efemerides"]
    if forzar_tipo:
        tipo = forzar_tipo
    else:
        tipo = tipos[estado.get("siguiente_tipo", 0) % len(tipos)]
        estado["siguiente_tipo"] = estado.get("siguiente_tipo", 0) + 1
    idioma = config.get("idioma", "es")

    if tipo == "diario":
        personajes = config.get("personajes") or CONFIG_INICIAL["personajes"]
        personaje = personajes[estado.get("siguiente_personaje", 0) % len(personajes)]
        estado["siguiente_personaje"] = estado.get("siguiente_personaje", 0) + 1
        return tipo, ["--diario", personaje, "--idiomas", idioma], f"diario de «{personaje}»"
    if tipo == "tema":
        temas = config.get("temas") or []
        if not temas:
            return elegir_trabajo(config, estado, "efemerides")  # lista vacía: efemérides
        tema = temas[0]
        return tipo, ["--tema", tema, "--idiomas", idioma], f"tema «{tema}»"
    hoy = date.today().isoformat()
    return "efemerides", ["--fecha", hoy, "--cantidad", "1", "--idiomas", idioma, "--sin-repetir"], \
        f"efeméride del {hoy}"


def hora_de_publicacion(config: dict) -> datetime:
    """Hoy a la hora de YouTube; si ya pasó (o falta menos de 1 h), dentro de 1 hora."""
    h, m = (int(x) for x in config.get("hora_youtube", "20:00").split(":"))
    objetivo = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    minimo = datetime.now() + timedelta(hours=1)
    return objetivo if objetivo >= minimo else minimo.replace(second=0, microsecond=0)


def hora_tiktok(config: dict, publicacion: datetime) -> datetime:
    h, m = (int(x) for x in config.get("hora_tiktok", "21:00").split(":"))
    recordatorio = publicacion.replace(hour=h, minute=m)
    return recordatorio if recordatorio > datetime.now() else datetime.now() + timedelta(minutes=5)


# --- Ejecución ---------------------------------------------------------------------------

def ejecutar(script: str, *argumentos: str) -> int:
    registrar(f"▶ {script} {' '.join(argumentos)}")
    entorno = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    proceso = subprocess.run([sys.executable, script, *argumentos], cwd=RAIZ, env=entorno,
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for linea in (proceso.stdout + proceso.stderr).splitlines():
        if linea.strip():
            registrar(f"    {linea}")
    return proceso.returncode


def apuntar_tiktok(nombre: str, guion: dict, cuando: datetime) -> None:
    pendientes = leer_json(PENDIENTES_TIKTOK, [])
    pendientes = [p for p in pendientes if p["nombre"] != nombre]
    video = Path(guion["video"])
    pendientes.append({
        "nombre": nombre,
        "titulo": guion.get("titulo", nombre),
        "video": video.as_posix(),
        "texto": paso3_video.ruta_descripcion(video).as_posix(),
        "hora": cuando.isoformat(timespec="minutes"),
        "avisado": False,
        "hecho": False,
    })
    escribir_json(PENDIENTES_TIKTOK, pendientes)


def crear_video(config: dict, forzar_tipo: str = "") -> bool:
    estado = leer_json(ESTADO, {})
    tipo, argumentos, descripcion = elegir_trabajo(config, estado, forzar_tipo)
    registrar(f"=== Piloto automático: {descripcion} ===")

    inicio = datetime.now().timestamp() - 1
    codigo = ejecutar("paso1_guiones.py", *argumentos)
    nuevos = sorted(r for r in paso3_video.CARPETA_GUIONES.glob("*.json") if r.stat().st_mtime >= inicio)
    if codigo == 1 or not nuevos:
        registrar("No se ha podido crear el guion (¿cupo de Groq agotado o Wikipedia en espera?).")
        avisos.notificar("Mente Inquieta · no se ha creado el vídeo de hoy",
                         "No se pudo escribir el guion. Mira el registro en el menú → Piloto automático.")
        return False
    escribir_json(ESTADO, estado)  # la rotación solo avanza si se creó el guion
    if tipo == "tema":  # tema hecho: sale de la lista
        config["temas"] = config["temas"][1:]
        escribir_json(CONFIG, config)

    ruta = nuevos[0]
    nombre = ruta.stem
    if tipo == "diario" and config.get("imagenes_ia_en_diarios"):
        if ejecutar("imagenes_ia.py", nombre) != 0:
            registrar("Aviso: no se pudieron generar las imágenes con IA; se usarán imágenes reales.")
    if ejecutar("paso2_audio.py", str(ruta)) == 1:
        avisos.notificar("Mente Inquieta · error en la voz", "No se pudo generar el audio. Mira el registro.")
        return False
    if ejecutar("paso3_video.py", str(paso3_video.CARPETA_AUDIO / nombre), "--forzar") != 0:
        avisos.notificar("Mente Inquieta · error en el vídeo", "No se pudo montar el vídeo. Mira el registro.")
        return False

    guion = json.loads(ruta.read_text(encoding="utf-8"))
    dudas = len(guion.get("sin_respaldo", []))
    publicacion = programar(nombre, ruta, guion, dudas, config)

    apuntar_tiktok(nombre, json.loads(ruta.read_text(encoding="utf-8")), hora_tiktok(config, publicacion))
    registrar(f"Recordatorio de TikTok para las {hora_tiktok(config, publicacion):%H:%M}.")
    return True


def programar(nombre: str, ruta: Path, guion: dict, dudas: int, config: dict) -> datetime:
    """Deja el vídeo en la cola de «Programados» (o en «Pendientes» si tiene dudas). Devuelve la hora prevista."""
    titulo = guion.get("titulo", nombre)
    publicacion = hora_de_publicacion(config)
    if dudas and config.get("solo_publicar_sin_dudas", True):
        registrar(f"NO se programa: el verificador marcó {dudas} frase(s) dudosa(s). Revísalo en Pendientes.")
        avisos.notificar("Mente Inquieta · revisa el vídeo de hoy",
                         f"«{titulo}» tiene {dudas} frase(s) dudosa(s): revísalo y prográmalo desde Pendientes.")
        return publicacion

    import horarios
    import programados
    if config.get("hora_recomendada", True):
        recomendada = horarios.recomendar([nombre]).get(nombre)
        if recomendada:
            publicacion = datetime.fromisoformat(recomendada["hora"])
            registrar(f"Hora recomendada: {recomendada['bonita']} ({recomendada['motivo']})")
    # El verificador no encontró nada raro y tú pediste publicar sin revisión manual: se da por revisado.
    guion["verificado"], guion["verificado_automatico"] = True, True
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        programados.anadir(nombre, publicacion.strftime("%Y-%m-%dT%H:%M"))
        programados.revisar()  # si ya toca subirlo (falta poco), que se suba ahora
    except Exception as error:  # noqa: BLE001 — el vídeo está hecho: se programa a mano desde el menú
        registrar(f"No se pudo programar: {error}")
        avisos.notificar("Mente Inquieta · no se pudo programar el vídeo",
                         "El vídeo está hecho; prográmalo desde Pendientes. Detalle en el registro.")
        return publicacion
    registrar(f"Programado para el {publicacion:%d/%m a las %H:%M} (en «Programados»: se sube a YouTube antes "
              "de esa hora y YouTube lo publica a su hora).")
    avisos.notificar("Mente Inquieta · vídeo de hoy listo",
                     f"«{titulo}» se publicará el {publicacion:%d/%m a las %H:%M}.")
    return publicacion


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Piloto automático: un vídeo al día")
    parser.add_argument("--tipo", choices=TIPOS, help="fuerza el tipo de vídeo de esta ejecución")
    parser.add_argument("--ahora", action="store_true", help="crearlo aunque el piloto esté desactivado")
    args = parser.parse_args(argv)
    config = configuracion()
    if not config.get("activo") and not args.tipo and not args.ahora:
        registrar("Piloto automático desactivado en automatico.json: no hago nada.")
        return 0
    try:
        return 0 if crear_video(config, args.tipo or "") else 2
    except Exception:  # que cualquier fallo quede registrado y avisado
        registrar("Error inesperado:\n" + traceback.format_exc())
        avisos.notificar("Mente Inquieta · error del piloto automático", "Mira el registro en el menú.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
