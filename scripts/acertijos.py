"""Vídeos de acertijos: un muñeco plantea el acertijo, hay una cuenta atrás para que la gente piense (y comente) y
después dice la solución. Todo con dibujos (scripts/dibujos_short.py), sin fotos.

La IA (Groq) propone acertijos clásicos con una única solución clara, sin repetir los ya hechos
(salida/_trabajo/acertijos.json). El guion se guarda en salida/guiones como los demás: después van la voz (paso 2) y
el vídeo (paso 3), y aparece en «Mis vídeos».

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
SEGUNDOS = 5  # la cuenta atrás

PROMPT = """Eres guionista de un canal español de Shorts de acertijos. Dame {cantidad} acertijo(s) para decir en voz
alta, de los que enganchan y hacen comentar.

Cada acertijo:
- SOLO acertijos CONOCIDOS, de los que llevan años en libros y concursos (no te inventes ninguno: los inventados
  salen flojos). Del nivel de estos: «El padre de Ana tiene cinco hijas: Lala, Lele, Lili, Lolo… ¿cómo se llama la
  quinta?» (Ana) · «Un gallo pone un huevo en lo alto de un tejado a dos aguas. ¿Hacia qué lado cae?» (los gallos no
  ponen huevos) · «Cuanto más le quitas, más grande es. ¿Qué es?» (un agujero) · «Tengo ciudades pero no casas, ríos
  pero no agua. ¿Qué soy?» (un mapa).
- Se entiende a la primera al oírlo y tiene UNA sola solución clara y correcta que no admita discusión (comprueba que
  la solución cumple TODO lo que dice el enunciado).
- En español de España, natural. El enunciado, de 15 a 40 palabras. Nada de juegos de palabras que solo funcionan
  escritos, ni matemáticas largas, ni temas ofensivos.
- Variados entre sí (adivinanza, lógica, pregunta trampa, deducción).
- No repitas ninguno de los YA HECHOS ni otro con la misma solución.

Responde SOLO con JSON:
{{"acertijos": [{{"enunciado": "el acertijo, tal como se dice", "solucion": "la respuesta en 1-5 palabras",
  "explicacion": "por qué, en una frase corta (máx. 16 palabras)", "icono": "un emoji de la solución",
  "titulo": "título del vídeo, una pregunta corta con gancho (máx. 55 caracteres), sin desvelar la solución"}}]}}"""


def hechos() -> list:
    try:
        return json.loads(HECHOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


PROMPT_JUEZ = """Eres un juez exigente de acertijos para un canal de vídeos. Para cada acertijo que te paso (con su
solución propuesta), decide:
- "correcta": true solo si la solución propuesta es LA respuesta correcta y única, y cumple todo el enunciado.
- "calidad": de 1 a 5. 5 = acertijo clásico, ingenioso, con un «¡ah, claro!»; 1-2 = flojo, obvio, absurdo, ambiguo o
  que no tiene gracia. Sé duro: ante la duda, baja la nota.
Responde SOLO con JSON: {"juicios": [{"n": 1, "correcta": true, "calidad": 4}]}"""


def _aprobados(api_key: str, candidatos: list) -> list:
    """Los acertijos que un segundo modelo da por correctos y buenos (calidad 4 o 5), los mejores primero."""
    lista = "\n".join(f"{i}. {a['enunciado']} → {a['solucion']}" for i, a in enumerate(candidatos, 1))
    try:
        juicios = json.loads(paso1_guiones.llamar_groq(
            api_key, os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO, PROMPT_JUEZ, lista)).get("juicios", [])
    except (ValueError, AttributeError):
        return []
    notas = {int(j["n"]): int(j.get("calidad") or 0) for j in juicios
             if isinstance(j, dict) and j.get("correcta") is True and str(j.get("n", "")).isdigit()}
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
    for a in json.loads(texto).get("acertijos", []):
        if not isinstance(a, dict):
            continue
        enunciado, solucion = " ".join(str(a.get("enunciado") or "").split()), " ".join(str(a.get("solucion") or "").split())
        if not 8 <= len(enunciado.split()) <= 55 or not solucion or paso1_guiones.slug(solucion) in soluciones:
            continue
        soluciones.add(paso1_guiones.slug(solucion))
        validos.append({"enunciado": enunciado, "solucion": solucion.rstrip("."),
                        "explicacion": " ".join(str(a.get("explicacion") or "").split()),
                        "icono": str(a.get("icono") or "").strip(),
                        "titulo": " ".join(str(a.get("titulo") or "").split())[:70] or "¿Eres capaz de resolverlo?"})
    return _aprobados(api_key, validos)[:cantidad] if validos else []


def guion_de(acertijo: dict, numero: int) -> dict:
    """El guion del vídeo: tres escenas, cada una con su dibujo ya decidido."""
    enunciado, solucion = acertijo["enunciado"], acertijo["solucion"]
    explicacion = acertijo.get("explicacion", "")
    escenas = [
        {"numero": 1, "narracion": f"Acertijo. {enunciado}",
         "visual": "riddle", "dibujo": {"tipo": "acertijo", "titulo": f"Acertijo n.º {numero}", "texto": enunciado}},
        {"numero": 2, "narracion": "Tienes cinco segundos. Escribe tu respuesta en los comentarios.",
         "visual": "countdown", "espera_s": SEGUNDOS,
         "dibujo": {"tipo": "cuenta", "desde": SEGUNDOS, "texto": enunciado}},
        {"numero": 3, "narracion": f"La respuesta es: {solucion}. {explicacion}".strip(),
         "visual": "answer", "dibujo": {"tipo": "solucion", "texto": solucion, "explicacion": explicacion,
                                         "icono": acertijo.get("icono", "")}},
    ]
    return {
        "fecha": date.today().isoformat(), "anio_evento": None, "evento": f"Acertijo {numero}", "idioma": "es",
        "titulo": acertijo["titulo"], "palabras": paso1_guiones.contar_palabras(escenas),
        "escenas": escenas, "nombre_corto": f"Acertijo {numero}", "gancho": "",  # el gancho taparía el enunciado
        "musica": "misterio",
        "hashtags": ["#acertijo", "#adivinanza", "#reto", "#ingenio"],
        "pregunta": "¿Lo has acertado? Di la verdad en los comentarios.",
        "palabras_clave": [], "fuentes": [], "sin_respaldo": [], "verificado": False,
        "acertijo": {"numero": numero, "solucion": solucion}, "estilo": "dibujos", "personaje": "detective",
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
