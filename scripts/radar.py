"""Radar de actualidad: encuentra la noticia de la que más se habla hoy en España.

Junta dos señales:
  - Tendencias de Google en España (su canal RSS público): lo que más se busca ahora, con su tráfico aproximado
    y los titulares de los medios que lo cuentan.
  - Bing Noticias (canal RSS) con unas cuantas búsquedas fijas de política y sociedad, para las polémicas que
    no llegan a tendencia pero sí copan las portadas.
Con eso, el modelo (Groq) ordena las candidatas: polémicas de política, sucesos y sociedad, contadas por varios
medios a la vez, y descarta lo que no sirve (deportes, famosos, crímenes con particulares señalados…) y lo que
el canal ya ha contado estos días.

Uso:
    python scripts/radar.py              # muestra las candidatas de ahora, sin crear nada
"""
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent  # carpeta principal (este archivo está en scripts/)
load_dotenv(RAIZ / ".env")

URL_TENDENCIAS = "https://trends.google.com/trending/rss?geo=ES"
URL_BING = "https://www.bing.com/news/search"
AGENTE = "Mozilla/5.0 MenteInquieta67/2.0 (+https://github.com/luukthegoat/pipeline-curiosidades)"
# Búsquedas fijas en Bing Noticias: cubren lo que se discute aunque no sea lo más buscado.
BUSQUEDAS_FIJAS = ["Gobierno España polémica", "Congreso", "PP PSOE Vox", "disturbios", "sucesos España",
                   "Sánchez", "Feijóo", "Abascal", "okupas", "inmigración España"]
HORAS_BING = 24  # titulares de Bing más viejos que esto no cuentan

PROMPT_RADAR = """Eres el editor de un canal de YouTube Shorts de actualidad en España. Tu trabajo es elegir de
qué noticia hacer el vídeo de ahora: la que más se está comentando y discutiendo HOY.

Recibirás TENDENCIAS (lo más buscado en Google en España, con su tráfico aproximado y titulares) y TITULARES
recientes de prensa. Hoy es {hoy}.

Buenas candidatas (de más a menos):
- Polémicas políticas del día: lo que ha dicho o hecho un cargo público o un partido y está levantando reacciones.
- Sucesos y conflictos con mucha repercusión (disturbios, saqueos, protestas, apagones, huelgas).
- Debates de sociedad con dos posturas claras (vivienda, okupas, inmigración, impuestos, educación…).
- Internacional SOLO si afecta directamente a España o es lo más comentado del día aquí. Ante la duda, elige
  siempre la noticia española: es la que mejor funciona en el canal.

DESCARTA siempre:
- Deportes, famosos, prensa rosa, televisión, realities, influencers, series, loterías y el tiempo (salvo catástrofe).
- Crímenes o detenciones donde se señala a una persona particular (no cargo público), muertes de particulares,
  suicidios y cualquier noticia con menores implicados.
- Encuestas y sondeos electorales.
- Lo que contaste estos días (lista YA CONTADO), aunque haya novedades menores.
- Noticias que solo cuenta un medio: tiene que aparecer en titulares de varios medios distintos.
{veto}
Elige hasta 3 candidatas, la mejor primero. Para cada una escribe la búsqueda de prensa (3 a 7 palabras en español,
con los nombres propios clave, sin comillas ni fechas) que encuentre artículos de esa noticia concreta.

Responde SOLO con un objeto JSON:
{{"candidatas": [{{"busqueda": "...", "titular": "titular neutro de la noticia en una frase",
"categoria": "politica | sucesos | sociedad | economia | internacional",
"medios": numero de medios distintos que la cuentan en los datos, "motivo": "por qué engancha, en una frase"}}]}}
Si no hay ninguna buena, devuelve {{"candidatas": []}}."""


def _texto(item: str, etiqueta: str) -> str:
    encontrado = re.search(rf"<{etiqueta}>(.*?)</{etiqueta}>", item, re.S)
    return html.unescape(encontrado.group(1)).strip() if encontrado else ""


def tendencias() -> list:
    """[{"busqueda", "trafico", "titulares": [(medio, titular)]}] de Google Tendencias en España."""
    respuesta = requests.get(URL_TENDENCIAS, timeout=30, headers={"User-Agent": AGENTE})
    respuesta.raise_for_status()
    resultado = []
    for item in re.findall(r"<item>(.*?)</item>", respuesta.text, re.S):
        titulares = [(_texto(n, "ht:news_item_source"), _texto(n, "ht:news_item_title"))
                     for n in re.findall(r"<ht:news_item>(.*?)</ht:news_item>", item, re.S)]
        resultado.append({"busqueda": _texto(item, "title"), "trafico": _texto(item, "ht:approx_traffic"),
                          "titulares": titulares})
    return resultado


def titulares_bing(consultas=BUSQUEDAS_FIJAS) -> list:
    """[(medio, titular)] de las últimas HORAS_BING horas para cada búsqueda fija, sin repetidos."""
    limite = datetime.now(timezone.utc) - timedelta(hours=HORAS_BING)
    vistos, resultado = set(), []
    for consulta in consultas:
        try:
            respuesta = requests.get(URL_BING, timeout=30, headers={"User-Agent": AGENTE},
                                     params={"q": consulta, "format": "rss", "setlang": "es", "cc": "ES"})
            respuesta.raise_for_status()
        except requests.RequestException:
            continue  # una búsqueda que falla no tumba el radar
        for item in re.findall(r"<item>(.*?)</item>", respuesta.text, re.S):
            try:
                if parsedate_to_datetime(_texto(item, "pubDate")) < limite:
                    continue
            except (TypeError, ValueError):
                continue
            titular = _texto(item, "title")
            enlace = _texto(item, "link")
            url = parse_qs(urlparse(enlace).query).get("url", [enlace])[0]
            medio = _texto(item, "News:Source") or urlparse(url).netloc
            if titular.lower() not in vistos:
                vistos.add(titular.lower())
                resultado.append((re.sub(r"\s+on MSN$", "", medio), titular))
    return resultado


def datos_para_el_modelo(trends: list, bing: list) -> str:
    lineas = ["TENDENCIAS:"]
    for t in trends:
        lineas.append(f"- «{t['busqueda']}» ({t['trafico']} búsquedas)")
        lineas += [f"    · {medio}: {titular}" for medio, titular in t["titulares"][:4]]
    lineas.append("\nTITULARES:")
    lineas += [f"- {medio}: {titular}" for medio, titular in bing[:80]]
    return "\n".join(lineas)


def candidatas(ya_contado=(), sin_politica: str = "") -> list:
    """Hasta 3 noticias para hacer vídeo, la mejor primero.

    `ya_contado`: titulares de lo publicado estos días (para no repetir). `sin_politica`: si no está vacío, el
    motivo por el que hoy no se hace política (p. ej. la jornada de reflexión) y se descarta esa categoría.
    """
    import paso1_guiones
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("falta GROQ_API_KEY en el archivo .env")
    datos = datos_para_el_modelo(tendencias(), titulares_bing())
    veto = (f"- HOY NO se hace NINGUNA noticia de política, partidos, candidatos ni elecciones ({sin_politica}).\n"
            if sin_politica else "")
    sistema = PROMPT_RADAR.format(hoy=datetime.now().strftime("%Y-%m-%d %H:%M"), veto=veto)
    contado = "\n".join(f"- {t}" for t in ya_contado) or "- (nada)"
    respuesta = paso1_guiones.llamar_groq(api_key, os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO,
                                          sistema, f"{datos}\n\nYA CONTADO:\n{contado}")
    try:
        lista = json.loads(respuesta).get("candidatas", [])
    except (ValueError, AttributeError):
        return []
    resultado = []
    for c in lista[:3]:
        if not isinstance(c, dict) or not str(c.get("busqueda", "")).strip():
            continue
        categoria = str(c.get("categoria", "")).strip().lower()
        if sin_politica and categoria == "politica":
            continue  # por si el modelo no hace caso del veto
        resultado.append({"busqueda": str(c["busqueda"]).strip(), "titular": str(c.get("titular", "")).strip(),
                          "categoria": categoria, "motivo": str(c.get("motivo", "")).strip()})
    return resultado


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    for i, c in enumerate(candidatas(), start=1):
        print(f"{i}. [{c['categoria']}] {c['titular']}\n   búsqueda: {c['busqueda']}\n   {c['motivo']}")
