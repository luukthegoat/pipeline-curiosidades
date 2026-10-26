"""Música de fondo: pistas ambientales sintetizadas (sin derechos de autor) y las tuyas.

Las pistas generadas se crean una sola vez en la carpeta musica/ (epico.mp3, misterio.mp3,
triste.mp3, neutro.mp3). Puedes añadir tus propias canciones (.mp3) a esa carpeta: aparecerán
en el menú con su nombre de archivo. Usa solo música que tengas derecho a usar.

Uso:
    python scripts/musica.py             # crea las pistas que falten
    python scripts/musica.py --rehacer   # las vuelve a crear
"""
import math
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

CARPETA_MUSICA = Path("musica")
DURACION = 96  # s; múltiplo del ciclo de acordes (16 s)

# Notas en Hz
N = {
    "D2": 73.42, "A2": 110.0, "C3": 130.81, "D3": 146.83, "Eb3": 155.56, "E3": 164.81, "F3": 174.61,
    "G3": 196.0, "A3": 220.0, "Bb2": 116.54, "Bb3": 233.08, "C4": 261.63, "D4": 293.66, "E4": 329.63,
    "F2": 87.31, "G2": 98.0,
}

# Cada tono: dos acordes que se alternan suavemente, brillo (filtro) y si lleva pulso grave.
TONOS = {
    "epico": {"acordes": (["D2", "A2", "D3", "F3"], ["Bb2", "F3", "Bb3", "D4"]), "brillo": 1800, "pulso": 70},
    "misterio": {"acordes": (["A2", "Eb3", "C3", "A3"], ["G2", "D3", "Bb3", "Eb3"]), "brillo": 1400, "pulso": 0},
    "triste": {"acordes": (["A2", "C3", "E3", "A3"], ["F2", "C3", "F3", "A3"]), "brillo": 1200, "pulso": 0},
    "neutro": {"acordes": (["C3", "G3", "D4", "E4"], ["A2", "E3", "C4", "E4"]), "brillo": 2200, "pulso": 0},
    "comico": {"comico": True, "brillo": 3500},  # melodía propia (expresion_comica), para el formato «Diario de…»
}


# Melodía cómica: notas cortas tipo pizzicato (do mayor, saltarina) sobre un bajo que hace «bom… bom».
MELODIA_COMICA = [523.25, 659.25, 783.99, 659.25, 698.46, 587.33, 493.88, 392.0,
                  523.25, 783.99, 880.0, 783.99, 698.46, 659.25, 587.33, 523.25]
BAJO_COMICO = [130.81, 196.0, 174.61, 196.0]
PULSO_COMICO = 0.3  # s por nota (≈ 100 pulsaciones por minuto, en corcheas)


def expresion_comica() -> str:
    """Expresión de aevalsrc: cada nota se elige con el número de pulso y se apaga rápido (exp)."""
    def secuencia(notas, duracion):
        n = len(notas)
        indice = f"mod(floor(t/{duracion}),{n})"
        return "+".join(f"eq({indice},{i})*{f}" for i, f in enumerate(notas))

    melodia = f"0.32*sin(2*PI*({secuencia(MELODIA_COMICA, PULSO_COMICO)})*t)*exp(-9*mod(t,{PULSO_COMICO}))"
    bajo = f"0.45*sin(2*PI*({secuencia(BAJO_COMICO, PULSO_COMICO * 4)})*t)*exp(-5*mod(t,{PULSO_COMICO * 2}))"
    return f"{melodia}+{bajo}"


def expresion(tono: dict) -> str:
    """Expresión de aevalsrc: dos acordes con leve desafinado (efecto coro) que se alternan cada 8 s."""
    def acorde(notas):
        return "+".join(f"sin(2*PI*{N[n]}*t)+sin(2*PI*{N[n] + 0.35}*t)" for n in notas)

    peso = "(0.5+0.5*cos(2*PI*t/16))"  # 1 → 0 → 1 en 16 s: transición suave entre acordes
    a, b = tono["acordes"]
    capa = f"({peso}*({acorde(a)})+(1-{peso})*({acorde(b)}))*0.06*(1+0.12*sin(2*PI*0.2*t))"
    if tono["pulso"]:
        periodo = 60 / tono["pulso"]
        capa += f"+0.5*sin(2*PI*52*t)*exp(-7*mod(t,{periodo:.4f}))"  # latido grave tipo tambor
    return capa


def generar(nombre: str, destino: Path) -> None:
    tono = TONOS[nombre]
    eco = "aecho=0.8:0.3:90:0.15," if tono.get("comico") else "aecho=0.8:0.6:180|320:0.35|0.25,"
    filtro = (
        f"lowpass=f={tono['brillo']},"
        f"{eco}"  # algo de reverberación (poca en la cómica: así suena más seca y saltarina)
        "afade=t=in:d=2,"
        f"afade=t=out:st={DURACION - 2}:d=2,"
        "loudnorm=I=-20:TP=-2"
    )
    comando = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i",
        f"aevalsrc='{expresion_comica() if tono.get('comico') else expresion(tono)}':s=44100:d={DURACION}",
        "-af", filtro, "-ac", "2", "-b:a", "160k", str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"no se pudo generar {nombre}: {resultado.stderr[-300:]}")


def asegurar_pistas(rehacer: bool = False) -> None:
    """Crea las pistas generadas que falten en musica/."""
    CARPETA_MUSICA.mkdir(exist_ok=True)
    for nombre in TONOS:
        destino = CARPETA_MUSICA / f"{nombre}.mp3"
        if rehacer or not destino.exists():
            print(f"Generando música «{nombre}»…")
            generar(nombre, destino)


def pistas_disponibles() -> list:
    """Nombres de las pistas que se pueden elegir (sin extensión), las generadas primero."""
    propias = sorted(p.stem for p in CARPETA_MUSICA.glob("*.mp3") if p.stem not in TONOS)
    return [n for n in TONOS if (CARPETA_MUSICA / f"{n}.mp3").exists()] + propias


def ruta_pista(nombre: str):
    """Ruta del mp3 de una pista, o None si es «ninguna» o no existe."""
    if not nombre or nombre == "ninguna":
        return None
    ruta = CARPETA_MUSICA / f"{nombre}.mp3"
    return ruta if ruta.is_file() else None


if __name__ == "__main__":
    asegurar_pistas(rehacer="--rehacer" in sys.argv)
    print("Pistas disponibles:", ", ".join(pistas_disponibles()))
