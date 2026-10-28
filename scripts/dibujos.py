"""Dibujos para los vídeos largos: escenas de 1920×1080 dibujadas por la propia app, con estilo de rotulador.

Nada sale de una IA de imágenes: cada escena es un SVG hecho con código (el narrador Bonesy, personajes
históricos sencillos, mapas reales de datos/mapas, fechas, cifras, líneas de tiempo…) y los objetos son
dibujos de Twemoji (CC-BY 4.0). Edge, en modo sin ventana, convierte cada escena en PNG.

Cada escena se dibuja por «pasos»: el paso 0 es lo básico y cada paso siguiente añade un elemento, para
que en el vídeo las cosas vayan apareciendo mientras la voz las nombra.

    tipos de escena: narrador, titulo, fecha, cifra, mapa, personajes, iconos, linea, comparacion
"""
import base64
import html
import json
import math
import re
import subprocess
import tempfile
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import requests

ANCHO, ALTO = 1920, 1080
DATOS = Path(__file__).resolve().parent.parent / "datos"
CACHE_ICONOS = Path("salida/twemoji")
URL_TWEMOJI = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/svg/{codigo}.svg"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

TINTA = "#262321"
PAPEL = "#fbf6ea"
HUESO = "#f4efe4"
COLORES = {
    "rojo": "#d9432f", "azul": "#2f6fb5", "amarillo": "#f2c14e", "verde": "#4f9d5b", "morado": "#7b5ea7",
    "naranja": "#ee8a3c", "gris": "#9a958c", "marron": "#8a5a3b", "negro": "#3a3633", "blanco": "#ffffff",
    "rosa": "#e98aa5", "celeste": "#7cc3e8", "caqui": "#8f8a4e", "dorado": "#d9a520", "granate": "#8e2b2b",
}
PIEL = "#f2c9a0"


def color(nombre: str, defecto: str = "rojo") -> str:
    nombre = (nombre or "").strip().lower()
    if nombre.startswith("#") and len(nombre) in (4, 7):
        return nombre
    return COLORES.get(normalizar(nombre), COLORES[defecto])


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").strip()


def esc(texto) -> str:
    return html.escape(str(texto or ""), quote=True)


# ------------------------------------------------------------------ texto

def partir(texto: str, max_caracteres: int, max_lineas: int = 6) -> list:
    """Parte el texto en líneas de como mucho `max_caracteres` (aprox.)."""
    lineas, actual = [], ""
    for palabra in str(texto or "").split():
        if actual and len(actual) + 1 + len(palabra) > max_caracteres:
            lineas.append(actual)
            actual = palabra
        else:
            actual = f"{actual} {palabra}".strip()
    if actual:
        lineas.append(actual)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        lineas[-1] = lineas[-1].rstrip(".,;:") + "…"
    return lineas


def texto(x, y, contenido, tam=44, ancho=None, fuente="mano", relleno=TINTA, ancla="middle", interlineado=1.15,
          max_lineas=6, peso="normal", centrar_vertical=False) -> str:
    """Texto (con saltos de línea si se da `ancho` en píxeles)."""
    familia = "Lilita" if fuente == "titulo" else "Mano"
    por_caracter = 0.5 if fuente == "titulo" else 0.43
    lineas = partir(contenido, int(ancho / (tam * por_caracter)), max_lineas) if ancho else [str(contenido)]
    alto_linea = tam * interlineado
    if centrar_vertical:
        y -= alto_linea * (len(lineas) - 1) / 2
    tspans = "".join(f'<tspan x="{x:.0f}" dy="{0 if i == 0 else alto_linea:.0f}">{esc(l)}</tspan>'
                     for i, l in enumerate(lineas))
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-family="{familia}" font-size="{tam}" fill="{relleno}" '
            f'text-anchor="{ancla}" font-weight="{peso}" dominant-baseline="middle">{tspans}</text>')


def lineas_de(contenido, tam, ancho, fuente="mano") -> int:
    por_caracter = 0.5 if fuente == "titulo" else 0.43
    return len(partir(contenido, int(ancho / (tam * por_caracter))))


# ------------------------------------------------------------------ iconos (Twemoji)

def _codigo_emoji(emoji: str) -> str:
    puntos = [f"{ord(c):x}" for c in emoji]
    if "200d" not in puntos:
        puntos = [p for p in puntos if p != "fe0f"]
    return "-".join(puntos)


@lru_cache(maxsize=None)
def svg_emoji(emoji: str):
    """El SVG de Twemoji del emoji (descargado una vez y guardado en caché) o None si no existe."""
    emoji = (emoji or "").strip()
    if not emoji or emoji.isascii():
        return None
    CACHE_ICONOS.mkdir(parents=True, exist_ok=True)
    for codigo in dict.fromkeys([_codigo_emoji(emoji), "-".join(f"{ord(c):x}" for c in emoji)]):
        ruta = CACHE_ICONOS / f"{codigo}.svg"
        if ruta.exists():
            return ruta.read_text(encoding="utf-8")
        try:
            respuesta = requests.get(URL_TWEMOJI.format(codigo=codigo), timeout=20)
        except requests.RequestException:
            return None
        if respuesta.status_code == 200 and "<svg" in respuesta.text:
            ruta.write_text(respuesta.text, encoding="utf-8")
            return respuesta.text
    return None


def icono(emoji: str, cx, cy, tam) -> str:
    """El dibujo del emoji centrado en (cx, cy); vacío si no existe."""
    svg = svg_emoji(emoji)
    if not svg:
        return ""
    svg = re.sub(r"<\?xml[^>]*>", "", svg).strip()
    return svg.replace("<svg ", f'<svg x="{cx - tam / 2:.0f}" y="{cy - tam / 2:.0f}" width="{tam:.0f}" '
                                f'height="{tam:.0f}" ', 1)


def iconos_validos(lista) -> list:
    return [e for e in (lista or []) if isinstance(e, str) and svg_emoji(e)]


# ------------------------------------------------------------------ figuras

POSES = {  # (codo, muñeca) de cada brazo, en coordenadas de la figura (pies en 0,0; la cabeza hacia y < 0)
    "neutro":   (((-64, -215), (-66, -158)), ((64, -215), (66, -158))),
    "senala":   (((-64, -215), (-66, -158)), ((105, -275), (160, -305))),
    "piensa":   (((-64, -215), (-66, -158)), ((95, -300), (42, -386))),
    "sorpresa": (((-100, -318), (-112, -385)), ((100, -318), (112, -385))),
    "explica":  (((-64, -215), (-66, -158)), ((88, -228), (138, -250))),
    "saluda":   (((-64, -215), (-66, -158)), ((100, -298), (108, -372))),
    "brazos":   (((-30, -220), (30, -232)), ((30, -214), (-30, -226))),  # brazos cruzados
}
HOMBROS = ((-50, -282), (50, -282))
ALIAS_POSES = {"pensando": "piensa", "pensar": "piensa", "pensativo": "piensa", "sorprendido": "sorpresa",
               "sorprendida": "sorpresa", "senalando": "senala", "explicando": "explica", "saludando": "saluda",
               "cruzado": "brazos", "brazos cruzados": "brazos"}


def _brazo(hombro, codo, muneca, manga, mano, sensor=False) -> str:
    puntos = f"M{hombro[0]},{hombro[1]} L{codo[0]},{codo[1]} L{muneca[0]},{muneca[1]}"
    partes = [f'<path d="{puntos}" fill="none" stroke="{TINTA}" stroke-width="34" stroke-linecap="round" '
              f'stroke-linejoin="round"/>',
              f'<path d="{puntos}" fill="none" stroke="{manga}" stroke-width="25" stroke-linecap="round" '
              f'stroke-linejoin="round"/>']
    dx, dy = muneca[0] - codo[0], muneca[1] - codo[1]
    largo = math.hypot(dx, dy) or 1
    ux, uy = dx / largo, dy / largo
    hx, hy = muneca[0] + ux * 16, muneca[1] + uy * 16
    partes.append(f'<circle cx="{hx:.0f}" cy="{hy:.0f}" r="11" fill="{mano}" stroke="{TINTA}" stroke-width="4"/>')
    for angulo in (-0.5, 0, 0.5):  # dedos
        c, s = math.cos(angulo), math.sin(angulo)
        fx, fy = ux * c - uy * s, ux * s + uy * c
        partes.append(f'<line x1="{hx + fx * 8:.0f}" y1="{hy + fy * 8:.0f}" x2="{hx + fx * 20:.0f}" '
                      f'y2="{hy + fy * 20:.0f}" stroke="{TINTA}" stroke-width="4" stroke-linecap="round"/>')
    if sensor:  # el reloj verde de Bonesy
        partes.append(f'<rect x="{muneca[0] - 10:.0f}" y="{muneca[1] - 10:.0f}" width="20" height="20" rx="5" '
                      f'fill="#7ff3e0" stroke="{TINTA}" stroke-width="4"/>')
    return "".join(partes)


def _piernas(color_pierna, hueso=False) -> str:
    partes = []
    for lado in (-1, 1):
        cadera, pie = (lado * 18, -150), (lado * 24, -24)
        ancho = 16 if hueso else 30
        partes += [f'<line x1="{cadera[0]}" y1="{cadera[1]}" x2="{pie[0]}" y2="{pie[1]}" stroke="{TINTA}" '
                   f'stroke-width="{ancho + 8}" stroke-linecap="round"/>',
                   f'<line x1="{cadera[0]}" y1="{cadera[1]}" x2="{pie[0]}" y2="{pie[1]}" stroke="{color_pierna}" '
                   f'stroke-width="{ancho}" stroke-linecap="round"/>']
        if hueso:
            partes.append(f'<circle cx="{lado * 21}" cy="-88" r="11" fill="{HUESO}" stroke="{TINTA}" stroke-width="4"/>')
    return "".join(partes) + _zapatos()


def _zapatos() -> str:
    partes = []
    for lado in (-1, 1):
        fx = lado * 26
        partes.append(f'<path d="M{fx - 26},-4 Q{fx - 26},-42 {fx},-42 Q{fx + 26},-42 {fx + 30},-4 Z" fill="{TINTA}" '
                      f'stroke="{TINTA}" stroke-width="4" stroke-linejoin="round"/>')
        partes.append(f'<line x1="{fx - 24}" y1="-7" x2="{fx + 28}" y2="-7" stroke="white" stroke-width="5" '
                      f'stroke-linecap="round"/>')
    return "".join(partes)


def _cuerpo(ropa_color, tipo="sudadera") -> str:
    contorno = (f'M-50,-292 Q0,-306 50,-292 Q66,-250 64,-150 Q0,-136 -64,-150 Q-66,-250 -50,-292 Z')
    partes = [f'<path d="{contorno}" fill="{ropa_color}" stroke="{TINTA}" stroke-width="6" stroke-linejoin="round"/>']
    if tipo == "sudadera":
        partes += [f'<path d="M-36,-296 Q0,-262 36,-296" fill="none" stroke="{TINTA}" stroke-width="5"/>',
                   f'<line x1="-10" y1="-282" x2="-12" y2="-246" stroke="{TINTA}" stroke-width="3"/>',
                   f'<line x1="10" y1="-282" x2="12" y2="-246" stroke="{TINTA}" stroke-width="3"/>',
                   f'<path d="M-34,-200 L34,-200 L42,-166 L-42,-166 Z" fill="none" stroke="{TINTA}" stroke-width="4" '
                   f'stroke-linejoin="round" opacity="0.7"/>']
    elif tipo == "traje":
        partes += [f'<path d="M-22,-298 L0,-240 L22,-298 Z" fill="white" stroke="{TINTA}" stroke-width="4"/>',
                   f'<path d="M0,-286 L-8,-262 L0,-228 L8,-262 Z" fill="{COLORES["granate"]}" stroke="{TINTA}" '
                   f'stroke-width="3"/>']
    elif tipo == "uniforme":
        partes += [f'<line x1="0" y1="-296" x2="0" y2="-150" stroke="{TINTA}" stroke-width="3"/>']
        partes += [f'<circle cx="10" cy="{y}" r="5" fill="{COLORES["dorado"]}" stroke="{TINTA}" stroke-width="2"/>'
                   for y in (-268, -240, -212, -184)]
        partes += [f'<rect x="-62" y="-196" width="124" height="14" fill="{COLORES["marron"]}" stroke="{TINTA}" '
                   f'stroke-width="3"/>',
                   f'<rect x="-60" y="-300" width="30" height="10" rx="3" fill="{COLORES["dorado"]}" stroke="{TINTA}" '
                   f'stroke-width="3"/>',
                   f'<rect x="30" y="-300" width="30" height="10" rx="3" fill="{COLORES["dorado"]}" stroke="{TINTA}" '
                   f'stroke-width="3"/>']
    elif tipo == "obrero":
        partes += [f'<path d="M-30,-230 L30,-230 L34,-150 L-34,-150 Z" fill="{COLORES["azul"]}" stroke="{TINTA}" '
                   f'stroke-width="4"/>',
                   f'<line x1="-26" y1="-232" x2="-38" y2="-292" stroke="{COLORES["azul"]}" stroke-width="10"/>',
                   f'<line x1="26" y1="-232" x2="38" y2="-292" stroke="{COLORES["azul"]}" stroke-width="10"/>']
    elif tipo == "vestido":
        partes = [f'<path d="M-46,-292 Q0,-304 46,-292 Q60,-230 92,-70 Q0,-50 -92,-70 Q-60,-230 -46,-292 Z" '
                  f'fill="{ropa_color}" stroke="{TINTA}" stroke-width="6" stroke-linejoin="round"/>']
    elif tipo == "sotana":
        partes = [f'<path d="M-50,-292 Q0,-306 50,-292 Q70,-200 72,-30 Q0,-20 -72,-30 Q-70,-200 -50,-292 Z" '
                  f'fill="{COLORES["negro"]}" stroke="{TINTA}" stroke-width="6"/>',
                  f'<rect x="-12" y="-300" width="24" height="12" fill="white" stroke="{TINTA}" stroke-width="3"/>']
    return "".join(partes)


def _cabeza_calavera(pose) -> str:
    ojos_grandes = pose == "sorpresa"
    pupila = 5 if ojos_grandes else 7
    mirada = 4 if pose in ("senala", "explica") else 0
    boca = ('<ellipse cx="0" cy="-308" rx="8" ry="10" fill="#4a2c1a"/>' if ojos_grandes else
            f'<path d="M-16,-310 Q0,-302 16,-310" fill="none" stroke="{TINTA}" stroke-width="4" stroke-linecap="round"/>')
    return (f'<rect x="-30" y="-330" width="60" height="40" rx="16" fill="{HUESO}" stroke="{TINTA}" stroke-width="6"/>'
            f'<ellipse cx="0" cy="-366" rx="54" ry="52" fill="{HUESO}" stroke="{TINTA}" stroke-width="6"/>'
            f'<rect x="-27" y="-330" width="54" height="20" fill="{HUESO}"/>'
            + "".join(f'<line x1="{x}" y1="-300" x2="{x}" y2="-292" stroke="{TINTA}" stroke-width="3"/>'
                      for x in (-14, -5, 5, 14))
            + "".join(f'<circle cx="{lado * 20}" cy="-368" r="{18 if ojos_grandes else 16}" fill="white" '
                      f'stroke="{TINTA}" stroke-width="4"/>'
                      f'<circle cx="{lado * 20 + mirada}" cy="-367" r="{pupila}" fill="#4a2c1a"/>'
                      for lado in (-1, 1))
            + f'<path d="M0,-342 L-7,-332 Q0,-328 7,-332 Z" fill="{TINTA}"/>' + boca)


def _sombrero(tipo, color_s) -> str:
    if tipo == "corona":
        return (f'<path d="M-40,-404 L-44,-446 L-22,-424 L0,-456 L22,-424 L44,-446 L40,-404 Z" '
                f'fill="{COLORES["dorado"]}" stroke="{TINTA}" stroke-width="5" stroke-linejoin="round"/>'
                f'<circle cx="0" cy="-424" r="6" fill="{COLORES["rojo"]}" stroke="{TINTA}" stroke-width="2"/>')
    if tipo == "gorra_militar":
        c = color_s or COLORES["caqui"]
        return (f'<path d="M-44,-404 Q-48,-446 0,-450 Q48,-446 44,-404 Z" fill="{c}" stroke="{TINTA}" stroke-width="5"/>'
                f'<rect x="-46" y="-414" width="92" height="16" fill="{c}" stroke="{TINTA}" stroke-width="5"/>'
                f'<path d="M-36,-398 Q0,-382 46,-398" fill="{TINTA}" stroke="{TINTA}" stroke-width="5"/>'
                f'<circle cx="0" cy="-428" r="6" fill="{COLORES["dorado"]}" stroke="{TINTA}" stroke-width="2"/>')
    if tipo == "casco":
        c = color_s or COLORES["caqui"]
        return (f'<path d="M-56,-392 Q-54,-462 0,-464 Q54,-462 56,-392 Z" fill="{c}" stroke="{TINTA}" stroke-width="5"/>'
                f'<line x1="-62" y1="-392" x2="62" y2="-392" stroke="{TINTA}" stroke-width="7" stroke-linecap="round"/>')
    if tipo == "boina":
        c = color_s or COLORES["negro"]
        return (f'<ellipse cx="4" cy="-418" rx="54" ry="20" fill="{c}" stroke="{TINTA}" stroke-width="5"/>'
                f'<line x1="4" y1="-438" x2="6" y2="-448" stroke="{TINTA}" stroke-width="5"/>')
    if tipo == "chistera":
        c = color_s or COLORES["negro"]
        return (f'<rect x="-34" y="-490" width="68" height="80" fill="{c}" stroke="{TINTA}" stroke-width="5"/>'
                f'<rect x="-34" y="-428" width="68" height="12" fill="{COLORES["granate"]}"/>'
                f'<line x1="-58" y1="-410" x2="58" y2="-410" stroke="{TINTA}" stroke-width="9" stroke-linecap="round"/>')
    if tipo == "sombrero":
        c = color_s or COLORES["marron"]
        return (f'<ellipse cx="0" cy="-408" rx="74" ry="14" fill="{c}" stroke="{TINTA}" stroke-width="5"/>'
                f'<path d="M-38,-410 Q-36,-456 0,-458 Q36,-456 38,-410 Z" fill="{c}" stroke="{TINTA}" stroke-width="5"/>')
    if tipo == "mitra":
        return (f'<path d="M-36,-406 Q-34,-460 0,-480 Q34,-460 36,-406 Z" fill="white" stroke="{TINTA}" stroke-width="5"/>'
                f'<line x1="0" y1="-478" x2="0" y2="-406" stroke="{COLORES["dorado"]}" stroke-width="8"/>')
    return ""


def _cabeza_persona(aspecto: dict, pose) -> str:
    piel = aspecto.get("piel") or PIEL
    pelo_color = color(aspecto.get("color_pelo") or "negro", "negro")
    pelo = normalizar(aspecto.get("pelo") or "corto")
    sorpresa = pose == "sorpresa"
    partes = []
    if pelo == "largo":
        partes.append(f'<path d="M-50,-370 Q-60,-300 -50,-286 L50,-286 Q60,-300 50,-370 Z" fill="{pelo_color}" '
                      f'stroke="{TINTA}" stroke-width="5"/>')
    partes.append(f'<circle cx="0" cy="-358" r="50" fill="{piel}" stroke="{TINTA}" stroke-width="6"/>')
    if pelo in ("corto", "largo", "canoso", "rizado"):
        c = COLORES["gris"] if pelo == "canoso" else pelo_color
        partes.append(f'<path d="M-50,-360 Q-52,-414 0,-412 Q52,-414 50,-360 Q30,-392 -50,-360 Z" fill="{c}" '
                      f'stroke="{TINTA}" stroke-width="5"/>')
    elif pelo == "calvo":
        partes.append(f'<path d="M-48,-350 Q-52,-372 -44,-380" fill="none" stroke="{COLORES["gris"]}" stroke-width="8"/>'
                      f'<path d="M48,-350 Q52,-372 44,-380" fill="none" stroke="{COLORES["gris"]}" stroke-width="8"/>')
    for lado in (-1, 1):
        partes.append(f'<circle cx="{lado * 18}" cy="-362" r="{8 if sorpresa else 6}" fill="{TINTA}"/>')
    if aspecto.get("gafas"):
        partes.append(''.join(f'<circle cx="{lado * 19}" cy="-362" r="15" fill="none" stroke="{TINTA}" stroke-width="4"/>'
                              for lado in (-1, 1)) + f'<line x1="-4" y1="-362" x2="4" y2="-362" stroke="{TINTA}" '
                      'stroke-width="4"/>')
    partes.append(f'<path d="M0,-352 Q6,-340 0,-336" fill="none" stroke="{TINTA}" stroke-width="4"/>')
    if aspecto.get("barba"):
        c = COLORES["gris"] if pelo == "canoso" else pelo_color
        partes.append(f'<path d="M-46,-350 Q-40,-290 0,-284 Q40,-290 46,-350 Q30,-318 0,-318 Q-30,-318 -46,-350 Z" '
                      f'fill="{c}" stroke="{TINTA}" stroke-width="5"/>')
    if aspecto.get("bigote"):
        partes.append(f'<path d="M-22,-326 Q-10,-336 0,-328 Q10,-336 22,-326 Q10,-320 0,-324 Q-10,-320 -22,-326 Z" '
                      f'fill="{pelo_color if pelo != "canoso" else COLORES["gris"]}" stroke="{TINTA}" stroke-width="3"/>')
    boca = ('<ellipse cx="0" cy="-318" rx="7" ry="9" fill="#4a2c1a"/>' if sorpresa else
            f'<path d="M-12,-318 Q0,-310 12,-318" fill="none" stroke="{TINTA}" stroke-width="4" stroke-linecap="round"/>')
    if not aspecto.get("barba"):
        partes.append(boca)
    partes.append(_sombrero(normalizar(aspecto.get("sombrero") or ""), color(aspecto["color_sombrero"])
                            if aspecto.get("color_sombrero") else None))
    return "".join(partes)


def figura(x, y, alto, pose="neutro", aspecto=None, mirar="derecha") -> str:
    """Bonesy (sin `aspecto`) o un personaje sencillo, con los pies en (x, y) y `alto` píxeles de alto."""
    escala = alto / 470
    pose = ALIAS_POSES.get(normalizar(pose or ""), normalizar(pose or ""))
    pose = pose if pose in POSES else "neutro"
    (codo_i, muneca_i), (codo_d, muneca_d) = POSES[pose]
    if aspecto is None:  # Bonesy: calavera, sudadera roja, piernas de hueso, reloj verde
        manga = cuerpo_color = COLORES["rojo"]
        mano = HUESO
        piernas = _piernas(HUESO, hueso=True)
        cuerpo = _cuerpo(cuerpo_color, "sudadera")
        cabeza = _cabeza_calavera(pose)
        sensor = True
    else:
        ropa = normalizar(aspecto.get("ropa") or "traje")
        cuerpo_color = color(aspecto.get("color_ropa") or ("caqui" if ropa == "uniforme" else "gris"), "gris")
        manga = COLORES["negro"] if ropa == "sotana" else cuerpo_color
        mano = aspecto.get("piel") or PIEL
        piernas = (_zapatos() if ropa in ("vestido", "sotana") else
                   _piernas(COLORES["azul"] if ropa == "obrero" else COLORES["negro"]))
        cuerpo = _cuerpo(cuerpo_color, ropa if ropa in ("traje", "uniforme", "obrero", "vestido", "sotana") else "traje")
        cabeza = _cabeza_persona(aspecto, pose)
        sensor = False
    brazo_i = _brazo(HOMBROS[0], codo_i, muneca_i, manga, mano, sensor)
    brazo_d = _brazo(HOMBROS[1], codo_d, muneca_d, manga, mano)
    volteo = -1 if mirar == "izquierda" else 1
    return (f'<g transform="translate({x:.0f},{y:.0f}) scale({escala * volteo:.3f},{escala:.3f})" filter="url(#mano)">'
            f'{piernas}{brazo_i if pose != "brazos" else ""}{cuerpo}{cabeza}{brazo_d}'
            f'{brazo_i if pose == "brazos" else ""}</g>')


def alto_cabeza(alto) -> float:
    """Altura (desde los pies) de lo alto de la cabeza de una figura de `alto` píxeles."""
    return alto * 420 / 470


# ------------------------------------------------------------------ piezas

def bocadillo(x, y, ancho, contenido, cola=None, tam=46, fondo="white") -> str:
    """Bocadillo con esquina superior izquierda en (x, y); `cola` = punto al que apunta."""
    lineas = lineas_de(contenido, tam, ancho - 60)
    alto = lineas * tam * 1.15 + 50
    partes = []
    if cola:
        bx = min(max(cola[0], x + 60), x + ancho - 60)
        by = y + alto if cola[1] > y + alto else y
        partes.append(f'<path d="M{bx - 30:.0f},{by:.0f} L{cola[0]:.0f},{cola[1]:.0f} L{bx + 30:.0f},{by:.0f} Z" '
                      f'fill="{fondo}" stroke="{TINTA}" stroke-width="5" stroke-linejoin="round"/>')
    partes.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{ancho:.0f}" height="{alto:.0f}" rx="34" fill="{fondo}" '
                  f'stroke="{TINTA}" stroke-width="5"/>')
    if cola:  # tapa la unión de la cola con el borde
        bx = min(max(cola[0], x + 60), x + ancho - 60)
        by = y + alto if cola[1] > y + alto else y
        partes.append(f'<line x1="{bx - 25:.0f}" y1="{by:.0f}" x2="{bx + 25:.0f}" y2="{by:.0f}" stroke="{fondo}" '
                      f'stroke-width="8"/>')
    cuerpo = f'<g filter="url(#mano)">{"".join(partes)}</g>'
    return cuerpo + texto(x + ancho / 2, y + 25 + tam * 0.6, contenido, tam, ancho - 60)


def etiqueta(cx, cy, contenido, tam=40, fondo="white", tinta=TINTA) -> str:
    ancho = max(len(str(contenido)) * tam * 0.48 + 50, 120)
    return (f'<g filter="url(#mano)"><rect x="{cx - ancho / 2:.0f}" y="{cy - tam * 0.75:.0f}" width="{ancho:.0f}" '
            f'height="{tam * 1.5:.0f}" rx="{tam * 0.4:.0f}" fill="{fondo}" stroke="{TINTA}" stroke-width="4"/></g>'
            + texto(cx, cy + 2, contenido, tam, relleno=tinta))


def subrayado(x1, x2, y, c=None) -> str:
    c = c or COLORES["rojo"]
    medio = (x1 + x2) / 2
    return (f'<path d="M{x1:.0f},{y:.0f} Q{medio:.0f},{y + 14:.0f} {x2:.0f},{y - 4:.0f}" fill="none" stroke="{c}" '
            f'stroke-width="10" stroke-linecap="round" filter="url(#mano)"/>')


def flecha(x1, y1, x2, y2, c=None, grosor=10, curva=0.2) -> str:
    c = c or COLORES["rojo"]
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    cx, cy = mx - dy * curva, my + dx * curva
    angulo = math.atan2(y2 - cy, x2 - cx)
    punta = 30
    p1 = (x2 - punta * math.cos(angulo - 0.45), y2 - punta * math.sin(angulo - 0.45))
    p2 = (x2 - punta * math.cos(angulo + 0.45), y2 - punta * math.sin(angulo + 0.45))
    return (f'<g filter="url(#mano)"><path d="M{x1:.0f},{y1:.0f} Q{cx:.0f},{cy:.0f} {x2:.0f},{y2:.0f}" fill="none" '
            f'stroke="{TINTA}" stroke-width="{grosor + 6}" stroke-linecap="round"/>'
            f'<path d="M{x1:.0f},{y1:.0f} Q{cx:.0f},{cy:.0f} {x2:.0f},{y2:.0f}" fill="none" stroke="{c}" '
            f'stroke-width="{grosor}" stroke-linecap="round"/>'
            f'<path d="M{p1[0]:.0f},{p1[1]:.0f} L{x2:.0f},{y2:.0f} L{p2[0]:.0f},{p2[1]:.0f} Z" fill="{c}" '
            f'stroke="{TINTA}" stroke-width="5" stroke-linejoin="round"/></g>')


# ------------------------------------------------------------------ mapas

ZONAS = {  # lon min, lon max, lat min, lat max
    "espana": (-9.6, 4.6, 34.7, 44.0),
    "europa": (-12, 42, 34, 64),
    "mundo": (-170, 190, -56, 80),
    "america": (-125, -32, -56, 50),
    "africa": (-20, 55, -36, 38),
    "asia": (25, 150, -10, 60),
    "mediterraneo": (-10, 37, 29, 47),
}
CANARIAS = ("Las Palmas", "Santa Cruz de Tenerife")
LIMITES_CANARIAS = (-18.3, -13.3, 27.5, 29.5)


def _en_canarias(lon, lat) -> bool:
    return -18.6 <= lon <= -13.0 and 27.3 <= lat <= 29.7


@lru_cache(maxsize=None)
def _mapa(nombre: str) -> list:
    return json.loads((DATOS / "mapas" / f"{nombre}.json").read_text(encoding="utf-8"))


def _proyeccion(caja, limites):
    """Equirectangular con corrección de latitud, encajada y centrada en caja = (x, y, ancho, alto)."""
    lon0, lon1, lat0, lat1 = limites
    k_lat = math.cos(math.radians((lat0 + lat1) / 2))
    ancho_geo, alto_geo = (lon1 - lon0) * k_lat, lat1 - lat0
    escala = min(caja[2] / ancho_geo, caja[3] / alto_geo)
    ox = caja[0] + (caja[2] - ancho_geo * escala) / 2
    oy = caja[1] + (caja[3] - alto_geo * escala) / 2

    def proyectar(lon, lat):
        return ox + (lon - lon0) * k_lat * escala, oy + (lat1 - lat) * escala
    return proyectar


def _ruta(anillos, proyectar) -> str:
    trozos = []
    for anillo in anillos:
        puntos = [proyectar(lon, lat) for lon, lat in anillo]
        trozos.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in puntos) + " Z")
    return " ".join(trozos)


def _indice_lugares(zona):
    """{nombre normalizado: [regiones]} con provincias, comunidades y países."""
    indice = {}
    regiones = []
    if zona == "espana":
        for p in _mapa("espana"):
            regiones.append(("prov", p))
            for n in [*p["alias"], p["comunidad"]]:
                indice.setdefault(normalizar(n), []).append(p["nombre"])
            indice.setdefault("espana", []).append(p["nombre"])
    for p in _mapa("mundo"):
        regiones.append(("pais", p))
        for n in p["alias"]:
            indice.setdefault(normalizar(n), []).append(p["nombre"])
    sinonimos = {"cataluna": "cataluna", "valencia": "comunidad valenciana", "pais valenciano": "comunidad valenciana",
                 "vascongadas": "pais vasco", "euskadi": "pais vasco", "baleares": "islas baleares",
                 "madrid": "madrid", "murcia": "region de murcia", "estados unidos": "estados unidos",
                 "eeuu": "estados unidos", "ee. uu.": "estados unidos", "urss": "rusia", "union sovietica": "rusia",
                 "reino unido": "reino unido", "inglaterra": "reino unido", "gran bretana": "reino unido",
                 "alemania nazi": "alemania", "italia fascista": "italia"}
    for alias, destino in sinonimos.items():
        if destino in indice and alias not in indice:
            indice[alias] = indice[destino]
    sovieticas = [p for n in ("rusia", "ucrania", "bielorrusia", "georgia", "armenia", "azerbaiyan", "kazajistan",
                              "uzbekistan", "turkmenistan", "kirguistan", "tayikistan") for p in indice.get(n, [])]
    for alias in ("urss", "union sovietica", "union de republicas socialistas sovieticas"):
        indice[alias] = sovieticas
    return indice, regiones


def _centroide(anillos):
    mayor = max(anillos, key=len)
    xs = [p[0] for p in mayor]; ys = [p[1] for p in mayor]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _coordenadas(lugar, zona):
    """(lon, lat) de un punto: dado a mano o el centro de la provincia/país con ese nombre."""
    if isinstance(lugar, dict) and lugar.get("lat") is not None and lugar.get("lon") is not None:
        try:
            return float(lugar["lon"]), float(lugar["lat"])
        except (TypeError, ValueError):
            pass
    nombre = normalizar(lugar.get("lugar") if isinstance(lugar, dict) else lugar)
    for fuente in (["espana"] if zona == "espana" else []) + ["mundo"]:
        for p in _mapa(fuente):
            if nombre in {normalizar(a) for a in p["alias"]}:
                return _centroide(p["anillos"])
    return None


def mapa(visual: dict, caja) -> tuple:
    """(capa base, [capas por paso], leyenda) de un mapa dentro de caja = (x, y, ancho, alto).

    En el mapa de España, Canarias va en un recuadro abajo a la izquierda, como en los mapas de siempre.
    """
    zona = normalizar(visual.get("zona") or "espana").replace(" ", "")
    zona = {"peninsula": "espana", "peninsulaiberica": "espana", "europe": "europa", "world": "mundo"}.get(zona, zona)
    if zona not in ZONAS:
        zona = "espana"
    limites = ZONAS[zona]
    proyectar = _proyeccion(caja, limites)
    indice, regiones = _indice_lugares(zona)
    lon0, lon1, lat0, lat1 = limites
    recuadro = proyectar_canarias = None
    if zona == "espana":
        recuadro = (caja[0] + 16, caja[1] + caja[3] - 186, 300, 170)
        proyectar_canarias = _proyeccion((recuadro[0] + 12, recuadro[1] + 30, recuadro[2] - 24, recuadro[3] - 40),
                                         LIMITES_CANARIAS)

    def situar(lon, lat):
        if recuadro and _en_canarias(lon, lat):
            return proyectar_canarias(lon, lat)
        return proyectar(lon, lat)

    def visible(anillos):
        return any(lon0 - 5 < lon < lon1 + 5 and lat0 - 5 < lat < lat1 + 5 for anillo in anillos for lon, lat in anillo[::5])

    colores_region = {}
    pasos = []
    leyenda = []
    for grupo in (visual.get("resaltar") or [])[:4]:
        c = color(grupo.get("color"), "rojo")
        nuevos = []
        for lugar in grupo.get("lugares") or []:
            for region in indice.get(normalizar(lugar), []):
                if region not in colores_region:
                    colores_region[region] = c
                    nuevos.append(region)
        if nuevos:
            pasos.append((nuevos, c))
            leyenda.append((grupo.get("etiqueta") or "", c))

    def dibujar_regiones(color_de, en_recuadro=False):
        """Las regiones del mapa grande o, con `en_recuadro`, solo las de Canarias en su recuadro."""
        trozos = []
        for clase, r in regiones:
            if zona == "espana":
                if clase == "pais" and r["nombre"] == "España":
                    continue  # en el mapa de España se dibujan las provincias
                if (clase == "prov" and r["nombre"] in CANARIAS) != en_recuadro:
                    continue
            elif en_recuadro:
                continue
            if not en_recuadro and not visible(r["anillos"]):
                continue
            c = color_de(r["nombre"], clase)
            if c is None:
                continue
            grosor = 1.6 if clase == "prov" else 2.2
            ruta = _ruta(r["anillos"], proyectar_canarias if en_recuadro else proyectar)
            trozos.append(f'<path d="{ruta}" fill="{c}" stroke="{TINTA}" stroke-width="{grosor}" stroke-linejoin="round"/>')
        return "".join(trozos)

    vecino = "#e7e0cf"
    tierra = "#f6e7c1"
    mar = "#dcebf2"
    fondo = dibujar_regiones(lambda n, clase: tierra if clase == "prov" else vecino)
    if recuadro:
        x, y, ancho, alto = recuadro
        fondo += (f'<rect x="{x}" y="{y}" width="{ancho}" height="{alto}" rx="14" fill="{mar}" stroke="{TINTA}" '
                  f'stroke-width="4"/>' + dibujar_regiones(lambda n, clase: tierra, en_recuadro=True))
    recorte = (f'<clipPath id="recorte"><rect x="{caja[0]}" y="{caja[1]}" width="{caja[2]}" height="{caja[3]}" '
               f'rx="24"/></clipPath>')
    base = (f'<defs>{recorte}</defs><g filter="url(#mano)"><rect x="{caja[0]}" y="{caja[1]}" width="{caja[2]}" '
            f'height="{caja[3]}" rx="24" fill="{mar}" stroke="{TINTA}" stroke-width="5"/>'
            f'<g clip-path="url(#recorte)">{fondo}</g></g>')
    if recuadro:
        base += texto(recuadro[0] + 16, recuadro[1] + 20, "Canarias", 28, ancla="start", relleno="#5b554e")

    capas = []
    for regiones_paso, c in pasos:
        elegidas = set(regiones_paso)

        def color_de(n, clase, elegidas=elegidas, c=c):
            return c if n in elegidas and (zona != "espana" or clase == "prov") else None
        capa = dibujar_regiones(color_de)
        if recuadro:
            capa += dibujar_regiones(color_de, en_recuadro=True)
        capas.append(f'<g filter="url(#mano)" clip-path="url(#recorte)">{capa}</g>')
    # puntos y flechas, en un último paso
    extra = []
    for f in (visual.get("flechas") or [])[:4]:
        a, b = _coordenadas(f.get("desde"), zona), _coordenadas(f.get("hasta"), zona)
        if a and b:
            (x1, y1), (x2, y2) = situar(*a), situar(*b)
            extra.append(flecha(x1, y1, x2, y2, color(f.get("color"), "rojo")))
    for p in (visual.get("puntos") or [])[:5]:
        coord = _coordenadas(p, zona)
        if not coord:
            continue
        px, py = situar(*coord)
        extra.append(f'<g filter="url(#mano)"><circle cx="{px:.0f}" cy="{py:.0f}" r="14" fill="{COLORES["rojo"]}" '
                     f'stroke="{TINTA}" stroke-width="5"/></g>')
        nombre = p.get("texto") or p.get("lugar") or ""
        if nombre:
            lado = -1 if px > caja[0] + caja[2] * 0.75 else 1
            arriba = py - 36 > caja[1] + 50  # pegado al borde de arriba: la etiqueta va debajo del punto
            extra.append(etiqueta(px + lado * (len(nombre) * 16 + 50), py - 36 if arriba else py + 40, nombre, 38))
    if extra:
        capas.append("".join(extra))
    return base, capas, leyenda


# ------------------------------------------------------------------ escenas

ZONA_CONTENIDO = (520, 1880)  # x de la parte derecha (a la izquierda está Bonesy)


def _narrador(pose="explica", alto=520, x=250, y=1040, mirar="derecha"):
    return figura(x, y, alto, pose, None, mirar)


def _calendario(cx, cy, dia, mes, anio) -> str:
    ancho, alto = 400, 440
    x, y = cx - ancho / 2, cy - alto / 2
    partes = [f'<rect x="{x:.0f}" y="{y:.0f}" width="{ancho}" height="{alto}" rx="26" fill="white" stroke="{TINTA}" stroke-width="6"/>',
              f'<path d="M{x:.0f},{y + 26:.0f} Q{x:.0f},{y:.0f} {x + 26:.0f},{y:.0f} L{x + ancho - 26:.0f},{y:.0f} '
              f'Q{x + ancho:.0f},{y:.0f} {x + ancho:.0f},{y + 26:.0f} L{x + ancho:.0f},{y + 110:.0f} L{x:.0f},{y + 110:.0f} Z" '
              f'fill="{COLORES["rojo"]}" stroke="{TINTA}" stroke-width="6"/>']
    partes += [f'<rect x="{x + d:.0f}" y="{y - 26:.0f}" width="18" height="52" rx="9" fill="{COLORES["gris"]}" '
               f'stroke="{TINTA}" stroke-width="4"/>' for d in (90, ancho - 108)]
    cuerpo = f'<g filter="url(#mano)">{"".join(partes)}</g>'
    textos = texto(cx, y + 58, (mes or "").upper() or "AÑO", 52, fuente="titulo", relleno="white")
    if dia:
        textos += texto(cx, y + 230, dia, 170, fuente="titulo")
        textos += texto(cx, y + 370, anio, 72, fuente="titulo", relleno=COLORES["rojo"])
    else:
        textos += texto(cx, y + 270, anio, 150, fuente="titulo")
    return cuerpo + textos


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


def _partes_fecha(fecha: str):
    fecha = str(fecha or "")
    anio = re.search(r"(\d{3,4})(?!.*\d{3,4})", fecha)
    mes = next((m for m in MESES if m in normalizar(fecha)), "")
    dia = re.match(r"\s*(\d{1,2})\b", fecha)
    return (dia.group(1) if dia and mes else ""), mes, (anio.group(1) if anio else fecha)


def escena(visual: dict, capitulo: str = "") -> list:
    """Lista de pasos; cada paso es la lista de capas SVG que se ven. También [(clave, paso)] para sincronizar."""
    tipo = normalizar(visual.get("tipo") or "narrador")
    pose = visual.get("pose") or None
    base, pasos, claves = [], [], []
    x0, x1 = ZONA_CONTENIDO
    centro = (x0 + x1) / 2
    if capitulo and tipo != "titulo":
        base.append(etiqueta(60 + len(capitulo) * 9.6 + 25, 62, capitulo, 34, fondo="#fff3c4"))

    if tipo == "titulo":
        base.append(_narrador(pose or "saluda", 600, 300))
        numero = visual.get("numero") or ""
        if numero:
            base.append(texto(centro + 60, 330, f"CAPÍTULO {numero}", 56, fuente="titulo", relleno=COLORES["rojo"]))
        n = lineas_de(visual.get("texto"), 120, 1200, "titulo")
        base.append(texto(centro + 60, 540 - (n - 1) * 60, visual.get("texto"), 120, 1200, "titulo", max_lineas=3))
        base.append(subrayado(centro - 380, centro + 500, 560 + n * 70))
        iconos = iconos_validos(visual.get("iconos"))[:1]
        if iconos:
            pasos.append([icono(iconos[0], centro + 60, 870, 190)])
    elif tipo == "fecha":
        base.append(_narrador(pose or "senala"))
        dia, mes, anio = _partes_fecha(visual.get("fecha"))
        base.append(_calendario(830, 540, dia, mes, anio))
        if visual.get("texto"):
            pasos.append([texto(1460, 540, visual["texto"], 64, 680, centrar_vertical=True, max_lineas=5)])
            claves.append(visual["texto"])
    elif tipo == "cifra":
        base.append(_narrador(pose or "sorpresa"))
        numero = str(visual.get("numero") or "")
        tam = 230 if len(numero) <= 7 else 170
        base.append(texto(centro, 330, numero, tam, fuente="titulo", relleno=COLORES["rojo"]))
        base.append(texto(centro, 520, visual.get("texto"), 64, 1250, max_lineas=2))
        iconos = iconos_validos(visual.get("iconos"))
        if iconos:
            cuantos = max(1, min(int(visual.get("repetir") or 8), 12))
            tam_i = 110
            total = cuantos * (tam_i + 16)
            capa = "".join(icono(iconos[i % len(iconos)], centro - total / 2 + tam_i / 2 + i * (tam_i + 16), 760, tam_i)
                           for i in range(cuantos))
            pasos.append([capa])
    elif tipo == "mapa":
        base.append(_narrador(pose or "senala", 480, 230))
        caja = (500, 110, 1380, 900)
        fondo, capas, leyenda = mapa(visual, caja)
        base.append(fondo)
        for i, capa in enumerate(capas):
            extra = [capa]
            if i < len(leyenda) and leyenda[i][0]:
                nombre, c = leyenda[i]
                ly = 200 + i * 100
                extra.append(f'<g filter="url(#mano)"><rect x="36" y="{ly - 28}" width="56" height="56" rx="12" '
                             f'fill="{c}" stroke="{TINTA}" stroke-width="5"/></g>'
                             + texto(108, ly, nombre, 40, 370, ancla="start", max_lineas=2, centrar_vertical=True))
                claves.append(nombre)
            else:
                claves.append((visual.get("puntos") or [{}])[0].get("texto") or "")
            pasos.append(extra)
        if visual.get("titulo"):
            base.append(etiqueta(caja[0] + caja[2] / 2, 70, visual["titulo"], 46))
    elif tipo == "personajes":
        personas = (visual.get("personas") or [])[:3]
        hay_narrador = len(personas) < 3
        if hay_narrador:
            base.append(_narrador(pose or "explica", 460, 220))
        inicio = x0 + 40 if hay_narrador else 260
        hueco = (x1 - inicio) / max(len(personas), 1)
        alto = 560
        for i, p in enumerate(personas):
            px = inicio + hueco * (i + 0.5)
            capa = [figura(px, 900, alto, p.get("pose") or ("explica" if i == 0 else "neutro"), p.get("aspecto") or {},
                           "izquierda" if px > centro + 200 else "derecha")]
            capa.append(etiqueta(px, 960, p.get("nombre") or "", 44))
            if p.get("rol"):
                capa.append(texto(px, 1025, p["rol"], 36, relleno="#5b554e"))
            pasos.append(capa)
            claves.append((p.get("nombre") or "").split()[-1] if p.get("nombre") else "")
        if visual.get("bocadillo") and personas:
            habla = min(int(visual.get("habla") or 0), len(personas) - 1)
            px = inicio + hueco * (habla + 0.5)
            ancho = 640
            bx = min(max(px - ancho / 2, 40), ANCHO - ancho - 40)
            cabeza = 900 - alto_cabeza(alto)
            by = max(110, cabeza - 70 - (lineas_de(visual["bocadillo"], 42, ancho - 60) * 42 * 1.15 + 50))
            pasos.append([bocadillo(bx, by, ancho, visual["bocadillo"], (px, cabeza - 15), 42)])
            claves.append("")
    elif tipo == "iconos":
        base.append(_narrador(pose or "explica"))
        elementos = [e for e in (visual.get("elementos") or []) if svg_emoji(e.get("icono", ""))][:3]
        if visual.get("texto"):
            base.append(texto(centro, 170, visual["texto"], 70, 1250, "titulo", max_lineas=2))
        hueco = (x1 - x0) / max(len(elementos), 1)
        for i, e in enumerate(elementos):
            ex = x0 + hueco * (i + 0.5)
            capa = [icono(e["icono"], ex, 540, 300 if len(elementos) < 3 else 260)]
            if e.get("texto"):
                capa.append(texto(ex, 790, e["texto"], 52, hueco - 40, max_lineas=3))
            pasos.append(capa)
            claves.append(e.get("texto") or "")
    elif tipo == "linea":
        base.append(_narrador(pose or "senala", 460, 220))
        hitos = (visual.get("hitos") or [])[:5]
        y = 560
        base.append(f'<g filter="url(#mano)"><line x1="{x0 - 20}" y1="{y}" x2="{x1 - 10}" y2="{y}" stroke="{TINTA}" '
                    f'stroke-width="12" stroke-linecap="round"/><path d="M{x1 - 40},{y - 26} L{x1 + 10},{y} '
                    f'L{x1 - 40},{y + 26}" fill="none" stroke="{TINTA}" stroke-width="12" stroke-linecap="round" '
                    f'stroke-linejoin="round"/></g>')
        hueco = (x1 - x0 - 60) / max(len(hitos), 1)
        actual = visual.get("actual")
        for i, h in enumerate(hitos):
            hx = x0 + hueco * (i + 0.5)
            destacado = actual is not None and str(actual) == str(i)
            c = COLORES["rojo"] if destacado else COLORES["amarillo"]
            arriba = i % 2 == 0  # alternos arriba y abajo de la línea para que quepan
            signo = -1 if arriba else 1
            capa = [f'<g filter="url(#mano)"><circle cx="{hx:.0f}" cy="{y}" r="{30 if destacado else 22}" fill="{c}" '
                    f'stroke="{TINTA}" stroke-width="6"/></g>',
                    texto(hx, y + signo * 80, h.get("fecha"), 64, fuente="titulo",
                          relleno=COLORES["rojo"] if destacado else TINTA)]
            lineas = lineas_de(h.get("texto"), 40, hueco + 60)
            capa.append(texto(hx, y + signo * 160 - (lineas - 1) * 46 * (arriba), h.get("texto"), 40, hueco + 60,
                              max_lineas=3))
            if h.get("icono") and svg_emoji(h["icono"]):
                capa.append(icono(h["icono"], hx, y + signo * (250 + lineas * 46), 120))
            pasos.append(capa)
            claves.append(str(h.get("fecha") or ""))
    elif tipo == "comparacion":
        base.append(_narrador(pose or "piensa", 440, 210))
        lados = [visual.get("izquierda") or {}, visual.get("derecha") or {}]
        anchos = ((480, 1140), (1220, 1880))
        for (ax, bx), lado in zip(anchos, lados):
            c = color(lado.get("color"), "azul")
            medio = (ax + bx) / 2
            capa = [f'<g filter="url(#mano)"><rect x="{ax}" y="120" width="{bx - ax}" height="860" rx="30" fill="white" '
                    f'stroke="{TINTA}" stroke-width="6"/><path d="M{ax},150 Q{ax},120 {ax + 30},120 L{bx - 30},120 '
                    f'Q{bx},120 {bx},150 L{bx},240 L{ax},240 Z" fill="{c}" stroke="{TINTA}" stroke-width="6"/></g>',
                    texto(medio, 182, lado.get("titulo"), 58, bx - ax - 40, "titulo", relleno="white", max_lineas=1)]
            iconos = iconos_validos(lado.get("iconos"))[:3]
            for j, e in enumerate(iconos):
                capa.append(icono(e, medio + (j - (len(iconos) - 1) / 2) * 170, 370, 150))
            yy = 530
            for punto in (lado.get("puntos") or [])[:3]:
                capa.append(f'<circle cx="{ax + 50}" cy="{yy}" r="11" fill="{c}"/>')
                capa.append(texto(ax + 80, yy, punto, 48, bx - ax - 110, ancla="start", max_lineas=3))
                yy += 48 * 1.15 * lineas_de(punto, 48, bx - ax - 110) + 50
            pasos.append(capa)
            claves.append(lado.get("titulo") or "")
        pasos[-1].append(f'<g filter="url(#mano)"><circle cx="1180" cy="560" r="62" fill="{COLORES["amarillo"]}" '
                         f'stroke="{TINTA}" stroke-width="6"/></g>' + texto(1180, 566, "VS", 64, fuente="titulo"))
    else:  # narrador
        base.append(_narrador(pose or "explica", 720, 420))
        frase = visual.get("bocadillo") or visual.get("texto") or ""
        if frase:
            base.append(bocadillo(760, 120, 1060, frase, (560, 380), 58))
        iconos = iconos_validos(visual.get("iconos"))[:3]
        if iconos:
            capa = "".join(icono(e, 1290 + (j - (len(iconos) - 1) / 2) * 260, 790, 220) for j, e in enumerate(iconos))
            pasos.append([capa])
            claves.append("")
    claves = (claves + [""] * len(pasos))[:len(pasos)]
    resultado = [base]
    for capa in pasos:
        resultado.append(resultado[-1] + capa)
    return resultado, claves


def miniatura(frase: str, iconos=None, mapa_visual=None) -> list:
    """Capas de la miniatura (se dibuja en 1920×1080 y se captura a 1280×720): frase enorme, Bonesy y un dibujo."""
    capas = []
    if mapa_visual:
        fondo, pasos, _ = mapa(mapa_visual, (980, 60, 900, 960))
        capas += [fondo, *pasos]
    else:
        lista = iconos_validos(iconos)[:2]
        for j, e in enumerate(lista):
            capas.append(icono(e, 1450 + (j - (len(lista) - 1) / 2) * 330, 560, 380))
    capas.append(figura(1680 if mapa_visual else 1700, 1060, 640, "sorpresa", None, "izquierda"))
    lineas = partir(frase.upper(), 11, 3)
    tam = 190 if len(lineas) <= 2 else 160
    y = 540 - (len(lineas) - 1) * tam * 0.55
    for i, linea in enumerate(lineas):
        relleno = COLORES["rojo"] if i == len(lineas) - 1 else TINTA
        capas.append(f'<text x="70" y="{y + i * tam * 1.08:.0f}" font-family="Lilita" font-size="{tam}" fill="{relleno}" '
                     f'stroke="white" stroke-width="22" paint-order="stroke" stroke-linejoin="round" '
                     f'dominant-baseline="middle">{esc(linea)}</text>')
    return capas


# ------------------------------------------------------------------ HTML y renderizado

@lru_cache(maxsize=None)
def _fuente_base64(nombre: str) -> str:
    return base64.b64encode((DATOS / "fuentes" / nombre).read_bytes()).decode()


def documento(capas: list, ancho=ANCHO, alto=ALTO, semilla=3) -> str:
    """HTML con el SVG de la escena (fuentes incrustadas: no depende de nada externo)."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Mano; src: url(data:font/ttf;base64,{_fuente_base64("PatrickHand-Regular.ttf")}); }}
@font-face {{ font-family: Lilita; src: url(data:font/ttf;base64,{_fuente_base64("LilitaOne-Regular.ttf")}); }}
html, body {{ margin: 0; padding: 0; overflow: hidden; background: {PAPEL}; }}
</style></head><body>
<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" viewBox="0 0 {ANCHO} {ALTO}">
<defs>
  <filter id="mano" x="-5%" y="-5%" width="110%" height="110%">
    <feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="2" seed="{semilla}" result="ruido"/>
    <feDisplacementMap in="SourceGraphic" in2="ruido" scale="5"/>
  </filter>
  <filter id="papel"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="7"/>
    <feColorMatrix values="0 0 0 0 0.45  0 0 0 0 0.38  0 0 0 0 0.28  0 0 0 0.06 0"/></filter>
  <pattern id="grano" width="320" height="320" patternUnits="userSpaceOnUse">
    <rect width="320" height="320" filter="url(#papel)"/></pattern>
</defs>
<rect width="{ANCHO}" height="{ALTO}" fill="{PAPEL}"/>
<rect width="{ANCHO}" height="{ALTO}" fill="url(#grano)"/>
{"".join(capas)}
</svg></body></html>"""


def renderizar(trabajos: list, hilos: int = 4, progreso=None) -> None:
    """trabajos = [(html, ruta_png, ancho, alto)]: hace las capturas con Edge sin ventana.

    `progreso(hechas, total)`, si se da, se llama tras cada imagen.

    Con Playwright abre Edge una sola vez para todas (unas décimas por imagen); sin él, abre un Edge por imagen
    (varios segundos cada una).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _renderizar_abriendo_edge(trabajos, hilos, progreso)
        return
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="msedge", headless=True)
        try:
            pagina = navegador.new_page(device_scale_factor=1)
            for hechas, (contenido, destino, ancho, alto) in enumerate(trabajos, start=1):
                destino = Path(destino)
                destino.parent.mkdir(parents=True, exist_ok=True)
                pagina.set_viewport_size({"width": ancho, "height": alto})
                pagina.set_content(contenido, wait_until="load")
                pagina.evaluate("document.fonts.ready.then(() => true)")
                pagina.screenshot(path=str(destino), type="png")
                if progreso:
                    progreso(hechas, len(trabajos))
        finally:
            navegador.close()


def _renderizar_abriendo_edge(trabajos: list, hilos: int, progreso=None) -> None:
    carpeta = Path(tempfile.mkdtemp(prefix="dibujos_"))
    cuenta = {"hechas": 0}
    cerrojo = threading.Lock()

    def uno(indice_trabajo):
        indice, (contenido, destino, ancho, alto) = indice_trabajo
        pagina = carpeta / f"escena_{indice}.html"
        pagina.write_text(contenido, encoding="utf-8")
        perfil = carpeta / f"perfil_{indice % hilos}"
        destino = Path(destino).resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(3):
            subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
                            "--force-device-scale-factor=1", f"--window-size={ancho},{alto}",
                            "--virtual-time-budget=1500", f"--user-data-dir={perfil}",
                            f"--screenshot={destino}", pagina.resolve().as_uri()],
                           capture_output=True, timeout=120)
            if destino.exists() and destino.stat().st_size > 1000:
                if progreso:
                    with cerrojo:
                        cuenta["hechas"] += 1
                        progreso(cuenta["hechas"], len(trabajos))
                return
        raise RuntimeError(f"Edge no ha podido dibujar {destino.name}")

    # Un perfil por hilo: dos Edge a la vez no pueden compartir perfil.
    grupos = [[(i, t) for i, t in enumerate(trabajos) if i % hilos == h] for h in range(hilos)]
    with ThreadPoolExecutor(hilos) as pool:
        list(pool.map(lambda grupo: [uno(t) for t in grupo], grupos))
