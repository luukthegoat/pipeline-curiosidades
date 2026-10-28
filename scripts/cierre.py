"""Toma final de cada vídeo: «¿Quieres la parte 2? Dale a like y suscríbete».

Animación de ~4 s con la estética del canal: la pregunta en grande, un 👍 que salta, una mano que pulsa el
botón «SUSCRIBIRSE» (que pasa a «SUSCRITO ✓»), la campana que suena 🔔 y un estallido de chispas doradas.
La frase la dice la misma voz del vídeo.

En los vídeos de tono triste (p. ej. un atentado) el cierre es sobrio: sin chispas ni campana bailando.

El segmento se guarda en caché: solo se vuelve a crear si cambia el texto, la voz o el diseño.
"""
import asyncio
import math
import subprocess
from pathlib import Path

import imageio_ffmpeg
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont

import paso2_audio

ANCHO, ALTO, FPS = 1080, 1920, 30
VERSION = "4"  # súbela si cambias el diseño: se rehacen los cierres en caché
DORADO = (255, 196, 0)
ROJO = (204, 0, 0)
GRIS = (60, 60, 64)
FONDO_CENTRO, FONDO_BORDE = (30, 36, 54), (10, 12, 20)


def _fuente(nombre: str, tamano: int):
    try:
        return ImageFont.truetype(nombre, tamano)
    except OSError:
        return ImageFont.load_default()


def textos(datos: dict) -> dict:
    """Pregunta en pantalla, frase de la voz y botones, según el tipo de vídeo y el idioma."""
    ingles = datos.get("idioma") == "en"
    serie, diario = datos.get("serie") or {}, datos.get("diario")
    sobrio = datos.get("musica") == "triste"
    if sobrio:
        pregunta = "MORE HISTORY?" if ingles else "¿MÁS HISTORIA?"
        voz = "Subscribe for more history." if ingles else "Suscríbete para más historia."
    elif serie.get("total", 1) > 1 and serie["parte"] < serie["total"]:
        siguiente = serie["parte"] + 1
        pregunta = f"PART {siguiente}?" if ingles else f"¿PARTE {siguiente}?"
        voz = f"Part {siguiente}? Subscribe." if ingles else f"¿Parte {siguiente}? Suscríbete."
    elif diario:
        siguiente = diario["dia"] + 1
        pregunta = f"DAY {siguiente}?" if ingles else f"¿DÍA {siguiente}?"
        voz = f"Day {siguiente}? Subscribe." if ingles else f"¿Día {siguiente}? Suscríbete."
    else:
        pregunta = "WANT MORE?" if ingles else "¿QUIERES MÁS?"
        voz = "Want more? Subscribe." if ingles else "¿Quieres más? Suscríbete."
    return {
        "pregunta": pregunta, "voz": voz, "sobrio": sobrio,
        "boton": "SUBSCRIBE" if ingles else "SUSCRIBIRSE",
        "boton_hecho": "SUBSCRIBED" if ingles else "SUSCRITO",
        "pie": "Like 👍 · Subscribe 🔔" if ingles else "Like 👍 · Suscríbete 🔔",
    }


# --- Dibujo de los fotogramas ---------------------------------------------------------

def _fondo() -> Image.Image:
    peq = Image.new("RGB", (108, 192))
    pix = peq.load()
    for y in range(192):
        for x in range(108):
            t = min(1.0, math.hypot(x - 54, (y - 96) * 0.6) / 80)
            pix[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(FONDO_CENTRO, FONDO_BORDE))
    return peq.resize((ANCHO, ALTO), Image.BICUBIC)


def _chispa(d: ImageDraw.ImageDraw, cx, cy, r, color):
    puntos = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.25
        puntos.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(puntos, fill=color)


def _salto(t: float, inicio: float, duracion: float = 0.35) -> float:
    """Escala con rebote (0 → 1.15 → 1) a partir de `inicio`."""
    if t < inicio:
        return 0.0
    x = min(1.0, (t - inicio) / duracion)
    return 1 + 0.15 * math.sin(math.pi * x) if x < 1 else 1.0


def _emoji(texto: str, tamano: int) -> Image.Image:
    fuente = _fuente("seguiemj.ttf", 109)  # Segoe UI Emoji solo dibuja en color a este tamaño: luego se escala
    capa = Image.new("RGBA", (260, 260), (0, 0, 0, 0))  # lienzo holgado: que no se corte ningún borde
    ImageDraw.Draw(capa).text((60, 60), texto, font=fuente, embedded_color=True)
    capa = capa.crop(capa.getbbox() or (0, 0, 260, 260))
    escala = tamano / max(capa.size)
    return capa.resize((max(1, round(capa.width * escala)), max(1, round(capa.height * escala))), Image.LANCZOS)


class Dibujante:
    def __init__(self, info: dict, duracion: float):
        self.info, self.duracion = info, duracion
        self.fondo = _fondo()
        # La letra más grande con la que la pregunta cabe a lo ancho incluso con el «pop» (x1,15).
        medidor = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        for tamano in range(128, 50, -4):
            self.f_pregunta = _fuente("ariblk.ttf", tamano)
            if (medidor.textlength(info["pregunta"], font=self.f_pregunta) + 80) * 1.15 <= ANCHO - 60:
                break
        self.f_boton = _fuente("ariblk.ttf", 70)
        self.f_texto = _fuente("ariblk.ttf", 52)
        self.f_check = _fuente("seguisym.ttf", 70)
        self.pulgar = _emoji("👍", 260)
        self.campana = _emoji("🔔", 110)
        self.mano = _emoji("👆", 170)
        self.clic = 1.1  # segundo en que la mano pulsa el botón (el cierre es corto: la gente desliza al final)

    def fotograma(self, t: float) -> Image.Image:
        info, sobrio = self.info, self.info["sobrio"]
        img = self.fondo.copy()
        d = ImageDraw.Draw(img)

        # Pregunta en grande, con un pequeño «pop» al entrar
        escala = max(0.01, _salto(t, 0.0, 0.3))
        texto = info["pregunta"]
        ancho = d.textlength(texto, font=self.f_pregunta)
        if escala > 0:
            capa = Image.new("RGBA", (int(ancho) + 60, 220), (0, 0, 0, 0))
            ImageDraw.Draw(capa).text((30, 10), texto, font=self.f_pregunta, fill=DORADO,
                                      stroke_width=10, stroke_fill=(0, 0, 0))
            capa = capa.resize((max(1, int(capa.width * escala)), max(1, int(capa.height * escala))), Image.LANCZOS)
            img.paste(capa, ((ANCHO - capa.width) // 2, 330 - capa.height // 2), capa)

        # 👍 que salta (y vuelve a saltar cuando se pulsa «suscribirse»)
        e = _salto(t, 0.35) * (1 if sobrio else (1 + 0.12 * max(0.0, math.sin(math.pi * min(1, max(0, (t - self.clic) / 0.3))))))
        if e > 0:
            p = self.pulgar.resize((max(1, int(self.pulgar.width * e)), max(1, int(self.pulgar.height * e))), Image.LANCZOS)
            img.paste(p, ((ANCHO - p.width) // 2, 700 - p.height // 2), p)

        # Chispas doradas que salen del 👍 al pulsar (no en el cierre sobrio)
        if not sobrio and t > self.clic:
            avance = min(1.0, (t - self.clic) / 0.9)
            alfa = int(255 * (1 - avance))
            capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
            dc = ImageDraw.Draw(capa)
            for i in range(10):
                angulo = 2 * math.pi * i / 10 + 0.3
                r = 160 + 260 * avance
                _chispa(dc, ANCHO / 2 + r * math.cos(angulo), 700 + r * math.sin(angulo),
                        26 + 10 * (i % 3), DORADO + (alfa,))
            img.paste(capa, (0, 0), capa)

        # Botón «SUSCRIBIRSE» → «SUSCRITO ✓» (se hunde un instante al pulsarlo)
        pulsado = t >= self.clic
        hundido = 0.94 if self.clic <= t < self.clic + 0.12 else 1.0
        bw, bh = 640 * hundido, 150 * hundido
        x0, y0 = (ANCHO - bw) / 2, 1050 - bh / 2
        d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=bh / 2, fill=GRIS if pulsado else ROJO)
        etiqueta = info["boton_hecho"] if pulsado else info["boton"]
        ancho_etiqueta = d.textlength(etiqueta, font=self.f_boton) + (70 if pulsado else 0)
        tx = (ANCHO - ancho_etiqueta) / 2
        d.text((tx, 1050 - 45), etiqueta, font=self.f_boton, fill=(255, 255, 255))
        if pulsado:
            d.text((tx + ancho_etiqueta - 55, 1050 - 48), "✓", font=self.f_check, fill=(255, 255, 255))

        # Campana al lado del botón: tras pulsar, suena (se balancea) salvo en el cierre sobrio
        angulo = 0.0
        if pulsado and not sobrio:
            angulo = 22 * math.sin((t - self.clic) * 18) * math.exp(-(t - self.clic) * 2.2)
        campana = self.campana.rotate(angulo, resample=Image.BICUBIC, expand=True)
        img.paste(campana, (int(x0 + bw + 30), int(1050 - campana.height / 2)), campana)

        # Mano que entra desde abajo, pulsa y se retira
        if t < self.clic + 0.7:
            if t < self.clic:
                avance = min(1.0, t / self.clic)
                y = 1900 - (1900 - 1110) * (1 - (1 - avance) ** 3)
            else:
                y = 1110 + 600 * max(0.0, (t - self.clic - 0.25) / 0.45) ** 2
            img.paste(self.mano, (int(ANCHO / 2 + 40), int(y)), self.mano)

        # Pie: la marca del canal
        pie = "MenteInquieta67"
        d.text(((ANCHO - d.textlength(pie, font=self.f_texto)) / 2, 1560), pie, font=self.f_texto, fill=(255, 255, 255))
        return img


# --- Segmento de vídeo ------------------------------------------------------------------

def crear(datos: dict, trabajo: Path, huella) -> tuple:
    """Crea (o reutiliza) el segmento final. Devuelve (ruta del .mp4, duración en segundos)."""
    info = textos(datos)
    idioma = datos.get("idioma", "es")
    voz = paso2_audio.VOCES.get(idioma, paso2_audio.VOCES["es"])
    salida, clave = trabajo / "seg_cierre.mp4", trabajo / "seg_cierre.clave"
    firma = huella(VERSION, info, voz, paso2_audio.VELOCIDAD)
    if salida.exists() and clave.exists() and clave.read_text().startswith(firma):
        return salida, float(clave.read_text().split("|")[1])

    bruto, audio = trabajo / "cierre_voz.mp3", trabajo / "cierre.mp3"
    asyncio.run(paso2_audio.sintetizar(info["voz"], voz, bruto))
    # La voz sintética trae silencio al principio y al final: fuera, para que el cierre dure lo justo.
    recorte = "silenceremove=start_periods=1:start_threshold=-45dB"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(bruto),
                    "-af", f"{recorte},areverse,{recorte},areverse", str(audio)], check=True)
    duracion = MP3(audio).info.length + 0.3
    duracion = max(duracion, 2.3)

    dibujante = Dibujante(info, duracion)
    comando = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-",
        "-i", str(audio.resolve()),
        "-filter_complex", f"[1:a]apad=whole_dur={duracion:.3f}[a]", "-map", "0:v", "-map", "[a]",
        "-t", f"{duracion:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", salida.name,
    ]
    proceso = subprocess.Popen(comando, cwd=trabajo, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for n in range(round(duracion * FPS)):
        proceso.stdin.write(dibujante.fotograma(n / FPS).tobytes())
    proceso.stdin.close()
    if proceso.wait() != 0:
        raise RuntimeError(f"ffmpeg falló al crear el cierre: {proceso.stderr.read().decode(errors='replace')[-300:]}")
    clave.write_text(f"{firma}|{duracion:.3f}")
    return salida, duracion
