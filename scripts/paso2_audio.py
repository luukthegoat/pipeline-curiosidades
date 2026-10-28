"""Paso 2: convierte cada escena de los guiones en audio y mide su duración exacta.

Lee los guiones JSON del paso 1 y, por cada uno, crea en salida/audio/<guion>/:
  - escena_01.mp3, escena_02.mp3… : la narración de cada escena (voz neuronal de edge-tts)
  - escenas.json                    : el guion + duración, inicio y fin de cada escena y
                                      el tiempo de cada palabra (para sincronizar el vídeo)
  - subtitulos.srt                  : subtítulos cortos, estilo Shorts, ya sincronizados

Uso:
    python scripts/paso2_audio.py                       # todos los guiones de salida/guiones
    python scripts/paso2_audio.py salida/guiones/X.json # solo uno
    python scripts/paso2_audio.py --solo-verificados    # omite los que no tengan "verificado": true
    python scripts/paso2_audio.py --forzar              # rehace los que ya tienen audio
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import edge_tts
from dotenv import load_dotenv
from mutagen.mp3 import MP3

load_dotenv()

CARPETA_GUIONES = Path("salida/guiones")
CARPETA_AUDIO = Path("salida/audio")

VOCES = {
    "es": os.getenv("VOZ_ES") or "es-ES-AlvaroNeural",
    "en": os.getenv("VOZ_EN") or "en-US-AndrewNeural",
}
VELOCIDAD = os.getenv("VELOCIDAD") or "+8%"   # algo más rápido: ritmo de vídeo corto
PAUSA_ENTRE_ESCENAS = 0.25                     # segundos de silencio que el paso 3 pondrá entre escenas
DURACION_MIN, DURACION_MAX = 28, 55            # aviso si queda fuera: noticias de ~30 s, el resto 40-45 s

PALABRAS_POR_SUBTITULO = 4
CORTE_POR_SILENCIO = 0.35  # s: una pausa larga en la voz también cierra el subtítulo

TICKS_POR_SEGUNDO = 10_000_000  # edge-tts da los tiempos en unidades de 100 ns


async def sintetizar(texto: str, voz: str, ruta: Path, intentos: int = 3) -> list:
    """Genera el mp3 y devuelve [(palabra, inicio_s, fin_s)] relativos al inicio del audio."""
    for intento in range(intentos):
        palabras = []
        try:
            comunicador = edge_tts.Communicate(texto, voz, rate=VELOCIDAD, boundary="WordBoundary")
            with open(ruta, "wb") as archivo:
                async for trozo in comunicador.stream():
                    if trozo["type"] == "audio":
                        archivo.write(trozo["data"])
                    elif trozo["type"] == "WordBoundary":
                        inicio = trozo["offset"] / TICKS_POR_SEGUNDO
                        palabras.append((trozo["text"], inicio, inicio + trozo["duration"] / TICKS_POR_SEGUNDO))
            return palabras
        except Exception as error:  # errores de red del servicio de voz
            if intento == intentos - 1:
                raise RuntimeError(f"no se pudo generar el audio ({type(error).__name__})") from error
            await asyncio.sleep(2 * (intento + 1))


def tiempo_srt(segundos: float) -> str:
    milisegundos = round(segundos * 1000)
    horas, resto = divmod(milisegundos, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    segs, ms = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{segs:02d},{ms:03d}"


def bloques_subtitulos(palabras: list) -> list:
    """Agrupa las palabras (con tiempos absolutos) en subtítulos cortos."""
    bloques, actual = [], []
    for palabra in palabras:
        if actual and (
            len(actual) >= PALABRAS_POR_SUBTITULO or palabra["inicio_s"] - actual[-1]["fin_s"] > CORTE_POR_SILENCIO
        ):
            bloques.append(actual)
            actual = []
        actual.append(palabra)
    if actual:
        bloques.append(actual)
    return [(b[0]["inicio_s"], b[-1]["fin_s"], " ".join(p["texto"] for p in b)) for b in bloques]


def escribir_srt(ruta: Path, bloques: list) -> None:
    lineas = []
    for numero, (inicio, fin, texto) in enumerate(bloques, start=1):
        lineas += [str(numero), f"{tiempo_srt(inicio)} --> {tiempo_srt(fin)}", texto, ""]
    ruta.write_text("\n".join(lineas), encoding="utf-8")


def reutilizables(ruta_salida: Path, voz: str) -> dict:
    """Escenas del audio anterior que se pueden reutilizar (misma voz y velocidad, mp3 presente)."""
    if not ruta_salida.exists():
        return {}
    try:
        anterior = json.loads(ruta_salida.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    ajustes = anterior.get("audio", {})
    if ajustes.get("voz") != voz or ajustes.get("velocidad") != VELOCIDAD:
        return {}  # cambió la voz: hay que rehacerlo todo
    return {
        e["numero"]: e for e in anterior.get("escenas", [])
        if "numero" in e and (ruta_salida.parent / e.get("audio", "")).is_file()
    }


def audio_de_los_clips(ruta_guion: Path, guion: dict) -> Path:
    """«Vídeo con IA» con la voz de la IA: el audio de cada escena es el del clip que subiste (no se sintetiza).

    Los tiempos de cada palabra no se conocen: se reparten a lo largo del clip para los subtítulos."""
    import video_ia
    nombre = ruta_guion.stem
    faltan = video_ia.faltan(nombre, guion["escenas"])
    if faltan:
        raise ValueError(f"faltan los clips de las escenas {', '.join(map(str, faltan))}: súbelos en la página del guion")
    carpeta = CARPETA_AUDIO / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    cursor, escenas, todas_las_palabras = 0.0, [], []
    for escena in guion["escenas"]:
        numero = escena["numero"]
        clip = video_ia.ruta_clip(nombre, numero)
        duracion = video_ia.duracion(clip)
        audio = carpeta / f"escena_{numero:02d}.m4a"
        video_ia.extraer_audio(clip, audio, duracion)
        palabras = escena["narracion"].split()
        inicio, fin = min(0.3, duracion * 0.1), max(duracion - 0.4, duracion * 0.6)
        paso = (fin - inicio) / max(1, len(palabras))
        palabras_abs = [{"texto": p, "inicio_s": round(cursor + inicio + i * paso, 3),
                         "fin_s": round(cursor + inicio + (i + 1) * paso, 3)} for i, p in enumerate(palabras)]
        escenas.append({**escena, "audio": audio.name, "duracion_s": round(duracion, 3), "inicio_s": round(cursor, 3),
                        "fin_s": round(cursor + duracion, 3), "palabras_tiempos": palabras_abs})
        todas_las_palabras += palabras_abs
        print(f"  escena {numero}: {duracion:.2f} s · voz del clip {clip.name}"
              + ("" if video_ia.tiene_audio(clip) else "  (¡el clip no tiene sonido!)"))
        cursor += duracion + PAUSA_ENTRE_ESCENAS
    duracion_total = round(cursor - PAUSA_ENTRE_ESCENAS, 3)
    resultado = {**guion, "escenas": escenas, "audio": {
        "voz": f"ia:{guion['video_ia'].get('herramienta', '')}", "velocidad": "", "pausa_entre_escenas_s": PAUSA_ENTRE_ESCENAS,
        "duracion_total_s": duracion_total, "subtitulos": "subtitulos.srt", "guion_origen": str(ruta_guion)}}
    ruta_salida = carpeta / "escenas.json"
    ruta_salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_srt(carpeta / "subtitulos.srt", bloques_subtitulos(todas_las_palabras))
    print(f"  total: {duracion_total:.1f} s")
    return ruta_salida


async def procesar_guion(ruta_guion: Path, forzar: bool) -> Path:
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    if (guion.get("video_ia") or {}).get("voz") == "ia":
        return audio_de_los_clips(ruta_guion, guion)
    idioma = guion.get("idioma", "es")
    if idioma not in VOCES:
        raise ValueError(f"idioma sin voz configurada: {idioma!r}")
    voz = VOCES[idioma]

    carpeta = CARPETA_AUDIO / ruta_guion.stem
    ruta_salida = carpeta / "escenas.json"
    anteriores = reutilizables(ruta_salida, voz) if not forzar else {}
    pendientes = [
        e for e in guion["escenas"]
        if anteriores.get(e.get("numero"), {}).get("narracion") != e["narracion"]
    ]
    if ruta_salida.exists() and not forzar and not pendientes:
        print("  ya tiene audio y el texto no ha cambiado (usa --forzar para rehacerlo)")
        return ruta_salida
    if anteriores and pendientes:
        print(f"  rehago solo las escenas cambiadas: {[e.get('numero') for e in pendientes]}")
    carpeta.mkdir(parents=True, exist_ok=True)

    cursor = 0.0
    todas_las_palabras = []
    escenas = []
    for escena in guion["escenas"]:
        numero = escena.get("numero", len(escenas) + 1)
        ruta_mp3 = carpeta / f"escena_{numero:02d}.mp3"
        previa = anteriores.get(numero)
        if previa and previa["narracion"] == escena["narracion"]:
            # Misma frase y misma voz: se reutiliza el mp3 y sus tiempos (relativos al inicio de la escena).
            palabras = [(p["texto"], p["inicio_s"] - previa["inicio_s"], p["fin_s"] - previa["inicio_s"])
                        for p in previa.get("palabras_tiempos", [])]
            duracion = previa["duracion_s"]
        else:
            palabras = await sintetizar(escena["narracion"], voz, ruta_mp3)
            duracion = MP3(ruta_mp3).info.length  # duración real del archivo, no una estimación
        palabras_abs = [
            {"texto": texto, "inicio_s": round(cursor + inicio, 3), "fin_s": round(cursor + fin, 3)}
            for texto, inicio, fin in palabras
        ]
        escenas.append(
            {
                **escena,
                "audio": ruta_mp3.name,
                "duracion_s": round(duracion, 3),
                "inicio_s": round(cursor, 3),
                "fin_s": round(cursor + duracion, 3),
                "palabras_tiempos": palabras_abs,
            }
        )
        todas_las_palabras += palabras_abs
        print(f"  escena {numero}: {duracion:.2f} s{' (sin cambios)' if previa and previa['narracion'] == escena['narracion'] else ''}")
        cursor += duracion + PAUSA_ENTRE_ESCENAS

    duracion_total = round(cursor - PAUSA_ENTRE_ESCENAS, 3)
    resultado = {
        **guion,
        "escenas": escenas,
        "audio": {
            "voz": voz,
            "velocidad": VELOCIDAD,
            "pausa_entre_escenas_s": PAUSA_ENTRE_ESCENAS,
            "duracion_total_s": duracion_total,
            "subtitulos": "subtitulos.srt",
            "guion_origen": str(ruta_guion),
        },
    }
    ruta_salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_srt(carpeta / "subtitulos.srt", bloques_subtitulos(todas_las_palabras))

    minimo, maximo = DURACION_MIN, DURACION_MAX
    aviso = "" if minimo <= duracion_total <= maximo else f"  ← fuera de {minimo}-{maximo} s"
    print(f"  total: {duracion_total:.1f} s{aviso}")
    return ruta_salida


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Genera el audio de cada escena de los guiones")
    parser.add_argument("guiones", nargs="*", type=Path, help="guiones JSON (por defecto, todos los de salida/guiones)")
    parser.add_argument("--solo-verificados", action="store_true", help='omite guiones sin "verificado": true')
    parser.add_argument("--forzar", action="store_true", help="rehace el audio aunque ya exista")
    args = parser.parse_args(argv)

    rutas = args.guiones or sorted(CARPETA_GUIONES.glob("*.json"))
    if not rutas:
        print(f"[error] No hay guiones en {CARPETA_GUIONES}. Ejecuta antes paso1_guiones.py", file=sys.stderr)
        return 1

    hechos = omitidos = fallidos = 0
    for ruta in rutas:
        print(f"\n· {ruta.name}")
        try:
            guion = json.loads(ruta.read_text(encoding="utf-8"))
            if not guion.get("verificado"):
                if args.solo_verificados:
                    print("  omitido: no está verificado")
                    omitidos += 1
                    continue
                dudas = len(guion.get("sin_respaldo", []))
                print(f"  aviso: guion sin verificar ({dudas} frase(s) sin respaldo); revísalo antes de publicar")
            ruta_salida = asyncio.run(procesar_guion(ruta, args.forzar))
            print(f"  → {ruta_salida}")
            hechos += 1
        except (ValueError, KeyError, RuntimeError, OSError) as error:
            print(f"  error: {error}", file=sys.stderr)
            fallidos += 1

    print(f"\nCon audio: {hechos} · Omitidos: {omitidos} · Con error: {fallidos}")
    return 0 if fallidos == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
