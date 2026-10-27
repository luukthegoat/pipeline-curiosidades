"""Menú web del pipeline de vídeos de curiosidades históricas.

Ábrelo con doble clic en «Abrir menu.bat». Se abre en tu navegador en
http://127.0.0.1:8765 y solo es accesible desde tu ordenador.
"""
import asyncio
import itertools
import json
import os
import socket
import subprocess
import sys
import hashlib
import threading
import time
import webbrowser
from urllib.parse import urlparse
from datetime import date, datetime
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

RAIZ = Path(__file__).resolve().parent.parent  # carpeta principal del proyecto
os.chdir(RAIZ)  # los pasos usan rutas relativas a la carpeta principal
SCRIPTS = RAIZ / "scripts"  # los pasos y módulos del programa
sys.path.insert(0, str(SCRIPTS))
import musica  # noqa: E402
import paso3_video  # noqa: E402  (nombres, carpetas e imágenes de los vídeos)
import wikimedia  # noqa: E402  (acceso a Wikimedia con caché y ritmo controlado)
import paso1_guiones  # noqa: E402  (estado del cupo diario de Groq)
import subir_youtube  # noqa: E402  (subida a YouTube Shorts)
import programados  # noqa: E402  (cola de publicaciones programadas)
import horarios  # noqa: E402  (horas recomendadas para publicar)
import borrar  # noqa: E402  (borrar un vídeo y todo lo suyo)
import actualidad  # noqa: E402  (noticias recientes para los vídeos de actualidad)
import video_ia  # noqa: E402  (vídeos hechos con clips de una IA de vídeo)
import piloto_actualidad  # noqa: E402  (vídeo de la noticia del día, solo y con salvaguarda)
import instagram  # noqa: E402  (publicar los vídeos como Reels)

GUIONES = RAIZ / "salida" / "guiones"
AUDIO = RAIZ / "salida" / "audio"
VIDEOS = RAIZ / "salida" / "videos"
PROPIAS = RAIZ / "salida" / "imagenes_propias"
MINIATURAS = RAIZ / "salida" / "cache_miniaturas"  # miniaturas de la página de imágenes
MUESTRA = RAIZ / "salida" / "_trabajo" / "muestra_voz.mp3"
ENV = RAIZ / ".env"
PUERTO = int(os.getenv("MENU_PUERTO") or 8765)
EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 400 * 1024 * 1024  # imágenes y clips de vídeo subidos: 400 MB como mucho


# --- Cola de tareas: se ejecutan una detrás de otra --------------------------------------

class Trabajo:
    """Una tarea (generar guiones, audio, vídeo…) con su salida para mostrarla en la web."""

    _ids = itertools.count(1)

    def __init__(self, titulo: str, funcion):
        self.id = next(self._ids)
        self.titulo = titulo
        self.funcion = funcion
        self.estado = "en cola"  # en cola · en curso · terminada · con errores · cancelada
        self.lineas = []
        self.resultado = []  # guiones creados o tratados, para enlazarlos al terminar
        self.proceso = None
        self.cerrojo = threading.Lock()

    def escribir(self, texto: str) -> None:
        with self.cerrojo:
            self.lineas.append(texto.rstrip("\n"))

    def ejecutar(self, script: str, *argumentos: str) -> int:
        if self.estado == "cancelada":
            return 1
        self.escribir(f"▶ {script} {' '.join(argumentos)}")
        entorno = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        self.proceso = subprocess.Popen(
            [sys.executable, str(SCRIPTS / script), *argumentos],
            cwd=RAIZ, env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for linea in self.proceso.stdout:
            self.escribir(linea)
        codigo = self.proceso.wait()
        self.escribir(f"{'✔' if codigo == 0 else '⚠'} {script} terminó (código {codigo})\n")
        return codigo

    def resumen(self) -> dict:
        return {"id": self.id, "titulo": self.titulo, "estado": self.estado}


class Cola:
    def __init__(self):
        self.cerrojo = threading.Lock()
        self.trabajos = []
        self.hilo = None

    def anadir(self, titulo: str, funcion) -> Trabajo:
        trabajo = Trabajo(titulo, funcion)
        with self.cerrojo:
            self.trabajos.append(trabajo)
            self.trabajos = self.trabajos[-30:]  # historial corto
            if not (self.hilo and self.hilo.is_alive()):
                self.hilo = threading.Thread(target=self._trabajar, daemon=True)
                self.hilo.start()
        return trabajo

    def _trabajar(self) -> None:
        while True:
            with self.cerrojo:
                trabajo = next((t for t in self.trabajos if t.estado == "en cola"), None)
                if trabajo is None:
                    self.hilo = None
                    return
                trabajo.estado = "en curso"
            try:
                ok = trabajo.funcion(trabajo)
                if trabajo.estado == "en curso":
                    trabajo.estado = "terminada" if ok else "con errores"
            except Exception as error:  # que un fallo inesperado se vea en la web
                trabajo.escribir(f"Error inesperado: {error}")
                trabajo.estado = "con errores"

    def buscar(self, id_trabajo) -> Trabajo:
        return next((t for t in self.trabajos if t.id == id_trabajo), None)

    def activos(self) -> list:
        return [t for t in self.trabajos if t.estado in ("en cola", "en curso")]

    def en_curso(self) -> bool:
        return bool(self.activos())

    def principal(self):
        """El trabajo a mostrar: el que está en marcha o, si no, el último."""
        return next((t for t in self.trabajos if t.estado == "en curso"), None) or (
            self.trabajos[-1] if self.trabajos else None)

    def cancelar(self, id_trabajo) -> None:
        trabajo = self.buscar(id_trabajo)
        if not trabajo or trabajo.estado not in ("en cola", "en curso"):
            return
        proceso, trabajo.estado = trabajo.proceso, "cancelada"
        if proceso and proceso.poll() is None:
            proceso.terminate()


cola = Cola()


def contar_pendientes() -> int:
    """Guiones que aún no están en YouTube ni programados."""
    en_cola = programados.por_guion()
    total = 0
    for ruta in GUIONES.glob("*.json") if GUIONES.exists() else []:
        try:
            if ruta.stem not in en_cola and not json.loads(ruta.read_text(encoding="utf-8")).get("youtube"):
                total += 1
        except (OSError, ValueError):
            continue
    return total


@app.context_processor
def contexto_global():
    hasta = wikimedia.en_espera_hasta()
    sin_cupo = paso1_guiones.cupos_agotados()
    principal = os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO
    modelos = [principal, *paso1_guiones.MODELOS_RESERVA]
    cupo = {
        "principal": time.strftime("%H:%M", time.localtime(sin_cupo[principal])) if principal in sin_cupo else "",
        "todos": all(m in sin_cupo for m in modelos),
        "libera": time.strftime("%H:%M", time.localtime(min(sin_cupo.values()))) if sin_cupo else "",
    }
    return {"cola": cola, "espera_wikipedia": time.strftime("%H:%M", time.localtime(hasta)) if hasta else "",
            "cupo_groq": cupo,
            "num_programados": len(programados.por_guion()),
            "num_pendientes": contar_pendientes(),
            "errores_programados": [v for v in programados.leer()["videos"] if v["estado"] == "error"],
            # Cambia al editar el CSS: así el navegador (o la ventana de la app) no usa una copia vieja.
            "version_css": int((Path(app.static_folder) / "estilo.css").stat().st_mtime)}


def producir(t: Trabajo, nombres: list) -> bool:
    """Audio (paso 2: solo escenas cambiadas) y vídeo (paso 3: solo escenas cambiadas) de los guiones."""
    if not nombres:
        t.escribir("No hay guiones que procesar.")
        return False
    if t.ejecutar("paso2_audio.py", *[str(GUIONES / f"{n}.json") for n in nombres]) == 1:
        return False
    con_audio = [str(AUDIO / n) for n in nombres if (AUDIO / n / "escenas.json").exists()]
    if t.ejecutar("paso3_video.py", *con_audio, "--forzar") != 0:
        return False
    # Los que no tienen nada que revisar se dan por revisados y se programan solos (Ajustes → Programar solos).
    hechos = programados.programar_sin_avisos(nombres)
    for titulo, hora in hechos:
        t.escribir(f"✔ Sin avisos del verificador: «{titulo}» queda revisado y programado para el {hora}.")
    if hechos:
        despertar_programados()
    return True


# --- Datos de los guiones -----------------------------------------------------

def ruta_guion(nombre: str) -> Path:
    ruta = (GUIONES / f"{nombre}.json").resolve()
    if ruta.parent != GUIONES.resolve() or not ruta.exists():
        abort(404)
    return ruta


def leer(nombre: str) -> dict:
    return json.loads(ruta_guion(nombre).read_text(encoding="utf-8"))


def escribir(nombre: str, datos: dict) -> None:
    ruta_guion(nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def ruta_video(datos: dict):
    """Ruta absoluta del vídeo de un guion, o None si aún no tiene."""
    if not datos.get("video"):
        return None
    ruta = (RAIZ / datos["video"]).resolve()
    return ruta if ruta.exists() and VIDEOS.resolve() in ruta.parents else None


_estadisticas = {"mtime": None, "datos": {}}


def estadisticas_youtube() -> dict:
    """Vistas y «me gusta» de cada vídeo subido (las guarda la vigilancia cada 15 min); se relee si cambian."""
    try:
        mtime = subir_youtube.ESTADISTICAS.stat().st_mtime
    except OSError:
        return {"actualizado": "", "videos": {}}
    if subir_youtube.RETENCION.exists():
        mtime = (mtime, subir_youtube.RETENCION.stat().st_mtime)
    if _estadisticas["mtime"] != mtime:
        _estadisticas.update(mtime=mtime, datos=subir_youtube.estadisticas())
    return _estadisticas["datos"]


@app.template_filter("miles")
def miles(numero) -> str:
    """12345 → «12.345»."""
    return f"{int(numero or 0):,}".replace(",", ".")


def resumen(ruta: Path) -> dict:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    nombre = ruta.stem
    audio = AUDIO / nombre / "escenas.json"
    duracion = None
    if audio.exists():
        try:
            duracion = json.loads(audio.read_text(encoding="utf-8"))["audio"]["duracion_total_s"]
        except (ValueError, KeyError):
            pass
    video = ruta_video(datos)
    return {
        "nombre": nombre,
        "titulo": datos.get("titulo", nombre),
        "idioma": datos.get("idioma", "?"),
        "anio": datos.get("anio_evento") or "tema",
        "fecha": datos.get("fecha", ""),
        "verificado": bool(datos.get("verificado")),
        "dudas": len(datos.get("sin_respaldo", [])),
        "audio": audio.exists(),
        "duracion": duracion,
        "video": bool(video),
        "miniatura": bool(video and paso3_video.ruta_miniatura(video).exists()),
        "youtube": datos.get("youtube"),
        "estadisticas": estadisticas_youtube()["videos"].get((datos.get("youtube") or {}).get("id")),
        "modificado": ruta.stat().st_mtime,
        "serie": datos.get("serie"),
        "programado": programados.por_guion().get(nombre),
        "tipo": horarios.tipo_de(datos),
    }


def todos() -> list:
    if not GUIONES.exists():
        return []
    guiones = []
    for ruta in GUIONES.glob("*.json"):
        try:
            guiones.append(resumen(ruta))
        except (OSError, ValueError):
            continue

    # Más recientes primero, pero las partes de una misma serie juntas y en orden (1, 2, 3…).
    def grupo(g):
        serie = g["serie"]
        return (serie["tema"], g["idioma"], g["fecha"]) if serie else g["nombre"]

    reciente = {}
    for g in guiones:
        reciente[grupo(g)] = max(reciente.get(grupo(g), 0), g["modificado"])
    return sorted(
        guiones,
        key=lambda g: (-reciente[grupo(g)], str(grupo(g)), g["serie"]["parte"] if g["serie"] else 0),
    )


# --- Ajustes de voz (.env) ------------------------------------------------------

def leer_env() -> dict:
    valores = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                clave, valor = linea.split("=", 1)
                valores[clave.strip()] = valor.strip()
    return valores


def guardar_env(cambios: dict) -> None:
    """Cambia (o añade) claves del .env sin tocar el resto, y las aplica al menú."""
    lineas = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    pendientes = dict(cambios)
    for i, linea in enumerate(lineas):
        clave = linea.split("=", 1)[0].strip()
        if "=" in linea and not linea.lstrip().startswith("#") and clave in pendientes:
            lineas[i] = f"{clave}={pendientes.pop(clave)}"
    lineas += [f"{clave}={valor}" for clave, valor in pendientes.items()]
    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.environ.update(cambios)  # para que los pasos lanzados desde el menú usen ya los nuevos


_voces = []


def voces() -> list:
    """Voces de edge-tts en español e inglés (se piden una vez a Microsoft)."""
    global _voces
    if not _voces:
        import edge_tts
        try:
            todas = asyncio.run(edge_tts.list_voices())
        except Exception:
            return []
        _voces = sorted(
            ({"id": v["ShortName"], "idioma": v["Locale"], "genero": "mujer" if v["Gender"] == "Female" else "hombre"}
             for v in todas if v["Locale"].startswith(("es-", "en-"))),
            key=lambda v: (v["idioma"], v["id"]),
        )
    return _voces


# --- Páginas ----------------------------------------------------------------------

@app.route("/")
def inicio():
    return render_template("inicio.html", recientes=todos()[:3], hoy=date.today().isoformat(),
                           herramientas=video_ia.HERRAMIENTAS, estilos=video_ia.NOMBRES_ESTILOS)


FILTROS = {"todos": "Todos", "revisar": "Por revisar", "listos": "Listos", "programados": "Programados",
           "publicados": "Publicados"}


def apartado(g: dict) -> str:
    """En qué filtro de «Mis vídeos» cae un guion."""
    if g["programado"]:
        return "programados"
    if g["youtube"]:
        return "publicados"
    return "listos" if g["verificado"] else "revisar"


def resumen_del_dia() -> dict:
    """Lo que sale hoy, lo siguiente que sale y cuántas subidas quedan (para la cabecera de «Mis vídeos»)."""
    ahora = datetime.now()
    hoy = ahora.date().isoformat()
    videos = sorted(programados.leer()["videos"], key=lambda v: v["hora"])
    de_hoy = [{**v, "hhmm": v["hora"][11:16], "pasada": v["hora"][:16] <= ahora.strftime("%Y-%m-%dT%H:%M")}
              for v in videos if v["hora"][:10] == hoy]
    siguiente = next((v for v in videos if v["hora"][:10] > hoy), None)
    return {
        "hoy": de_hoy,
        "siguiente": {**siguiente, "bonita": programados.formato_bonito(siguiente["hora"])} if siguiente else None,
        "subidas": programados.subidas_ultimas_24h(),
        "max": programados.MAX_SUBIDAS_DIA,
    }


@app.route("/videos")
def mis_videos():
    guiones = todos()
    for g in guiones:
        g["apartado"] = apartado(g)
    cuantos = {clave: sum(1 for g in guiones if clave == "todos" or g["apartado"] == clave) for clave in FILTROS}
    ver = request.args.get("ver") or ("revisar" if cuantos["revisar"] else "todos")
    if ver not in FILTROS:
        ver = "todos"
    lista = [g for g in guiones if ver == "todos" or g["apartado"] == ver]
    if ver == "publicados" and request.args.get("orden") == "vistas":
        lista.sort(key=lambda g: -(g["estadisticas"] or {}).get("vistas", 0))
    if ver == "publicados" and request.args.get("orden") == "retencion":
        lista.sort(key=lambda g: -((g["estadisticas"] or {}).get("se_quedan") or -1))
    stats = estadisticas_youtube()
    vistas = {"total": sum(v["vistas"] for v in stats["videos"].values()),
              "actualizado": stats["actualizado"][:16].replace("T", " a las ") if stats["actualizado"] else ""}
    # Retención media del canal (ponderada por vistas) y si falta permiso o la API para traerla.
    con_ret = [v for v in stats["videos"].values() if v.get("se_quedan") is not None and v["vistas"]]
    total_ret = sum(v["vistas"] for v in con_ret)
    vistas["se_quedan"] = round(sum(v["se_quedan"] * v["vistas"] for v in con_ret) / total_ret) if total_ret else None
    con_pct = [v for v in stats["videos"].values() if v.get("visto_pct") and v["vistas"]]
    total_pct = sum(v["vistas"] for v in con_pct)
    vistas["visto_pct"] = round(sum(v["visto_pct"] * v["vistas"] for v in con_pct) / total_pct) if total_pct else None
    vistas["error_retencion"] = subir_youtube.retencion().get("error", "")
    sin_youtube = [g["nombre"] for g in lista if g["apartado"] in ("revisar", "listos") and g["video"]]
    return render_template(
        "videos.html", guiones=lista, ver=ver, filtros=FILTROS, cuantos=cuantos, dia=resumen_del_dia(),
        vistas=vistas, orden=request.args.get("orden", ""),
        recomendadas=horarios.recomendar(sin_youtube) if sin_youtube else {},
        con_dudas=sum(1 for g in guiones if g["apartado"] == "revisar" and g["dudas"]),
        mensaje=request.args.get("mensaje", ""), error=request.args.get("error", ""),
        yt_conectado=subir_youtube.TOKEN.exists(),
    )


def volver_a(nombre: str, mensaje: str = "", error: str = ""):
    """Tras una acción, vuelve a «Mis vídeos» (con su filtro) si se lanzó desde allí, o a la página del vídeo."""
    if request.form.get("volver") == "videos":
        return redirect(url_for("mis_videos", ver=request.form.get("ver") or None,
                                mensaje=mensaje or None, error=error or None))
    return redirect(url_for("ver_guion", nombre=nombre, mensaje=error or mensaje))


@app.post("/crear")
def crear():
    modo = request.form.get("modo", "tema")
    tema = request.form.get("tema", "").strip()
    fecha = request.form.get("fecha") or date.today().isoformat()
    cantidad = request.form.get("cantidad", "1")
    partes = request.form.get("partes", "1")
    partes = partes if partes.isdigit() and 1 <= int(partes) <= 10 else "1"
    idiomas = ",".join(request.form.getlist("idiomas")) or "es"
    completo = request.form.get("completo") == "on"
    personaje = request.form.get("personaje", "").strip()
    problema = request.form.get("problema", "").strip()
    dia = request.form.get("dia", "").strip()
    if modo == "actualidad":
        noticia = request.form.get("noticia", "").strip()
        if not noticia:
            return redirect(url_for("inicio", error="Escribe de qué noticia quieres el vídeo."))
        return redirect(url_for("ver_actualidad", tema=noticia, dias=request.form.get("dias", "3"),
                                mas=request.form.get("mas_idiomas", "")))
    if modo == "video_ia":
        tematica = request.form.get("tematica", "").strip()
        if not tematica:
            return redirect(url_for("inicio", error="Escribe la temática del vídeo con IA."))
        herramienta = request.form.get("herramienta", "veo")
        argumentos = ["--video-ia", tematica, "--herramienta", herramienta,
                      "--estilo", request.form.get("estilo", "cine"), "--idiomas", idiomas]
        if request.form.get("voz") in ("ia", "app"):
            argumentos += ["--voz", request.form["voz"]]
        # Solo el guion: los clips los generas tú con los prompts y luego se monta el vídeo.
        return lanzar_guiones(f"Vídeo con IA ({video_ia.herramienta(herramienta)['nombre']}): «{tematica}»",
                              argumentos, False)
    if modo == "tema" and not tema:
        return redirect(url_for("inicio", error="Escribe un tema para el vídeo."))
    if modo == "diario" and not personaje:
        return redirect(url_for("inicio", error="Escribe el personaje del diario."))

    if modo == "tema":
        argumentos = ["--tema", tema, "--partes", partes]
        titulo = f"Serie de {partes} vídeos sobre «{tema}»" if partes != "1" else f"Vídeo sobre «{tema}»"
    elif modo == "diario":
        argumentos = ["--diario", personaje, "--problema", problema]
        if dia.isdigit() and int(dia) > 0:
            argumentos += ["--dia", dia]
        titulo = f"Diario de «{personaje}»" + (f" · día {dia}" if dia.isdigit() else " · día siguiente")
    else:
        argumentos = ["--fecha", fecha, "--cantidad", cantidad]
        titulo = f"Efemérides del {fecha}"
    argumentos += ["--idiomas", idiomas]

    return lanzar_guiones(titulo, argumentos, completo)


def lanzar_guiones(titulo: str, argumentos: list, completo: bool):
    """Pone en la cola paso1_guiones.py con esos argumentos (y, si se pide, el audio y el vídeo)."""
    def trabajo(t: Trabajo) -> bool:
        antes = set(GUIONES.glob("*.json")) if GUIONES.exists() else set()
        codigo = t.ejecutar("paso1_guiones.py", *argumentos)
        nuevos = sorted(p.stem for p in set(GUIONES.glob("*.json")) - antes) if GUIONES.exists() else []
        t.resultado = nuevos
        if codigo == 1 or not nuevos or t.estado == "cancelada":
            return codigo == 0
        if not completo:
            t.escribir("Guiones listos. Revísalos y después genera su audio y vídeo desde su página.")
            return codigo == 0
        t.escribir("Guiones listos (SIN VERIFICAR). Sigo con el audio y el vídeo…\n")
        return producir(t, nuevos) and codigo == 0

    nuevo = cola.anadir(titulo + (" · guion, audio y vídeo" if completo else " · solo guion"), trabajo)
    return redirect(url_for("ver_tarea", id=nuevo.id))


# --- Actualidad: noticias recientes en vez de Wikipedia ---------------------------------------

@app.route("/actualidad")
def ver_actualidad():
    tema = request.args.get("tema", "").strip()
    if tema:  # búsqueda nueva: se hace y se redirige a su página (así recargar no vuelve a buscar)
        dias = request.args.get("dias", "3")
        try:
            resultado = actualidad.buscar(tema, int(dias) if dias.isdigit() else 3, bool(request.args.get("mas")))
        except Exception as error:  # noqa: BLE001 — se muestra en la página
            return render_template("actualidad.html", busqueda=None, tema=tema,
                                   error=f"No se ha podido buscar: {error}")
        return redirect(url_for("ver_actualidad", id=resultado["id"]))
    try:
        busqueda = actualidad.leer(request.args.get("id", ""))
    except (OSError, ValueError):
        return redirect(url_for("inicio", error="Esa búsqueda ya no existe: vuelve a buscar la noticia."))
    return render_template("actualidad.html", busqueda=busqueda, tema=busqueda["tema"], error="",
                           tavily=bool(os.getenv("TAVILY_API_KEY")))


@app.post("/actualidad/<id_busqueda>/crear")
def crear_actualidad(id_busqueda):
    try:
        busqueda = actualidad.leer(id_busqueda)
    except (OSError, ValueError):
        return redirect(url_for("inicio", error="Esa búsqueda ya no existe: vuelve a buscar la noticia."))
    elegidos = [n for n in request.form.getlist("articulos") if n.isdigit()]
    if len(elegidos) < 2:
        return redirect(url_for("ver_actualidad", id=id_busqueda))
    idiomas = ",".join(request.form.getlist("idiomas")) or "es"
    argumentos = ["--actualidad", id_busqueda, "--articulos", ",".join(elegidos), "--idiomas", idiomas]
    return lanzar_guiones(f"Actualidad: «{busqueda['tema']}»", argumentos, request.form.get("completo") == "on")


@app.post("/ajustes/autoprogramar")
def guardar_autoprogramar():
    activo = request.form.get("activo") == "1"
    guardar_env({"AUTO_PROGRAMAR": "1" if activo else "0"})
    mensaje = ("Activado: los vídeos sin avisos se revisan y se programan solos." if activo
               else "Desactivado: los vídeos esperarán en Pendientes a que los programes tú.")
    if activo:
        hechos = programados.programar_sin_avisos()
        despertar_programados()
        if hechos:
            mensaje += f" Programados ahora: {len(hechos)}."
    return redirect(url_for("ajustes", mensaje=mensaje, _anchor="autoprogramar"))


@app.post("/ajustes/piloto")
def guardar_piloto():
    if request.form.get("activo") == "0":
        piloto_actualidad.desactivar()
        return redirect(url_for("ajustes", mensaje="Piloto de actualidad desactivado.", _anchor="piloto"))
    max_dia = request.form.get("max_dia", type=int) or piloto_actualidad.configuracion()["max_dia"]
    piloto_actualidad.guardar_configuracion({"max_dia": max(1, min(max_dia, 5))})
    error = piloto_actualidad.activar()
    mensaje = (f"No se ha podido programar la tarea de Windows: {error}" if error else
               "Piloto de actualidad activado: mirará la noticia del día a sus horas y publicará lo que pase la salvaguarda.")
    return redirect(url_for("ajustes", mensaje=mensaje, _anchor="piloto"))


@app.post("/ajustes/piloto/ahora")
def piloto_ahora():
    def trabajo(t: Trabajo) -> bool:
        antes = set(GUIONES.glob("*.json")) if GUIONES.exists() else set()
        codigo = t.ejecutar("piloto_actualidad.py", "--ahora")
        t.resultado = sorted(p.stem for p in set(GUIONES.glob("*.json")) - antes) if GUIONES.exists() else []
        return codigo == 0

    nuevo = cola.anadir("Piloto de actualidad: noticia del día", trabajo)
    return redirect(url_for("ver_tarea", id=nuevo.id))


@app.post("/ajustes/tavily")
def guardar_tavily():
    guardar_env({"TAVILY_API_KEY": request.form.get("clave", "").strip()})
    return redirect(url_for("ajustes", mensaje="Clave de Tavily guardada." if request.form.get("clave", "").strip()
                            else "Clave de Tavily quitada: se usará Bing Noticias.", _anchor="actualidad"))


@app.post("/ajustes/pexels")
def guardar_pexels():
    guardar_env({"PEXELS_API_KEY": request.form.get("clave", "").strip()})
    return redirect(url_for("ajustes", mensaje="Clave de Pexels guardada: los vídeos nuevos podrán llevar planos de ambiente."
                            if request.form.get("clave", "").strip() else "Clave de Pexels quitada.", _anchor="pexels"))


@app.route("/tarea")
def ver_tarea():
    trabajo = cola.buscar(request.args.get("id", type=int)) or cola.principal()
    return render_template("tarea.html", trabajo=trabajo, trabajos=list(reversed(cola.trabajos)))


@app.get("/api/tarea")
def api_tarea():
    trabajo = cola.buscar(request.args.get("id", type=int)) or cola.principal()
    if not trabajo:
        return jsonify(trabajo=None, trabajos=[])
    with trabajo.cerrojo:
        lineas = list(trabajo.lineas)
    resultado = [resumen(GUIONES / f"{n}.json") for n in trabajo.resultado if (GUIONES / f"{n}.json").exists()]
    return jsonify(
        trabajo={**trabajo.resumen(), "lineas": lineas,
                 "resultado": [{"nombre": r["nombre"], "titulo": r["titulo"], "idioma": r["idioma"]} for r in resultado]},
        trabajos=[t.resumen() for t in reversed(cola.trabajos)],
    )


@app.post("/tarea/<int:id_trabajo>/cancelar")
def cancelar_tarea(id_trabajo):
    cola.cancelar(id_trabajo)
    return redirect(url_for("ver_tarea", id=id_trabajo))


@app.route("/guion/<nombre>")
def ver_guion(nombre):
    datos = leer(nombre)
    video = ruta_video(datos)
    descripcion = paso3_video.ruta_descripcion(video) if video else None
    return render_template(
        "guion.html",
        nombre=nombre,
        datos=datos,
        info=resumen(ruta_guion(nombre)),
        archivo_video=video.relative_to(RAIZ).as_posix() if video else "",
        descripcion=descripcion.read_text(encoding="utf-8") if descripcion and descripcion.exists() else "",
        pistas=musica.pistas_disponibles(),
        mensaje=request.args.get("mensaje", ""),
        yt_conectado=subir_youtube.TOKEN.exists(),
        yt_privacidad=leer_env().get("YT_PRIVACIDAD") or "private",
        recomendada=horarios.recomendar([nombre]).get(nombre) if not datos.get("youtube") else None,
        borrado=borrar.resumen(nombre),
        clips=video_ia.clips(nombre, datos["escenas"]) if datos.get("video_ia") else {},
        herramienta=video_ia.herramienta((datos.get("video_ia") or {}).get("herramienta", "")),
    )


@app.post("/guion/<nombre>/clip")
def subir_clip(nombre):
    datos = leer(nombre)
    numero = request.form.get("escena", "")
    archivo = request.files.get("clip")
    extension = Path(archivo.filename or "").suffix.lower() if archivo else ""
    if not numero.isdigit() or int(numero) not in [e["numero"] for e in datos["escenas"]]:
        abort(400)
    if extension not in video_ia.EXTENSIONES_CLIP:
        return redirect(url_for("ver_guion", nombre=nombre, mensaje="Sube un vídeo .mp4, .mov o .webm.",
                                _anchor="clips"))
    carpeta = video_ia.carpeta_clips(nombre)
    carpeta.mkdir(parents=True, exist_ok=True)
    for viejo in carpeta.glob(f"escena_{int(numero):02d}.*"):
        viejo.unlink()
    archivo.save(carpeta / f"escena_{int(numero):02d}{extension}")
    faltan = video_ia.faltan(nombre, datos["escenas"])
    mensaje = (f"Clip de la escena {numero} guardado. Faltan las escenas: {', '.join(map(str, faltan))}."
               if faltan else "¡Ya están todos los clips! Pulsa «Generar audio y vídeo».")
    return redirect(url_for("ver_guion", nombre=nombre, mensaje=mensaje, _anchor="clips"))


@app.post("/guion/<nombre>/clip/<int:numero>/quitar")
def quitar_clip(nombre, numero):
    leer(nombre)
    ruta = video_ia.ruta_clip(nombre, numero)
    if ruta:
        ruta.unlink()
    return redirect(url_for("ver_guion", nombre=nombre, mensaje=f"Clip de la escena {numero} quitado.", _anchor="clips"))


@app.route("/clip/<nombre>/<int:numero>")
def ver_clip(nombre, numero):
    leer(nombre)
    ruta = video_ia.ruta_clip(nombre, numero)
    if not ruta:
        abort(404)
    return send_file(ruta.resolve(), conditional=True)


@app.post("/guion/<nombre>/borrar")
def borrar_guion(nombre):
    if cola.en_curso():  # una tarea podría estar usando sus archivos
        return volver_a(nombre, error="Hay tareas en marcha: espera a que terminen para borrar el vídeo.")
    try:
        mensaje = borrar.borrar(nombre, de_youtube=request.form.get("youtube") == "1")
    except Exception as error:  # noqa: BLE001 — se muestra en la página
        return volver_a(nombre, error=f"No se ha podido borrar: {error}")
    despertar_programados()
    return redirect(url_for("mis_videos", ver=request.form.get("ver") or None, mensaje=mensaje))


@app.post("/guion/<nombre>/guardar")
def guardar_guion(nombre):
    datos = leer(nombre)
    cambiado = False
    for escena in datos.get("escenas", []):
        nuevo = request.form.get(f"narracion_{escena['numero']}", "").strip()
        if nuevo and nuevo != escena["narracion"]:
            escena["narracion"] = nuevo
            cambiado = True
    nuevo_titulo = request.form.get("titulo", "").strip()
    if nuevo_titulo and nuevo_titulo != datos.get("titulo"):
        datos["titulo"] = nuevo_titulo
        cambiado = True
    if not cambiado:
        return redirect(url_for("ver_guion", nombre=nombre, mensaje="No había cambios."))
    datos["verificado"] = False
    datos["editado_a_mano"] = True
    escribir(nombre, datos)
    return redirect(url_for(
        "ver_guion", nombre=nombre,
        mensaje="Cambios guardados. Vuelve a marcarlo como verificado y rehaz el vídeo: solo se regeneran las escenas cambiadas.",
    ))


@app.post("/guion/<nombre>/ajustes")
def ajustes_guion(nombre):
    datos = leer(nombre)
    datos["gancho"] = request.form.get("gancho", "").strip()[:40]
    pista = request.form.get("musica", "neutro")
    datos["musica"] = pista if pista in musica.pistas_disponibles() or pista == "ninguna" else "neutro"
    escribir(nombre, datos)
    return redirect(url_for("ver_guion", nombre=nombre, mensaje="Gancho y música guardados. Rehaz el vídeo para aplicarlos."))


@app.post("/guion/<nombre>/verificar")
def verificar_guion(nombre):
    datos = leer(nombre)
    datos["verificado"] = request.form.get("valor") == "1"
    escribir(nombre, datos)
    titulo = datos.get("titulo", nombre)
    return volver_a(nombre, f"«{titulo}» marcado como revisado." if datos["verificado"] else "Marca de revisado quitada.")


@app.post("/guion/<nombre>/revisar-y-programar")
def revisar_y_programar(nombre):
    """Da el vídeo por revisado y lo programa a su hora recomendada (o a la que se elija) en un solo paso."""
    datos = leer(nombre)
    if not ruta_video(datos):
        return volver_a(nombre, error="Antes de programarlo, genera el vídeo.")
    hora = request.form.get("hora") or (horarios.recomendar([nombre]).get(nombre) or {}).get("hora")
    if not hora:
        return volver_a(nombre, error="No hay hueco recomendado en las próximas semanas: elige tú la hora.")
    if not datos.get("verificado"):
        datos["verificado"] = True
        escribir(nombre, datos)
    try:
        programados.anadir(nombre, hora)
    except ValueError as error:
        return volver_a(nombre, error=f"No se ha podido programar: {error}")
    despertar_programados()
    return volver_a(nombre, f"«{datos.get('titulo', nombre)}» revisado y programado para el "
                            f"{programados.formato_bonito(hora)}.")


@app.post("/guion/<nombre>/producir")
def producir_guion(nombre):
    titulo = f"Audio y vídeo de «{leer(nombre).get('titulo', nombre)}»"

    def trabajo(t: Trabajo) -> bool:
        t.resultado = [nombre]
        return producir(t, [nombre])

    nuevo = cola.anadir(titulo, trabajo)
    return redirect(url_for("ver_tarea", id=nuevo.id))


# --- Imágenes de cada escena --------------------------------------------------------

def imagen_guardable(imagen: dict) -> dict:
    """Lo que se guarda en el guion de una imagen elegida (sin datos internos de búsqueda)."""
    return {k: imagen.get(k) for k in ("archivo", "url", "pagina", "autor", "licencia", "anio", "articulo", "ruta",
                                       "video", "duracion", "miniatura")
            if imagen.get(k) is not None}


@app.route("/guion/<nombre>/imagenes")
def imagenes_guion(nombre):
    datos = leer(nombre)
    candidatas = paso3_video.candidatas(nombre, datos, renovar=request.args.get("renovar") == "1")
    selector = paso3_video.SelectorImagenes(candidatas, datos.get("evento", ""), datos.get("anio_evento"))
    elegidas_ruta = paso3_video.elegidas_path(nombre)
    elegidas = json.loads(elegidas_ruta.read_text(encoding="utf-8")) if elegidas_ruta.exists() else {}
    escenas = []
    for escena in datos.get("escenas", []):
        actual = escena.get("imagen") or (elegidas.get(str(escena["numero"])) or {}).get("imagen")
        ranking = selector.ranking(escena)
        opciones = [candidatas[i] for i in ranking[:12]]
        # Los vídeos son pocos: se ofrecen siempre (aunque no estén entre los 12 mejores) para elegirlos a mano.
        opciones += [candidatas[i] for i in ranking[12:] if candidatas[i].get("video")][:6]
        escenas.append({"escena": escena, "actual": actual, "a_mano": bool(escena.get("imagen")), "opciones": opciones})
    return render_template("imagenes.html", nombre=nombre, datos=datos, escenas=escenas,
                           miniatura=paso3_video.miniatura_url, total=len(candidatas),
                           mensaje=request.args.get("mensaje", ""))


@app.post("/guion/<nombre>/imagen")
def elegir_imagen(nombre):
    datos = leer(nombre)
    numero = request.form.get("escena", type=int)
    archivo = request.form.get("archivo", "")
    escena = next((e for e in datos.get("escenas", []) if e["numero"] == numero), None)
    if not escena:
        abort(400)
    if archivo == "auto":
        escena.pop("imagen", None)
        mensaje = f"Escena {numero}: vuelve a elegirse automáticamente."
    else:
        candidata = next((c for c in paso3_video.candidatas(nombre, datos) if c["archivo"] == archivo), None)
        if not candidata:
            abort(400)
        escena["imagen"] = imagen_guardable(candidata)
        mensaje = f"Escena {numero}: imagen elegida."
    escribir(nombre, datos)
    return redirect(url_for("imagenes_guion", nombre=nombre, mensaje=mensaje) + f"#escena-{numero}")


@app.post("/guion/<nombre>/subir-imagen")
def subir_imagen(nombre):
    datos = leer(nombre)
    numero = request.form.get("escena", type=int)
    archivo = request.files.get("imagen")
    escena = next((e for e in datos.get("escenas", []) if e["numero"] == numero), None)
    extension = Path(archivo.filename).suffix.lower() if archivo and archivo.filename else ""
    if not escena or extension not in EXTENSIONES_IMAGEN:
        return redirect(url_for("imagenes_guion", nombre=nombre, mensaje="Sube una imagen JPG, PNG o WEBP."))
    PROPIAS.mkdir(parents=True, exist_ok=True)
    destino = PROPIAS / f"{nombre}_escena{numero:02d}{extension}"
    archivo.save(destino)
    escena["imagen"] = {"archivo": archivo.filename, "ruta": destino.relative_to(RAIZ).as_posix(),
                        "autor": "Propia", "licencia": "propia", "pagina": ""}
    escribir(nombre, datos)
    return redirect(url_for("imagenes_guion", nombre=nombre, mensaje=f"Escena {numero}: imagen subida.")
                    + f"#escena-{numero}")


@app.route("/img")
def miniatura_wikimedia():
    """Miniatura (Wikimedia o museos) servida desde la caché local: el navegador no llama a esos servidores."""
    url = request.args.get("u", "")
    if urlparse(url).hostname not in ("upload.wikimedia.org", "thumb.wikimedia.org",
                                      "images.metmuseum.org", "www.artic.edu"):
        abort(400)
    destino = MINIATURAS / f"{hashlib.sha1(url.encode()).hexdigest()}{Path(urlparse(url).path).suffix.lower() or '.jpg'}"
    try:
        wikimedia.archivo(url, destino)
    except wikimedia.WikimediaEnEspera:
        return "Wikimedia nos ha pedido esperar", 503
    except Exception:
        abort(404)
    return send_file(destino, max_age=7 * 24 * 3600)


@app.route("/propia/<nombre>/<int:numero>")
def imagen_propia(nombre, numero):
    escena = next((e for e in leer(nombre).get("escenas", []) if e["numero"] == numero), {})
    ruta = (RAIZ / (escena.get("imagen") or {}).get("ruta", "-")).resolve()
    if PROPIAS.resolve() not in ruta.parents or not ruta.exists():
        abort(404)
    return send_file(ruta)


# --- Archivos ---------------------------------------------------------------------

@app.route("/video/<nombre>.mp4")
def video(nombre):
    ruta = ruta_video(leer(nombre))
    if not ruta:
        abort(404)
    return send_file(ruta, mimetype="video/mp4", conditional=True)


@app.route("/miniatura/<nombre>.jpg")
def miniatura(nombre):
    ruta = ruta_video(leer(nombre))
    if not ruta or not paso3_video.ruta_miniatura(ruta).exists():
        abort(404)
    return send_file(paso3_video.ruta_miniatura(ruta), mimetype="image/jpeg")


@app.route("/musica/<pista>.mp3")
def escuchar_musica(pista):
    ruta = musica.ruta_pista(pista)
    if not ruta:
        abort(404)
    return send_file(ruta.resolve(), mimetype="audio/mpeg")


@app.post("/abrir-carpeta")
def abrir_carpeta():
    VIDEOS.mkdir(parents=True, exist_ok=True)
    os.startfile(VIDEOS)
    return redirect(request.referrer or url_for("inicio"))


@app.post("/abrir-musica")
def abrir_carpeta_musica():
    musica.CARPETA_MUSICA.mkdir(exist_ok=True)
    os.startfile(musica.CARPETA_MUSICA.resolve())
    return redirect(request.referrer or url_for("ajustes"))


@app.post("/guion/<nombre>/abrir-carpeta")
def abrir_carpeta_video(nombre):
    ruta = ruta_video(leer(nombre))
    if not ruta:
        abort(404)
    os.startfile(ruta.parent)
    return redirect(url_for("ver_guion", nombre=nombre))


# --- YouTube ------------------------------------------------------------------------

_canal = {"info": None, "hasta": 0.0}  # nombre del canal conectado (se consulta como mucho cada 10 min)


def canal_youtube(renovar: bool = False):
    if renovar or time.time() > _canal["hasta"]:
        _canal["info"] = subir_youtube.canal_conectado() if subir_youtube.TOKEN.exists() else None
        _canal["hasta"] = time.time() + 600
    return _canal["info"]


@app.post("/guion/<nombre>/subir-youtube")
def subir_a_youtube(nombre):
    datos = leer(nombre)
    if not datos.get("verificado"):
        return redirect(url_for("ver_guion", nombre=nombre, mensaje="Antes de subirlo, márcalo como verificado."))
    if request.form.get("publicar_el"):  # programado: lo apunta en la cola y lo sube el programa a su tiempo
        if not ruta_video(datos):
            return redirect(url_for("ver_guion", nombre=nombre, mensaje="Antes de programarlo, genera el vídeo."))
        try:
            programados.anadir(nombre, request.form["publicar_el"])
        except ValueError as error:
            return redirect(url_for("ver_guion", nombre=nombre, mensaje=f"No se ha podido programar: {error}."))
        despertar_programados()
        return redirect(url_for("ver_programados", mensaje=f"«{datos.get('titulo', nombre)}» programado."))
    privacidad = request.form.get("privacidad", "private")
    argumentos = [nombre, "--privacidad", privacidad if privacidad in subir_youtube.PRIVACIDADES else "private"]

    def trabajo(t: Trabajo) -> bool:
        t.resultado = [nombre]
        return t.ejecutar("subir_youtube.py", *argumentos) == 0

    nuevo = cola.anadir(f"Subir a YouTube «{datos.get('titulo', nombre)}»", trabajo)
    return redirect(url_for("ver_tarea", id=nuevo.id))


# --- Pendientes: lo que falta revisar y programar --------------------------------------------

def programar_recomendados(nombres: list):
    """Programa cada guion a su hora recomendada y lleva a «Programados»."""
    recomendadas = horarios.recomendar(nombres)
    hechos, fallos = 0, []
    for nombre in nombres:
        r = recomendadas.get(nombre)
        if not r:
            fallos.append(f"«{nombre}»: no hay hueco en las próximas semanas")
            continue
        try:
            programados.anadir(nombre, r["hora"])
            hechos += 1
        except ValueError as error:
            fallos.append(f"«{nombre}»: {error}")
    despertar_programados()
    mensaje = f"{hechos} vídeo(s) programados a su hora recomendada."
    if fallos:
        mensaje += " No se han podido programar: " + "; ".join(fallos)
    return redirect(url_for("ver_programados", mensaje=mensaje))


@app.route("/pendientes")
def ver_pendientes():  # antigua página: ahora es el filtro «Por revisar» de Mis vídeos
    return redirect(url_for("mis_videos", ver="revisar"))


@app.post("/videos/programar-listos")
def programar_listos():
    nombres = request.form.getlist("nombres")
    if not nombres:
        return redirect(url_for("mis_videos", ver="listos", error="No hay vídeos listos para programar."))
    return programar_recomendados(nombres)


# --- Programados: la cola la lleva el programa y YouTube publica a su hora ------------------

_despertador = threading.Event()


def despertar_programados() -> None:
    """Que la vigilancia revise la cola ya (tras programar algo), sin esperar al siguiente minuto."""
    _despertador.set()


def vigilar_programados() -> None:
    """Mientras el menú está abierto, mira cada minuto si hay que subir algún vídeo programado."""
    def bucle():
        ultima_comprobacion = 0.0
        while True:
            try:
                if time.time() - ultima_comprobacion > 15 * 60 and subir_youtube.TOKEN.exists():
                    ultima_comprobacion = time.time()  # cada 15 min: ¿se ha cambiado algo en YouTube Studio?
                    programados.sincronizar()
                    subir_youtube.actualizar_estadisticas()  # y las vistas de cada vídeo
            except Exception as error:  # noqa: BLE001 — sin conexión no pasa nada: se mira la próxima vez
                print(f"[programados] {error}", file=sys.stderr)
            try:
                if programados.toca_revisar():
                    subprocess.run([sys.executable, str(SCRIPTS / "programados.py")], cwd=RAIZ, timeout=3 * 3600,
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as error:  # noqa: BLE001 — la vigilancia no debe caerse nunca
                print(f"[programados] {error}", file=sys.stderr)
            _despertador.wait(60)
            _despertador.clear()

    threading.Thread(target=bucle, daemon=True, name="programados").start()


@app.route("/programados")
def ver_programados():
    return render_template("programados.html", cola_prog=programados.para_mostrar(),
                           proxima=programados.proxima_revision(), mensaje=request.args.get("mensaje", ""),
                           error=request.args.get("error", ""), max_dia=programados.MAX_SUBIDAS_DIA,
                           antelacion=int(programados.ANTELACION_H), subidas_hoy=programados.subidas_ultimas_24h(),
                           yt_conectado=subir_youtube.TOKEN.exists())


def _accion_programado(funcion, *argumentos):
    try:
        mensaje = funcion(*argumentos)
    except Exception as error:  # noqa: BLE001 — se muestra en la página
        return redirect(url_for("ver_programados", error=f"No se ha podido: {error}"))
    despertar_programados()
    return redirect(url_for("ver_programados", mensaje=mensaje or "Hecho."))


@app.route("/calendario")
def ver_calendario():
    hoy = date.today()
    try:
        anio, mes = (int(x) for x in request.args.get("mes", f"{hoy.year}-{hoy.month}").split("-"))
        date(anio, mes, 1)
    except ValueError:
        anio, mes = hoy.year, hoy.month
    return render_template("calendario.html", cal=programados.calendario(anio, mes),
                           este_mes=f"{hoy.year}-{hoy.month:02d}", mes_actual=f"{anio}-{mes:02d}",
                           mensaje=request.args.get("mensaje", ""), error=request.args.get("error", ""))


@app.post("/programados/<nombre>/hora")
def hora_programado(nombre):
    return _accion_programado(programados.cambiar_hora, nombre, request.form.get("hora", ""))


@app.post("/programados/<nombre>/ya")
def ya_programado(nombre):
    return _accion_programado(programados.publicar_ya, nombre)


@app.post("/programados/<nombre>/reintentar")
def reintentar_programado(nombre):
    return _accion_programado(programados.reintentar, nombre)


@app.post("/programados/<nombre>/quitar")
def quitar_programado(nombre):
    return _accion_programado(programados.quitar, nombre)


@app.post("/programados/limpiar")
def limpiar_programados():
    return _accion_programado(programados.limpiar_historial)


@app.post("/programados/revisar")
def revisar_programados():
    """«Actualizar»: trae de YouTube lo cambiado en YouTube Studio (horas, publicados, borrados) y mira si toca subir algo."""
    destino = "ver_calendario" if request.form.get("volver") == "calendario" else "ver_programados"
    extra = {"mes": request.form["mes"]} if request.form.get("mes") else {}
    try:
        cambios = programados.sincronizar()
        subir_youtube.actualizar_estadisticas()
    except Exception as error:  # noqa: BLE001 — sin conexión o sin YouTube conectado
        return redirect(url_for(destino, error=f"No se ha podido comprobar con YouTube: {error}", **extra))
    datos = programados.leer()
    datos["siguiente_intento"] = None  # y que la cola mire ya si toca subir algo
    programados.guardar(datos)
    despertar_programados()
    mensaje = ("Actualizado con YouTube: " + "; ".join(cambios) + "." if cambios
               else "Actualizado: todo coincide con YouTube.")
    return redirect(url_for(destino, mensaje=mensaje, **extra))


@app.post("/videos/vistas")
def actualizar_vistas():
    """«↻ Actualizar» en Publicados: trae ya de YouTube las vistas de cada vídeo."""
    orden = request.form.get("orden")
    destino = {"ver": "publicados", **({"orden": orden} if orden in ("vistas", "retencion") else {})}
    try:
        cuantos = len(subir_youtube.actualizar_estadisticas())
    except Exception as error:  # noqa: BLE001 — sin conexión o sin YouTube conectado
        return redirect(url_for("mis_videos", error=f"No se han podido traer las vistas de YouTube: {error}", **destino))
    try:
        subir_youtube.actualizar_retencion(forzar=True)
    except Exception as error:  # noqa: BLE001 — las vistas sí se han traído
        return redirect(url_for("mis_videos", error=f"Vistas actualizadas, pero no la retención: {error}", **destino))
    return redirect(url_for("mis_videos", mensaje=f"Vistas y retención actualizadas ({cuantos} vídeos).", **destino))


@app.post("/youtube/conectar")
def conectar_youtube():
    def trabajo(t: Trabajo) -> bool:
        t.escribir("Se abrirá Google en tu navegador: inicia sesión con la cuenta del canal y pulsa «Permitir».")
        ok = t.ejecutar("subir_youtube.py", "--conectar") == 0
        canal_youtube(renovar=True)
        return ok

    nuevo = cola.anadir("Conectar el canal de YouTube", trabajo)
    return redirect(url_for("ver_tarea", id=nuevo.id))


@app.post("/youtube/desconectar")
def desconectar_youtube():
    subir_youtube.desconectar()
    canal_youtube(renovar=True)
    return redirect(url_for("ajustes", mensaje="Canal desconectado.") + "#youtube")


@app.post("/youtube/credenciales")
def subir_credenciales():
    archivo = request.files.get("credenciales")
    try:
        contenido = json.loads(archivo.read().decode("utf-8")) if archivo else {}
    except (ValueError, UnicodeDecodeError):
        contenido = {}
    if "installed" not in contenido:
        return redirect(url_for("ajustes", mensaje="Ese archivo no es válido: tiene que ser el JSON de un cliente OAuth "
                                                   "de tipo «App de escritorio».") + "#youtube")
    subir_youtube.CARPETA_CREDENCIALES.mkdir(exist_ok=True)
    subir_youtube.CLIENTE.write_text(json.dumps(contenido), encoding="utf-8")
    return redirect(url_for("ajustes", mensaje="Credenciales guardadas. Ahora pulsa «Conectar con YouTube».") + "#youtube")


@app.post("/youtube/privacidad")
def privacidad_youtube():
    privacidad = request.form.get("privacidad", "private")
    if privacidad in subir_youtube.PRIVACIDADES:
        guardar_env({"YT_PRIVACIDAD": privacidad})
    return redirect(url_for("ajustes", mensaje="Privacidad por defecto guardada.") + "#youtube")


# --- Ajustes -----------------------------------------------------------------------

@app.route("/ajustes")
def ajustes():
    env = leer_env()
    return render_template(
        "ajustes.html",
        voces=voces(),
        voz_es=env.get("VOZ_ES") or "es-ES-AlvaroNeural",
        voz_en=env.get("VOZ_EN") or "en-US-AndrewNeural",
        velocidad=int((env.get("VELOCIDAD") or "+8%").replace("%", "") or 0),
        pistas=musica.pistas_disponibles(),
        muestra=request.args.get("muestra"),
        mensaje=request.args.get("mensaje", ""),
        yt_cliente=subir_youtube.CLIENTE.exists(),
        yt_canal=canal_youtube(),
        yt_token=subir_youtube.TOKEN.exists(),
        yt_privacidad=env.get("YT_PRIVACIDAD") or "private",
        tavily=bool(os.getenv("TAVILY_API_KEY")),
        pexels=bool(os.getenv("PEXELS_API_KEY")),
        autoprogramar=os.getenv("AUTO_PROGRAMAR", "1") == "1",
        piloto=piloto_actualidad.configuracion(),
        piloto_tarea=piloto_actualidad.estado_tarea(),
        piloto_contados=list(reversed(piloto_actualidad.contados(2))),
        piloto_registro=piloto_actualidad.ultimas_lineas(25),
        ig=instagram.leer_config(), ig_conectado=instagram.conectado(),
    )


def _ir_a_instagram(mensaje: str):
    return redirect(url_for("ajustes", mensaje=mensaje) + "#instagram")


@app.post("/ajustes/instagram/app")
def instagram_app():
    instagram.guardar_app(request.form.get("app_id", ""), request.form.get("app_secreto", ""))
    return _ir_a_instagram("Datos de la app de Meta guardados.")


@app.post("/ajustes/instagram/conectar")
def instagram_conectar():
    try:
        cuenta = instagram.conectar(request.form.get("token", ""))
    except Exception as error:  # noqa: BLE001 — se muestra en la página
        return _ir_a_instagram(f"No se ha podido conectar: {error}")
    return _ir_a_instagram(f"Instagram conectado: @{cuenta['usuario']} (página «{cuenta['pagina']}»).")


@app.post("/ajustes/instagram/desconectar")
def instagram_desconectar():
    instagram.desconectar()
    return _ir_a_instagram("Instagram desconectado.")


@app.post("/ajustes/instagram/publicar")
def instagram_publicar():
    """Activa o desactiva publicar los programados también como Reels (desde ahora: no los ya pasados)."""
    config = instagram.leer_config()
    activar = request.form.get("activo") == "1"
    config["publicar"] = activar
    if activar:
        config["desde"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    instagram.CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    despertar_programados()
    return _ir_a_instagram("Desde ahora, cada vídeo programado se publica también en Instagram a su misma hora."
                           if activar else "Ya no se publica en Instagram.")


@app.post("/ajustes")
def guardar_ajustes():
    velocidad = max(-30, min(40, request.form.get("velocidad", 8, type=int)))
    ids = {v["id"] for v in voces()}
    cambios = {"VELOCIDAD": f"{velocidad:+d}%"}
    for clave in ("VOZ_ES", "VOZ_EN"):
        valor = request.form.get(clave, "")
        if valor in ids:
            cambios[clave] = valor
    guardar_env(cambios)
    return redirect(url_for("ajustes", mensaje="Voz guardada. Se usará en los próximos audios "
                                                "(los ya hechos se rehacen al pulsar «Rehacer audio y vídeo»)."))


@app.post("/ajustes/muestra")
def muestra_voz():
    import edge_tts
    voz = request.form.get("voz", "")
    velocidad = max(-30, min(40, request.form.get("velocidad", 8, type=int)))
    if voz not in {v["id"] for v in voces()}:
        abort(400)
    texto = ("¿Sabías que una ciudad que resistió mil años cayó en solo cincuenta y tres días?"
             if voz.startswith("es-") else "Did you know a city that stood for a thousand years fell in just 53 days?")
    MUESTRA.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(edge_tts.Communicate(texto, voz, rate=f"{velocidad:+d}%").save(str(MUESTRA)))
    return redirect(url_for("ajustes", muestra=f"{voz}|{velocidad}"))


@app.route("/muestra.mp3")
def escuchar_muestra():
    if not MUESTRA.exists():
        abort(404)
    return send_file(MUESTRA, mimetype="audio/mpeg", max_age=0)


@app.route("/ayuda")
def ayuda():
    return render_template("ayuda.html")


def puerto_ocupado() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", PUERTO)) == 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):  # una flecha o un acento en la consola no debe tumbar el menú
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")
    url = f"http://127.0.0.1:{PUERTO}"
    if puerto_ocupado():  # ya está abierto: solo abre el navegador
        webbrowser.open(url)
        sys.exit(0)
    paso3_video.migrar_videos_antiguos()  # vídeos hechos con la versión anterior → carpeta por tema
    musica.asegurar_pistas()
    vigilar_programados()
    print(f"Menú abierto en {url}  (cierra esta ventana para apagarlo)")
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=PUERTO, debug=False, threaded=True)
