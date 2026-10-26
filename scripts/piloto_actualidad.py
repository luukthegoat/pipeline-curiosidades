"""Piloto de actualidad: hace y publica solo el vídeo de la noticia del día, con salvaguarda.

Cada ejecución (Windows la lanza a las horas de la configuración):
  1. Si hoy ya se hicieron los vídeos del máximo diario, no hace nada.
  2. El radar (radar.py) elige la noticia de la que más se habla y que el canal aún no ha contado.
  3. Busca artículos de prensa (actualidad.py). Salvaguarda 1: hacen falta al menos «min_medios» medios
     reconocidos; si no, prueba con la siguiente candidata.
  4. Escribe el guion (paso 1, que lo verifica contra los artículos), la voz (paso 2) y el vídeo (paso 3).
  5. Salvaguarda 2: si el verificador marcó alguna frase sin respaldo, NO se publica: queda en «Mis vídeos»
     sin revisar y te avisa. Si está limpio, se da por revisado y se publica en YouTube al momento.
Cerca de unas elecciones (lista «elecciones»), el día antes y el mismo día no hace noticias de política.

La configuración está en piloto_actualidad.json (se cambia desde el menú → Ajustes → Piloto de actualidad).

Uso:
    python scripts/piloto_actualidad.py             # crea el vídeo que toque (si el piloto está activado)
    python scripts/piloto_actualidad.py --ahora     # lo crea aunque esté desactivado o ya se haya llegado al máximo
    python scripts/piloto_actualidad.py activar     # registra las tareas de Windows con las horas de la configuración
    python scripts/piloto_actualidad.py desactivar  # las quita
"""
import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent  # carpeta principal (este archivo está en scripts/)
os.chdir(RAIZ)  # los pasos usan rutas relativas a la carpeta principal
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(errors="replace")

import avisos  # noqa: E402
import paso3_video  # noqa: E402

CONFIG = RAIZ / "piloto_actualidad.json"
ESTADO = RAIZ / "salida" / "_trabajo" / "piloto_actualidad_estado.json"
REGISTRO = RAIZ / "salida" / "_trabajo" / "piloto_actualidad.log"
PYTHONW = RAIZ / ".venv" / "Scripts" / "pythonw.exe"  # sin ventana negra
TAREA = "Mente Inquieta - piloto de actualidad"
DIAS_SIN_REPETIR = 5  # lo contado en estos días no se vuelve a contar

CONFIG_INICIAL = {
    "activo": False,
    "horas": ["09:30", "13:30", "18:00", "21:00"],  # cuándo mira el radar (como mucho un vídeo cada vez)
    "max_dia": 2,           # vídeos de actualidad al día, como mucho
    "min_medios": 3,        # medios reconocidos que tienen que contar la noticia
    "idioma": "es",
    "elecciones": ["2026-11-29"],  # el día antes (reflexión) y el mismo día no se hace política
}


# --- Configuración, estado y registro --------------------------------------------------------

def leer_json(ruta: Path, por_defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return por_defecto


def escribir_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def configuracion() -> dict:
    return {**CONFIG_INICIAL, **leer_json(CONFIG, {})}


def guardar_configuracion(cambios: dict) -> dict:
    config = {**configuracion(), **cambios}
    escribir_json(CONFIG, config)
    return config


def registrar(texto: str) -> None:
    linea = f"[{datetime.now():%Y-%m-%d %H:%M}] {texto}"
    print(linea, flush=True)
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRO.open("a", encoding="utf-8") as archivo:
        archivo.write(linea + "\n")


def ultimas_lineas(cuantas: int = 40) -> list:
    try:
        return REGISTRO.read_text(encoding="utf-8").splitlines()[-cuantas:]
    except OSError:
        return []


def contados(dias: int = DIAS_SIN_REPETIR) -> list:
    """Noticias que el piloto ya ha convertido en vídeo en los últimos `dias` (las más nuevas al final)."""
    limite = (date.today() - timedelta(days=dias)).isoformat()
    return [c for c in leer_json(ESTADO, {}).get("contados", []) if c.get("fecha", "") >= limite]


def noticias_hechas(dias: int = DIAS_SIN_REPETIR) -> list:
    """Titulares de lo ya contado estos días: lo del piloto y también las noticias que hiciste tú desde el menú."""
    titulares = [c["titular"] for c in contados(dias)]
    limite = (date.today() - timedelta(days=dias)).isoformat()
    for ruta in paso3_video.CARPETA_GUIONES.glob("*_actualidad_*.json"):
        guion = leer_json(ruta, {})
        if guion.get("actualidad") and guion.get("fecha", "") >= limite:
            titulares.append(f"{guion.get('titulo', '')} ({guion['actualidad'].get('tema', '')})")
    return list(dict.fromkeys(titulares))


def apuntar_contado(candidata: dict, nombre: str, publicado: bool) -> None:
    estado = leer_json(ESTADO, {})
    estado["contados"] = contados(30) + [{
        "fecha": date.today().isoformat(), "hora": datetime.now().strftime("%H:%M"),
        "titular": candidata["titular"], "busqueda": candidata["busqueda"], "nombre": nombre, "publicado": publicado,
    }]
    escribir_json(ESTADO, estado)


def motivo_sin_politica(config: dict, hoy: date = None) -> str:
    """Si hoy es la jornada de reflexión o el día de unas elecciones de la lista, el motivo; si no, «»."""
    hoy = hoy or date.today()
    for texto in config.get("elecciones", []):
        try:
            dia = date.fromisoformat(texto)
        except ValueError:
            continue
        if dia - timedelta(days=1) <= hoy <= dia:
            return f"jornada de reflexión y elecciones del {dia:%d/%m}"
    return ""


# --- Ejecución ------------------------------------------------------------------------------

def ejecutar(script: str, *argumentos: str) -> int:
    registrar(f"▶ {script} {' '.join(argumentos)}")
    entorno = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    ruta = Path(__file__).resolve().parent / script  # los demás pasos están en esta misma carpeta
    proceso = subprocess.run([sys.executable, str(ruta), *argumentos], cwd=RAIZ, env=entorno,
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for linea in (proceso.stdout + proceso.stderr).splitlines():
        if linea.strip():
            registrar(f"    {linea}")
    return proceso.returncode


def buscar_articulos(candidata: dict, config: dict):
    """La búsqueda de prensa de una candidata y los números de sus artículos de medios reconocidos, o None."""
    import actualidad
    if re.search(r"\b(encuesta|sondeo|CIS)\b", f"{candidata['titular']} {candidata['busqueda']}", re.I):
        registrar(f"Descartada (es una encuesta): {candidata['titular']}")
        return None
    busqueda = actualidad.buscar(candidata["busqueda"], dias=2)
    reconocidos = [i for i, a in enumerate(busqueda["articulos"]) if a["reconocido"]]
    medios = sorted({busqueda["articulos"][i]["medio"] for i in reconocidos})
    if len(medios) < config["min_medios"]:
        registrar(f"Descartada (solo {len(medios)} medio(s) reconocido(s), hacen falta {config['min_medios']}): "
                  f"{candidata['titular']}")
        return None
    registrar(f"Artículos de {len(medios)} medios reconocidos: {', '.join(medios)}")
    return busqueda, reconocidos[:5]


def crear_video(config: dict, forzar: bool = False) -> bool:
    hoy = date.today().isoformat()
    de_hoy = [c for c in contados(0) if c["fecha"] == hoy]
    if len(de_hoy) >= config["max_dia"] and not forzar:
        registrar(f"Hoy ya van {len(de_hoy)} vídeo(s) de actualidad (máximo {config['max_dia']}): no hago nada.")
        return True

    import radar
    sin_politica = motivo_sin_politica(config)
    if sin_politica:
        registrar(f"Hoy no hay política: {sin_politica}.")
    registrar("=== Piloto de actualidad: buscando la noticia del día ===")
    lista = radar.candidatas(noticias_hechas(), sin_politica)
    if not lista:
        registrar("El radar no ha encontrado ninguna noticia que valga ahora. Se vuelve a mirar en la próxima hora.")
        return True

    elegida = articulos = None
    for candidata in lista:
        registrar(f"Candidata [{candidata['categoria']}]: {candidata['titular']} · {candidata['motivo']}")
        encontrado = buscar_articulos(candidata, config)
        if encontrado:
            elegida, (busqueda, articulos) = candidata, encontrado
            break
    if not elegida:
        registrar("Ninguna candidata tiene medios suficientes: no se crea vídeo esta vez.")
        return True

    inicio = datetime.now().timestamp() - 1
    codigo = ejecutar("paso1_guiones.py", "--actualidad", busqueda["id"],
                      "--articulos", ",".join(map(str, articulos)), "--idiomas", config["idioma"])
    nuevos = sorted(r for r in paso3_video.CARPETA_GUIONES.glob("*.json") if r.stat().st_mtime >= inicio)
    if codigo == 1 or not nuevos:
        registrar("No se ha podido escribir el guion (¿cupo de Groq agotado?).")
        avisos.notificar("Mente Inquieta · piloto de actualidad",
                         "No se pudo escribir el guion de la noticia del día. Mira el registro en Ajustes.")
        return False
    ruta = nuevos[0]
    nombre = ruta.stem
    if ejecutar("paso2_audio.py", str(ruta)) == 1:
        avisos.notificar("Mente Inquieta · error en la voz", "No se pudo generar el audio. Mira el registro.")
        return False
    if ejecutar("paso3_video.py", str(paso3_video.CARPETA_AUDIO / nombre), "--forzar") != 0:
        avisos.notificar("Mente Inquieta · error en el vídeo", "No se pudo montar el vídeo. Mira el registro.")
        return False

    guion = json.loads(ruta.read_text(encoding="utf-8"))
    publicado = publicar(nombre, ruta, guion)
    apuntar_contado(elegida, nombre, publicado)
    return True


def publicar(nombre: str, ruta: Path, guion: dict) -> bool:
    """Salvaguarda 2 y publicación al momento. Devuelve si se ha mandado a YouTube."""
    titulo = guion.get("titulo", nombre)
    dudas = guion.get("sin_respaldo", [])
    if dudas:
        registrar(f"NO se publica: el verificador marcó {len(dudas)} frase(s) sin respaldo en los artículos:")
        for d in dudas:
            registrar(f"    escena {d.get('escena')}: «{d.get('frase', '')}» ({d.get('motivo', '')})")
        avisos.notificar("Mente Inquieta · revisa la noticia de hoy",
                         f"«{titulo}» tiene {len(dudas)} frase(s) dudosa(s): está en Mis vídeos esperando tu revisión.")
        return False

    import programados
    # El verificador no encontró nada raro y el piloto publica sin revisión manual: se da por revisado.
    guion["verificado"], guion["verificado_automatico"] = True, True
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        programados.anadir(nombre, datetime.now().strftime(programados.FORMATO))
        programados.publicar_ya(nombre)  # la noticia engancha si sale pronto: no espera a una hora fija
        programados.revisar()
    except Exception as error:  # noqa: BLE001 — el vídeo está hecho: se publica a mano desde el menú
        registrar(f"No se pudo publicar: {error}")
        avisos.notificar("Mente Inquieta · no se pudo publicar la noticia",
                         "El vídeo está hecho; publícalo desde Mis vídeos. Detalle en el registro.")
        return False
    video = programados.buscar(programados.leer(), nombre) or {}
    if video.get("estado") == "en_youtube":
        registrar(f"✔ Publicado en YouTube: {video.get('url', '')}")
    else:
        registrar(f"En Programados: {video.get('mensaje') or video.get('estado', '')}")
    return True


# --- Tareas de Windows ----------------------------------------------------------------------

_REGISTRAR = r"""
$accion = New-ScheduledTaskAction -Execute $env:T_EXE -Argument ('"' + $env:T_SCRIPT + '"') -WorkingDirectory $env:T_DIR
$disparadores = @($env:T_HORAS.Split(',') | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $env:T_NOMBRE -Action $accion -Trigger $disparadores -Settings $ajustes -Description $env:T_DESC -Force | Out-Null
"""
_BORRAR = r"Unregister-ScheduledTask -TaskName $env:T_NOMBRE -Confirm:$false -ErrorAction SilentlyContinue"


def _powershell(script: str, **variables) -> subprocess.CompletedProcess:
    entorno = {**os.environ, **{k: str(v) for k, v in variables.items()}}
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                          env=entorno, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def activar() -> str:
    """Registra (o actualiza) la tarea de Windows con las horas de la configuración. Devuelve el error, o «»."""
    config = guardar_configuracion({"activo": True})
    horas = [h for h in config["horas"] if re.fullmatch(r"\d{1,2}:\d{2}", h)] or CONFIG_INICIAL["horas"]
    ejecutable = PYTHONW if PYTHONW.exists() else Path(sys.executable)
    resultado = _powershell(_REGISTRAR, T_EXE=ejecutable, T_SCRIPT=Path(__file__).resolve(), T_DIR=RAIZ,
                            T_HORAS=",".join(horas), T_NOMBRE=TAREA,
                            T_DESC="Hace y publica el vídeo de la noticia del día de Mente Inquieta.")
    return resultado.stderr.strip()[-300:] if resultado.returncode != 0 else ""


def desactivar() -> None:
    guardar_configuracion({"activo": False})
    _powershell(_BORRAR, T_NOMBRE=TAREA)


def estado_tarea() -> dict:
    """{"existe", "proxima", "ultima"} de la tarea de Windows (con schtasks: tarda décimas, no segundos)."""
    try:
        salida = subprocess.run(["schtasks", "/query", "/tn", TAREA, "/fo", "csv", "/v", "/nh"],
                                capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return {"existe": False}
    if salida.returncode != 0:
        return {"existe": False}
    texto = salida.stdout.decode("mbcs" if os.name == "nt" else "utf-8", errors="replace")
    fila = next(csv.reader(io.StringIO(texto.strip())), [])
    if len(fila) < 7:
        return {"existe": False}
    # columnas: equipo, nombre, próxima ejecución, estado, modo, última ejecución, último resultado…
    proxima, ultima = fila[2], fila[5]
    return {"existe": True, "proxima": proxima if "/" in proxima else "",
            "ultima": "" if "1999" in ultima or "/" not in ultima else ultima}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Piloto de actualidad: el vídeo de la noticia del día")
    parser.add_argument("orden", nargs="?", choices=("activar", "desactivar"))
    parser.add_argument("--ahora", action="store_true",
                        help="crearlo aunque el piloto esté desactivado o ya se haya llegado al máximo de hoy")
    args = parser.parse_args(argv)
    if args.orden == "activar":
        error = activar()
        print(error or f"✔ Tarea «{TAREA}» programada")
        return 1 if error else 0
    if args.orden == "desactivar":
        desactivar()
        print("✔ Piloto de actualidad desactivado")
        return 0
    config = configuracion()
    if not config.get("activo") and not args.ahora:
        registrar("Piloto de actualidad desactivado: no hago nada.")
        return 0
    try:
        return 0 if crear_video(config, forzar=args.ahora) else 2
    except Exception:  # que cualquier fallo quede registrado y avisado
        registrar("Error inesperado:\n" + traceback.format_exc())
        avisos.notificar("Mente Inquieta · error del piloto de actualidad", "Mira el registro en Ajustes.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
