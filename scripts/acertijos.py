"""Vídeos de acertijos contados como una historia: el detective cuenta el caso en viñetas, sale una tarjeta con las
pistas y una cuenta atrás («piensa, puedes pausar») para que la gente conteste en los comentarios, y después la
solución. Todo con dibujos (scripts/dibujos_short.py), sin fotos.

La IA (Groq) propone acertijos clásicos de ingenio (de los de «¿por qué hace eso?») con una única solución clara; un
segundo modelo descarta los flojos, y no se repiten (salida/_trabajo/acertijos.json). El guion se guarda en
salida/guiones como los demás: después van la voz (paso 2) y el vídeo (paso 3).

Uso:
    python scripts/acertijos.py                # un acertijo nuevo (solo el guion)
    python scripts/acertijos.py --cantidad 3   # tres
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

import paso1_guiones

load_dotenv()

HECHOS = Path("salida/_trabajo/acertijos.json")
SEGUNDOS = 6  # la cuenta atrás

PROMPT = """Eres guionista de un canal español de Shorts de acertijos que se cuentan como una HISTORIA ilustrada.
Dame {cantidad} acertijo(s) de ingenio (pensamiento lateral), de los que enganchan porque pasa algo raro y el
espectador quiere saber por qué.

Cada acertijo:
- SOLO acertijos CLÁSICOS y conocidos, de los que llevan años en libros y concursos (no te inventes ninguno: los
  inventados salen flojos). Del estilo de: el hombre que vive en el piso 20 y, salvo los días de lluvia, sube en
  ascensor solo hasta el 10 y sigue a pie (es bajito: no llega al botón; con lluvia lleva paraguas) · el hombre que
  entra en un bar, pide un vaso de agua, el camarero le apunta con una pistola de juguete y él da las gracias y se va
  (tenía hipo) · el padre y el hijo del accidente y el cirujano que dice «no puedo operarlo, es mi hijo» (es su
  madre) · el camionero que va en dirección contraria y la policía no le dice nada (va andando).
- Tiene UNA explicación clara y correcta, que encaja con TODO lo que cuenta la historia y hace decir «¡ah, claro!».
- Apto para todos los públicos: nada de suicidios, asesinatos, sangre ni temas ofensivos.
- Se cuenta en 3 o 4 viñetas, en presente, con frases fáciles de decir en voz alta. La PRIMERA viñeta empieza
  con lo raro, para enganchar («Este hombre sube diez pisos andando… teniendo ascensor.»).
- La historia cuenta el planteamiento COMPLETO: todos los datos que hacen falta para resolverlo (quien no conozca el
  acertijo tiene que poder deducirlo solo con lo que oye). Entre 40 y 75 palabras en total.
- NADA delata la solución antes de tiempo: ni la narración («se revela…»), ni los rótulos, ni las pistas, ni los
  emojis (si la respuesta es «es su madre», no dibujes una doctora; si es «tenía hipo», no pongas 😮‍💨). Los emojis
  dibujan solo lo que se cuenta: el lugar, los personajes tal como los imagina quien escucha, los objetos.
- Las pistas son HECHOS de la historia que ayudan a pensar («Vive en el piso 20», «Los días de lluvia sube directo»),
  nunca conclusiones ni la respuesta con otras palabras.
- No repitas ninguno de los YA HECHOS ni otro con la misma solución.

Responde SOLO con JSON:
{{"acertijos": [{{
  "titulo": "título del vídeo: una pregunta corta con gancho (máx. 55 caracteres), sin desvelar la solución",
  "historia": [{{"narracion": "lo que dice la voz en esta viñeta (12 a 22 palabras)",
                "iconos": ["1 a 3 emojis que dibujen la viñeta: 🏢 🛗 🌧️ ☂️ 🧔 🍺 💧 🚚 👮 …"],
                "texto": "rótulo de la viñeta, 2 a 5 palabras"}}],
  "pistas": ["2 o 3 pistas que resumen lo que se sabe, de 3 a 7 palabras cada una"],
  "pregunta": "la pregunta del acertijo, corta (máx. 8 palabras): «¿Por qué no sube en ascensor?»",
  "solucion": "la respuesta en 1 a 6 palabras",
  "explicacion": "la explicación completa, para decir en voz alta (12 a 30 palabras)",
  "icono": "un emoji de la solución"}}]}}"""


def hechos() -> list:
    try:
        return json.loads(HECHOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


PROMPT_JUEZ = """Eres un juez exigente de acertijos de ingenio para un canal de vídeos. Para cada acertijo que te paso
(la historia y su solución propuesta), decide:
- "correcta": true solo si la solución explica TODO lo que cuenta la historia, sin contradicciones, y es la clásica.
- "completa": true solo si la historia da TODOS los datos necesarios para deducir la solución.
- "delata": true si la narración, los rótulos, las pistas o los emojis revelan o insinúan la solución antes de tiempo.
- "calidad": de 1 a 5. 5 = acertijo clásico, ingenioso, con un «¡ah, claro!»; 1-2 = flojo, obvio, absurdo, ambiguo o
  que no tiene gracia. Sé duro: ante la duda, baja la nota.
Responde SOLO con JSON: {"juicios": [{"n": 1, "correcta": true, "completa": true, "delata": false, "calidad": 4}]}"""


def _aprobados(api_key: str, candidatos: list) -> list:
    """Los acertijos que un segundo modelo da por correctos y buenos (calidad 4 o 5), los mejores primero."""
    lista = "\n\n".join(
        f"{i}. HISTORIA: {a['enunciado']}\n   RÓTULOS Y EMOJIS: "
        + " | ".join(f"{v['texto']} {' '.join(v['iconos'])}" for v in a["historia"])
        + f"\n   PISTAS: {' | '.join(a['pistas'])}\n   PREGUNTA: {a['pregunta']}\n   SOLUCIÓN: {a['solucion']} "
          f"({a['explicacion']})" for i, a in enumerate(candidatos, 1))
    try:
        juicios = json.loads(paso1_guiones.llamar_groq(
            api_key, os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO, PROMPT_JUEZ, lista)).get("juicios", [])
    except (ValueError, AttributeError):
        return []
    notas = {int(j["n"]): int(j.get("calidad") or 0) for j in juicios
             if isinstance(j, dict) and j.get("correcta") is True and j.get("completa") is not False
             and j.get("delata") is not True and str(j.get("n", "")).isdigit()}
    buenos = [(notas[i], a) for i, a in enumerate(candidatos, 1) if notas.get(i, 0) >= 4]
    return [a for _, a in sorted(buenos, key=lambda par: -par[0])]


def pedir(cantidad: int) -> list:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("falta GROQ_API_KEY en el archivo .env")
    ya = "\n".join(f"- {a['enunciado']} → {a['solucion']}" for a in hechos()[-150:]) or "- (ninguno)"
    # Se piden de sobra: un segundo modelo descarta los flojos o mal resueltos.
    texto = paso1_guiones.llamar_groq(api_key, os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO,
                                      PROMPT.format(cantidad=cantidad + 4), f"YA HECHOS:\n{ya}")
    validos = []
    soluciones = {paso1_guiones.slug(a["solucion"]) for a in hechos()}
    limpio = lambda valor: " ".join(str(valor or "").split())  # noqa: E731
    for a in json.loads(texto).get("acertijos", []):
        if not isinstance(a, dict):
            continue
        historia = [{"narracion": limpio(v.get("narracion")), "iconos": [str(e) for e in v.get("iconos") or []][:3],
                     "texto": limpio(v.get("texto"))[:60]}
                    for v in a.get("historia") or [] if isinstance(v, dict) and limpio(v.get("narracion"))][:5]
        solucion, explicacion = limpio(a.get("solucion")).rstrip("."), limpio(a.get("explicacion"))
        palabras = sum(len(v["narracion"].split()) for v in historia)
        if (len(historia) < 2 or not 30 <= palabras <= 95 or not solucion or not explicacion
                or paso1_guiones.slug(solucion) in soluciones):
            continue
        soluciones.add(paso1_guiones.slug(solucion))
        validos.append({"historia": historia, "enunciado": " ".join(v["narracion"] for v in historia),
                        "pistas": [limpio(p)[:60] for p in a.get("pistas") or [] if limpio(p)][:3],
                        "pregunta": limpio(a.get("pregunta"))[:70] or "¿Cómo es posible?",
                        "solucion": solucion, "explicacion": explicacion, "icono": limpio(a.get("icono")),
                        "titulo": limpio(a.get("titulo"))[:70] or "¿Eres capaz de resolverlo?"})
    return _aprobados(api_key, validos)[:cantidad] if validos else []


def guion_de(acertijo: dict, numero: int) -> dict:
    """El guion del vídeo: las viñetas de la historia, las pistas con la cuenta atrás y la solución."""
    escenas = [{"narracion": v["narracion"], "visual": "story",
                "dibujo": {"tipo": "vineta", "iconos": v["iconos"], "texto": v["texto"]}}
               for v in acertijo["historia"]]
    escenas.append({"narracion": f"{acertijo['pregunta']} Piensa. Puedes pausar el vídeo.", "visual": "countdown",
                    "espera_s": SEGUNDOS,
                    "dibujo": {"tipo": "cuenta", "desde": SEGUNDOS, "pregunta": acertijo["pregunta"],
                               "pistas": acertijo["pistas"], "texto": acertijo["enunciado"]}})
    escenas.append({"narracion": f"La respuesta: {acertijo['explicacion']}", "visual": "answer",
                    "dibujo": {"tipo": "solucion", "texto": acertijo["solucion"], "explicacion": "",
                               "icono": acertijo.get("icono", "")}})
    escenas = [{"numero": i, **e} for i, e in enumerate(escenas, start=1)]
    return {
        "fecha": date.today().isoformat(), "anio_evento": None, "evento": f"Acertijo {numero}", "idioma": "es",
        "titulo": acertijo["titulo"], "palabras": paso1_guiones.contar_palabras(escenas),
        "escenas": escenas, "nombre_corto": f"Acertijo {numero}", "gancho": "",  # el gancho taparía la viñeta
        "musica": "misterio",
        "hashtags": ["#acertijo", "#adivinanza", "#reto", "#ingenio"],
        "pregunta": "¿Lo has acertado? Di la verdad en los comentarios.",
        "palabras_clave": [], "fuentes": [], "sin_respaldo": [], "verificado": False,
        "acertijo": {"numero": numero, "solucion": acertijo["solucion"]}, "estilo": "dibujos", "personaje": "detective",
    }


def crear(cantidad: int = 1) -> list:
    """Crea los guiones y devuelve sus rutas."""
    rutas = []
    lista = hechos()
    for acertijo in pedir(cantidad):
        numero = len(lista) + 1
        guion = guion_de(acertijo, numero)
        paso1_guiones.CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
        ruta = paso1_guiones.CARPETA_SALIDA / f"{guion['fecha']}_acertijo_{numero:03d}_es.json"
        ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
        lista.append({"numero": numero, "fecha": guion["fecha"], "enunciado": acertijo["enunciado"],
                      "solucion": acertijo["solucion"]})
        HECHOS.parent.mkdir(parents=True, exist_ok=True)
        HECHOS.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {ruta} · «{acertijo['enunciado']}» → {acertijo['solucion']}")
        rutas.append(ruta)
    return rutas


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Guiones de vídeos de acertijos")
    parser.add_argument("--cantidad", type=int, default=1)
    args = parser.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")
    try:
        rutas = crear(max(1, min(args.cantidad, 5)))
    except Exception as error:  # noqa: BLE001
        print(f"[error] {error}", file=sys.stderr)
        return 1
    print(f"Acertijos generados: {len(rutas)}")
    return 0 if rutas else 1


if __name__ == "__main__":
    sys.exit(main())
