"""Noticias de actualidad: busca artículos recientes sobre un tema y extrae su texto.

Wikipedia no sirve para lo que está pasando ahora, así que el material de estos vídeos son artículos de prensa:
  - Bing Noticias (gratis, sin clave): su canal RSS da titular, medio, fecha y enlace; el texto se descarga
    de la web de cada medio (los que tienen muro de pago o solo vídeo se descartan solos).
  - Tavily (si hay TAVILY_API_KEY en .env): buscador para IA; completa lo de Bing (y lo sustituye si Bing falla)
    con el texto de cada artículo ya limpio.
Se queda con un artículo por medio, de los últimos días, con texto suficiente, y marca los medios reconocidos.

Uso:
    python scripts/actualidad.py "saqueos Francia" [--dias 3] [--mas-idiomas]
"""
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent  # carpeta principal (este archivo está en scripts/)
load_dotenv(RAIZ / ".env")

CARPETA = RAIZ / "salida" / "_trabajo" / "actualidad"
URL_TAVILY = "https://api.tavily.com/search"
AGENTE = "MenteInquieta/1.0 (+https://github.com/luukthegoat/pipeline-curiosidades)"
MIN_CARACTERES = 1200      # menos texto suele ser un muro de pago, un vídeo o un resumen de agencia
MAX_ARTICULOS = 10         # los que se enseñan para elegir
MAX_POR_ARTICULO = 3200    # lo que entra de cada uno en el material del guion
MAX_MATERIAL = 9500        # total: el cupo por minuto de Groq no da para más

# Medios reconocidos: salen primero y marcados (la lista no es exhaustiva: los demás también se pueden usar).
MEDIOS = {
    "rtve.es": "RTVE", "efe.com": "EFE", "europapress.es": "Europa Press", "elpais.com": "El País",
    "elmundo.es": "El Mundo", "abc.es": "ABC", "lavanguardia.com": "La Vanguardia", "elconfidencial.com": "El Confidencial",
    "eldiario.es": "elDiario.es", "20minutos.es": "20minutos", "elperiodico.com": "El Periódico",
    "larazon.es": "La Razón", "publico.es": "Público", "cadenaser.com": "Cadena SER", "cope.es": "COPE",
    "ondacero.es": "Onda Cero", "antena3.com": "Antena 3", "telecinco.es": "Telecinco", "lasexta.com": "laSexta",
    "elespanol.com": "El Español", "infobae.com": "Infobae", "clarin.com": "Clarín", "eltiempo.com": "El Tiempo",
    "france24.com": "France 24", "rfi.fr": "RFI", "lemonde.fr": "Le Monde", "lefigaro.fr": "Le Figaro",
    "liberation.fr": "Libération", "francetvinfo.fr": "franceinfo", "bfmtv.com": "BFMTV", "afp.com": "AFP",
    "reuters.com": "Reuters", "apnews.com": "AP", "bbc.com": "BBC", "bbc.co.uk": "BBC", "theguardian.com": "The Guardian",
    "nytimes.com": "The New York Times", "washingtonpost.com": "The Washington Post", "dw.com": "DW",
    "euronews.com": "Euronews", "cnn.com": "CNN", "politico.eu": "Politico Europe", "aljazeera.com": "Al Jazeera",
}


def dominio(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def medio_de(url: str) -> tuple:
    """(nombre del medio, ¿es reconocido?)"""
    host = dominio(url)
    for clave, nombre in MEDIOS.items():
        if host == clave or host.endswith("." + clave):
            return nombre, True
    return host, False


# --- Búsqueda ------------------------------------------------------------------------------

def buscar_tavily(tema: str, dias: int, clave: str) -> list:
    respuesta = requests.post(URL_TAVILY, timeout=60, headers={"Authorization": f"Bearer {clave}"}, json={
        "query": tema, "topic": "news", "days": dias, "max_results": 20,
        "search_depth": "advanced", "include_raw_content": True,
    })
    respuesta.raise_for_status()
    articulos = []
    for r in respuesta.json().get("results", []):
        articulos.append({
            "url": r.get("url", ""), "titulo": r.get("title", ""), "fecha": (r.get("published_date") or "")[:25],
            "texto": (r.get("raw_content") or r.get("content") or "").strip(),
        })
    return articulos


def buscar_bing(tema: str, dias: int, mas_idiomas: bool) -> list:
    """Noticias de Bing (su canal RSS público): buena relevancia, con medio, fecha y enlace al artículo."""
    import html
    from email.utils import parsedate_to_datetime
    from urllib.parse import parse_qs
    mercados = [("es", "ES")] + ([("en", "US"), ("fr", "FR")] if mas_idiomas else [])
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    articulos = []
    for idioma, pais in mercados:
        respuesta = requests.get("https://www.bing.com/news/search", timeout=30,
                                 params={"q": tema, "format": "rss", "setlang": idioma, "cc": pais},
                                 headers={"User-Agent": "Mozilla/5.0 " + AGENTE})
        respuesta.raise_for_status()
        for item in re.findall(r"<item>(.*?)</item>", respuesta.text, re.S):
            def campo(etiqueta):
                encontrado = re.search(rf"<{etiqueta}>(.*?)</{etiqueta}>", item, re.S)
                return html.unescape(encontrado.group(1)).strip() if encontrado else ""
            enlace = campo("link")
            url = parse_qs(urlparse(enlace).query).get("url", [enlace])[0]  # el enlace real va dentro del de Bing
            try:
                fecha = parsedate_to_datetime(campo("pubDate"))
            except (TypeError, ValueError):
                fecha = None
            if fecha and fecha < limite:
                continue
            articulos.append({"url": url, "titulo": campo("title"), "texto": "",
                              "fecha": fecha.astimezone().isoformat(timespec="minutes") if fecha else "",
                              "fuente": campo("News:Source")})
    return articulos


def extraer_texto(url: str) -> str:
    """Texto principal de un artículo (sin menús, anuncios ni comentarios)."""
    import trafilatura
    try:
        respuesta = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 " + AGENTE,
                                                           "Accept-Language": "es,en;q=0.8,fr;q=0.6"})
        if respuesta.status_code != 200:
            return ""
        return (trafilatura.extract(respuesta.text, include_comments=False, include_tables=False,
                                    favor_precision=True) or "").strip()
    except (requests.RequestException, ValueError):
        return ""


def buscar(tema: str, dias: int = 3, mas_idiomas: bool = False) -> dict:
    """Busca, descarga y ordena los artículos. Guarda el resultado y lo devuelve (con su «id»)."""
    # Bing primero: da los medios españoles grandes. Tavily (si hay clave) completa con lo que Bing no trae y, si
    # Bing falla, lo sustituye. Solo con Tavily salían medios pequeños y en inglés.
    clave = os.getenv("TAVILY_API_KEY", "").strip()
    motores, encontrados = [], []
    try:
        encontrados += buscar_bing(tema, dias, mas_idiomas)
        motores.append("Bing Noticias")
    except requests.RequestException:
        if not clave:
            raise
    if clave:
        try:
            encontrados += buscar_tavily(tema, dias, clave)
            motores.append("Tavily")
        except requests.RequestException:
            if not encontrados:
                raise
    motor = " + ".join(motores)

    # Un artículo por medio (el primero que da el buscador, que es el más relevante)
    por_medio = {}
    for a in encontrados:
        if a["url"] and dominio(a["url"]) not in por_medio:
            por_medio[dominio(a["url"])] = a
    candidatos = list(por_medio.values())
    candidatos.sort(key=lambda a: not medio_de(a["url"])[1])  # reconocidos primero (orden estable)
    candidatos = candidatos[:MAX_ARTICULOS * 2]

    sin_texto = [a for a in candidatos if len(a["texto"]) < MIN_CARACTERES]
    with ThreadPoolExecutor(max_workers=6) as hilos:
        for articulo, texto in zip(sin_texto, hilos.map(lambda a: extraer_texto(a["url"]), sin_texto)):
            articulo["texto"] = texto or articulo["texto"]

    articulos = []
    for a in candidatos:
        if len(a["texto"]) < MIN_CARACTERES:
            continue
        medio, reconocido = medio_de(a["url"])
        if not reconocido and a.get("fuente"):
            medio = re.sub(r"\s+on MSN$", "", a["fuente"])
        articulos.append({**a, "medio": medio, "reconocido": reconocido, "caracteres": len(a["texto"]),
                          "titulo": re.sub(r"\s+", " ", a["titulo"]).strip() or medio})
        if len(articulos) == MAX_ARTICULOS:
            break
    resultado = {
        "id": hashlib.sha1(f"{tema}|{datetime.now().isoformat()}".encode()).hexdigest()[:10],
        "tema": tema, "dias": dias, "motor": motor, "buscado": datetime.now().isoformat(timespec="minutes"),
        "articulos": articulos, "descartados": len(candidatos) - len(articulos),
    }
    CARPETA.mkdir(parents=True, exist_ok=True)
    (CARPETA / f"{resultado['id']}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    limpiar_antiguas()
    return resultado


def leer(id_busqueda: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{10}", id_busqueda or ""):
        raise ValueError("búsqueda no válida")
    return json.loads((CARPETA / f"{id_busqueda}.json").read_text(encoding="utf-8"))


def limpiar_antiguas(dias: int = 14) -> None:
    limite = time.time() - dias * 86400
    for ruta in CARPETA.glob("*.json"):
        if ruta.stat().st_mtime < limite:
            ruta.unlink(missing_ok=True)


def material(articulos: list) -> str:
    """El MATERIAL del guion: cada artículo con su medio y su fecha, recortado para que quepa todo."""
    por_articulo = min(MAX_POR_ARTICULO, MAX_MATERIAL // max(1, len(articulos)))
    bloques = []
    for i, a in enumerate(articulos, start=1):
        texto = a["texto"][:por_articulo]
        if len(a["texto"]) > por_articulo:
            texto = texto.rsplit(". ", 1)[0] + "."
        bloques.append(f"FUENTE {i} · {a['medio']} · {a.get('fecha', '')[:16]}\nTítulo: {a['titulo']}\n{texto}")
    return "\n\n".join(bloques)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Busca noticias recientes sobre un tema")
    parser.add_argument("tema")
    parser.add_argument("--dias", type=int, default=3)
    parser.add_argument("--mas-idiomas", action="store_true", help="también medios en inglés y francés")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    r = buscar(args.tema, args.dias, args.mas_idiomas)
    print(f"{r['motor']} · {len(r['articulos'])} artículos (descartados {r['descartados']} sin texto suficiente) · id {r['id']}")
    for a in r["articulos"]:
        print(f"  {'★' if a['reconocido'] else ' '} {a['medio']:<20} {a['fecha'][:16]:<17} {a['caracteres']:>6}  {a['titulo'][:70]}")
