"""Asistente de la app: le escribes lo que quieras y entiende qué vídeo hacer (o te contesta con los datos del canal).

Usa una IA local con Ollama (si está instalado y abierto en este ordenador) y, si no, Groq, como el resto de la app.
No crea nada por su cuenta: propone una acción y el menú la lanza cuando pulsas «Crear».
"""
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import requests

import paso1_guiones
import wikimedia

OLLAMA = "http://127.0.0.1:11434"
MODELO_OLLAMA = "qwen2.5:7b"   # el recomendado: entiende bien el español y responde en JSON (unos 5 GB)
HISTORIAL = Path("salida/asistente.json")
MAX_MENSAJES = 60      # los que se guardan
MENSAJES_CONTEXTO = 10  # los que se le pasan a la IA para que siga la conversación

TIPOS = {
    "short": "Short sobre un tema",
    "serie": "Serie de Shorts",
    "efemerides": "Efemérides de una fecha",
    "diario": "Diario de… (humor)",
    "largo": "Vídeo largo con dibujos",
    "actualidad": "Short de actualidad",
}

PROMPT = """Eres el asistente de MenteInquieta67, la app con la que se hacen los vídeos de historia y actualidad del canal
de YouTube MenteInquieta67. Hablas en español de España, tuteando (nunca de usted): breve, cercano y claro. Hoy es
{hoy}.

Lo que la app sabe hacer (acciones):
- "short": un Short de 40-45 s sobre un tema histórico o curioso. Datos: "tema" (2-6 palabras).
- "serie": una serie de 2 o 3 Shorts sobre un tema amplio. Datos: "tema", "partes" (2 o 3).
- "efemerides": Shorts de lo que pasó un día concreto. Datos: "fecha" (AAAA-MM-DD), "cantidad" (1 a 3).
- "diario": un Short de humor «Diario de…» en primera persona. Datos: "personaje" (p. ej. «soldado romano en
  Britania»), "problema" (lo que le pasa, opcional).
- "largo": un vídeo largo de unos 10 minutos explicado con dibujos. Datos: "tema" (el título de un artículo de
  Wikipedia en español, p. ej. «Reyes Católicos», «Segunda República española»).
- "actualidad": un Short de una noticia reciente. Datos: "noticia" (2-5 palabras para buscarla en la prensa).
- "ninguna": si solo pregunta algo, charla, o no está claro qué vídeo quiere.

Reglas:
- Si pide un vídeo, elige la acción y rellena sus datos. En "respuesta", 1-2 frases: qué vas a hacer y que pulse
  «Crear» para empezar (no digas que ya lo has hecho).
- Si falta algo imprescindible o no está claro qué vídeo quiere (p. ej. «hazme algo»), usa "ninguna" y pregunta, o
  propón 2-3 ideas concretas para que elija. Nunca te inventes un vídeo que no ha pedido.
- Si pregunta por el canal o sus vídeos, contesta con los DATOS DEL CANAL; nunca inventes cifras.
- Si pide ideas, propón temas concretos: lo que mejor funciona en el canal es la historia de España y la actualidad
  española.
- Nada de temas que inciten al odio, a la violencia o que acusen a personas reales sin fuentes.

DATOS DEL CANAL:
{contexto}

Responde SOLO con un JSON: {{"respuesta": "texto para el usuario", "accion": {{"tipo": "...", ...datos}}}}"""


# --- Motor: Ollama (local) o Groq ------------------------------------------------------------------

def _ollama_modelos() -> list:
    try:
        respuesta = requests.get(f"{OLLAMA}/api/tags", timeout=1.5)
        return [m["name"] for m in respuesta.json().get("models", [])]
    except (requests.RequestException, ValueError):
        return []


def motor() -> dict:
    """Qué IA va a contestar: {"local": bool, "nombre": «…», "modelo": «…»}."""
    modelos = _ollama_modelos() if os.getenv("ASISTENTE_LOCAL", "1") == "1" else []
    preferido = os.getenv("OLLAMA_MODELO") or MODELO_OLLAMA
    if modelos:
        modelo = preferido if preferido in modelos else next(
            (m for m in modelos if m.split(":")[0] == preferido.split(":")[0]), modelos[0])
        return {"local": True, "modelo": modelo, "nombre": f"IA local ({modelo}, en tu ordenador)"}
    return {"local": False, "modelo": os.getenv("MODELO") or paso1_guiones.MODELO_POR_DEFECTO,
            "nombre": "Groq (en internet). Para usar una IA local, instala Ollama: mira Ajustes → Asistente"}


def _llamar(sistema: str, conversacion: list) -> str:
    quien = motor()
    if quien["local"]:
        mensajes = [{"role": "system", "content": sistema}] + [
            {"role": "user" if m["rol"] == "tu" else "assistant", "content": m["texto"]} for m in conversacion]
        respuesta = requests.post(f"{OLLAMA}/api/chat", timeout=300, json={
            "model": quien["modelo"], "messages": mensajes, "format": "json", "stream": False,
            "options": {"temperature": 0.4}})
        respuesta.raise_for_status()
        return respuesta.json()["message"]["content"]
    # Groq: la conversación va como texto (la función de la app es de una sola pregunta)
    texto = "\n".join(f"{'USUARIO' if m['rol'] == 'tu' else 'ASISTENTE'}: {m['texto']}" for m in conversacion)
    return paso1_guiones.llamar_groq(os.getenv("GROQ_API_KEY"), quien["modelo"], sistema,
                                     f"CONVERSACIÓN (responde al último mensaje del USUARIO):\n{texto}")


# --- Historial ---------------------------------------------------------------------------------------

def historial() -> list:
    try:
        return json.loads(HISTORIAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def guardar(mensajes: list) -> None:
    HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
    HISTORIAL.write_text(json.dumps(mensajes[-MAX_MENSAJES:], ensure_ascii=False, indent=2), encoding="utf-8")


def borrar() -> None:
    guardar([])


# --- Entender lo que se pide ------------------------------------------------------------------------

def _titulo_wikipedia(tema: str) -> str:
    """El título exacto del artículo de Wikipedia que más se parece (los vídeos largos salen de un artículo)."""
    try:
        datos = wikimedia.json_api(paso1_guiones.URL_WIKI_API, {"action": "opensearch", "search": tema, "limit": 1,
                                                                "namespace": 0, "format": "json"})
        return datos[1][0] if isinstance(datos, list) and len(datos) > 1 and datos[1] else ""
    except Exception:  # noqa: BLE001 — sin conexión: se queda el tema tal cual
        return tema


def validar(accion) -> dict:
    """Deja solo acciones que la app puede lanzar, con sus datos limpios; si falta algo, «ninguna»."""
    if not isinstance(accion, dict) or accion.get("tipo") not in TIPOS:
        return {"tipo": "ninguna"}
    tipo = accion["tipo"]
    limpio = lambda clave, maximo=80: " ".join(str(accion.get(clave) or "").split())[:maximo]  # noqa: E731
    if tipo in ("short", "serie", "largo"):
        tema = limpio("tema")
        if not tema:
            return {"tipo": "ninguna"}
        if tipo == "largo":
            titulo = _titulo_wikipedia(tema)
            if not titulo:
                return {"tipo": "ninguna", "aviso": f"No encuentro en Wikipedia un artículo sobre «{tema}»."}
            return {"tipo": tipo, "tema": titulo}
        if tipo == "serie":
            try:
                partes = min(max(int(accion.get("partes") or 3), 2), paso1_guiones.MAX_PARTES)
            except (TypeError, ValueError):
                partes = 3
            return {"tipo": tipo, "tema": tema, "partes": partes}
        return {"tipo": tipo, "tema": tema}
    if tipo == "efemerides":
        try:
            fecha = date.fromisoformat(str(accion.get("fecha")))
        except ValueError:
            return {"tipo": "ninguna"}
        try:
            cantidad = min(max(int(accion.get("cantidad") or 1), 1), 3)
        except (TypeError, ValueError):
            cantidad = 1
        return {"tipo": tipo, "fecha": fecha.isoformat(), "cantidad": cantidad}
    if tipo == "diario":
        personaje = limpio("personaje")
        return {"tipo": tipo, "personaje": personaje, "problema": limpio("problema", 120)} if personaje else {"tipo": "ninguna"}
    noticia = limpio("noticia", 60)
    return {"tipo": tipo, "noticia": noticia} if noticia else {"tipo": "ninguna"}


def describir(accion: dict) -> str:
    """«Vídeo largo con dibujos: «Reyes Católicos»» para enseñarlo en el chat."""
    tipo = accion.get("tipo")
    if tipo in ("short", "largo"):
        return f"{TIPOS[tipo]}: «{accion['tema']}»"
    if tipo == "serie":
        return f"{TIPOS[tipo]}: «{accion['tema']}» en {accion['partes']} partes"
    if tipo == "efemerides":
        return f"{TIPOS[tipo]}: {accion['fecha']} ({accion['cantidad']} vídeo{'s' if accion['cantidad'] > 1 else ''})"
    if tipo == "diario":
        return f"{TIPOS[tipo]}: «{accion['personaje']}»" + (f" — {accion['problema']}" if accion.get("problema") else "")
    if tipo == "actualidad":
        return f"{TIPOS[tipo]}: «{accion['noticia']}»"
    return ""


def responder(mensaje: str, contexto: str) -> dict:
    """Añade el mensaje al historial, pide la respuesta a la IA y la guarda. Devuelve el mensaje del asistente."""
    mensajes = historial()
    mensajes.append({"rol": "tu", "texto": mensaje.strip()[:2000], "hora": datetime.now().isoformat(timespec="seconds")})
    sistema = PROMPT.format(hoy=date.today().isoformat(), contexto=contexto)
    try:
        bruto = _llamar(sistema, mensajes[-MENSAJES_CONTEXTO:])
        datos = json.loads(re.sub(r"^```(?:json)?|```$", "", bruto.strip()))
        texto = str(datos.get("respuesta") or "").strip() or "Hecho."
        accion = validar(datos.get("accion"))
    except Exception as error:  # noqa: BLE001 — que el fallo se vea en el chat y no rompa la página
        texto, accion = f"No he podido contestar ({type(error).__name__}: {str(error)[:160]}). Prueba otra vez.", {"tipo": "ninguna"}
    if accion.pop("aviso", ""):
        texto += " (No he encontrado ese tema en Wikipedia: dime otro título.)"
    respuesta = {"rol": "asistente", "texto": texto, "hora": datetime.now().isoformat(timespec="seconds"),
                 "motor": motor()["nombre"].split(" (")[0]}
    if accion["tipo"] != "ninguna":
        respuesta["accion"] = accion
    mensajes.append(respuesta)
    guardar(mensajes)
    return respuesta
