"""Piloto automático: nada más encender el ordenador, hace y publica solo los vídeos del día.

Cada día, como mucho una vez cada uno:
  1. La EFEMÉRIDE de hoy (algo que pasó tal día como hoy), con dibujos. Se publica en cuanto está hecha: es del día.
  2. Un ACERTIJO con cuenta atrás, con dibujos.
  3. Un vídeo de FÚTBOL: la noticia de fútbol del día (algo que ya ha pasado, nunca previas ni rumores), con dibujos.
  4. Dos de ACTUALIDAD de España o geopolítica (con el radar y las salvaguardas de piloto_actualidad.py): una por
     la mañana o a mediodía y otra por la tarde, para que cada una sea de lo último.
En total, 5 vídeos al día. Es el único piloto: el antiguo «piloto de actualidad» queda dentro de este.

Cada vídeo se publica a su MEJOR HORA (FRANJAS): se sube a YouTube ya programado, así sale a su hora aunque el
ordenador esté apagado. Si su franja ya ha pasado, va a la siguiente franja buena del día; si no queda ninguna, ya.

Salvaguarda: un vídeo con datos (efeméride, fútbol) solo se publica si el verificador no marcó ninguna frase sin
respaldo; si marcó alguna, se intenta con otro tema y, si tampoco, queda en «Mis vídeos» esperando tu revisión.

La configuración está en piloto.json (se cambia desde el menú → Ajustes → Piloto automático).

Uso:
    python scripts/piloto.py             # hace lo que falte de hoy (si el piloto está activado)
    python scripts/piloto.py --ahora     # lo hace aunque esté desactivado
    python scripts/piloto.py --solo acertijo
    python scripts/piloto.py activar     # arranque con Windows + tarea diaria
    python scripts/piloto.py desactivar
"""
import argparse
import ctypes
import json
import os
import re
import socket
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
os.chdir(RAIZ)
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(errors="replace")

import avisos  # noqa: E402
import paso3_video  # noqa: E402
import piloto_actualidad as pa  # noqa: E402  (registro, ejecución de pasos y tareas de Windows)

CONFIG = RAIZ / "piloto.json"
ESTADO = RAIZ / "salida" / "_trabajo" / "piloto_estado.json"
CERROJO = RAIZ / "salida" / "_trabajo" / "piloto.lock"
TAREA = "Mente Inquieta - piloto automatico"
ACCESO = Path(os.getenv("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/MenteInquieta67 piloto.lnk"
TIPOS = {"efemeride": "Efeméride del día", "acertijo": "Acertijo", "futbol": "Fútbol"}
NOMBRES = {**TIPOS, "actualidad": "Actualidad", "actualidad_2": "Actualidad (tarde)"}
ACTUALIDAD_AL_DIA = 2
INTENTOS_NOTICIAS = 4  # noticias que se intentan al día como mucho (las que no pasan la verificación no cuentan)
SEGUNDA_NOTICIA_DESDE = 16  # hora: la segunda noticia del día se hace por la tarde, para que sea de lo último

# Las mejores horas para publicar Shorts con público de España (hora peninsular): al despertar y en el transporte,
# a la hora de comer, a la salida del trabajo o de clase y en el pico de la noche. Son reglas generales: con más
# datos del canal conviene ajustarlas con YouTube Studio → «Cuándo están conectados tus espectadores».
FRANJAS = ("08:30", "14:00", "17:30", "19:30", "21:30")
# La franja de cada vídeo: la efeméride, temprano («tal día como hoy» vale todo el día); la noticia de la mañana, a
# la hora de comer; el acertijo, por la tarde (se comenta con calma); el fútbol, antes de los partidos de la noche;
# la segunda noticia, en el pico de la noche.
FRANJA_DE = {"efemeride": "08:30", "actualidad": "14:00", "acertijo": "17:30", "futbol": "19:30", "actualidad_2": "21:30"}
MARGEN_MIN = 20       # una franja a menos de esto ya no da tiempo: se pasa a la siguiente
SEPARACION_MIN = 45   # dos vídeos no salen más juntos que esto

CONFIG_INICIAL = {
    "activo": False,
    "efemeride": True, "acertijo": True, "futbol": True, "actualidad": True,
    # Cuándo trabaja, además de al encender el ordenador: un rato antes de cada franja de publicación
    "revisiones": ["07:45", "12:45", "16:30", "20:15"],
}
BUSQUEDAS_FUTBOL = ["LaLiga", "Real Madrid", "FC Barcelona", "selección española fútbol", "Champions League",
                    "fichajes fútbol", "Atlético de Madrid"]
# Titulares que no son una noticia: previas, horarios, dónde verlo, rumores, quinielas, opinión.
NO_ES_NOTICIA = re.compile(
    r"horario|d[oó]nde ver|a qu[eé] hora|en directo|previa|alineaci[oó]n(?:es)? probable|posible once|pron[oó]stico|"
    r"apuesta|quiniela|rumor|podr[ií]a|estar[ií]a|interesa|suena para|sigue en vivo|minuto a minuto|c[oó]mo queda|"
    r"opini[oó]n|\bvs\.?\b|claves del", re.I)
PROMPT_FUTBOL = """Eres el editor de un canal español de Shorts de fútbol. De los TITULARES de hoy elige hasta 3
noticias de fútbol para un vídeo de 40 segundos, la mejor primero: resultados y goles importantes, fichajes
confirmados, récords, lesiones de estrellas, polémicas arbitrales, la selección.
SOLO cosas que YA HAN PASADO y que cuentan varios medios como un hecho (un partido ya jugado, un fichaje ya oficial,
una sanción ya impuesta). NUNCA previas de partidos que aún no se han jugado, horarios, dónde verlo, rumores de
fichajes, quinielas ni opiniones. Si no hay ninguna que valga, devuelve la lista vacía. No repitas lo YA CONTADO.
Responde SOLO con JSON: {"candidatas": [{"titular": "…", "busqueda": "3-6 palabras para buscarla en la prensa",
"motivo": "por qué engancha"}]}"""


def configuracion() -> dict:
    return {**CONFIG_INICIAL, **pa.leer_json(CONFIG, {})}


def guardar_configuracion(cambios: dict) -> dict:
    config = {**configuracion(), **cambios}
    pa.escribir_json(CONFIG, config)
    return config


def hechos_hoy() -> dict:
    """{tipo: nombre del guion} de lo que el piloto ya ha hecho hoy."""
    return pa.leer_json(ESTADO, {}).get(date.today().isoformat(), {})


def apuntar(tipo: str, nombre: str) -> None:
    estado = pa.leer_json(ESTADO, {})
    estado = {dia: v for dia, v in estado.items() if dia >= str(date.today().replace(day=1))}  # solo este mes
    estado.setdefault(date.today().isoformat(), {})[tipo] = nombre
    pa.escribir_json(ESTADO, estado)


def registrar(texto: str) -> None:
    pa.registrar(texto)


# --- Hacer un vídeo ---------------------------------------------------------------------------------

def _guiones_nuevos(desde: float) -> list:
    return sorted((r for r in paso3_video.CARPETA_GUIONES.glob("*.json") if r.stat().st_mtime >= desde),
                  key=lambda r: r.stat().st_mtime)


def montar(ruta: Path) -> bool:
    """Voz y vídeo de un guion."""
    if pa.ejecutar("paso2_audio.py", str(ruta)) == 1:
        return False
    return pa.ejecutar("paso3_video.py", str(paso3_video.CARPETA_AUDIO / ruta.stem), "--forzar") == 0


def mejor_hora(tipo: str, ahora: datetime = None):
    """La hora de hoy a la que debe salir un vídeo de ese tipo: su franja; si ya ha pasado o está ocupada, la
    siguiente franja buena libre; None si hoy ya no queda ninguna (entonces se publica al momento)."""
    import programados
    ahora = ahora or datetime.now()
    hoy = ahora.date()
    ocupadas = []
    for video in programados.leer()["videos"]:
        try:
            hora = datetime.strptime(video["hora"][:16], programados.FORMATO)
        except (KeyError, ValueError):
            continue
        if hora.date() == hoy:
            ocupadas.append(hora)
    franjas = [datetime.combine(hoy, datetime.strptime(f, "%H:%M").time()) for f in FRANJAS]
    propia = datetime.combine(hoy, datetime.strptime(FRANJA_DE.get(tipo, FRANJAS[0]), "%H:%M").time())
    # Primero la suya; después, las siguientes del día (y, si no, las anteriores que aún no hayan pasado)
    orden = [propia] + [f for f in franjas if f > propia] + [f for f in franjas if f < propia]
    for franja in orden:
        libre = all(abs((franja - o).total_seconds()) >= SEPARACION_MIN * 60 for o in ocupadas)
        if libre and (franja - ahora).total_seconds() >= MARGEN_MIN * 60:
            return franja
    return None


def publicar(tipo: str, ruta: Path, config: dict = None) -> bool:
    """Lo programa en YouTube a su mejor hora de hoy (o lo publica ya si no queda ninguna). False si tiene dudas."""
    import programados
    guion = json.loads(ruta.read_text(encoding="utf-8"))
    if guion.get("sin_respaldo"):
        return False
    guion["verificado"], guion["verificado_automatico"] = True, True
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    cuando = mejor_hora(tipo)
    try:
        programados.anadir(ruta.stem, (cuando or datetime.now()).strftime(programados.FORMATO))
        if not cuando:
            programados.publicar_ya(ruta.stem)
        programados.revisar()  # lo sube ya a YouTube, programado: sale a su hora aunque se apague el ordenador
    except Exception as error:  # noqa: BLE001 — el vídeo está hecho: se publica a mano desde el menú
        registrar(f"No se pudo programar «{guion.get('titulo')}»: {error}")
        avisos.notificar("MenteInquieta67 · no se pudo publicar", f"«{guion.get('titulo')}» está hecho; publícalo desde Mis vídeos.")
        return True
    registrar(f"✔ {NOMBRES.get(tipo, tipo)}: «{guion.get('titulo')}» → "
              + (f"programado para las {cuando:%H:%M}" if cuando else "ya no quedan franjas hoy: se publica ahora"))
    return True


def _hacer(tipo: str, config: dict, crear_guion, intentos: int = 2) -> bool:
    """Crea el guion con `crear_guion()` (devuelve su ruta o None), lo monta y lo publica. Con dudas, otro intento."""
    for intento in range(intentos):
        ruta = crear_guion()
        if not ruta:
            return False
        if not montar(ruta):
            avisos.notificar("MenteInquieta67 · piloto automático", f"No se pudo montar el vídeo de {TIPOS[tipo].lower()}.")
            return False
        apuntar(tipo, ruta.stem)
        if publicar(tipo, ruta, config):
            return True
        guion = json.loads(ruta.read_text(encoding="utf-8"))
        registrar(f"«{guion.get('titulo')}» tiene {len(guion['sin_respaldo'])} frase(s) sin respaldo: no se publica solo."
                  + (" Pruebo con otro tema." if intento + 1 < intentos else ""))
    avisos.notificar("MenteInquieta67 · revisa un vídeo",
                     f"El de {TIPOS[tipo].lower()} de hoy tiene frases dudosas: está en Mis vídeos esperando tu revisión.")
    return False


def _guion_efemeride():
    inicio = time.time() - 1
    # --fecha-confirmada: solo hechos cuyo artículo dice que pasaron tal día como hoy (la lista de Wikipedia falla)
    pa.ejecutar("paso1_guiones.py", "--fecha", date.today().isoformat(), "--cantidad", "1", "--sin-repetir",
                "--fecha-confirmada", "--idiomas", "es")
    nuevos = _guiones_nuevos(inicio)
    return nuevos[-1] if nuevos else None


def _guion_acertijo():
    inicio = time.time() - 1
    pa.ejecutar("acertijos.py", "--cantidad", "1")
    nuevos = _guiones_nuevos(inicio)
    return nuevos[-1] if nuevos else None


def _futbol_contado(dias: int = 4) -> list:
    limite = date.fromordinal(date.today().toordinal() - dias).isoformat()
    titulos = []
    for ruta in paso3_video.CARPETA_GUIONES.glob("*_actualidad_*.json"):
        guion = pa.leer_json(ruta, {})
        if guion.get("futbol") and guion.get("fecha", "") >= limite:
            titulos.append(guion.get("titulo", ""))
    return titulos


def _guion_futbol():
    import actualidad
    import paso1_guiones
    import radar
    titulares = [(medio, titular) for medio, titular in radar.titulares_bing(BUSQUEDAS_FUTBOL)
                 if not NO_ES_NOTICIA.search(titular)]
    if not titulares:
        registrar("Fútbol: no hay titulares ahora.")
        return None
    datos = "TITULARES:\n" + "\n".join(f"- {medio}: {titular}" for medio, titular in titulares[:80])
    datos += "\n\nYA CONTADO:\n" + ("\n".join(f"- {t}" for t in _futbol_contado()) or "- (nada)")
    try:
        candidatas = json.loads(paso1_guiones.llamar_groq(
            os.getenv("GROQ_API_KEY", ""), os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO, PROMPT_FUTBOL,
            datos)).get("candidatas", [])
    except (ValueError, AttributeError):
        candidatas = []
    for candidata in candidatas[:3]:
        if (not isinstance(candidata, dict) or not candidata.get("busqueda")
                or NO_ES_NOTICIA.search(str(candidata.get("titular", "")))):
            continue
        registrar(f"Fútbol, candidata: {candidata.get('titular')}")
        busqueda = actualidad.buscar(str(candidata["busqueda"]), dias=2)
        reconocidos = [i for i, a in enumerate(busqueda["articulos"]) if a["reconocido"]]
        if len({busqueda["articulos"][i]["medio"] for i in reconocidos}) < 2:
            registrar("    descartada: la cuentan menos de 2 medios reconocidos")
            continue
        inicio = time.time() - 1
        pa.ejecutar("paso1_guiones.py", "--actualidad", busqueda["id"], "--articulos",
                    ",".join(map(str, reconocidos[:5])), "--idiomas", "es")
        nuevos = _guiones_nuevos(inicio)
        if nuevos:
            guion = json.loads(nuevos[-1].read_text(encoding="utf-8"))
            # Su estilo (dibujos, o fotos y dibujos) se elige en Ajustes → Estilo de los Shorts
            guion.update(futbol=True, personaje="futbolista")
            if "#futbol" not in [h.lower() for h in guion.get("hashtags", [])]:
                guion["hashtags"] = ["#futbol", *guion.get("hashtags", [])][:5]
            nuevos[-1].write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
            return nuevos[-1]
    registrar("Fútbol: ninguna noticia con medios suficientes ahora; se vuelve a mirar en la próxima revisión.")
    return None


CREADORES = {"efemeride": _guion_efemeride, "acertijo": _guion_acertijo, "futbol": _guion_futbol}


# --- El día --------------------------------------------------------------------------------------------

def _esperar_internet(minutos: int = 5) -> bool:
    """Al encender, la wifi tarda: espera a que haya conexión."""
    for _ in range(minutos * 6):
        try:
            socket.create_connection(("api.groq.com", 443), timeout=5).close()
            return True
        except OSError:
            time.sleep(10)
    return False


def _es_mi_turno() -> bool:
    """Solo un piloto a la vez (el del arranque y el de la tarea diaria pueden coincidir)."""
    try:
        if CERROJO.exists() and time.time() - CERROJO.stat().st_mtime < 3 * 3600:
            return False
        CERROJO.parent.mkdir(parents=True, exist_ok=True)
        CERROJO.write_text(str(os.getpid()))
        return True
    except OSError:
        return True


def trabajar(config: dict, solo: str = "") -> None:
    if hasattr(ctypes, "windll"):  # que el ordenador no se suspenda mientras trabaja
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    if not _esperar_internet():
        registrar("Piloto automático: no hay internet; lo intento en la próxima revisión.")
        return
    registrar("=== Piloto automático: los vídeos de hoy ===")
    for tipo in TIPOS:
        if (solo and tipo != solo) or not config.get(tipo):
            continue
        if tipo in hechos_hoy() and not solo:
            registrar(f"{TIPOS[tipo]}: ya está hecho hoy.")
            continue
        try:
            # Con frases dudosas se prueba con otro tema (el acertijo no tiene datos que verificar)
            _hacer(tipo, config, CREADORES[tipo], intentos={"efemeride": 3, "futbol": 2}.get(tipo, 1))
        except Exception:  # un fallo en uno no para los demás
            registrar(f"Error con {TIPOS[tipo].lower()}:\n" + traceback.format_exc())
    if config.get("actualidad") and not solo:
        try:
            _actualidad()
        except Exception:
            registrar("Error con la actualidad:\n" + traceback.format_exc())
    if not solo:
        _liberar_espacio(config)
    registrar("=== Piloto automático: hecho por ahora ===")


def _liberar_espacio(config: dict) -> None:
    """Una vez al día: borra del ordenador lo de los vídeos publicados hace más de «limpieza_dias» (ver limpieza.py)."""
    dias = int(config.get("limpieza_dias", 7) or 0)
    estado = pa.leer_json(ESTADO, {})
    if dias <= 0 or estado.get("limpieza") == date.today().isoformat():
        return
    try:
        import limpieza
        r = limpieza.limpiar(dias)
        if r["archivos"]:
            registrar(f"Espacio liberado: {r['megas']} MB ({r['videos']} vídeos publicados hace más de {dias} días; "
                      "siguen en YouTube).")
    except Exception:
        registrar("Error al liberar espacio:\n" + traceback.format_exc())
    estado = pa.leer_json(ESTADO, {})
    estado["limpieza"] = date.today().isoformat()
    pa.escribir_json(ESTADO, estado)


def noticias_hoy() -> list:
    """Las noticias que el piloto ha convertido en vídeo hoy."""
    hoy = date.today().isoformat()
    return [c for c in pa.contados(0) if c["fecha"] == hoy]


def _actualidad() -> None:
    """La noticia que toque ahora: la primera del día, a cualquier hora; la segunda, por la tarde."""
    # Cuentan las que han salido: una noticia que se quedó en «revísalo» no ocupa su hueco, se prueba con otra
    # (como mucho INTENTOS_NOTICIAS al día, para no gastar el cupo de la IA en un mal día).
    intentos = noticias_hoy()
    hechas = len([n for n in intentos if n.get("publicado")])
    if hechas >= ACTUALIDAD_AL_DIA:
        registrar("Actualidad: ya están las dos noticias de hoy.")
        return
    if len(intentos) >= INTENTOS_NOTICIAS:
        registrar(f"Actualidad: ya se han intentado {len(intentos)} noticias hoy; no se prueban más.")
        return
    if hechas == 1 and datetime.now().hour < SEGUNDA_NOTICIA_DESDE:
        registrar(f"Actualidad: la segunda noticia se hace a partir de las {SEGUNDA_NOTICIA_DESDE}:00.")
        return
    tipo = "actualidad" if hechas == 0 and datetime.now().hour < SEGUNDA_NOTICIA_DESDE else "actualidad_2"
    pa.crear_video({**pa.configuracion(), "max_dia": INTENTOS_NOTICIAS},
                   publicar_con=lambda nombre, ruta, guion: _publicar_noticia(tipo, ruta, guion))


def _publicar_noticia(tipo: str, ruta: Path, guion: dict) -> bool:
    if publicar(tipo, ruta):
        return True
    registrar(f"NO se publica «{guion.get('titulo')}»: el verificador marcó {len(guion.get('sin_respaldo', []))} frase(s).")
    avisos.notificar("MenteInquieta67 · revisa la noticia de hoy",
                     f"«{guion.get('titulo')}» tiene frases dudosas: está en Mis vídeos esperando tu revisión.")
    return False


def noticia_publicada(nombre: str) -> None:
    """Apunta que una noticia que estaba esperando revisión ya ha salido (la has aprobado tú)."""
    estado = pa.leer_json(pa.ESTADO, {})
    for contado in estado.get("contados", []):
        if contado.get("nombre") == nombre:
            contado["publicado"] = True
    pa.escribir_json(pa.ESTADO, estado)


def descartar(nombre: str) -> None:
    """Quita de «hoy» un vídeo que no quieres: el piloto podrá hacer otro en su lugar en la próxima revisión."""
    ruta = paso3_video.CARPETA_GUIONES / f"{nombre}.json"
    guion = pa.leer_json(ruta, {})
    if guion:
        guion["descartado"] = True
        pa.escribir_json(ruta, guion)
    estado = pa.leer_json(ESTADO, {})
    hoy = estado.get(date.today().isoformat(), {})
    for tipo in [t for t, n in hoy.items() if n == nombre]:
        del hoy[tipo]
    pa.escribir_json(ESTADO, estado)


def resumen_hoy() -> list:
    """Para el panel: los 5 vídeos de hoy con su estado ({tipo, nombre, titulo, estado, hora, url})."""
    import programados
    config, hechos = configuracion(), hechos_hoy()
    cola = {v["nombre"]: v for v in programados.leer()["videos"]}
    def vale(nombre) -> bool:  # ni descartado ni borrado desde la app
        guion = pa.leer_json(paso3_video.CARPETA_GUIONES / f"{nombre}.json", None)
        return bool(guion) and not guion.get("descartado")

    noticias = sorted((n for n in noticias_hoy() if vale(n["nombre"])),
                      key=lambda n: not n.get("publicado"))  # las que han salido, primero
    filas = [(t, hechos.get(t) if hechos.get(t) and vale(hechos[t]) else None) for t in TIPOS if config.get(t)]
    if config.get("actualidad"):
        filas += [(f"actualidad{'_2' if i else ''}", noticias[i]["nombre"] if i < len(noticias) else None)
                  for i in range(ACTUALIDAD_AL_DIA)]
    resumen = []
    for tipo, nombre in filas:
        fila = {"tipo": tipo, "que": NOMBRES[tipo], "nombre": nombre, "franja": FRANJA_DE[tipo], "estado": "pendiente",
                "titulo": "", "hora": "", "url": "", "dudas": []}
        if nombre:
            guion = pa.leer_json(paso3_video.CARPETA_GUIONES / f"{nombre}.json", {})
            video = cola.get(nombre) or {}
            yt = guion.get("youtube") or {}
            fila["titulo"] = guion.get("titulo", nombre)
            fila["hora"] = (video.get("hora") or yt.get("publicar_el") or "")[11:16]
            fila["url"] = yt.get("url", "")
            if guion.get("sin_respaldo") and not yt:
                fila["estado"] = "revisar"
                fila["dudas"] = [{"frase": d.get("frase", ""), "motivo": d.get("motivo", "")}
                                 for d in guion["sin_respaldo"]]
            elif video.get("estado") == "error":
                fila["estado"] = "error"
            elif yt and (not fila["hora"] or fila["hora"] <= datetime.now().strftime("%H:%M")):
                fila["estado"] = "publicado"
            elif video or yt:
                fila["estado"] = "programado"
            else:
                fila["estado"] = "hecho"
        resumen.append(fila)
    return sorted(resumen, key=lambda f: f["hora"] or f["franja"])


# --- Arranque con Windows ------------------------------------------------------------------------------

_ACCESO = r"""
$acceso = (New-Object -ComObject WScript.Shell).CreateShortcut($env:T_LNK)
$acceso.TargetPath = $env:T_EXE
$acceso.Arguments = '"' + $env:T_SCRIPT + '"'
$acceso.WorkingDirectory = $env:T_DIR
$acceso.Description = 'Piloto automatico de MenteInquieta67: hace los videos del dia al encender'
$acceso.Save()
"""


def activar() -> str:
    """Arranque con Windows (acceso en la carpeta Inicio), tarea diaria de repaso y actualidad a 2 al día."""
    config = guardar_configuracion({"activo": True})
    ejecutable = pa.PYTHONW if pa.PYTHONW.exists() else Path(sys.executable)
    comun = {"T_EXE": ejecutable, "T_SCRIPT": Path(__file__).resolve(), "T_DIR": RAIZ}
    errores = []
    resultado = pa._powershell(_ACCESO, T_LNK=ACCESO, **comun)
    if resultado.returncode != 0:
        errores.append(resultado.stderr.strip()[-200:])
    resultado = pa._powershell(pa._REGISTRAR, T_HORAS=",".join(config["revisiones"]), T_NOMBRE=TAREA,
                               T_DESC="Hace y publica los videos del dia de MenteInquieta67.", **comun)
    if resultado.returncode != 0:
        errores.append(resultado.stderr.strip()[-200:])
    pa.desactivar()  # el piloto de actualidad antiguo ya no va por su cuenta: sus noticias las hace este
    return " · ".join(e for e in errores if e)


def desactivar() -> None:
    guardar_configuracion({"activo": False})
    ACCESO.unlink(missing_ok=True)
    pa._powershell(pa._BORRAR, T_NOMBRE=TAREA)


def arranca_con_windows() -> bool:
    return ACCESO.exists()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Piloto automático: los vídeos del día")
    parser.add_argument("orden", nargs="?", choices=("activar", "desactivar"))
    parser.add_argument("--ahora", action="store_true", help="aunque el piloto esté desactivado")
    parser.add_argument("--solo", choices=tuple(TIPOS), default="", help="solo ese vídeo (aunque ya esté hecho hoy)")
    args = parser.parse_args(argv)
    if args.orden == "activar":
        error = activar()
        print(error or "✔ Piloto automático activado: arranca al encender el ordenador")
        return 1 if error else 0
    if args.orden == "desactivar":
        desactivar()
        print("✔ Piloto automático desactivado")
        return 0
    config = configuracion()
    if not config.get("activo") and not (args.ahora or args.solo):
        return 0
    if not _es_mi_turno():
        registrar("Piloto automático: ya hay otro trabajando.")
        return 0
    try:
        trabajar(config, args.solo)
        return 0
    except Exception:
        registrar("Error inesperado del piloto automático:\n" + traceback.format_exc())
        avisos.notificar("MenteInquieta67 · error del piloto automático", "Mira el registro en Ajustes.")
        return 2
    finally:
        CERROJO.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
