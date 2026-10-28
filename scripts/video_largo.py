"""Vídeo largo (8-10 minutos, horizontal) explicado con dibujos. PROTOTIPO.

A partir de un artículo de Wikipedia hace un vídeo por capítulos al estilo «X en 10 minutos»: el narrador
Bonesy, mapas, fechas, cifras, personajes y líneas de tiempo dibujados por la app (scripts/dibujos.py), con
la voz de siempre y música de fondo. Las cosas aparecen en pantalla cuando la voz las nombra.

Pasos (cada uno reutiliza lo que ya esté hecho: los archivos se nombran por su contenido, así que al corregir
una frase del guion solo se rehacen su voz, sus dibujos y su clip):
    guion    Groq: índice de capítulos y luego cada capítulo con sus escenas y dibujos; se verifica con Wikipedia
    audio    edge-tts por escena, con los tiempos de cada palabra
    dibujos  Edge dibuja cada paso de cada escena (PNG 1920×1080) y la miniatura
    video    ffmpeg: un clip por escena, todos seguidos y la música debajo; descripción con capítulos

Uso:
    python scripts/video_largo.py "Guerra civil española"
    python scripts/video_largo.py "Guerra civil española" --solo-guion        # para revisarlo antes de dibujar
    python scripts/video_largo.py "Guerra civil española" --desde dibujos     # rehace desde ese paso
    python scripts/video_largo.py "Guerra civil española" --subir --privacidad unlisted
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv
from mutagen.mp3 import MP3

import dibujos
import paso1_guiones
import paso2_audio

load_dotenv()

CARPETA = Path("salida/largos")
PASOS = ("guion", "audio", "dibujos", "video")
VELOCIDAD = "+4%"              # algo más pausado que en los Shorts: es un vídeo para escuchar
PAUSA_ESCENA = 0.45           # s de silencio tras cada escena
DURACION_CAPITULO = 2.2       # s de la tarjeta de capítulo (sin voz)
FUNDIDO = 0.25                # s del fundido cuando aparece un elemento nuevo
PALABRAS_INTRO = (55, 90)
PALABRAS_CAPITULO = (170, 260)
VOLUMEN_MUSICA = 0.07
LUFS = -14                    # volumen final del vídeo (el de referencia de YouTube)
SECCIONES_FUERA = re.compile(r"^(véase también|referencias|notas|bibliografía|enlaces externos|filmografía|"
                             r"fuentes|lecturas|en la cultura|.*en la ficción)", re.I)

PROMPT_INDICE = """Eres guionista de un canal de divulgación de historia en español al estilo «X explicado en 10 minutos»
(vídeos largos, horizontales, con dibujos). Con el MATERIAL (artículo de Wikipedia) planifica un vídeo de 9-10 minutos.

Devuelve SOLO un JSON:
{"titulo": "título de YouTube, máx. 70 caracteres, que despierte curiosidad (ej.: «La Guerra Civil española en 10 minutos»)",
 "miniatura": "2-4 palabras ENORMES para la miniatura (ej.: «ESPAÑA PARTIDA EN DOS»)",
 "iconos_miniatura": ["1 o 2 emojis que resuman el tema"],
 "tono": "uno de: epico, misterio, triste, neutro",
 "gancho": "la pregunta o el dato sorprendente con el que arranca el vídeo (1 frase)",
 "capitulos": [{"titulo": "título corto del capítulo (2-5 palabras)", "secciones": [números de las SECCIONES que usa],
                "idea": "qué cuenta este capítulo, en 1-2 frases", "icono": "1 emoji para su tarjeta"}],
 "anio": el año central del tema, en número (p. ej. 1521; antes de Cristo, en negativo)}

Reglas:
- Entre 5 y 6 capítulos en ESTRICTO orden cronológico (nunca vuelvas atrás en el tiempo) que cuenten la historia
  completa: contexto, causas, lo que pasó y cómo terminó / qué consecuencias tuvo.
- Cada capítulo usa 1-4 secciones del índice: las que contienen SUS hechos (si habla de una batalla, la sección de esa
  batalla). El guionista solo podrá usar lo que haya en ellas.
- Rigor y neutralidad: los temas políticos se cuentan con hechos, sin tomar partido.
- "anio" sirve para vestir al narrador como uno más de aquella época."""

PROMPT_CAPITULO = """Eres guionista de un canal de divulgación de historia en español, al estilo «X explicado en 10 minutos».
El vídeo se titula «{titulo}». Los capítulos son: {indice}.
Ahora escribe {que} con SOLO hechos del MATERIAL.

La narración la lee una voz en off, y en pantalla hay dibujos sencillos con un narrador (Bonesy, un esqueleto con
sudadera roja). Cada escena tiene "narracion" (lo que se oye) y "visual" (lo que se ve mientras tanto).

Reglas del texto:
- {palabras} palabras de narración en total, en {escenas} escenas de 12-30 palabras cada una.
- Español de España, cercano y claro, como si se lo contaras a un amigo curioso: frases cortas, nada de jerga.
- Cada escena empuja a la siguiente: preguntas, giros, «pero…», «y entonces…». Nada de relleno.
- Rigor: fechas, cifras y nombres exactos del MATERIAL. Si hay cifras discutidas, dilo («según las estimaciones…»).
- Neutralidad: hechos, no opiniones; no tomes partido en temas políticos.
{extra}

Tipos de "visual" (elige el que mejor ENSEÑE lo que dice la narración; varía, nunca el mismo tipo dos veces seguidas):
- {{"tipo": "narrador", "bocadillo": "frase corta que dice Bonesy", "pose": "piensa|sorpresa|explica|senala|brazos", "iconos": ["emoji"]}}
- {{"tipo": "fecha", "fecha": "18 de julio de 1936", "texto": "qué pasó (máx. 8 palabras)"}}
- {{"tipo": "cifra", "numero": "500.000", "texto": "de qué es la cifra (máx. 8 palabras)", "iconos": ["emoji"], "repetir": 8}}
- {{"tipo": "mapa", "zona": "espana|europa|mundo|mediterraneo|america|africa|asia", "titulo": "título corto",
   "resaltar": [{{"lugares": ["provincias, comunidades autónomas o países"], "color": "rojo|azul|verde|amarillo|morado|naranja|negro|gris", "etiqueta": "qué significa ese color"}}],
   "puntos": [{{"lugar": "Guernica", "texto": "Guernica", "lat": 43.31, "lon": -2.68}}],
   "flechas": [{{"desde": {{"lugar": "Sevilla", "lat": 37.39, "lon": -5.98}}, "hasta": {{"lugar": "Madrid", "lat": 40.42, "lon": -3.70}}, "color": "azul"}}]}}
  (usa mapas siempre que haya lugares, territorios, avances o frentes; lat/lon de los puntos con 2 decimales)
- {{"tipo": "personajes", "personas": [{{"nombre": "Nombre Apellido", "rol": "quién es (3-5 palabras)",
     "aspecto": {{"pelo": "corto|calvo|canoso|largo", "bigote": true/false, "barba": true/false, "gafas": true/false,
                  "ropa": "traje|uniforme|obrero|vestido|sotana", "color_ropa": "gris|azul|negro|caqui|marron|rojo|verde",
                  "sombrero": "ninguno|corona|gorra_militar|casco|boina|chistera|sombrero|mitra"}}}}],
   "bocadillo": "frase corta que dice el primero (opcional)", "habla": 0}}   (1-3 personas, con su aspecto real aproximado)
- {{"tipo": "iconos", "texto": "título corto", "elementos": [{{"icono": "emoji", "texto": "2-4 palabras"}}]}}   (1-3 elementos)
- {{"tipo": "linea", "hitos": [{{"fecha": "1931", "texto": "2-5 palabras", "icono": "emoji opcional"}}], "actual": 2}}   (3-5 hitos)
- {{"tipo": "comparacion", "izquierda": {{"titulo": "...", "color": "rojo", "iconos": ["emoji"], "puntos": ["2-6 palabras"]}},
   "derecha": {{"titulo": "...", "color": "azul", "iconos": ["emoji"], "puntos": ["..."]}}}}
Los emojis tienen que ser emojis estándar (🏰 ⚔️ 👑 🚢 💣 ✈️ 🗳️ 📜 💰 🏭 🌾 ⛪ 🪖 🔥 ⚖️ 🇪🇸 …), nunca texto.

Responde SOLO con un JSON: {{"escenas": [{{"narracion": "...", "visual": {{...}}}}]}}"""

EXTRA_INTRO = """- Es la INTRODUCCIÓN del vídeo (antes del capítulo 1): engancha en la primera frase con este gancho:
  «{gancho}». Luego cuenta en 1-2 frases qué vamos a ver, sin destripar el final. Nada de «hola» ni presentaciones.
- La primera escena es un "narrador" con pose "sorpresa" o "piensa"."""
EXTRA_FINAL = """- Es el ÚLTIMO capítulo: termina con una conclusión de 1-2 frases y luego una escena "narrador" que haga una
  pregunta a los espectadores para que comenten (sobre el tema, sin pedir opiniones políticas) y les pida que se suscriban
  para más historia explicada así."""


def _ffmpeg(argumentos: list) -> None:
    resultado = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                                *map(str, argumentos)], capture_output=True, text=True)
    if resultado.returncode:
        raise RuntimeError(f"ffmpeg: {resultado.stderr[-800:]}")


# Ropa de Bonesy según el año del tema (la IA da bien el año; eligiendo prendas o épocas se equivocaba).
# (hasta el año, ropa). En el siglo XX va siempre de civil: en una guerra civil, nada que lo ponga de un lado.
VESTUARIOS = [
    (475, {"ropa": "toga", "sombrero": "casco_romano"}),
    (1491, {"ropa": "armadura"}),
    (1699, {"ropa": "armadura", "sombrero": "morrion"}),
    (1799, {"ropa": "traje", "color_ropa": "azul", "sombrero": "tricornio"}),
    (1899, {"ropa": "traje", "color_ropa": "negro", "sombrero": "chistera"}),
    (1945, {"ropa": "traje", "color_ropa": "marron", "sombrero": "sombrero"}),
    (1979, {"ropa": "traje", "color_ropa": "gris"}),
]
REALEZA = re.compile(r"\b(?i:reyes|rey|reina|reinas|dinast[ií]a)\b|\b[A-ZÁÉÍÓÚ][a-záéíóúñ]+ [IVX]+\b")


def vestuario(anio, tema: str) -> dict:
    """La ropa de Bonesy: la de la época del tema, o de rey si el tema es un rey o una reina («Felipe II», «Reyes
    Católicos»)."""
    try:
        anio = int(str(anio).strip())
    except (TypeError, ValueError):
        anio = 9999
    ropa = next((r for hasta, r in VESTUARIOS if anio <= hasta), {"ropa": "sudadera"})
    if REALEZA.search(tema or ""):
        ropa = {"ropa": "capa_real", "sombrero": "corona"}
    return {"ropa": ropa["ropa"], "color_ropa": ropa.get("color_ropa", ""), "sombrero": ropa.get("sombrero", "")}


def _secciones(articulo: str) -> list:
    """[(título, texto)] del artículo; la primera es la introducción."""
    trozos = re.split(r"\n(={2,})\s*(.+?)\s*\1\n", "\n" + articulo)
    secciones = [("Introducción", trozos[0].strip())]
    for i in range(1, len(trozos) - 2, 3):
        titulo, contenido = trozos[i + 1], trozos[i + 2].strip()
        if SECCIONES_FUERA.match(titulo):
            continue
        if len(contenido) > 150:
            secciones.append((titulo, contenido))
    return secciones


def _llamar(sistema: str, usuario: str) -> dict:
    paso1_guiones.MAX_TOKENS = 6000  # un capítulo con sus dibujos no cabe en 3000
    api_key = os.getenv("GROQ_API_KEY")
    modelo = os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO
    for intento in range(3):
        try:
            return json.loads(paso1_guiones.llamar_groq(api_key, modelo, sistema, usuario))
        except ValueError:
            print("    respuesta sin JSON válido, repito…", flush=True)
    raise RuntimeError("Groq no ha devuelto un JSON válido")


def _verificar(material: str, escenas: list) -> list:
    return paso1_guiones.verificar_guion(os.getenv("GROQ_API_KEY"), paso1_guiones.MODELO_VERIFICADOR, material, escenas)


def _palabras(escenas) -> int:
    return sum(len(e.get("narracion", "").split()) for e in escenas)


def _escenas_validas(datos) -> list:
    escenas = [e for e in (datos or {}).get("escenas", []) if isinstance(e, dict) and e.get("narracion")]
    for e in escenas:
        if not isinstance(e.get("visual"), dict):
            e["visual"] = {"tipo": "narrador", "pose": "explica"}
    return escenas


def hacer_guion(tema: str, carpeta: Path) -> dict:
    articulo = paso1_guiones.texto_articulo(tema)
    if len(articulo) < 3000:
        raise RuntimeError(f"Wikipedia no tiene bastante material sobre «{tema}»")
    secciones = _secciones(articulo)
    indice_secciones = "\n".join(f"{i}. {t} ({len(c)} caracteres)" for i, (t, c) in enumerate(secciones))
    print(f"  material: {len(articulo)} caracteres en {len(secciones)} secciones", flush=True)
    plan = _llamar(PROMPT_INDICE, f"SECCIONES:\n{indice_secciones}\n\nMATERIAL (introducción):\n{secciones[0][1][:5000]}")
    capitulos = plan.get("capitulos") or []
    if len(capitulos) < 3:
        raise RuntimeError("el índice ha salido con menos de 3 capítulos")
    print(f"  «{plan.get('titulo')}»: " + " · ".join(c["titulo"] for c in capitulos), flush=True)
    indice = "; ".join(f"{n}. {c['titulo']}" for n, c in enumerate(capitulos, start=1))

    def material_de(numeros, maximo=9000):
        textos = [f"== {secciones[n][0]} ==\n{secciones[n][1]}" for n in numeros
                  if isinstance(n, int) and 0 <= n < len(secciones)]
        reparto = maximo // max(len(textos), 1)
        return "\n\n".join(t[:reparto] for t in textos) or secciones[0][1][:maximo]

    partes = [{"titulo": "Introducción", "intro": True, "secciones": [0], "idea": plan.get("gancho", "")}]
    partes += [{**c, "numero": n} for n, c in enumerate(capitulos, start=1)]
    for parte in partes:
        es_intro = parte.get("intro")
        ultimo = parte is partes[-1]
        minimo, maximo = PALABRAS_INTRO if es_intro else PALABRAS_CAPITULO
        sistema = PROMPT_CAPITULO.format(
            titulo=plan.get("titulo", tema), indice=indice,
            que="la introducción del vídeo" if es_intro else f"el capítulo {parte['numero']}, «{parte['titulo']}» "
                                                               f"({parte.get('idea', '')})",
            palabras=f"Entre {minimo} y {maximo}", escenas="3-4" if es_intro else "9-12",
            extra=(EXTRA_INTRO.format(gancho=plan.get("gancho", "")) if es_intro else "")
                  + (EXTRA_FINAL if ultimo else ""))
        material = material_de(parte.get("secciones") or [0])
        for intento in range(2):
            escenas = _escenas_validas(_llamar(sistema, f"MATERIAL:\n{material}"))
            n = _palabras(escenas)
            if minimo * 0.85 <= n <= maximo * 1.15:
                break
            print(f"    {parte['titulo']}: {n} palabras (fuera de {minimo}-{maximo}), repito…", flush=True)
        dudas = _verificar(material, escenas)
        if dudas:  # una segunda versión que corrige justo esas frases; se queda la que tenga menos dudas
            lista = "\n".join(f"- «{d['frase']}»: {d['motivo']}" for d in dudas)
            corregidas = _escenas_validas(_llamar(sistema, f"MATERIAL:\n{material}\n\nEn una versión anterior estas frases "
                                                           f"NO estaban respaldadas por el MATERIAL; no las repitas:\n{lista}"))
            if corregidas and minimo * 0.85 <= _palabras(corregidas) <= maximo * 1.15:
                dudas_nuevas = _verificar(material, corregidas)
                if len(dudas_nuevas) < len(dudas):
                    escenas, dudas = corregidas, dudas_nuevas
        parte.update(escenas=escenas, dudas=dudas)
        print(f"  {parte['titulo']}: {len(escenas)} escenas, {_palabras(escenas)} palabras, "
              f"{len(dudas)} dudas", flush=True)
        for d in dudas:
            print(f"      ¿{d['frase']}? → {d['motivo']}", flush=True)
    guion = {"tema": tema, **{k: plan.get(k) for k in ("titulo", "miniatura", "iconos_miniatura", "tono", "gancho")},
             "bonesy": vestuario(plan.get("anio"), tema),
             "fuente": f"https://es.wikipedia.org/wiki/{tema.replace(' ', '_')}", "revisado": False,
             "partes": partes}
    (carpeta / "guion.json").write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(_palabras(p["escenas"]) for p in partes)
    print(f"  guion: {total} palabras (≈ {total / 2.5 / 60:.1f} min)", flush=True)
    return guion


def _huella(*partes) -> str:
    """Huella corta del contenido: si no cambia, se reutiliza el archivo que ya está hecho."""
    return hashlib.sha1(json.dumps(partes, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _limpiar(carpeta: Path, patron: str, usados: set) -> None:
    """Borra lo que ya no usa ninguna escena (de versiones anteriores del guion)."""
    for archivo in carpeta.glob(patron):
        if archivo.name not in usados:
            archivo.unlink()


def _avisar_cada(paso: int, que: str):
    """Para los pasos largos: escribe «que: 20/170» cada `paso` elementos (lo ve la página de la tarea)."""
    def avisar(hechos: int, total: int) -> None:
        if hechos % paso == 0 or hechos == total:
            print(f"    {que}: {hechos}/{total}", flush=True)
    return avisar


def _guardar(guion: dict, carpeta: Path) -> None:
    (carpeta / "guion.json").write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")


def _escenas(guion):
    """Todas las escenas en orden; las tarjetas de capítulo van como escenas sin voz."""
    numero = 0
    for parte in guion["partes"]:
        if not parte.get("intro"):
            icono = parte.get("icono") or next(iter(guion.get("iconos_miniatura") or []), None)
            yield {"id": f"cap_{parte['numero']:02d}", "tarjeta": True, "parte": parte,
                   "visual": {"tipo": "titulo", "numero": parte["numero"], "texto": parte["titulo"],
                              "iconos": [icono] if icono else []}}
        for escena in parte["escenas"]:
            numero += 1
            yield {"id": f"esc_{numero:03d}", "tarjeta": False, "parte": parte, "escena": escena,
                   "visual": escena["visual"]}


def hacer_audio(guion: dict, carpeta: Path) -> None:
    """La voz de cada escena; solo se graba otra vez la que ha cambiado de texto."""
    paso2_audio.VELOCIDAD = VELOCIDAD
    voz = paso2_audio.VOCES["es"]
    destino = carpeta / "audio"
    destino.mkdir(exist_ok=True)
    escenas = [item["escena"] for item in _escenas(guion) if not item["tarjeta"]]
    for escena in escenas:
        escena["audio"] = _huella(voz, VELOCIDAD, escena["narracion"]) + ".mp3"
    _limpiar(destino, "*.mp3", {e["audio"] for e in escenas})
    pendientes = [e for e in escenas if not ((destino / e["audio"]).exists() and e.get("audio_hecho") == e["audio"]
                                             and e.get("palabras"))]
    avisar = _avisar_cada(10, "voz")
    for grabadas, escena in enumerate(pendientes, start=1):
        ruta = destino / escena["audio"]
        palabras = asyncio.run(paso2_audio.sintetizar(escena["narracion"], voz, ruta))
        escena["palabras"] = [[p, round(a, 3), round(b, 3)] for p, a, b in palabras]
        escena["duracion"] = round(MP3(ruta).info.length, 3)
        escena["audio_hecho"] = escena["audio"]
        avisar(grabadas, len(pendientes))
    grabadas = len(pendientes)
    _guardar(guion, carpeta)
    total = sum(e["duracion"] + PAUSA_ESCENA for e in escenas)
    print(f"  audio: {grabadas} escenas grabadas y {len(escenas) - grabadas} que ya estaban "
          f"({total / 60:.1f} min de voz)", flush=True)


def _momentos(claves: list, palabras: list, duracion: float) -> list:
    """Segundo en que aparece cada paso: cuando la voz dice su palabra clave (o repartidos si no la dice)."""
    pasos = len(claves)
    if not pasos:
        return []
    repartidos = [duracion * (i + 1) / (pasos + 1) for i in range(pasos)]
    momentos, cursor = [], 0.4
    normalizadas = [(dibujos.normalizar(re.sub(r"[^\w]", "", p)), a) for p, a, _ in palabras]
    for i, clave in enumerate(claves):
        tokens = [dibujos.normalizar(t) for t in re.findall(r"\w+", str(clave)) if len(t) >= 4 or t.isdigit()]
        tokens.sort(key=len, reverse=True)
        cuando = None
        for token in tokens[:2]:
            cuando = next((a for p, a in normalizadas if a >= cursor and p == token), None)
            if cuando is not None:
                break
        cuando = max(cuando - 0.15 if cuando is not None else repartidos[i], cursor)
        cuando = min(cuando, duracion - 0.6)
        momentos.append(round(max(cuando, cursor), 2))
        cursor = momentos[-1] + 0.6
    return momentos


def hacer_dibujos(guion: dict, carpeta: Path) -> None:
    """Los dibujos de cada paso de cada escena y la miniatura; solo se dibuja lo que ha cambiado."""
    destino = carpeta / "dibujos"
    destino.mkdir(exist_ok=True)
    trabajos, usados = {}, set()
    for item in _escenas(guion):
        parte = item["parte"]
        etiqueta = "" if parte.get("intro") else f"{parte['numero']} · {parte['titulo']}"
        pasos, claves = dibujos.escena(item["visual"], etiqueta, guion.get("bonesy"))
        semilla = int(_huella(item["visual"], etiqueta)[:6], 16) % 50 + 1  # el temblor del trazo a mano
        rutas = []
        for capas in pasos:
            html = dibujos.documento(capas, semilla=semilla)
            nombre = _huella(html) + ".png"
            usados.add(nombre)
            rutas.append(str(destino / nombre))
            if not (destino / nombre).exists():
                trabajos[nombre] = (html, destino / nombre, 1920, 1080)
        if item["tarjeta"]:
            parte["imagenes_tarjeta"] = rutas
        else:
            escena = item["escena"]
            escena["imagenes"] = rutas
            escena["momentos"] = [0.0] + _momentos(claves, escena.get("palabras", []), escena.get("duracion", 6))
    _limpiar(destino, "*.png", usados)
    mapa_miniatura = guion.get("miniatura_mapa") or next(
        (e["visual"] for p in guion["partes"] for e in p["escenas"]
         if e["visual"].get("tipo") == "mapa" and e["visual"].get("resaltar")), None)
    html = dibujos.documento(dibujos.miniatura(guion.get("miniatura") or guion["titulo"], guion.get("iconos_miniatura"),
                                               mapa_miniatura, guion.get("bonesy")), ancho=1280, alto=720)
    miniatura = carpeta / "miniatura.png"
    if guion.get("miniatura_hecha") != _huella(html) or not miniatura.exists():
        trabajos["miniatura"] = (html, miniatura, 1280, 720)
    inicio = time.time()
    print(f"  dibujando {len(trabajos)} de {len(usados) + 1} imágenes (las demás ya estaban)…", flush=True)
    if trabajos:
        dibujos.renderizar(list(trabajos.values()), progreso=_avisar_cada(20, "dibujos"))
    guion["miniatura_hecha"] = _huella(html)
    print(f"  dibujos hechos en {time.time() - inicio:.0f} s", flush=True)
    _guardar(guion, carpeta)


def _clip(imagenes: list, momentos: list, duracion: float, audio, salida: Path) -> None:
    """Un clip con las imágenes de los pasos (fundido corto entre ellas) y la voz."""
    n = len(imagenes)
    momentos = list(momentos[:n]) + [None] * (n - len(momentos))
    momentos[0] = 0.0
    for i in range(1, n):  # crecientes, con sitio para el fundido y antes del final
        minimo = momentos[i - 1] + FUNDIDO + 0.1
        momentos[i] = min(max(momentos[i] if momentos[i] is not None else minimo + 0.6, minimo), duracion - 0.2)
    entradas, filtros = [], []
    for i, imagen in enumerate(imagenes):
        inicio = momentos[i] - (FUNDIDO if i else 0)
        fin = momentos[i + 1] if i + 1 < n else duracion
        # Cada imagen se lee una vez y se repite (tpad): leerla 30 veces por segundo hacía el montaje muy lento.
        entradas += ["-framerate", "30", "-i", imagen]
        filtros.append(f"[{i}:v]format=yuv420p,setsar=1,tpad=stop_mode=clone:stop_duration={fin - inicio:.3f},"
                       f"trim=duration={fin - inicio:.3f}[p{i}]")
    if n == 1:
        filtros.append("[p0]fps=30[v]")
    else:
        anterior = "[p0]"
        for i in range(1, n):
            salida_filtro = "[w]" if i == n - 1 else f"[x{i}]"
            filtros.append(f"{anterior}[p{i}]xfade=transition=fade:duration={FUNDIDO}:"
                           f"offset={momentos[i] - FUNDIDO:.3f}{salida_filtro}")
            anterior = salida_filtro
        filtros.append("[w]fps=30[v]")
    if audio:
        entradas += ["-i", audio]
        filtros.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={duracion:.3f}[a]")
    else:
        entradas += ["-f", "lavfi", "-t", f"{duracion:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        filtros.append(f"[{n}:a]anull[a]")
    _ffmpeg([*entradas, "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "[a]", "-t", f"{duracion:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "20", "-r", "30",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(salida)])


def _tiempo(segundos: float) -> str:
    m, s = divmod(int(segundos), 60)
    return f"{m}:{s:02d}"


def hacer_video(guion: dict, carpeta: Path) -> None:
    """Un clip por escena (solo los que han cambiado), todos seguidos y la música debajo."""
    clips = carpeta / "clips"
    clips.mkdir(exist_ok=True)
    plan, capitulos, transcurrido = [], [("0:00", "Introducción")], 0.0
    for item in _escenas(guion):
        if item["tarjeta"]:
            imagenes = item["parte"]["imagenes_tarjeta"]
            momentos = [0.0] + [0.8] * (len(imagenes) - 1)
            duracion, audio = DURACION_CAPITULO, None
            capitulos.append((_tiempo(transcurrido), f"{item['parte']['numero']}. {item['parte']['titulo']}"))
        else:
            escena = item["escena"]
            imagenes, momentos = escena["imagenes"], escena["momentos"]
            duracion = round(escena["duracion"] + PAUSA_ESCENA, 3)
            audio = str(carpeta / "audio" / escena["audio"])
        nombre = _huella([Path(i).name for i in imagenes], momentos, duracion, Path(audio).name if audio else "")
        plan.append((imagenes, momentos, duracion, audio, clips / f"{nombre}.mp4"))
        transcurrido += duracion
    _limpiar(clips, "*.mp4", {p[-1].name for p in plan})
    inicio = time.time()
    pendientes = [p for p in plan if not p[-1].exists()]
    avisar = _avisar_cada(10, "clips")
    for nuevos, (imagenes, momentos, duracion, audio, salida) in enumerate(pendientes, start=1):
        _clip(imagenes, momentos, duracion, audio, salida)
        avisar(nuevos, len(pendientes))
    nuevos = len(pendientes)
    print(f"  {nuevos} clips nuevos de {len(plan)} en {time.time() - inicio:.0f} s", flush=True)
    lista = [p[-1] for p in plan]
    archivo_lista = clips / "lista.txt"
    archivo_lista.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in lista), encoding="utf-8")
    sin_musica = carpeta / "sin_musica.mp4"
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", archivo_lista, "-c", "copy", sin_musica])
    pista = Path("musica") / f"{guion.get('tono') or 'epico'}.mp3"
    if not pista.exists():
        pista = Path("musica/neutro.mp3")
    final = carpeta / "video.mp4"
    # Volumen a -14 LUFS, el nivel de YouTube: si queda más bajo, YouTube no lo sube y suena flojo.
    volumen = f"loudnorm=I={LUFS}:TP=-1.5:LRA=11,aresample=48000"
    if pista.exists():
        mezcla = (f"[1:a]volume={VOLUMEN_MUSICA},afade=t=in:d=2,afade=t=out:st={max(transcurrido - 4, 0):.2f}:d=4[m];"
                  f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,{volumen}[a]")
        entradas = ["-i", sin_musica, "-stream_loop", "-1", "-i", pista]
    else:
        mezcla, entradas = f"[0:a]{volumen}[a]", ["-i", sin_musica]
    _ffmpeg([*entradas, "-filter_complex", mezcla, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-t", f"{transcurrido:.2f}", final])
    sin_musica.unlink()
    descripcion = [guion.get("gancho") or "", "", "Capítulos:", *[f"{t} {n}" for t, n in capitulos], "",
                   f"Fuente: Wikipedia ({guion['fuente']}).",
                   "Dibujos y animación: Mente Inquieta. Iconos: Twemoji (CC-BY 4.0). Mapas: Natural Earth y "
                   "click_that_hood.", "", "#historia #historiadeespaña #explicado"]
    (carpeta / "descripcion.txt").write_text("\n".join(descripcion), encoding="utf-8")
    print(f"  vídeo: {final} ({_tiempo(transcurrido)})", flush=True)


def _subir(carpeta: Path, privacidad: str, publicar_el: str) -> int:
    """Sube el vídeo a YouTube (como vídeo normal, no Short) con su miniatura y sus capítulos."""
    import subir_youtube
    from googleapiclient.errors import HttpError
    try:
        subir_youtube.subir_largo(carpeta, privacidad, publicar_el)
    except HttpError as error:
        print(f"  ⚠ No se ha podido subir: {subir_youtube._explicar(error)}", flush=True)
        return 1
    except ValueError as error:
        print(f"  ⚠ No se ha podido subir: {error}", flush=True)
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tema", help="título del artículo de Wikipedia en español")
    parser.add_argument("--desde", choices=PASOS, help="rehace desde este paso (borra lo de después)")
    parser.add_argument("--solo-guion", action="store_true", help="solo escribe el guion, para revisarlo antes de dibujar")
    parser.add_argument("--subir", action="store_true", help="sube a YouTube el vídeo ya hecho, con su miniatura")
    parser.add_argument("--privacidad", choices=("private", "unlisted", "public"), default="private")
    parser.add_argument("--publicar-el", default="", help="hora local (2026-11-02T18:00): queda privado y se publica solo")
    args = parser.parse_args(argv)
    carpeta = CARPETA / paso1_guiones.slug(args.tema)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_guion = carpeta / "guion.json"
    if args.subir:
        return _subir(carpeta, args.privacidad, args.publicar_el)
    desde = PASOS.index(args.desde) if args.desde else None
    if desde is not None:
        import shutil
        for paso in PASOS[desde:]:
            objetivo = {"audio": carpeta / "audio", "dibujos": carpeta / "dibujos", "video": carpeta / "clips"}.get(paso)
            if objetivo and objetivo.exists():
                shutil.rmtree(objetivo)
        if desde == 0 and ruta_guion.exists():
            ruta_guion.unlink()
    print("1/4 guion", flush=True)
    guion = json.loads(ruta_guion.read_text(encoding="utf-8")) if ruta_guion.exists() else hacer_guion(args.tema, carpeta)
    if args.solo_guion:
        print("Guion listo: revísalo en la app (Vídeos largos) antes de hacer el vídeo.", flush=True)
        return 0
    if desde is not None and desde <= 1:
        for parte in guion["partes"]:
            for e in parte["escenas"]:
                e.pop("palabras", None)
    print("2/4 audio", flush=True)
    hacer_audio(guion, carpeta)
    print("3/4 dibujos", flush=True)
    hacer_dibujos(guion, carpeta)
    print("4/4 vídeo", flush=True)
    hacer_video(guion, carpeta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
