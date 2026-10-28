"""Paso 1: genera guiones de vídeos cortos a partir de efemérides reales de Wikipedia.

Descarga los eventos de «tal día como hoy» de Wikipedia en español, elige los que
tienen más material y pide a un LLM (Groq) un guion de 40-45 segundos por idioma,
dividido en escenas con narración y descripción visual. El guion solo puede usar
hechos del material descargado, y el JSON guarda las fuentes para verificarlas.

Uso:
    python scripts/paso1_guiones.py
    python scripts/paso1_guiones.py --cantidad 5 --fecha 2026-07-20
    python scripts/paso1_guiones.py --idiomas es
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

import wikimedia  # acceso a Wikipedia con caché y ritmo controlado (evita que te pongan en espera)

load_dotenv()

URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
URL_EFEMERIDES = "https://es.wikipedia.org/api/rest_v1/feed/onthisday/{tipo}/{mes:02d}/{dia:02d}"
URL_WIKI_API = "https://es.wikipedia.org/w/api.php"

MODELO_POR_DEFECTO = "openai/gpt-oss-120b"
CARPETA_SALIDA = Path("salida/guiones")

# Una narración de unos 40 s (40-45 s con el cierre) a ritmo de vídeo corto (~2,5 palabras por segundo): los Shorts que se ven enteros son
# los que YouTube reparte, y con 60-75 s casi nadie llegaba al final.
PALABRAS_POR_SEGUNDO = 2.5
PALABRAS_MIN, PALABRAS_MAX = 95, 115
PALABRAS_OBJETIVO = 105

ANTIGUEDAD_MINIMA = 20      # años: evita fichajes y noticias recientes
MAX_PAGINAS_POR_EVENTO = 3
MAX_CARACTERES_PRINCIPAL = 6000   # artículo principal del evento
MAX_CARACTERES_PAGINA = 2500      # artículos secundarios

MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
            "noviembre", "diciembre")
IDIOMAS = {"es": "español", "en": "inglés"}

PROMPT_SISTEMA = """Eres guionista de vídeos cortos de historia (YouTube Shorts, TikTok, Reels).
Recibirás un MATERIAL con información de Wikipedia sobre un evento histórico.

Reglas de veracidad, obligatorias:
- Usa SOLO hechos que aparezcan en el MATERIAL. No añadas fechas, cifras, nombres, citas ni detalles que no estén ahí.
- Si un dato no está claro en el MATERIAL, no lo menciones.
- No inventes diálogos ni frases atribuidas a personas reales.

Estilo:
- La PRIMERA FRASE decide si la gente se queda: piensa antes 3 opciones y usa la más intrigante. Funcionan:
  un dato sorprendente, una contradicción («la ciudad que resistió mil años cayó en 53 días») o una pregunta
  que el espectador necesite resolver. Nunca empieces con «Hoy te voy a contar», «¿Sabías que…?», una fecha suelta
  («En 1936, …») o un saludo. La primera frase es el gancho y tiene como mucho 18 palabras.
  El gancho tiene que ser cierto según el MATERIAL.
- Frases cortas, fáciles de narrar en voz alta. Tono curioso y cercano, sin exagerar.
- Ve al grano: nada de introducciones ni de contexto que no sea imprescindible. Cada escena aporta un dato nuevo.
- La ÚLTIMA escena termina con una PREGUNTA directa al espectador, corta y fácil de contestar en los comentarios
  (una opinión o una apuesta: «¿Tú habrías firmado?», «¿Héroe o traidor?»). Nunca «¿Lo sabías?» ni «Comenta abajo».
- Longitud TOTAL de la narración: entre {min_palabras} y {max_palabras} palabras (40-45 segundos). Apunta a unas {objetivo}.
- Entre 5 y 6 escenas, de 17 a 22 palabras de narración cada una. Cuenta las palabras antes de responder.
- Si te sobra material, quédate con lo más sorprendente; nunca rellenes con datos inventados.

Responde SOLO con un objeto JSON con esta forma:
{{
  "titulo": "título atractivo del vídeo",
  "nombre_corto": "2 a 4 palabras que nombren el tema, sin artículo inicial ni número de parte (p. ej. «Guerra civil», «Juana de Arco»)",
  "gancho": "1 a 4 palabras impactantes que se verán en grande en el primer segundo y en la miniatura (p. ej. «53 días.», «Un simple florero»); deben ser ciertas según el MATERIAL",
  "tono": "uno de: epico, misterio, triste, neutro (para elegir la música de fondo)",
  "escenas": [
    {{"narracion": "texto que dice la voz en off", "visual": "descripción concreta de la imagen o clip: qué se ve, época, encuadre"}}
  ],
  "pregunta": "la pregunta final de la última escena, tal cual (irá también como comentario fijado)",
  "hashtags": ["#historia", "..."]
}}
Los NOMBRES de las claves son siempre exactamente estos, sin traducir: "titulo", "nombre_corto", "gancho", "tono", "escenas", "narracion", "visual", "pregunta", "hashtags".
Los VALORES de "narracion", "titulo", "nombre_corto", "gancho", "pregunta" y "hashtags" van en {idioma}. El de "tono" va tal cual de la lista. El valor de "visual" va SIEMPRE en inglés (servirá para buscar o generar imágenes)."""

PROMPT_DIARIO = """Eres guionista de vídeos cortos virales de humor histórico (TikTok, Shorts) con el formato «Día X de …».
Recibirás un PERSONAJE, un número de DÍA, quizá un TEMA concreto, y un MATERIAL de Wikipedia.

Veracidad, obligatoria: el humor está en el TONO, no en los hechos.
- Todo dato histórico (lugares, fechas, costumbres, normas, objetos, comida, cifras) debe salir del MATERIAL.
- No inventes citas, nombres propios ni cifras. Puedes exagerar emociones y usar jerga moderna, nunca hechos falsos.

Formato:
- Primera persona, como una entrada de diario: el personaje cuenta su día con tono sarcástico, agotado,
  deadpan y muy cercano, aplicando jerga moderna a la miseria histórica.
- Escena 1 (gancho): empieza EXACTAMENTE con «{gancho}» seguido de qué hace el personaje, y en esa misma frase
  plantea la situación más absurda o injusta del día (piensa 3 opciones y usa la más graciosa), para que nadie deslice.
- Escenas centrales: UNA molestia, norma absurda o penuria concreta y real de la época (si hay TEMA, esa), con detalles del MATERIAL.
  Cada escena se apoya en al menos UN dato real y concreto del MATERIAL; el chiste es la reacción del personaje a ese dato.
- Si el MATERIAL no dice algo, no lo afirmes (ni cifras, ni objetos, ni cargos): búscale la gracia a lo que sí dice.
- Última escena: despedida cínica o graciosa pensando en el día siguiente, y una pregunta corta al espectador
  («¿Tú aguantarías un día?»).
- Longitud TOTAL de la narración: entre {min_palabras} y {max_palabras} palabras (unos 40-45 segundos). Apunta a {objetivo}.
- Entre 5 y 6 escenas.

Responde SOLO con un objeto JSON con esta forma:
{{
  "titulo": "título gancho que empiece por «{gancho}»",
  "nombre_corto": "«Diario» + el personaje en 2 o 3 palabras (p. ej. «Diario soldado romano»)",
  "gancho": "{gancho_corto}",
  "tono": "comico",
  "personaje_visual": "en inglés: el personaje en 3D estilo Pixar con un atuendo moderno gracioso; idéntico en todas las escenas",
  "prompt_video": "en inglés: prompt para Sora/Runway/Midjourney con el personaje, el escenario de época, la yuxtaposición graciosa, iluminación cinematográfica, vertical 9:16",
  "escenas": [
    {{"narracion": "texto que dice la voz en off", "visual": "en inglés: prompt de imagen de esta escena con la descripción completa del personaje, su acción y el escenario, vertical 9:16"}}
  ],
  "pregunta": "la pregunta final al espectador, tal cual",
  "palabras_clave": ["de 4 a 8 palabras graciosas de la narración para resaltar en los subtítulos"],
  "hashtags": ["#historia", "..."]
}}
Los NOMBRES de las claves son siempre exactamente estos, sin traducir.
Los VALORES de "titulo", "nombre_corto", "gancho", "narracion", "palabras_clave" y "hashtags" van en {idioma};
"personaje_visual", "prompt_video" y "visual" van SIEMPRE en inglés."""

PALABRAS_DIARIO = (95, 115, 105)  # mínimo, máximo y objetivo: unos 40-45 s

PROMPT_ACTUALIDAD = """Eres guionista de vídeos cortos de ACTUALIDAD (YouTube Shorts, TikTok) para un canal de divulgación.
Recibirás un MATERIAL con varios artículos de prensa recientes, cada uno con su medio y su fecha. Hoy es {hoy}.

Reglas de veracidad, obligatorias (es una noticia en curso: un error aquí es grave):
- Usa SOLO hechos que aparezcan en el MATERIAL. No añadas cifras, fechas, nombres, causas ni consecuencias que no estén.
- Atribuye las cifras y las afirmaciones discutibles a quien las da: «según la policía», «según Le Monde»,
  «según el Gobierno francés». Si los medios dan cifras distintas, dilo («entre 800 y 1.200 detenidos, según la fuente»).
- Sitúa los hechos en el tiempo con las fechas del MATERIAL («el sábado 17», «esta semana»), tal y como las da: si
  dice «el sábado» sin número, di «el sábado»; nunca calcules el número del día ni el mes. La última escena dice que
  la información es «a {hoy_corto}» y que la situación puede cambiar.
- Tono neutro e informativo: sin opiniones, sin adjetivos alarmistas, sin culpar a colectivos por su origen, religión
  o ideología, sin detalles morbosos de violencia. No nombres a personas particulares (víctimas, detenidos, menores);
  sí a cargos públicos y a instituciones.
- Si el MATERIAL no deja claro por qué pasa algo, no lo expliques: cuenta solo lo que se sabe.
- Si hay polémica, recoge las posturas enfrentadas que aparezcan en el MATERIAL (Gobierno y oposición, vecinos y
  ayuntamiento…), cada una atribuida a quien la defiende y con un espacio parecido. El vídeo no toma partido.
- Los artículos pueden estar en otros idiomas: tradúcelo TODO al {idioma} (también el título y el gancho), y los términos («curfew» → «toque de
  queda»). Solo se dejan en el original los nombres propios y las citas textuales, entre comillas y atribuidas.

Estilo:
- La PRIMERA FRASE engancha con un hecho cierto y concreto del MATERIAL (una cifra, una imagen, una contradicción).
  Nunca empieces con «Hoy te voy a contar», una fecha suelta ni un saludo. Como mucho 18 palabras. Sin titulares
  engañosos.
- Frases cortas, fáciles de narrar. Cuenta: qué ha pasado, dónde y cuándo, cifras, reacciones y qué puede pasar ahora
  (solo si el MATERIAL lo dice).
- La ÚLTIMA escena, después de la fecha, lanza al espectador una pregunta abierta sobre la polémica para que opine
  en los comentarios («¿Quién crees que tiene razón?», «¿Tú qué harías?»), sin sugerir la respuesta.
- Ve al grano: lo esencial de la noticia, sin rodeos.
- Longitud TOTAL de la narración: entre {min_palabras} y {max_palabras} palabras (40-45 segundos). Apunta a unas {objetivo}.
- Entre 5 y 6 escenas, de 17 a 22 palabras de narración cada una.

Responde SOLO con un objeto JSON con esta forma:
{{
  "titulo": "título informativo y atractivo, sin exagerar",
  "nombre_corto": "2 a 4 palabras que nombren la noticia (p. ej. «Disturbios Francia»)",
  "gancho": "1 a 4 palabras ciertas que se verán en grande al empezar (p. ej. «1.200 detenidos»)",
  "tono": "uno de: neutro, misterio, triste (para la música de fondo; nunca epico ni comico en noticias)",
  "escenas": [
    {{"narracion": "texto que dice la voz en off", "visual": "descripción de una imagen de ARCHIVO neutra para esa escena: lugar, edificio, institución, bandera o mapa (nunca el suceso en sí)"}}
  ],
  "pregunta": "la pregunta final al espectador, tal cual",
  "busquedas_imagenes": ["3 a 5 búsquedas en inglés para encontrar fotos de archivo en Wikimedia Commons de los LUGARES e INSTITUCIONES de la noticia: ciudades, calles conocidas, monumentos, edificios oficiales, banderas (p. ej. «Paris Champs-Élysées», «Palais de l'Élysée», «Hôtel de Matignon», «Flag of France»). NUNCA disturbios, protestas, incendios, policía en acción, víctimas ni capturas de apps o webs: esas fotos serían de otros sucesos o tendrían derechos"],
  "hashtags": ["#actualidad", "..."]
}}
Los NOMBRES de las claves son siempre exactamente estos, sin traducir. Los VALORES de "narracion", "titulo", "nombre_corto",
"gancho" y "hashtags" van en {idioma}. Los de "visual" y "busquedas_imagenes" van SIEMPRE en inglés."""

PROMPT_VIDEO_IA = """Eres guionista de vídeos cortos virales (YouTube Shorts, TikTok) que se generan con una IA de vídeo
(Veo, Sora, Runway, Kling): cada escena será un clip de unos {segundos} segundos con el mismo personaje.
Recibirás una TEMÁTICA. Puede ser histórica, de ficción o una recreación: cuéntala de forma entretenida y visual.

Reglas:
- {escenas} escenas exactamente, una por clip. Cada escena es UNA acción clara y fácil de generar en vídeo (un plano,
  sin cortes, sin multitudes complicadas, sin texto en pantalla).
- Un PROTAGONISTA fijo en todas las escenas, descrito con detalle para que la IA lo dibuje siempre igual.
- La PRIMERA escena engancha en el primer segundo (una situación sorprendente, una pregunta, algo que no encaja).
- Si es un hecho real, no inventes datos concretos (fechas, cifras, nombres) que no sean de conocimiento general;
  si es ficción o humor, que se note.
{reglas_voz}

Responde SOLO con un objeto JSON:
{{
  "titulo": "título atractivo",
  "nombre_corto": "2 a 4 palabras que nombren el vídeo",
  "gancho": "1 a 4 palabras en grande en el primer segundo",
  "tono": "uno de: epico, misterio, triste, neutro, comico (para la música)",
  "personaje": "descripción visual del protagonista EN INGLÉS, muy concreta: edad, rasgos, pelo, ropa, accesorios, colores (1-2 frases)",
  "escenas": [
    {{"narracion": "lo que se dice en esta escena", "accion": "qué pasa en el plano EN INGLÉS: acción del personaje, lugar, época, plano de cámara (close-up, medium shot, tracking shot…) y luz"}}
  ],
  "hashtags": ["#...", "..."]
}}
Los NOMBRES de las claves son siempre exactamente estos. "narracion", "titulo", "nombre_corto", "gancho" y "hashtags" van
en {idioma}; "personaje" y "accion" van SIEMPRE en inglés."""

REGLAS_VOZ_IA = """- La "narracion" de cada escena la DICE EL PERSONAJE en el clip, mirando a cámara o a otro personaje: como mucho
  {maximo} palabras por escena (tiene que caber en {segundos} segundos hablando con calma). Frases naturales, en primera
  persona o como diálogo."""
REGLAS_VOZ_APP = """- La "narracion" la lee una voz en off sobre los clips: entre {minimo} y {maximo} palabras en total (unos 40-45 s),
  repartidas entre las escenas. En los clips nadie habla."""

PROMPT_VERIFICADOR = """Eres verificador de datos. Recibirás un MATERIAL (las fuentes) y las escenas numeradas de un guion.
Revisa cada afirmación factual de la narración (fechas, cifras, lugares, personas, cómo ocurrió algo, causas y consecuencias).
Señala SOLO las que no estén respaldadas por el MATERIAL o lo contradigan. Ignora las frases de opinión, preguntas retóricas y llamadas a comentar.

Responde SOLO con un objeto JSON:
{"sin_respaldo": [{"escena": 1, "frase": "fragmento exacto del guion", "motivo": "qué no aparece o qué dice el material"}]}
Si todo está respaldado, devuelve {"sin_respaldo": []}. Escribe "motivo" en español."""

# Por si el modelo traduce las claves al escribir en inglés.
CLAVES_ALTERNATIVAS = {
    "title": "titulo", "scenes": "escenas", "narration": "narracion", "narración": "narracion",
    "short_name": "nombre_corto", "hook": "gancho", "tone": "tono", "image_searches": "busquedas_imagenes",
    "action": "accion", "character": "personaje",
}
TONOS = ("epico", "misterio", "triste", "neutro", "comico")


def normalizar_claves(valor):
    if isinstance(valor, dict):
        return {CLAVES_ALTERNATIVAS.get(k, k): normalizar_claves(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [normalizar_claves(v) for v in valor]
    return valor


# --- Wikipedia --------------------------------------------------------------

def descargar_efemerides(fecha: date, tipo: str) -> list:
    """tipo: "selected" (elegidas por los editores de Wikipedia) o "events" (todas)."""
    url = URL_EFEMERIDES.format(tipo=tipo, mes=fecha.month, dia=fecha.day)
    return wikimedia.json_api(url).get(tipo, [])


def texto_articulo(titulo: str) -> str:
    """Texto plano del artículo (más material que el resumen corto del feed)."""
    parametros = {
        "action": "query", "prop": "extracts", "explaintext": 1,
        "redirects": 1, "titles": titulo, "format": "json", "formatversion": 2,
    }
    try:
        paginas = wikimedia.json_api(URL_WIKI_API, parametros).get("query", {}).get("pages", [])
        return (paginas[0].get("extract") or "") if paginas else ""
    except wikimedia.WikimediaEnEspera:
        raise  # que se vea el aviso de espera, no un «artículo vacío»
    except requests.RequestException:
        return ""


# Lo que mejor funciona en el canal: España (y el mundo hispano) y personajes famosos. Esos eventos pesan más.
TEMAS_CERCANOS = re.compile(
    r"\b(españ\w*|madrid|barcelona|sevilla|valencia|bilbao|cataluñ\w*|andaluc\w*|galicia|país vasco|castilla|"
    r"aragón|navarra|canari\w*|baleares|franco|franquis\w*|guerra civil|república española|borbón|"
    r"alfonso xii|felipe vi?|juan carlos|real madrid|barça|fc barcelona|atlético de madrid|"
    r"méxic\w*|argentin\w*|colombi\w*|chile\w*|perú|peruan\w*|venezol\w*|cuba\w*|hispan\w*|latinoam\w*)\b", re.I)
FAMOSOS = re.compile(
    r"\b(futbolista|futbol\w*|tenista|piloto|ciclista|baloncestista|boxeador|deportista|cantante|cantautor|"
    r"actor|actriz|cineasta|director de cine|músico|compositor|rapero|banda|pintor|científico|inventor|"
    r"explorador|astronauta)\b", re.I)
PESO_CERCANO, PESO_FAMOSO, PESO_SELECCIONADO = 1.8, 1.5, 1.5


def peso_tema(evento: dict) -> float:
    """Cuánto más interesa el evento al público del canal (1 = normal)."""
    paginas = evento.get("pages", [])[:MAX_PAGINAS_POR_EVENTO]
    texto = " ".join([evento.get("text", "")] + [f"{_titulo(p)} {p.get('description', '')}" for p in paginas])
    peso = PESO_CERCANO if TEMAS_CERCANOS.search(texto) else 1.0
    if FAMOSOS.search(" ".join(p.get("description", "") for p in paginas)):
        peso *= PESO_FAMOSO
    return peso


def elegir_eventos(seleccionados: list, eventos: list, cantidad: int, anio_actual: int) -> list:
    """Los eventos con más material, dando más peso a España, a los famosos y a los que eligió Wikipedia.

    Uno por año para variar.
    """
    candidatos, vistos = [], set()
    for evento in [*seleccionados, *eventos]:
        anio = evento.get("year")
        if not isinstance(anio, int) or not evento.get("pages") or evento.get("text") in vistos:
            continue
        elegido = evento in seleccionados
        if not elegido and anio > anio_actual - ANTIGUEDAD_MINIMA:
            continue
        vistos.add(evento.get("text"))
        riqueza = sum(len(p.get("extract", "")) for p in evento.get("pages", [])[:MAX_PAGINAS_POR_EVENTO])
        if riqueza:
            candidatos.append((riqueza * peso_tema(evento) * (PESO_SELECCIONADO if elegido else 1), evento))
    candidatos.sort(key=lambda par: par[0], reverse=True)

    elegidos, anios = [], set()
    for _, evento in candidatos:
        if evento["year"] not in anios:
            elegidos.append(evento)
            anios.add(evento["year"])
        if len(elegidos) == cantidad:
            break
    return elegidos


def _titulo(pagina: dict) -> str:
    return pagina.get("titles", {}).get("normalized") or pagina.get("title", "")


def ordenar_paginas(evento: dict) -> list:
    """Pone primero los artículos cuyo título aparece en el texto del evento (el protagonista)."""
    texto = evento.get("text", "").lower()
    paginas = evento.get("pages", [])
    return sorted(paginas, key=lambda p: _titulo(p).lower() not in texto)


def preparar_material(evento: dict) -> tuple:
    """Devuelve (texto del material para el LLM, lista de fuentes)."""
    partes = [f"EVENTO ({evento['year']}): {evento['text']}"]
    fuentes = []
    for pagina in ordenar_paginas(evento)[:MAX_PAGINAS_POR_EVENTO]:
        titulo = _titulo(pagina)
        url = pagina.get("content_urls", {}).get("desktop", {}).get("page", "")
        texto = texto_articulo(pagina.get("title", titulo)) or pagina.get("extract", "")
        if not texto:
            continue
        maximo = MAX_CARACTERES_PRINCIPAL if not fuentes else MAX_CARACTERES_PAGINA
        partes.append(f"--- ARTÍCULO: {titulo}\n{texto[:maximo]}")
        fuentes.append({"titulo": titulo, "url": url})
    return "\n\n".join(partes), fuentes


# --- Groq --------------------------------------------------------------------

# La capa gratuita de Groq tiene un cupo de tokens POR DÍA y POR MODELO (p. ej. 200.000 para
# gpt-oss-120b, unos 10-12 guiones). Cuando un modelo lo agota, se pasa al siguiente de reserva.
MODELOS_RESERVA = [m.strip() for m in (os.getenv("MODELOS_RESERVA") or "openai/gpt-oss-20b,qwen/qwen3.8-27b").split(",")
                   if m.strip()]
MODELO_VERIFICADOR = os.getenv("MODELO_VERIFICADOR") or "openai/gpt-oss-20b"  # ahorra cupo del principal
ARCHIVO_CUPO = Path("salida/_trabajo/groq_cupo.json")  # modelos sin cupo y hasta cuándo (lo lee el menú)
ESPERA_CORTA = 60  # s; esperas más largas son el cupo diario: no se espera, se cambia de modelo
ultimo_modelo = ""  # el modelo que respondió la última llamada


class GroqSinCupo(RuntimeError):
    """Todos los modelos han agotado su cupo diario gratuito."""

    def __init__(self, hasta: float):
        self.hasta = hasta
        super().__init__(
            f"Se ha agotado el cupo diario gratuito de Groq en todos los modelos. Vuelve a probar a las "
            f"{time.strftime('%H:%M', time.localtime(hasta))} (o activa el plan de pago en console.groq.com)."
        )


class _CupoAgotado(Exception):
    def __init__(self, segundos: float):
        self.segundos = segundos


def cupos_agotados() -> dict:
    """{modelo: hora hasta la que no tiene cupo} de los que siguen agotados."""
    try:
        cupos = json.loads(ARCHIVO_CUPO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {m: hasta for m, hasta in cupos.items() if hasta > time.time()}


def _apuntar_sin_cupo(modelo: str, segundos: float) -> float:
    cupos = cupos_agotados()
    cupos[modelo] = time.time() + segundos
    ARCHIVO_CUPO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO_CUPO.write_text(json.dumps(cupos), encoding="utf-8")
    return cupos[modelo]


ESPERAS_RED = (5, 15, 30, 60)  # s entre reintentos si se corta internet (casi 2 minutos en total)


def _post_con_reintentos(url: str, cabeceras: dict, carga: dict) -> requests.Response:
    """POST que aguanta cortes breves de red (DNS que no responde, wifi que se cae, tiempo agotado)."""
    for espera in (*ESPERAS_RED, None):
        try:
            return requests.post(url, headers=cabeceras, json=carga, timeout=120)
        except (requests.ConnectionError, requests.Timeout) as error:
            if espera is None:
                raise RuntimeError("no hay conexión con Groq (¿se ha caído internet?). Vuelve a lanzarlo cuando "
                                   "vuelva la conexión") from error
            print(f"    sin conexión con Groq; reintento en {espera} s…", flush=True)
            time.sleep(espera)


def _llamar_modelo(api_key: str, modelo: str, sistema: str, usuario: str) -> str:
    carga = {
        "model": modelo,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 3000,
        "reasoning_effort": "low",  # gpt-oss razona antes de responder; "low" gasta menos tokens
    }
    if not modelo.startswith("openai/gpt-oss"):
        del carga["reasoning_effort"]  # otros modelos no aceptan este parámetro
    cabeceras = {"Authorization": f"Bearer {api_key}"}
    for intento in range(4):
        respuesta = _post_con_reintentos(URL_GROQ, cabeceras, carga)
        if respuesta.status_code == 429:
            try:
                espera = float(respuesta.headers.get("retry-after", 10))
            except ValueError:
                espera = 10.0
            if espera > ESPERA_CORTA or intento == 3:
                raise _CupoAgotado(espera)  # cupo diario: no tiene sentido esperar aquí
            print(f"    límite por minuto de Groq, esperando {espera:.0f} s…", flush=True)
            time.sleep(espera)
            continue
        if respuesta.status_code >= 400:
            # Mostramos el mensaje de Groq (no contiene la clave) para poder diagnosticar.
            raise RuntimeError(f"Groq respondió {respuesta.status_code}: {respuesta.text[:300]}")
        return respuesta.json()["choices"][0]["message"]["content"] or ""
    raise _CupoAgotado(60)


def llamar_groq(api_key: str, modelo: str, sistema: str, usuario: str) -> str:
    """Llama al modelo preferido y, si no tiene cupo, a los de reserva (y al principal) por orden."""
    global ultimo_modelo
    principal = os.getenv("MODELO") or MODELO_POR_DEFECTO
    orden = list(dict.fromkeys([modelo, principal, *MODELOS_RESERVA]))
    for candidato in orden:
        if candidato in cupos_agotados():
            continue
        try:
            contenido = _llamar_modelo(api_key, candidato, sistema, usuario)
        except _CupoAgotado as agotado:
            hasta = _apuntar_sin_cupo(candidato, agotado.segundos)
            print(f"    {candidato}: cupo diario agotado hasta las {time.strftime('%H:%M', time.localtime(hasta))}; "
                  "paso al siguiente modelo", flush=True)
            continue
        if candidato != ultimo_modelo and candidato not in (modelo, principal):
            print(f"    usando el modelo de reserva {candidato}", flush=True)
        ultimo_modelo = candidato
        return contenido
    raise GroqSinCupo(min(cupos_agotados().values(), default=time.time() + 600))
    raise RuntimeError("Límite de peticiones de Groq superado")


def validar_guion(datos: dict) -> list:
    """Comprueba la forma del guion. Devuelve la lista de escenas limpia."""
    if not isinstance(datos, dict) or not str(datos.get("titulo", "")).strip():
        raise ValueError("falta el título")
    escenas = datos.get("escenas")
    if not isinstance(escenas, list) or not escenas:
        raise ValueError("faltan escenas")
    limpias = []
    for escena in escenas:
        narracion = str((escena or {}).get("narracion", "")).strip()
        accion = str((escena or {}).get("accion", "")).strip()  # formato «Vídeo con IA»: lo que pasa en el clip
        visual = str((escena or {}).get("visual", "")).strip() or accion
        if not narracion or not visual:
            raise ValueError("hay una escena sin narración o sin visual")
        limpias.append({"narracion": narracion, "visual": visual, **({"accion": accion} if accion else {})})
    return limpias


def contar_palabras(escenas: list) -> int:
    return sum(len(e["narracion"].split()) for e in escenas)


MAX_PALABRAS_GANCHO = 18  # la primera frase tiene que caber en los 3-4 primeros segundos
_MESES = "|".join(MESES_ES) + "|january|february|march|april|may|june|july|august|september|october|november|december"
# Arranques que hacen deslizar: saludos, presentaciones, «había una vez» y fechas sueltas («En 1936,», «El 11 de
# septiembre de 2001,», «Corría el año…»). Un año dentro de un dato sorprendente sí vale («En 1936 cayó…» no).
INICIOS_FLOJOS = re.compile(
    r"^(hola|hey|buenas|bienvenid|hello|hi\b|welcome|"
    r"hoy (te|os|les) (voy|vamos)|hoy (vamos|voy) a|en (este|el) (v[ií]deo|short)|te voy a contar|os voy a contar|"
    r"today (i|we)('m| am|'re| are)? ?(going|gonna)|in this (video|short)|let me tell you|"
    r"[ée]rase una vez|hab[ií]a una vez|once upon a time|corr[ií]a el a[ñn]o|"
    r"¿?sab[ií]as que|did you know)", re.I)
FECHA_SUELTA = re.compile(
    rf"^(en|el|in|on)?\s*(el\s+)?(\d{{1,2}}\s+(de\s+)?({_MESES})(\s+de)?\s*)?(\d{{3,4}}|({_MESES})\s+\d{{1,2}},?\s+\d{{4}})\s*,",
    re.I)


# «Buenaventura Durruti, figura clave del anarquismo…»: presentar a alguien como una enciclopedia hace deslizar.
PRESENTACION = re.compile(
    r"^([A-ZÁÉÍÓÚÑ][\w.'-]+\s+){0,3}[A-ZÁÉÍÓÚÑ][\w.'-]+,\s+(figura|l[ií]der|conocid|famos|considerad|"
    r"nacid|reconocid|destacad|important|c[eé]lebre|known|famous|born)\w*")


def problema_gancho(narracion: str) -> str:
    """Por qué la primera frase de la escena 1 no sirve de gancho, o "" si vale."""
    texto = narracion.strip().lstrip("«\"'¡")
    primera = re.split(r"(?<=[.!?…])\s+", texto, maxsplit=1)[0]
    if INICIOS_FLOJOS.match(texto):
        return f"empieza con «{' '.join(primera.split()[:4])}…», que hace deslizar"
    if fecha := FECHA_SUELTA.match(texto):
        return f"empieza con una fecha suelta («{fecha.group(0).rstrip(' ,')}»)"
    if PRESENTACION.match(texto):
        return "empieza presentando al protagonista como una enciclopedia («X, figura clave de…»)"
    if len(primera.split()) > MAX_PALABRAS_GANCHO:
        return f"tiene {len(primera.split())} palabras y debe tener {MAX_PALABRAS_GANCHO} como mucho"
    return ""


def pregunta_de(escenas: list) -> str:
    """La pregunta con la que acaba la última escena («¿Tú qué habrías hecho?»), o "" si no acaba preguntando."""
    final = escenas[-1]["narracion"].strip().rstrip("»\"' ") if escenas else ""
    if not final.endswith("?"):
        return ""
    inicio = final.rfind("¿")
    if inicio < 0:  # en inglés no hay «¿»: desde el final de la frase anterior
        inicio = max(final.rfind(". ", 0, len(final) - 1), final.rfind("! ", 0, len(final) - 1)) + 1
    pregunta = final[inicio:].strip()
    return pregunta[:2].upper() + pregunta[2:] if pregunta.startswith("¿") else pregunta[:1].upper() + pregunta[1:]


def generar_guion(api_key: str, modelo: str, material: str, idioma: str, indicaciones: str = "",
                  sistema: str = "", minimo: int = PALABRAS_MIN, maximo: int = PALABRAS_MAX,
                  objetivo: int = PALABRAS_OBJETIVO, revisar_gancho: bool = True, pregunta_final: bool = True) -> dict:
    """Pide el guion y lo valida. `sistema`, `minimo`, `maximo` y `objetivo` permiten otros formatos (p. ej. el diario).

    Con `revisar_gancho`, la primera frase tiene que enganchar (ni saludos, ni fechas sueltas, ni frases largas).
    Con `pregunta_final`, la última escena tiene que acabar preguntando al espectador (da comentarios).
    """
    sistema = sistema or PROMPT_SISTEMA.format(min_palabras=minimo, max_palabras=maximo, objetivo=objetivo,
                                               idioma=IDIOMAS[idioma])
    if indicaciones:
        material = f"{indicaciones}\n\n{material}"
    usuario = f"MATERIAL:\n{material}"
    ultimo_error = mejor = None
    mejor_puntos = None
    for _ in range(3):  # reintenta si el JSON, la longitud o el gancho no valen
        try:
            datos = normalizar_claves(json.loads(llamar_groq(api_key, modelo, sistema, usuario)))
            escenas = validar_guion(datos)
            palabras = contar_palabras(escenas)
            fallos = []
            if not minimo <= palabras <= maximo:
                direccion = "corto: añade" if palabras < minimo else "largo: quita"
                fallos.append(f"tiene {palabras} palabras y debe tener entre {minimo} y {maximo}; "
                              f"es demasiado {direccion} unas {abs(objetivo - palabras)} palabras")
            gancho = problema_gancho(escenas[0]["narracion"]) if revisar_gancho else ""
            if gancho:
                fallos.append(f"la primera frase no engancha: {gancho}. Empieza directamente con el dato más "
                              "sorprendente, la contradicción o la pregunta del MATERIAL, en una frase corta")
            sin_pregunta = pregunta_final and not pregunta_de(escenas)
            if sin_pregunta:
                fallos.append("la última escena no termina con una pregunta al espectador: añádela al final")
            if not fallos:
                return {**datos, "escenas": escenas, "pregunta": pregunta_de(escenas) or datos.get("pregunta", "")}
            # Mejor un buen gancho que la pregunta, y la pregunta que la longitud exacta.
            puntos = (bool(gancho), sin_pregunta, abs(palabras - objetivo))
            if mejor is None or puntos < mejor_puntos:
                mejor, mejor_puntos = {**datos, "escenas": escenas}, puntos
            raise ValueError("; ".join(fallos))
        except ValueError as error:  # incluye JSON inválido
            ultimo_error = error
            usuario = f"MATERIAL:\n{material}\n\nTu intento anterior no era válido ({error}). Corrígelo."
    if mejor is not None:  # forma correcta pero longitud o gancho mejorables: se guarda avisando
        print(f"    aviso: {ultimo_error}; se guarda el intento más cercano")
        return {**mejor, "pregunta": pregunta_de(mejor["escenas"]) or mejor.get("pregunta", "")}
    raise ValueError(f"no se obtuvo un guion válido: {ultimo_error}")


AVISO_ACTUALIDAD = """
ATENCIÓN: es una noticia de actualidad y hoy es {hoy}. Dos cosas las exige el formato y NUNCA se señalan, aunque el
MATERIAL no las diga: la fecha de hoy en la última escena («a {hoy_corto}», «la situación puede cambiar») y las
preguntas al espectador («¿tú qué opinas?», «¿qué pasará ahora?»), que no son afirmaciones. Si una frase mezcla eso
con un dato, juzga solo el dato. Sí señala cifras, nombres, fechas de los hechos o atribuciones («según X») que el
MATERIAL no respalde."""


AVISO_HUMOR = """
ATENCIÓN: este guion es de HUMOR en primera persona («Día X como…»). Ignora las exageraciones evidentes, las
quejas, las opiniones, las comparaciones absurdas, la jerga moderna y los chistes que nadie tomaría como un dato.
Señala SOLO las afirmaciones que un espectador creería como hechos históricos (objetos, costumbres, cifras,
cargos, lugares, fechas) y que el MATERIAL no respalda."""


def verificar_guion(api_key: str, modelo: str, material: str, escenas: list, humor: bool = False,
                    noticia: bool = False) -> list:
    """Segunda pasada: lista las frases del guion que el material no respalda.

    Con `humor` (formato diario) no cuenta los chistes como datos: solo las afirmaciones históricas.
    """
    numeradas = "\n".join(f"{i}. {e['narracion']}" for i, e in enumerate(escenas, start=1))
    hoy = date.today()
    aviso_noticia = AVISO_ACTUALIDAD.format(hoy=hoy.isoformat(), hoy_corto=f"{hoy.day} de {MESES_ES[hoy.month - 1]}")
    sistema = PROMPT_VERIFICADOR + (AVISO_HUMOR if humor else "") + (aviso_noticia if noticia else "")
    respuesta = llamar_groq(api_key, MODELO_VERIFICADOR, sistema, f"MATERIAL:\n{material}\n\nGUION:\n{numeradas}")
    try:
        datos = json.loads(respuesta)
    except ValueError:
        return [{"escena": None, "frase": "", "motivo": "el verificador no devolvió JSON válido: revisa todo a mano"}]
    dudas = datos.get("sin_respaldo", []) if isinstance(datos, dict) else []
    return [
        {"escena": d.get("escena"), "frase": str(d.get("frase", "")), "motivo": str(d.get("motivo", ""))}
        for d in dudas
        if isinstance(d, dict)
    ]


# --- Salida --------------------------------------------------------------------

def slug(texto: str, maximo: int = 40) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")[:maximo].rstrip("-") or "evento"


def acortar_nombre(nombre) -> str:
    """Nombre corto de verdad: hasta la primera coma o dos puntos, y 4 palabras como mucho."""
    nombre = re.split(r"[,:;(]", str(nombre or ""))[0]
    return " ".join(nombre.split()[:4]).strip(" .-")


def normalizar_tono(tono) -> str:
    tono = unicodedata.normalize("NFKD", str(tono or "")).encode("ascii", "ignore").decode().lower().strip()
    return tono if tono in TONOS else ""


def guardar(guion: dict, evento: dict, fuentes: list, dudas: list, fecha: date, idioma: str, modelo: str) -> Path:
    escenas = [{"numero": i, **escena} for i, escena in enumerate(guion["escenas"], start=1)]
    palabras = contar_palabras(escenas)
    titulo = guion["titulo"].strip()
    parte, total = evento.get("parte"), evento.get("total")
    if total and total > 1:
        titulo = f"{titulo} ({'Part' if idioma == 'en' else 'Parte'} {parte}/{total})"
    documento = {
        "fecha": fecha.isoformat(),
        "anio_evento": evento["year"],
        "evento": evento["text"],
        "idioma": idioma,
        "titulo": titulo,
        "palabras": palabras,
        "duracion_estimada_s": round(palabras / PALABRAS_POR_SEGUNDO),
        "escenas": escenas,
        # Nombre del archivo de vídeo y de su carpeta (p. ej. «Guerra civil» → «Guerra civil pt3.mp4»).
        "nombre_corto": acortar_nombre(guion.get("nombre_corto")),
        # Frase corta en grande al empezar el vídeo y en la miniatura.
        "gancho": str(guion.get("gancho") or "").strip()[:40],
        # Música de fondo: un tono de salida/musica (epico, misterio, triste, neutro) o "ninguna".
        "musica": normalizar_tono(guion.get("tono")) or "neutro",
        "hashtags": [h for h in guion.get("hashtags", []) if isinstance(h, str)],
        # Pregunta final: se repite en la descripción y como comentario para fijar (da comentarios).
        "pregunta": str(guion.get("pregunta") or "").strip()[:200],
        # Palabras que los subtítulos resaltan siempre (las graciosas o clave).
        "palabras_clave": [str(p) for p in guion.get("palabras_clave", []) if isinstance(p, str)][:10],
        "fuentes": fuentes,
        # Frases que el verificador automático no encontró en el material: corrígelas o compruébalas.
        "sin_respaldo": dudas,
        "verificado": False,  # cámbialo a true cuando hayas comprobado los datos con las fuentes
        "modelo": modelo,
    }
    sufijo = ""
    if total and total > 1:
        documento["serie"] = {"tema": evento["text"], "parte": parte, "total": total}
        sufijo = f"_parte{parte}de{total}"
    prefijo = evento["year"] if evento.get("year") else "tema"
    if evento.get("video_ia"):  # clips generados con una IA de vídeo: personaje fijo y prompt por escena
        import video_ia
        prefijo = "videoia"
        datos_ia = {**evento["video_ia"], "personaje": str(guion.get("personaje") or "").strip()}
        documento["video_ia"] = datos_ia
        for escena in documento["escenas"]:
            escena["prompt_video"] = video_ia.prompt_completo(datos_ia, escena, idioma)
            escena["visual"] = escena.get("accion") or escena.get("visual") or ""
    if evento.get("actualidad"):  # noticia: medios, fecha de los datos y búsquedas para las imágenes de archivo
        prefijo = "actualidad"
        documento["actualidad"] = {
            **evento["actualidad"],
            "fecha_datos": date.today().isoformat(),
            "pregunta": "la pregunta final al espectador, tal cual",
  "busquedas_imagenes": [str(b) for b in guion.get("busquedas_imagenes", []) if isinstance(b, str)][:5],
        }
    if evento.get("diario"):  # formato «Día X como…»: prompts para el generador de IA y el número de día
        diario = evento["diario"]
        documento["diario"] = diario
        documento["nombre_corto"] = diario["nombre_corto"] or documento["nombre_corto"]
        documento["personaje_visual"] = str(guion.get("personaje_visual") or "").strip()
        documento["prompt_video"] = str(guion.get("prompt_video") or "").strip()
        prefijo, sufijo = "diario", f"_dia{diario['dia']}"
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    nombre = f"{fecha.isoformat()}_{prefijo}_{slug(evento['text'])}{sufijo}_{idioma}.json"
    ruta = CARPETA_SALIDA / nombre
    numero = 2
    while ruta.exists():  # nunca se pisa un guion que ya existe (puede estar revisado, con vídeo o en YouTube)
        ruta = CARPETA_SALIDA / nombre.replace(f"_{idioma}.json", f"_{numero}_{idioma}.json")
        numero += 1
    ruta.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


# Artículos sobre obras (no sobre el hecho histórico): se descartan al buscar un tema.
OBRAS = re.compile(r"\((película|serie|telenovela|canción|álbum|banda|videojuego|novela|libro|musical|ópera|obra)", re.I)


def buscar_articulo(tema: str) -> str:
    """Título del artículo de Wikipedia en español que mejor encaja con el tema, o ""."""
    parametros = {
        "action": "query", "list": "search", "srsearch": tema, "srlimit": 5,
        "srprop": "size", "format": "json", "formatversion": 2,
    }
    datos = wikimedia.json_api(URL_WIKI_API, parametros, caducidad=24 * 3600)  # búsquedas: 1 día
    resultados = [r for r in datos.get("query", {}).get("search", []) if not OBRAS.search(r["title"])]
    if not resultados:
        return ""
    # Entre los 3 más relevantes, el más completo (un artículo corto da poco material para el guion).
    return max(resultados[:3], key=lambda r: r.get("size", 0))["title"]


# Secciones del final de los artículos que no aportan hechos para el guion.
SECCIONES_FINALES = re.compile(
    r"^==+\s*(Referencias|Notas|Notas y referencias|Bibliografía|Bibliografía adicional|Enlaces externos|"
    r"Véase también|Fuentes|Galería)\s*==+\s*$",
    re.M | re.I,
)
MAX_CARACTERES_PARTE = 6000   # material por parte de una serie
MIN_CARACTERES_PARTE = 1500   # por debajo no hay material para un vídeo
MAX_PARTES = 3                # en las series largas cada parte pierde público: 3 como mucho


def dividir_en_partes(texto: str, partes: int) -> list:
    """Reparte el artículo, en orden, en tramos de tamaño parecido (uno por vídeo)."""
    final = SECCIONES_FINALES.search(texto)
    if final:
        texto = texto[: final.start()]
    parrafos = [p.strip() for p in texto.split("\n") if p.strip()]
    objetivo = sum(len(p) for p in parrafos) / partes
    tramos, acumulado = [[] for _ in range(partes)], 0
    for parrafo in parrafos:
        tramos[min(int(acumulado / objetivo), partes - 1)].append(parrafo)
        acumulado += len(parrafo)
    return ["\n".join(t)[:MAX_CARACTERES_PARTE] for t in tramos]


PROMPT_INDICE = """Planificas una serie de {partes} vídeos cortos de historia (~40-45 segundos cada uno) sobre «{tema}».
Recibirás las secciones numeradas de un artículo de Wikipedia, con su tamaño y su comienzo.

Reparte las secciones entre las {partes} partes:
- En orden narrativo (normalmente cronológico): antecedentes → desarrollo → desenlace y consecuencias.
- Cada sección en una sola parte. Puedes dejar fuera secciones que no aporten hechos interesantes.
- Cada parte necesita material suficiente: al menos {minimo} caracteres en total.
- El desenlace (el momento clave final) va en la ÚLTIMA parte; las anteriores deben crear intriga sin adelantarlo.

Responde SOLO con un objeto JSON:
{{"partes": [{{"secciones": [1, 2], "enfoque": "qué cuenta esta parte, en una frase"}}],
  "desenlace": "en una frase, lo que las partes anteriores a la última NO deben revelar"}}"""


def secciones_articulo(texto: str) -> list:
    """[(título, texto)] del artículo, sin las secciones finales (referencias, enlaces…)."""
    final = SECCIONES_FINALES.search(texto)
    if final:
        texto = texto[: final.start()]
    trozos = re.split(r"^(==+)\s*(.+?)\s*\1\s*$", texto, flags=re.M)
    secciones = [("Introducción", trozos[0].strip())]
    for i in range(1, len(trozos) - 2, 3):
        secciones.append((trozos[i + 1].strip(), trozos[i + 2].strip()))
    return [(titulo, cuerpo) for titulo, cuerpo in secciones if len(cuerpo) > 80]


def indice_serie(api_key: str, modelo: str, tema: str, secciones: list, partes: int):
    """Pide a la IA el reparto de secciones por parte. Devuelve (lista de partes, desenlace) o None."""
    lista = "\n".join(
        f"{i}. {titulo} ({len(cuerpo)} caracteres): {cuerpo[:150].replace(chr(10), ' ')}…"
        for i, (titulo, cuerpo) in enumerate(secciones, start=1)
    )
    sistema = PROMPT_INDICE.format(partes=partes, tema=tema, minimo=MIN_CARACTERES_PARTE)
    try:
        datos = json.loads(llamar_groq(api_key, modelo, sistema, f"SECCIONES:\n{lista}"))
        plan = datos["partes"]
        if not isinstance(plan, list) or len(plan) != partes:
            return None
        for parte in plan:
            numeros = [int(n) for n in parte.get("secciones", []) if 1 <= int(n) <= len(secciones)]
            if not numeros:
                return None
            parte["secciones"] = sorted(set(numeros))  # en el orden del artículo
        return plan, str(datos.get("desenlace", ""))
    except (ValueError, KeyError, TypeError, RuntimeError, requests.RequestException):
        return None


def material_de_secciones(secciones: list, numeros: list) -> str:
    """Texto de las secciones elegidas, repartiendo el máximo de caracteres entre ellas."""
    cupo = MAX_CARACTERES_PARTE // len(numeros)
    return "\n\n".join(f"== {secciones[n - 1][0]} ==\n{secciones[n - 1][1][:cupo]}" for n in numeros)


def preparar_tema(tema: str, partes: int = 1, api_key: str = "", modelo: str = MODELO_POR_DEFECTO) -> list:
    """Material para un tema libre: el artículo de Wikipedia que mejor encaja.

    Con varias partes, la IA hace primero un índice de la serie (qué secciones cuenta cada
    parte); si falla, el artículo se reparte en orden en tramos iguales.
    Devuelve una lista de (evento, material, fuentes), una por vídeo.
    """
    titulo = buscar_articulo(tema)
    texto = texto_articulo(titulo) if titulo else ""
    if not texto:
        raise ValueError(f"No encuentro un artículo de Wikipedia en español sobre «{tema}»")
    url = "https://es.wikipedia.org/wiki/" + requests.utils.quote(titulo.replace(" ", "_"))
    fuentes = [{"titulo": titulo, "url": url}]
    if partes <= 1:
        material = f"TEMA: {tema}\n\n--- ARTÍCULO: {titulo}\n{texto[:MAX_CARACTERES_PRINCIPAL]}"
        return [({"year": None, "text": tema}, material, fuentes)]

    posibles = max(1, len(SECCIONES_FINALES.split(texto)[0]) // MIN_CARACTERES_PARTE)
    if partes > posibles:
        print(f"Aviso: el artículo solo da para unas {posibles} partes; hago {posibles}.")
        partes = posibles
        if partes == 1:
            return preparar_tema(tema, 1)
    contexto = texto[:600]

    secciones = secciones_articulo(texto)
    indice = indice_serie(api_key, modelo, tema, secciones, partes) if api_key and len(secciones) >= partes else None
    if indice:
        plan, desenlace = indice
        print("Índice de la serie:")
        for numero, parte in enumerate(plan, start=1):
            print(f"  Parte {numero}: {parte.get('enfoque', '')}  [secciones {parte['secciones']}]")
        tramos = [material_de_secciones(secciones, parte["secciones"]) for parte in plan]
        enfoques = [str(parte.get("enfoque", "")) for parte in plan]
    else:
        print("Índice de la serie no disponible: reparto el artículo en tramos iguales.")
        tramos, enfoques, desenlace = dividir_en_partes(texto, partes), [""] * partes, ""

    trabajos = []
    for numero, tramo in enumerate(tramos, start=1):
        material = f"TEMA: {tema}\n\n"
        if numero > 1:
            material += f"CONTEXTO (solo para situarte; no lo vuelvas a contar):\n{contexto}\n\n"
        material += f"--- ARTÍCULO: {titulo} (tramo {numero} de {partes})\n{tramo}"
        evento = {
            "year": None, "text": tema, "parte": numero, "total": partes,
            "enfoque": enfoques[numero - 1], "desenlace": desenlace, "enfoques": enfoques,
        }
        trabajos.append((evento, material, fuentes))
    return trabajos


# --- Diario («Día X como…») --------------------------------------------------------

ARCHIVO_DIARIOS = Path("salida/_trabajo/diarios.json")  # nombre corto de cada personaje (igual en todos sus días)


def clave_personaje(personaje: str, idioma: str = "") -> str:
    return slug(personaje, 60) + (f"|{idioma}" if idioma else "")


def siguiente_dia(personaje: str) -> int:
    """El día que toca: uno más que el último diario guardado de ese personaje (1 si no hay ninguno)."""
    clave, ultimo = clave_personaje(personaje), 0
    for ruta in CARPETA_SALIDA.glob("*.json") if CARPETA_SALIDA.exists() else []:
        try:
            diario = json.loads(ruta.read_text(encoding="utf-8")).get("diario") or {}
        except (OSError, ValueError):
            continue
        if clave_personaje(diario.get("personaje", "")) == clave:
            ultimo = max(ultimo, int(diario.get("dia") or 0))
    return ultimo + 1


def _nombres_diario() -> dict:
    try:
        return json.loads(ARCHIVO_DIARIOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def nombre_diario(personaje: str, idioma: str) -> str:
    return _nombres_diario().get(clave_personaje(personaje, idioma), "")


def apuntar_nombre_diario(personaje: str, idioma: str, nombre: str) -> None:
    nombres = _nombres_diario()
    nombres[clave_personaje(personaje, idioma)] = nombre
    ARCHIVO_DIARIOS.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO_DIARIOS.write_text(json.dumps(nombres, ensure_ascii=False, indent=2), encoding="utf-8")


def buscar_resultados(consulta: str, cuantos: int) -> list:
    """Títulos de Wikipedia por orden de relevancia (sin películas, novelas…)."""
    parametros = {"action": "query", "list": "search", "srsearch": consulta, "srlimit": cuantos + 3,
                  "format": "json", "formatversion": 2}
    datos = wikimedia.json_api(URL_WIKI_API, parametros, caducidad=24 * 3600)
    return [r["title"] for r in datos.get("query", {}).get("search", []) if not OBRAS.search(r["title"])][:cuantos]


def parrafos_relevantes(texto: str, claves: set, limite: int) -> str:
    """El principio del artículo y, sobre todo, los párrafos que hablan del tema (hasta `limite` caracteres)."""
    parrafos = [p.strip() for p in SECCIONES_FINALES.split(texto)[0].split("\n") if len(p.strip()) > 60]
    if not parrafos:
        return ""
    def puntos(p):
        return sum(1 for c in claves if c in slug(p, 10_000).replace("-", " "))
    elegidos = [parrafos[0]] + sorted(parrafos[1:], key=puntos, reverse=True)  # la entradilla siempre
    resultado = ""
    for parrafo in elegidos:
        if len(resultado) + len(parrafo) > limite:
            break
        resultado += parrafo + "\n"
    return resultado.strip()


def preparar_diario(personaje: str, problema: str, dia: int) -> tuple:
    """Material de Wikipedia para un diario: los artículos más relevantes del personaje y del tema.

    Devuelve (evento, material, fuentes).
    """
    titulos = buscar_resultados(personaje, 2)
    if problema:
        # Solo junto al personaje: el tema suelto trae artículos sin relación (series, libros…).
        titulos += buscar_resultados(f"{problema} {personaje}", 1)
    titulos = list(dict.fromkeys(titulos))[:3]
    claves = {p for p in slug(f"{problema} {personaje}", 200).split("-") if len(p) > 3}
    partes, fuentes = [], []
    for titulo in titulos:
        texto = parrafos_relevantes(texto_articulo(titulo), claves, MAX_CARACTERES_PRINCIPAL // len(titulos))
        if texto:
            partes.append(f"--- ARTÍCULO: {titulo}\n{texto}")
            fuentes.append({"titulo": titulo, "url": "https://es.wikipedia.org/wiki/"
                            + requests.utils.quote(titulo.replace(" ", "_"))})
    if not partes:
        raise ValueError(f"No encuentro en Wikipedia material sobre «{personaje}»")
    material = (
        f"PERSONAJE: {personaje}\nDÍA: {dia}\n"
        f"TEMA: {problema or '(elige tú una molestia o norma absurda real que aparezca en el MATERIAL)'}\n\n"
        + "\n\n".join(partes)
    )
    evento = {"year": None, "text": personaje,
              "diario": {"personaje": personaje, "dia": dia, "problema": problema, "nombre_corto": ""}}
    return evento, material, fuentes


def sistema_diario(dia: int, idioma: str) -> str:
    gancho, corto = (f"Day {dia} as", f"DAY {dia}") if idioma == "en" else (f"Día {dia} como", f"DÍA {dia}")
    minimo, maximo, objetivo = PALABRAS_DIARIO
    return PROMPT_DIARIO.format(gancho=gancho, gancho_corto=corto, min_palabras=minimo, max_palabras=maximo,
                                objetivo=objetivo, idioma=IDIOMAS[idioma])


def indicaciones_serie(evento: dict, titulos_previos: list) -> str:
    """Instrucciones extra para que cada parte de una serie encaje con las demás."""
    parte, total = evento.get("parte"), evento.get("total")
    if not total or total <= 1:
        return ""
    lineas = [
        f"SERIE: este guion es la PARTE {parte} DE {total} de una serie de vídeos sobre «{evento['text']}».",
        "Cuenta SOLO los hechos del tramo del artículo que viene en el MATERIAL; las otras partes cubren el resto.",
        f"El \"nombre_corto\" resume en 2 a 4 palabras el tema de toda la serie, no solo esta parte "
        f"(tema: «{evento['text']}»; si es largo, NO lo copies: resúmelo, p. ej. «Guerra civil»).",
    ]
    if evento.get("enfoque"):
        lineas.append(f"Esta parte cuenta: {evento['enfoque']}")
    if evento.get("enfoques"):
        lineas.append("Índice de la serie: " + " | ".join(f"{i}. {e}" for i, e in enumerate(evento["enfoques"], 1)))
    # Casi nadie ve las partes en orden: YouTube enseña cada una suelta. Tiene que entenderse sola.
    lineas.append("MUY IMPORTANTE: esta parte tiene que entenderse SOLA, sin haber visto las demás. Después del "
                  "gancho, sitúa en media frase de quién o de qué hablas y cuándo pasó. Nunca digas «como vimos», "
                  "«en la parte anterior» ni «seguimos».")
    if parte == 1:
        lineas.append("Es la primera parte: presenta el tema con un gancho fuerte.")
    else:
        lineas.append("No es la primera parte, pero empieza con un gancho propio de lo que cuenta ESTA parte, "
                      "no con un resumen de las anteriores. No repitas lo ya contado.")
        lineas.append("Títulos de las partes anteriores: " + " | ".join(titulos_previos))
    if parte < total:
        if evento.get("desenlace"):
            lineas.append(f"NO reveles el desenlace, que se cuenta en la última parte: {evento['desenlace']}")
        lineas.append("Termina con la pregunta al espectador sobre lo que pasará después, sin desvelarlo "
                      "(la parte siguiente se anuncia en la descripción).")
    else:
        lineas.append("Es la última parte: cierra la historia y termina con la pregunta al espectador.")
    return "\n".join(lineas)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Genera guiones a partir de Wikipedia (efemérides o un tema libre)")
    parser.add_argument("--tema", help='tema libre, p. ej. "La caída de Constantinopla" (en vez de efemérides)')
    parser.add_argument("--partes", type=int, default=1, help="con --tema: dividirlo en varios vídeos de 40-45 s")
    parser.add_argument("--diario", metavar="PERSONAJE",
                        help='formato «Día X como…» de humor histórico, p. ej. "soldado romano en Vindolanda"')
    parser.add_argument("--dia", type=int, default=0, help="con --diario: número de día (por defecto, el siguiente)")
    parser.add_argument("--problema", default="", help="con --diario: la molestia o norma de la época a contar")
    parser.add_argument("--cantidad", type=int, default=3, help="número de eventos (por defecto 3)")
    parser.add_argument("--fecha", type=date.fromisoformat, default=date.today(), help="AAAA-MM-DD (por defecto hoy)")
    parser.add_argument("--idiomas", default="es,en", help="idiomas separados por comas: es,en")
    parser.add_argument("--video-ia", metavar="TEMATICA",
                        help="vídeo hecho con clips de una IA de vídeo: la app escribe el guion y un prompt por escena")
    parser.add_argument("--herramienta", default="veo", help="con --video-ia: veo, sora, runway o kling")
    parser.add_argument("--estilo", default="cine", help="con --video-ia: cine, documental, animacion, anime o pintura")
    parser.add_argument("--voz", choices=("ia", "app"), default="",
                        help="con --video-ia: quién pone la voz (por defecto, la IA si sabe hacerlo)")
    parser.add_argument("--actualidad", metavar="ID",
                        help="vídeo de actualidad con los artículos de una búsqueda de actualidad.py (ver --articulos)")
    parser.add_argument("--articulos", default="", help="con --actualidad: números de los artículos a usar, p. ej. 0,2,3")
    parser.add_argument("--sin-repetir", action="store_true",
                        help="efemérides: salta los eventos que ya tienen guion (no los reescribe) y coge el siguiente")
    args = parser.parse_args(argv)

    api_key = os.getenv("GROQ_API_KEY", "")
    modelo = os.getenv("MODELO") or MODELO_POR_DEFECTO
    if not api_key:
        print("[error] Falta GROQ_API_KEY en el archivo .env", file=sys.stderr)
        return 1
    idiomas = [i.strip() for i in args.idiomas.split(",") if i.strip()]
    desconocidos = [i for i in idiomas if i not in IDIOMAS]
    if desconocidos:
        print(f"[error] Idiomas no soportados: {desconocidos}. Usa: {list(IDIOMAS)}", file=sys.stderr)
        return 1

    if args.video_ia:
        import video_ia
        h = video_ia.herramienta(args.herramienta)
        voz = args.voz or ("ia" if h["voz"] else "app")
        escenas = max(5, min(8, round(60 / h["segundos"])))
        print(f"Vídeo con IA: «{args.video_ia}» · {h['nombre']} · {escenas} clips de ~{h['segundos']} s · "
              f"voz {'de la IA' if voz == 'ia' else 'de la app'}")
        evento = {"year": None, "text": args.video_ia, "video_ia": {
            "tematica": args.video_ia, "herramienta": args.herramienta if args.herramienta in video_ia.HERRAMIENTAS
            else "veo", "voz": voz, "segundos": h["segundos"], "estilo": args.estilo,
            "estilo_visual": video_ia.ESTILOS.get(args.estilo, video_ia.ESTILOS["cine"]), "escenas": escenas}}
        trabajos = [(evento, f"TEMÁTICA: {args.video_ia}", [])]
    elif args.actualidad:
        import actualidad
        try:
            busqueda = actualidad.leer(args.actualidad)
        except (OSError, ValueError) as error:
            print(f"[error] no encuentro esa búsqueda de actualidad ({error}): vuelve a buscar", file=sys.stderr)
            return 1
        elegidos = [int(n) for n in args.articulos.split(",") if n.strip().isdigit()] or list(range(len(busqueda["articulos"])))
        articulos = [busqueda["articulos"][n] for n in elegidos if n < len(busqueda["articulos"])]
        if len(articulos) < 2:
            print("[error] hacen falta al menos 2 artículos de medios distintos para contrastar", file=sys.stderr)
            return 1
        print(f"Actualidad: «{busqueda['tema']}» con {len(articulos)} artículos: "
              + ", ".join(a["medio"] for a in articulos))
        evento = {"year": None, "text": busqueda["tema"],
                  "actualidad": {"tema": busqueda["tema"], "medios": [a["medio"] for a in articulos]}}
        fuentes = [{"titulo": f"{a['medio']}: {a['titulo']}", "url": a["url"], "medio": a["medio"],
                    "fecha": a.get("fecha", "")} for a in articulos]
        trabajos = [(evento, actualidad.material(articulos), fuentes)]
    elif args.diario:
        dia = args.dia if args.dia > 0 else siguiente_dia(args.diario)
        print(f"Diario de «{args.diario}» · día {dia}" + (f" · tema: {args.problema}" if args.problema else ""))
        try:
            trabajos = [preparar_diario(args.diario, args.problema, dia)]
        except (ValueError, requests.RequestException) as error:
            print(f"[error] {error}", file=sys.stderr)
            return 1
        print(f"Material de Wikipedia: {trabajos[0][2][0]['titulo']} ({trabajos[0][2][0]['url']})")
    elif args.tema:
        print(f"Buscando «{args.tema}» en Wikipedia…")
        try:
            trabajos = preparar_tema(args.tema, max(1, min(args.partes, MAX_PARTES)), api_key, modelo)
        except (ValueError, requests.RequestException) as error:
            print(f"[error] {error}", file=sys.stderr)
            return 1
        print(f"Artículo encontrado: {trabajos[0][2][0]['titulo']} ({trabajos[0][2][0]['url']})")
        if len(trabajos) > 1:
            print(f"Serie de {len(trabajos)} partes de 40-45 s")
    else:
        print(f"Descargando efemérides del {args.fecha:%d/%m}…")
        try:
            eventos = elegir_eventos(
                descargar_efemerides(args.fecha, "selected"),
                descargar_efemerides(args.fecha, "events"),
                args.cantidad + (20 if args.sin_repetir else 0),
                date.today().year,
            )
            if args.sin_repetir:  # los que ya tienen guion (hecho a mano o el día anterior), fuera
                idiomas = [i.strip() for i in args.idiomas.split(",") if i.strip()]
                existe = lambda e: any(  # noqa: E731
                    (CARPETA_SALIDA / f"{args.fecha.isoformat()}_{e['year']}_{slug(e['text'])}_{i}.json").exists()
                    for i in idiomas)
                repetidos = [e for e in eventos if existe(e)]
                for e in repetidos:
                    print(f"  ya tiene guion, se salta: {e['year']} · {e['text'][:70]}")
                eventos = [e for e in eventos if not existe(e)][:args.cantidad]
            if not eventos:
                print("[error] No hay eventos con material suficiente para esa fecha", file=sys.stderr)
                return 1
            trabajos = [(evento, *preparar_material(evento)) for evento in eventos]
        except requests.RequestException as error:  # incluye el aviso de espera de Wikipedia
            print(f"[error] {error}", file=sys.stderr)
            return 1

    generados = fallidos = 0
    titulos_previos = {idioma: [] for idioma in idiomas}  # para que cada parte de una serie siga a la anterior
    nombres_serie = {}  # idioma → nombre corto común a todas las partes
    for evento, material, fuentes in trabajos:
        parte = f" · parte {evento['parte']}/{evento['total']}" if evento.get("total") else ""
        print(f"\n· {evento['year'] or 'Tema'}: {evento['text'][:90]}{parte}")
        for idioma in idiomas:
            try:
                if evento.get("diario"):
                    diario = evento["diario"]
                    minimo, maximo, objetivo = PALABRAS_DIARIO
                    guion = generar_guion(api_key, modelo, material, idioma, "",
                                          sistema_diario(diario["dia"], idioma), minimo, maximo, objetivo,
                                          revisar_gancho=False)  # su gancho es el «Día X como…» fijo
                    # Todos los días de un personaje comparten nombre (y carpeta): se fija la primera vez.
                    nombre = nombre_diario(diario["personaje"], idioma) or acortar_nombre(guion.get("nombre_corto"))
                    apuntar_nombre_diario(diario["personaje"], idioma, nombre)
                    evento = {**evento, "diario": {**diario, "nombre_corto": nombre}}
                elif evento.get("video_ia"):
                    ia = evento["video_ia"]
                    maximo_escena = int(ia["segundos"] * 2.3)
                    if ia["voz"] == "ia":
                        reglas = REGLAS_VOZ_IA.format(maximo=maximo_escena, segundos=ia["segundos"])
                        minimo, maximo = ia["escenas"] * 8, ia["escenas"] * maximo_escena
                    else:
                        reglas = REGLAS_VOZ_APP.format(minimo=PALABRAS_MIN, maximo=PALABRAS_MAX)
                        minimo, maximo = PALABRAS_MIN, PALABRAS_MAX
                    sistema = PROMPT_VIDEO_IA.format(segundos=ia["segundos"], escenas=ia["escenas"],
                                                     reglas_voz=reglas, idioma=IDIOMAS[idioma])
                    guion = generar_guion(api_key, modelo, material, idioma, "", sistema, minimo, maximo,
                                          (minimo + maximo) // 2, pregunta_final=False)  # el formato no la pide
                elif evento.get("actualidad"):
                    hoy = date.today()
                    sistema = PROMPT_ACTUALIDAD.format(
                        hoy=hoy.isoformat(), hoy_corto=f"{hoy.day} de {MESES_ES[hoy.month - 1]}" if idioma == "es"
                        else hoy.strftime("%B %d"), min_palabras=PALABRAS_MIN, max_palabras=PALABRAS_MAX,
                        objetivo=PALABRAS_OBJETIVO, idioma=IDIOMAS[idioma])
                    guion = generar_guion(api_key, modelo, material, idioma, "", sistema)
                else:
                    indicaciones = indicaciones_serie(evento, titulos_previos[idioma])
                    guion = generar_guion(api_key, modelo, material, idioma, indicaciones)
                modelo_usado = ultimo_modelo or modelo  # puede ser uno de reserva
                titulos_previos[idioma].append(guion["titulo"])
                if evento.get("total"):  # todas las partes de una serie comparten el nombre de la primera
                    guion["nombre_corto"] = nombres_serie.setdefault(idioma, guion.get("nombre_corto") or "")
                dudas = [] if evento.get("video_ia") else verificar_guion(  # creativo: no hay fuente que verificar
                    api_key, modelo, material, guion["escenas"], humor=bool(evento.get("diario")),
                    noticia=bool(evento.get("actualidad")))
                ruta = guardar(guion, evento, fuentes, dudas, args.fecha, idioma, modelo_usado)
                aviso = f" · {len(dudas)} frase(s) sin respaldo, revísalas" if dudas else " · verificado contra el material"
                if evento.get("video_ia"):
                    aviso = " · copia los prompts en su página y sube un clip por escena"
                print(f"  [{idioma}] {ruta}{aviso} · escrito con {modelo_usado}")
                generados += 1
            except GroqSinCupo as error:  # no queda cupo en ningún modelo: no tiene sentido seguir
                print(f"[error] {error}", file=sys.stderr)
                fallidos += 1
                print(f"\nGuiones generados: {generados} · Con error: {fallidos}")
                return 2
            except (ValueError, RuntimeError, requests.RequestException) as error:
                print(f"  [{idioma}] error: {error}", file=sys.stderr)
                fallidos += 1

    print(f"\nGuiones generados: {generados} · Con error: {fallidos}")
    print("Revisa cada guion con sus fuentes antes de publicarlo.")
    return 0 if fallidos == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
