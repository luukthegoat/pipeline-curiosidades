"""Dibujos dentro de los Shorts: algunas escenas empiezan con su foto y, cuando la voz llega a la palabra clave, pasan a
un dibujo animado hecho por la app (un mapa con el lugar, una cifra enorme, una fecha, causas y consecuencias…).

Una IA (Groq) elige 2-3 escenas por vídeo y qué dibujar en cada una, solo con lo que dice el texto; la respuesta se
guarda (dibujos_ia.json en la carpeta de trabajo del vídeo) para no volver a preguntar al rehacerlo. Los dibujos usan
las piezas de los vídeos largos (scripts/dibujos.py) en un lienzo de 1080×1036: la franja de la imagen en el Short.
Cada clip (foto con zoom lento + dibujo que se va completando al ritmo de la voz) se guarda en caché.

Se desactiva en Ajustes (DIBUJOS_SHORTS=0).
"""
import json
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageOps

import dibujos as D

ANCHO, ALTO, FPS = 1080, 1036, 30
ABAJO = 880          # por debajo de esta altura van los subtítulos: ahí no se pone nada importante
FOTO_MINIMA = 1.2    # s de foto antes del dibujo (en la primera escena, hasta que acaba el gancho)
DIBUJO_MINIMO = 1.8  # s de dibujo como mínimo; si no caben, la escena se queda solo con la foto
POP = (0.35, 0.75, 1.12, 1.04, 1.0)  # escala de cada elemento nuevo en sus primeros fotogramas
VERSION = "2"        # súbela si cambia el aspecto de los dibujos: se rehacen los clips
TIPOS = ("mapa", "cifra", "fecha", "iconos", "comparacion", "linea", "narrador", "acertijo", "cuenta", "solucion")
R, T = D.COLORES["rojo"], D.TINTA
ESTILOS = {"dibujos": "Todo con dibujos y muñecos", "mixto": "Fotos y 2-3 dibujos", "fotos": "Solo fotos y vídeos"}


def estilo() -> str:
    """Cómo se ilustran los Shorts (Ajustes): «dibujos» (todas las escenas dibujadas), «mixto» o «fotos»."""
    if os.getenv("DIBUJOS_SHORTS", "1") != "1":
        return "fotos"
    valor = os.getenv("ESTILO_SHORTS", "dibujos")
    return valor if valor in ESTILOS else "dibujos"


def activado() -> bool:
    return estilo() != "fotos"


def estilo_de(datos: dict) -> str:
    """El estilo de un vídeo: los acertijos y los que lo piden en su guion van siempre con dibujos."""
    if datos.get("acertijo"):
        return "dibujos"
    if datos.get("estilo") in ESTILOS:
        return datos["estilo"]
    if datos.get("futbol"):
        return estilo_de_tipo("ESTILO_FUTBOL")
    if datos.get("actualidad"):
        return estilo_de_tipo("ESTILO_NOTICIAS")  # con dibujos, sobrios (lo manda el PROMPT: nada de sangre ni armas)
    return estilo()


def estilo_de_tipo(variable: str) -> str:
    """El estilo de las noticias o del fútbol (Ajustes): el suyo si se ha elegido; si no, el general."""
    valor = os.getenv(variable, "")
    return valor if valor in ESTILOS else estilo()


# Palabras del tema → muñeco que lo cuenta (el primero que encaje; se cambia en la página de imágenes).
REGLAS_PERSONAJE = (
    ("futbolista", r"f[uú]tbol|gol\b|goles|liga|mundial|champions|bal[oó]n|selecci[oó]n|madrid cf|bar[cç]a|estadio"),
    ("soldado", r"guerra|batalla|ej[eé]rcito|soldado|invasi[oó]n|golpe de estado|bombardeo|tropas|militar"),
    ("rey", r"\brey\b|reina|reyes|imperio|emperador|corona|dinast|monarqu"),
    ("cientifica", r"cient[ií]fic|invent|descubrimiento cient|vacuna|experimento|f[ií]sica|qu[ií]mica|medicina|nasa|"
                   r"espacio|luna|cohete|sat[eé]lite"),
    ("exploradora", r"explora|expedici[oó]n|viaje|descubri|conquista|naveg|barco|oc[eé]ano|vuelta al mundo"),
)


def personaje_de(datos: dict) -> str:
    """Qué muñeco cuenta el vídeo: el elegido a mano o, si no, el que toca por el tipo y el tema."""
    if datos.get("personaje") in D.PERSONAJES:
        return datos["personaje"]
    if datos.get("acertijo"):
        return "detective"
    texto = " ".join([str(datos.get("titulo", "")), str(datos.get("evento", "")),
                      *(e.get("narracion", "") for e in datos.get("escenas", [])[:3])]).lower()
    for clave, patron in REGLAS_PERSONAJE:
        if re.search(rf"\b(?:{patron})", texto):  # al principio de palabra: «liga» no es «obliga»
            return clave
    if datos.get("actualidad"):
        return "reportera"
    return "profesor" if datos.get("anio_evento") or datos.get("serie") else "bonesy"


# --- Qué dibujar (IA) ------------------------------------------------------------------------------

_ELEGIR = """Eres el montador de un canal de Shorts de historia y actualidad. Cada escena del vídeo tiene su foto; en
algunas, a mitad de la frase, la imagen pasa a un DIBUJO animado que explica mejor lo que se dice (los dibujos
retienen mucho: el espectador entiende de un vistazo dónde, cuánto, cuándo o por qué).

Elige {cuantas} escenas (de las que te paso) donde un dibujo aporte más que una foto, y qué dibujar:
- lugares, rutas, fronteras o avances → "mapa"
- una cifra importante (muertos, dinero, porcentaje, distancia…) → "cifra"
- una fecha clave → "fecha"
- causas y consecuencias, pasos de un proceso o 2-3 ideas → "iconos"
- antes/después o dos bandos → "comparacion"
- varias fechas seguidas → "linea"
Si el texto nombra lugares (ciudades, regiones, países), uno de los dibujos TIENE que ser un mapa de esa escena: es lo
que mejor funciona. Mejor no en la escena 1 (allí la foto engancha), salvo un mapa del lugar. Nunca dos dibujos del
mismo tipo. «De 18 000 a menos de 5 000» o antes/después → "comparacion", no "iconos".
- "desde": una palabra EXACTA del texto de la escena a partir de la cual se ve el dibujo (no la primera: antes se ve
  la foto). Suele ser donde empieza lo que el dibujo enseña (el lugar, la cifra…).
"""

_REGLAS = """
Reglas:
- SOLO datos que dice el texto de la escena: no inventes cifras, fechas, lugares ni nombres.
- Emojis que encajen con el tema, la época y el país: soldados españoles o de cualquier guerra → 🪖 (nunca 💂, que es
  la guardia británica); cada elemento con un emoji DISTINTO.
- Textos en palabras normales, sin símbolos raros («menos de 5000», no «<5000»).
- Textos del dibujo cortísimos (2-5 palabras). Emojis estándar de Twemoji (🚄 🏛️ 🗳️ ⚔️ 👑 💰 🔥 🕯️ 🚑 📜 🌍 ⚠️ ❌ …), nunca texto.
- Sucesos con víctimas: tono sobrio (🕯️, 🚑), nunca sangre, armas apuntando ni calaveras.

Formatos de "visual":
- {{"tipo": "mapa", "zona": "espana|europa|mundo|mediterraneo|america|africa|asia", "titulo": "2-4 palabras",
   "resaltar": [{{"lugares": ["provincias españolas, comunidades o países"], "color": "rojo|azul|verde|amarillo|morado|naranja", "etiqueta": "qué significa"}}],
   "puntos": [{{"texto": "Nombre", "lat": 39.41, "lon": -3.71}}], "flechas": [{{"desde": {{"lat": 0, "lon": 0}}, "hasta": {{"lat": 0, "lon": 0}}, "color": "rojo"}}]}}
   (con "resaltar" o "puntos"; lat/lon reales con 2 decimales)
- {{"tipo": "cifra", "numero": "69", "texto": "de qué es (2-5 palabras)", "iconos": ["emoji"], "repetir": 6}}
- {{"tipo": "fecha", "fecha": "18 de julio de 1936", "texto": "qué pasó (2-6 palabras)", "icono": "emoji"}}
- {{"tipo": "iconos", "titulo": "2-4 palabras", "secuencia": true, "elementos": [{{"icono": "emoji", "texto": "2-4 palabras"}}]}}
   (1-3 elementos; "secuencia": true si van uno tras otro, con flechas: causa → consecuencia)
- {{"tipo": "comparacion", "izquierda": {{"titulo": "...", "color": "azul", "iconos": ["emoji"], "puntos": ["2-4 palabras"]}},
   "derecha": {{"titulo": "...", "color": "rojo", "iconos": ["emoji"], "puntos": ["..."]}}}}  (1-2 puntos por lado)
- {{"tipo": "linea", "hitos": [{{"fecha": "1931", "texto": "2-4 palabras", "icono": "emoji"}}]}}  (2-4 hitos)
"""

PROMPT = (_ELEGIR + _REGLAS
          + '\nResponde SOLO con JSON: {{"dibujos": [{{"escena": 2, "desde": "palabra", "visual": {{...}}}}]}}')


def _cuantas(escenas: int) -> str:
    return "1" if escenas <= 2 else ("2" if escenas <= 5 else "3")


# En los vídeos hechos enteros con dibujos, cada escena lleva el suyo y el muñeco del canal lo va contando.
PROMPT_TODO = ("""Eres el montador de un canal de Shorts de historia, fútbol y actualidad. El vídeo se hace
ENTERO con dibujos animados: TODAS las escenas llevan un dibujo (ninguna foto), y un muñeco narrador lo va contando.

Para CADA escena elige el dibujo que mejor enseñe lo que dice:
- lugares, rutas, fronteras o avances → "mapa"
- una cifra importante → "cifra"
- una fecha clave → "fecha"
- causas y consecuencias, pasos o 2-3 ideas → "iconos"
- antes/después o dos bandos → "comparacion"
- varias fechas seguidas → "linea"
- lo demás (el gancho, una anécdota, la pregunta final) → "narrador": el muñeco dice una frase corta en un bocadillo
Varía: nunca el mismo tipo dos escenas seguidas, y como mucho la mitad de las escenas con "narrador". Si el texto
nombra lugares, al menos una escena es un mapa.
""" + _REGLAS + """- {{"tipo": "narrador", "bocadillo": "frase corta que dice el muñeco (3-8 palabras, con gancho)",
   "pose": "explica|senala|sorpresa|piensa|saluda", "iconos": ["1-2 emojis de lo que cuenta"]}}

Responde SOLO con JSON, con un dibujo por escena: {{"dibujos": [{{"escena": 1, "visual": {{...}}}}]}}""")


def planificar(datos: dict, trabajo: Path, huella) -> dict:
    """{número de escena: {"desde": palabra, "visual": {...}}}; {} si no hay IA o no está activado.

    Las escenas que ya traen su dibujo en el guion (los acertijos) lo usan tal cual, sin preguntar a la IA."""
    if datos.get("video_ia"):
        return {}
    propios = {e["numero"]: {"desde": "", "visual": v, "todo": True} for e in datos.get("escenas", [])
               if (v := validar(e.get("dibujo")))}
    if len(propios) == len(datos.get("escenas", [])) and propios:
        return propios
    if estilo_de(datos) == "fotos":
        return propios
    todo = estilo_de(datos) == "dibujos"
    escenas = [{"escena": e["numero"], "texto": e["narracion"]} for e in datos.get("escenas", [])]
    if not escenas:
        return {}
    pedido = json.dumps({"titulo": datos.get("titulo", ""), "escenas": escenas}, ensure_ascii=False)
    guardado = trabajo / "dibujos_ia.json"
    instrucciones = PROMPT_TODO if todo else PROMPT
    firma = huella(VERSION, instrucciones, pedido)  # si cambian las instrucciones, se vuelve a preguntar
    respuesta = None
    if guardado.exists():
        anterior = json.loads(guardado.read_text(encoding="utf-8"))
        respuesta = anterior.get("respuesta") if anterior.get("firma") == firma else None
    if respuesta is None:
        try:
            import paso1_guiones
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                raise RuntimeError("sin GROQ_API_KEY")
            texto = paso1_guiones.llamar_groq(api_key, os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO,
                                              instrucciones.format(cuantas=_cuantas(len(escenas))), pedido)
            respuesta = json.loads(re.sub(r"^```(?:json)?|```$", "", texto.strip())).get("dibujos", [])
        except Exception as error:  # noqa: BLE001 — sin IA el vídeo sale igual
            if not todo:
                print(f"  aviso: no se han podido planificar los dibujos ({type(error).__name__}); van solo fotos")
                return propios
            # Vídeo de dibujos: el muñeco cuenta todas las escenas (no se guarda: la próxima vez se vuelve a pedir)
            print(f"  aviso: la IA no ha podido elegir los dibujos ({type(error).__name__}): lo cuenta todo el muñeco")
            respuesta = []
        else:
            guardado.parent.mkdir(parents=True, exist_ok=True)
            guardado.write_text(json.dumps({"firma": firma, "respuesta": respuesta}, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    numeros = {e["escena"] for e in escenas}
    plan = dict(propios)
    for item in respuesta if isinstance(respuesta, list) else []:
        try:
            numero = int(item.get("escena"))
        except (TypeError, ValueError, AttributeError):
            continue
        visual = validar(item.get("visual"))
        if numero in numeros and numero not in plan and visual:
            plan[numero] = {"desde": str(item.get("desde") or ""), "visual": visual, "todo": todo}
    if todo:  # ninguna escena se queda sin dibujo: a las que falten, el muñeco con las primeras palabras
        for e in datos.get("escenas", []):
            if e["numero"] not in plan:
                frase = " ".join(e["narracion"].split()[:6]).rstrip(".,;:") + "…"
                plan[e["numero"]] = {"desde": "", "todo": True,
                                     "visual": {"tipo": "narrador", "bocadillo": frase, "pose": "explica", "iconos": []}}
    return plan


def _corto(valor, maximo=40) -> str:
    texto = re.sub(r"<\s*", "menos de ", re.sub(r">\s*", "más de ", str(valor or "")))
    return " ".join(texto.split())[:maximo]


@lru_cache(maxsize=None)
def _nombres_espana() -> frozenset:
    """Provincias, comunidades y otros nombres de lugares de España (para usar el mapa de España)."""
    nombres = {"espana", "peninsula", "peninsula iberica", "baleares", "canarias", "valencia", "murcia", "euskadi"}
    for p in D._mapa("espana"):
        nombres |= {D.normalizar(n) for n in [*p["alias"], p["comunidad"]]}
    return frozenset(nombres)


def _en_espana(lon, lat) -> bool:
    lon0, lon1, lat0, lat1 = D.ZONAS["espana"]
    return (lon0 <= lon <= lon1 and lat0 <= lat <= lat1) or D._en_canarias(lon, lat)


def validar(visual) -> dict:
    """El visual limpio si se puede dibujar; {} si no."""
    if not isinstance(visual, dict):
        return {}
    tipo = D.normalizar(str(visual.get("tipo") or "")).replace(" ", "")
    if tipo not in TIPOS:
        return {}
    if tipo == "narrador":
        pose = D.normalizar(str(visual.get("pose") or "explica"))
        return {"tipo": tipo, "bocadillo": _corto(visual.get("bocadillo") or visual.get("texto"), 70),
                "pose": pose if pose in D.POSES else "explica", "iconos": D.iconos_validos(visual.get("iconos"))[:2]}
    if tipo == "acertijo":  # el enunciado en una pizarra, con el muñeco pensando
        texto = _corto(visual.get("texto"), 260)
        return {"tipo": tipo, "texto": texto, "titulo": _corto(visual.get("titulo") or "Acertijo", 24)} if texto else {}
    if tipo == "cuenta":  # cuenta atrás mientras el espectador piensa
        try:
            desde = min(max(int(visual.get("desde") or 5), 3), 10)
        except (TypeError, ValueError):
            desde = 5
        return {"tipo": tipo, "desde": desde, "texto": _corto(visual.get("texto"), 260)}
    if tipo == "solucion":
        texto = _corto(visual.get("texto"), 60)
        icono = visual.get("icono") if D.iconos_validos([visual.get("icono")]) else ""
        return {"tipo": tipo, "texto": texto, "explicacion": _corto(visual.get("explicacion"), 110), "icono": icono} if texto else {}
    if tipo == "mapa":
        zona = D.normalizar(str(visual.get("zona") or "espana")).replace(" ", "")
        zona = zona if zona in D.ZONAS else "espana"
        lugares = [str(l) for g in visual.get("resaltar") or [] if isinstance(g, dict) for l in g.get("lugares") or []]
        coordenadas = [(p.get("lon"), p.get("lat")) for p in visual.get("puntos") or [] if isinstance(p, dict)]
        if (zona != "espana" and (lugares or coordenadas)
                and all(D.normalizar(l) in _nombres_espana() for l in lugares)
                and all(isinstance(x, (int, float)) and isinstance(y, (int, float)) and _en_espana(x, y)
                        for x, y in coordenadas)):
            zona = "espana"  # todo pasa en España: en el mapa del Mediterráneo se vería diminuto
        indice, _ = D._indice_lugares(zona)
        resaltar = []
        for grupo in (visual.get("resaltar") or [])[:3]:
            if isinstance(grupo, dict):
                lugares = [str(l) for l in grupo.get("lugares") or [] if D.normalizar(str(l)) in indice]
                if lugares:
                    resaltar.append({"lugares": lugares, "color": grupo.get("color") or "rojo",
                                     "etiqueta": _corto(grupo.get("etiqueta"), 24)})
        puntos = [{"texto": _corto(p.get("texto") or p.get("lugar"), 18), "lat": p["lat"], "lon": p["lon"]}
                  for p in (visual.get("puntos") or [])[:3]
                  if isinstance(p, dict) and isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float))]
        flechas = [f for f in (visual.get("flechas") or [])[:3] if isinstance(f, dict)
                   and D._coordenadas(f.get("desde"), zona) and D._coordenadas(f.get("hasta"), zona)]
        if not resaltar and not puntos:
            return {}
        return {"tipo": tipo, "zona": zona, "titulo": _corto(visual.get("titulo"), 30), "resaltar": resaltar,
                "puntos": puntos, "flechas": flechas}
    if tipo == "cifra":
        numero = _corto(visual.get("numero"), 10)
        if not numero:
            return {}
        try:
            repetir = min(max(int(visual.get("repetir") or 6), 4), 7)  # un icono suelto se pierde: de 4 a 7
        except (TypeError, ValueError):
            repetir = 6
        return {"tipo": tipo, "numero": numero, "texto": _corto(visual.get("texto")),
                "iconos": D.iconos_validos(visual.get("iconos"))[:2], "repetir": repetir}
    if tipo == "fecha":
        if not visual.get("fecha"):
            return {}
        icono = visual.get("icono") if D.iconos_validos([visual.get("icono")]) else ""
        return {"tipo": tipo, "fecha": _corto(visual["fecha"], 30), "texto": _corto(visual.get("texto")), "icono": icono}
    if tipo == "iconos":
        elementos = [{"icono": e["icono"], "texto": _corto(e.get("texto"), 30)}
                     for e in (visual.get("elementos") or []) if isinstance(e, dict) and D.svg_emoji(e.get("icono", ""))][:3]
        if not elementos or len({e["icono"] for e in elementos}) < len(elementos):
            return {}  # el mismo icono repetido no explica nada
        return {"tipo": tipo, "titulo": _corto(visual.get("titulo"), 30), "secuencia": bool(visual.get("secuencia")),
                "elementos": elementos}
    if tipo == "comparacion":
        lados = []
        for clave in ("izquierda", "derecha"):
            lado = visual.get(clave) if isinstance(visual.get(clave), dict) else {}
            lados.append({"titulo": _corto(lado.get("titulo"), 26),  # la letra se ajusta al ancho
                          "color": lado.get("color") or "",
                          "iconos": D.iconos_validos(lado.get("iconos"))[:2],
                          "puntos": [_corto(p, 30) for p in (lado.get("puntos") or [])[:2]]})
        if not all(l["titulo"] for l in lados):
            return {}
        return {"tipo": tipo, "izquierda": lados[0], "derecha": lados[1]}
    hitos = [{"fecha": _corto(h.get("fecha"), 12), "texto": _corto(h.get("texto"), 26),
              "icono": h.get("icono") if D.iconos_validos([h.get("icono")]) else ""}
             for h in (visual.get("hitos") or []) if isinstance(h, dict) and h.get("fecha")][:4]
    return {"tipo": "linea", "hitos": hitos} if len(hitos) >= 2 else {}


# --- Cómo se dibuja (lienzo 1080×1036) ------------------------------------------------------------

REEMPLAZA = "\x00reemplaza"  # clave de un paso que sustituye al anterior en vez de sumarse (la cuenta atrás)


def _pizarra(texto: str, y0: int, y1: int, tam_max: int = 62) -> str:
    """El enunciado en una tarjeta blanca entre y0 e y1, con la letra más grande que quepa."""
    alto = y1 - y0 - 50
    tam = next((t for t in range(tam_max, 30, -4) if D.lineas_de(texto, t, 900) * t * 1.2 <= alto), 32)
    return (f'<g filter="url(#mano)"><rect x="40" y="{y0}" width="1000" height="{y1 - y0}" rx="28" fill="white" '
            f'stroke="{T}" stroke-width="6"/></g>'
            + D.texto(540, (y0 + y1) / 2 + 6, texto, tam, 900, interlineado=1.2, max_lineas=9, centrar_vertical=True))


def escena(visual: dict, personaje: str = None):
    """(capas base, [(capa, centro del «pop» o None, clave)]): la base se ve desde el principio y cada paso se suma
    cuando la voz dice su clave.

    `personaje`: el muñeco del vídeo (en los vídeos hechos enteros con dibujos): cuenta las escenas «narrador» y se
    asoma en una esquina en los mapas, las cifras y las fechas."""
    tipo = visual["tipo"]
    base, pasos = [], []
    quien = personaje or "bonesy"
    if tipo == "narrador":
        base.append(D.personaje(quien, 270, 1005, 600, visual.get("pose") or "explica"))
        if visual.get("bocadillo"):
            pasos.append((D.bocadillo(60, 50, 960, visual["bocadillo"], (330, 440), 64), (540, 180), visual["bocadillo"]))
        iconos = visual.get("iconos") or []
        if iconos:
            xs = (790,) if len(iconos) == 1 else (680, 920)
            tam = 290 if len(iconos) == 1 else 220
            pasos.append(("".join(D.icono(e, x, 690, tam) for x, e in zip(xs, iconos)), (800, 690), ""))
    elif tipo == "acertijo":
        base += [D.etiqueta(540, 70, visual.get("titulo") or "Acertijo", 58, fondo="#ffd23f"),
                 _pizarra(visual["texto"], 130, 650), D.personaje(quien, 190, 1015, 350, "piensa")]
        pasos.append((D.texto(560, 800, "?", 190, fuente="titulo", relleno=R)
                      + D.texto(730, 760, "?", 250, fuente="titulo", relleno=D.COLORES["azul"])
                      + D.texto(900, 810, "?", 170, fuente="titulo", relleno=D.COLORES["amarillo"]), (730, 780), ""))
    elif tipo == "cuenta":
        if visual.get("texto"):
            base.append(_pizarra(visual["texto"], 40, 400, 46))
        base += [D.personaje(quien, 170, 1015, 340, "piensa"), D.icono("⏳", 910, 660, 170)]
        for n in range(visual["desde"], 0, -1):
            pasos.append((f'<g filter="url(#mano)"><circle cx="540" cy="650" r="175" fill="#ffd23f" stroke="{T}" '
                          f'stroke-width="10"/></g>' + D.texto(540, 662, str(n), 250, fuente="titulo", relleno=R),
                          (540, 650), REEMPLAZA))
    elif tipo == "solucion":
        texto = visual["texto"]
        tam = 150 if len(texto) <= 12 else (104 if len(texto) <= 26 else 76)
        base += [D.etiqueta(540, 70, "Solución", 58, fondo="#b8e6c1"), D.personaje(quien, 200, 1015, 380, "sorpresa")]
        pasos.append((D.texto(540, 290, texto, tam, 1000, "titulo", relleno=R, max_lineas=3, centrar_vertical=True),
                      (540, 290), texto))
        extra = D.texto(540, 540, visual["explicacion"], 50, 940, max_lineas=3, centrar_vertical=True) if visual.get("explicacion") else ""
        if visual.get("icono"):
            extra += D.icono(visual["icono"], 760, 800, 240)
        if extra:
            pasos.append((extra, (540, 600), visual.get("explicacion", "")))
    elif tipo == "mapa":
        caja = (30, 130, 1020, 750)
        fondo, capas, leyenda = D.mapa(visual, caja)
        base.append(fondo)
        if visual.get("titulo"):
            base.append(D.etiqueta(540, 66, visual["titulo"], 52))
        proyectar = D._proyeccion(caja, D.ZONAS[visual["zona"]])
        claves_lugar = [" ".join(g["lugares"]) for g in visual.get("resaltar") or []]
        for i, capa in enumerate(capas):
            extra = capa
            if i < len(leyenda) and leyenda[i][0]:
                nombre, c = leyenda[i]
                y = 170 + i * 62
                extra += (f'<g filter="url(#mano)"><rect x="50" y="{y - 26}" width="{len(nombre) * 19 + 80}" height="52" '
                          f'rx="12" fill="white" stroke="{T}" stroke-width="4"/><rect x="62" y="{y - 15}" width="30" '
                          f'height="30" rx="6" fill="{c}" stroke="{T}" stroke-width="3"/></g>'
                          + D.texto(104, y, nombre, 38, ancla="start"))
            if i < len(claves_lugar):
                pasos.append((extra, None, claves_lugar[i]))
            else:  # puntos y flechas
                punto = (visual.get("puntos") or [{}])[0]
                centro = proyectar(punto["lon"], punto["lat"]) if "lat" in punto else None
                pasos.append((extra, centro, punto.get("texto", "")))
    elif tipo == "cifra":
        numero = visual["numero"]
        tam = 240 if len(numero) <= 5 else (190 if len(numero) <= 7 else 150)
        capa = D.texto(540, 300, numero, tam, fuente="titulo", relleno=R)
        if visual.get("texto"):
            capa += D.texto(540, 490, visual["texto"], 70, 980, "titulo", max_lineas=2)
        pasos.append((capa, (540, 360), numero))
        if visual.get("iconos"):
            n, tam_i = visual["repetir"], 120
            medio = 540
            if personaje:  # el muñeco está en la esquina de abajo a la derecha: la fila, más corta y a la izquierda
                n, medio = min(n, 5), 420
            ancho = n * (tam_i + 14)
            fila = "".join(D.icono(visual["iconos"][i % len(visual["iconos"])], medio - ancho / 2 + tam_i / 2 + i * (tam_i + 14),
                                   740, tam_i) for i in range(n))
            pasos.append((fila, (medio, 740), visual.get("texto", "")))
    elif tipo == "fecha":
        dia, mes, anio = D._partes_fecha(visual["fecha"])
        pasos.append((D._calendario(540, 320, dia, mes, anio), (540, 320), anio or visual["fecha"]))
        if visual.get("texto"):
            capa = ""
            x = 540
            if visual.get("icono"):
                capa += D.icono(visual["icono"], 150, 730, 170)
                x = 610
            ancho = 760 if visual.get("icono") else 980
            if personaje:  # sitio para el muñeco de la esquina
                x, ancho = x - 90, ancho - 200
            capa += D.texto(x, 730, visual["texto"], 66, ancho, "titulo", centrar_vertical=True, max_lineas=2)
            pasos.append((capa, (540, 730), visual["texto"]))
    elif tipo == "iconos":
        elementos = visual["elementos"]
        if visual.get("titulo"):
            base.append(D.texto(540, 110, visual["titulo"], 92, 1000, "titulo", max_lineas=1)
                        + D.subrayado(260, 820, 180))
        xs = {1: (540,), 2: (290, 790), 3: (185, 540, 895)}[len(elementos)]
        tam = {1: 380, 2: 300, 3: 240}[len(elementos)]
        y = 470
        for i, (x, e) in enumerate(zip(xs, elementos)):
            capa = ""
            if i and visual.get("secuencia"):
                capa += D.flecha(xs[i - 1] + tam * 0.45, y, x - tam * 0.45, y, R, 9, 0)
            capa += D.icono(e["icono"], x, y, tam)
            if e.get("texto"):
                capa += D.texto(x, y + tam / 2 + 70, e["texto"], 54 if len(elementos) == 3 else 62,
                                1000 / len(elementos) - 40, "titulo", max_lineas=3)
            pasos.append((capa, (x, y), e.get("texto", "")))
    elif tipo == "comparacion":
        for (ax, bx), lado, defecto in zip(((30, 520), (560, 1050)), (visual["izquierda"], visual["derecha"]),
                                           ("azul", "rojo")):
            c = D.color(lado.get("color"), defecto)
            medio = (ax + bx) / 2
            capa = (f'<g filter="url(#mano)"><rect x="{ax}" y="60" width="{bx - ax}" height="800" rx="30" fill="white" '
                    f'stroke="{T}" stroke-width="6"/><path d="M{ax},90 Q{ax},60 {ax + 30},60 L{bx - 30},60 Q{bx},60 '
                    f'{bx},90 L{bx},170 L{ax},170 Z" fill="{c}" stroke="{T}" stroke-width="6"/></g>'
                    + D.texto(medio, 117, lado["titulo"], min(58, (bx - ax - 40) / (0.52 * max(len(lado["titulo"]), 1))),
                              fuente="titulo", relleno="white"))
            for j, e in enumerate(lado.get("iconos") or []):
                capa += D.icono(e, medio + (j - (len(lado["iconos"]) - 1) / 2) * 180, 330, 170)
            y = 530
            for punto in lado.get("puntos") or []:
                capa += D.texto(medio, y, punto, 52, bx - ax - 50, "titulo", max_lineas=2)
                y += 52 * 1.15 * D.lineas_de(punto, 52, bx - ax - 50, "titulo") + 50
            pasos.append((capa, (medio, 460), lado["titulo"]))
        pasos[-1] = (pasos[-1][0] + f'<g filter="url(#mano)"><circle cx="540" cy="470" r="60" fill="{D.COLORES["amarillo"]}" '
                     f'stroke="{T}" stroke-width="6"/></g>' + D.texto(540, 476, "VS", 62, fuente="titulo"),
                     pasos[-1][1], pasos[-1][2])
    else:  # linea
        hitos = visual["hitos"]
        y = 450
        base.append(f'<g filter="url(#mano)"><line x1="50" y1="{y}" x2="1000" y2="{y}" stroke="{T}" stroke-width="12" '
                    f'stroke-linecap="round"/><path d="M990,{y - 26} L1040,{y} L990,{y + 26}" fill="none" stroke="{T}" '
                    f'stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/></g>')
        hueco = 960 / len(hitos)
        for i, h in enumerate(hitos):
            x = 50 + hueco * (i + 0.5)
            arriba = i % 2 == 0
            signo = -1 if arriba else 1
            ultimo = i == len(hitos) - 1
            capa = (f'<g filter="url(#mano)"><circle cx="{x:.0f}" cy="{y}" r="{30 if ultimo else 22}" '
                    f'fill="{R if ultimo else D.COLORES["amarillo"]}" stroke="{T}" stroke-width="6"/></g>'
                    + D.texto(x, y + signo * 80, h["fecha"], 70, fuente="titulo", relleno=R if ultimo else T)
                    + D.texto(x, y + signo * (170 if arriba else 155), h.get("texto"), 50, hueco + 40, max_lineas=3,
                              centrar_vertical=True))
            if h.get("icono"):
                capa += D.icono(h["icono"], x, y + signo * 290, 130)
            pasos.append((capa, (x, y), h["fecha"]))
    if personaje and tipo in ("mapa", "cifra", "fecha"):  # por delante del dibujo, asomado en la esquina
        base.append(D.personaje(personaje, 975, 1000, 300, "senala", "izquierda"))
    return base, pasos


# --- Cuándo aparece cada cosa ------------------------------------------------------------------------

def _tokens(texto) -> list:
    return [t for t in re.findall(r"\w+", D.normalizar(str(texto or ""))) if len(t) >= 4 or t.isdigit()]


def _momento(palabras: list, clave, desde: float = 0.0):
    """Segundo en que suena la primera palabra de `clave` (a partir de `desde`), o None."""
    tokens = _tokens(clave)
    for p in palabras:
        if p["inicio_s"] >= desde - 0.05 and any(t in _tokens(p["texto"]) for t in tokens):
            return p["inicio_s"]
    return None


def tiempos(plan: dict, palabras: list, duracion: float, primera: bool, gancho: float, personaje: str = None):
    """(segundo en que empieza el dibujo, [segundo de cada paso relativo al dibujo]) o None si no cabe.

    Con plan["todo"] (vídeos hechos enteros con dibujos) el dibujo ocupa la escena entera, desde el segundo 0."""
    _, pasos = escena(plan["visual"], personaje)
    if plan["visual"]["tipo"] == "cuenta":  # los números, repartidos en el silencio que queda al acabar la voz
        fin_voz = (palabras[-1]["fin_s"] + 0.3) if palabras else 0.3
        hueco = max(duracion - fin_voz - 0.3, 1.0) / len(pasos)
        return 0.0, [round(fin_voz + k * hueco, 2) for k in range(len(pasos))]
    if plan.get("todo"):
        inicio = 0.0
    else:
        minimo = max(FOTO_MINIMA, gancho + 0.2 if primera else 0)
        if duracion - minimo < DIBUJO_MINIMO:
            return None
        inicio = _momento(palabras, plan["desde"])
        if inicio is None or inicio < minimo or duracion - inicio < DIBUJO_MINIMO:
            inicio = max(minimo, min(duracion * 0.45, duracion - DIBUJO_MINIMO))
        inicio = max(minimo, inicio - 0.1)
    largo = duracion - inicio
    momentos, anterior = [], 0.0
    for k, (_, _, clave) in enumerate(pasos):
        reparto = 0.1 + (largo - 0.9) * k / max(len(pasos), 1)  # sin palabra que lo marque: repartidos
        t = _momento(palabras, clave, inicio + anterior)
        t = (t - inicio) if t is not None and t - inicio < largo - 0.4 else reparto
        t = max(t, anterior + (0.25 if k else 0.1))
        momentos.append(round(t, 2))
        anterior = t
    return round(inicio, 2), momentos


# --- Clip ---------------------------------------------------------------------------------------------

def _pop(capa: str, centro, escala: float) -> str:
    if not centro or escala == 1:
        return capa
    cx, cy = centro
    return f'<g transform="translate({cx:.0f} {cy:.0f}) scale({escala}) translate({-cx:.0f} {-cy:.0f})">{capa}</g>'


def _fotogramas_foto(ruta, duracion: float):
    imagen = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    grande = ImageOps.fit(imagen, (int(ANCHO * 1.12), int(ALTO * 1.12)))
    n = round(duracion * FPS)
    for i in range(n):
        z = 1.12 - 0.1 * i / max(n - 1, 1)
        aw, ah = min(ANCHO * z, grande.width), min(ALTO * z, grande.height)
        x0, y0 = (grande.width - aw) / 2, (grande.height - ah) / 2
        yield grande.resize((ANCHO, ALTO), Image.BILINEAR, box=(x0, y0, x0 + aw, y0 + ah))


def _fotogramas_dibujo(visual: dict, momentos: list, duracion: float, carpeta: Path, prefijo: str, personaje=None):
    """Solo se renderizan los fotogramas distintos (cada paso y los de su «pop»); el resto se repiten."""
    base, pasos = escena(visual, personaje)
    lineas, acumulado = [(0.0, list(base))], list(base)
    for t, (capa, centro, clave) in zip(momentos, pasos):
        if clave == REEMPLAZA:
            acumulado = list(base)  # la cuenta atrás: cada número sustituye al anterior
        if centro:
            for k, escala in enumerate(POP[:-1]):
                lineas.append((t + k / FPS, acumulado + [_pop(capa, centro, escala)]))
        acumulado = acumulado + [capa]
        lineas.append((t + ((len(POP) - 1) / FPS if centro else 0), list(acumulado)))
    trabajos = [(D.documento(capas, ancho=ANCHO, alto=ALTO, vista=(ANCHO, ALTO), semilla=3),
                 carpeta / f"{prefijo}_{j:03d}.png", ANCHO, ALTO) for j, (_, capas) in enumerate(lineas)]
    D.renderizar(trabajos)
    actual, cargada = 0, {}
    for i in range(round(duracion * FPS)):
        t = i / FPS
        while actual + 1 < len(lineas) and lineas[actual + 1][0] <= t + 1e-6:
            actual += 1
        ruta = trabajos[actual][1]
        if ruta not in cargada:
            cargada = {ruta: Image.open(ruta).convert("RGB")}
        yield cargada[ruta]
    for _, ruta, _, _ in trabajos:
        ruta.unlink(missing_ok=True)


def clip(trabajo: Path, numero: int, ruta_imagen, plan: dict, momento, duracion: float, huella, info_archivo,
         personaje: str = None) -> Path:
    """El clip de la escena (1080×1036): la foto con zoom lento y, desde `momento[0]`, el dibujo. Con caché."""
    inicio, momentos = momento
    if not ruta_imagen:
        inicio = 0.0  # sin foto: todo el rato el dibujo
    destino = trabajo / f"dibujo_{numero:02d}.mp4"
    clave = trabajo / f"dibujo_{numero:02d}.clave"
    firma = huella(VERSION, info_archivo(ruta_imagen) if inicio > 0 else None, plan["visual"], inicio, momentos,
                   round(duracion, 2), personaje)
    if destino.exists() and clave.exists() and clave.read_text() == firma:
        return destino
    proceso = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", destino.name],
        stdin=subprocess.PIPE, cwd=trabajo, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        if inicio > 0:
            for cuadro in _fotogramas_foto(ruta_imagen, inicio):
                proceso.stdin.write(cuadro.tobytes())
        for cuadro in _fotogramas_dibujo(plan["visual"], momentos, duracion - inicio, trabajo, f"dib{numero:02d}",
                                         personaje):
            proceso.stdin.write(cuadro.tobytes())
    finally:
        proceso.stdin.close()
        proceso.wait()
    if proceso.returncode != 0:
        raise RuntimeError(f"ffmpeg no pudo montar el dibujo de la escena {numero}")
    clave.write_text(firma)
    return destino
