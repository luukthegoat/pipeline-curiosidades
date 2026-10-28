"""Banner (imagen de cabecera) del canal de YouTube «MenteInquieta67».

YouTube pide 2048x1152 y enseña un trozo distinto en cada pantalla:
  - TV: la imagen entera
  - Ordenador: una franja central de 2048x338 (más o menos, según el ancho)
  - Móvil: solo la zona segura central de 1235x338
Por eso el logo, el nombre y el lema van dentro de la zona segura; fuera solo hay decoración.

Crea en esta carpeta:
  - banner_youtube.png         : el banner para subir
  - vista_previa_banner.png    : cómo se ve en TV, ordenador y móvil

Uso (desde la carpeta principal):  .venv\\Scripts\\python.exe marca\\crear_banner.py
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import crear_logo as logo

CARPETA = Path(__file__).resolve().parent
ANCHO, ALTO = 2048, 1152
SEGURA = (1235, 338)        # zona visible en todos los dispositivos
ESCRITORIO = (2048, 338)    # franja que suele verse en ordenador
NOMBRE = "MenteInquieta67"
LEMA = "Curiosidades en 1 minuto · historia, ciencia y misterios"


def fuente(nombre: str, tamano: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(nombre, tamano)
    except OSError:
        return ImageFont.load_default()


def fondo() -> Image.Image:
    """Degradado radial oscuro, más claro en el centro (donde va el contenido)."""
    peq = (256, 144)
    img = Image.new("RGB", peq)
    pix = img.load()
    cx, cy = peq[0] / 2, peq[1] / 2
    for y in range(peq[1]):
        for x in range(peq[0]):
            t = min(1.0, math.hypot((x - cx) / 1.4, y - cy) / (peq[1] * 0.75))
            pix[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(logo.FONDO_CENTRO, logo.FONDO_BORDE))
    return img.resize((ANCHO, ALTO), Image.BICUBIC)


def chispas_decorativas(img: Image.Image) -> None:
    """Chispas doradas tenues repartidas por los lados (fuera de la zona del texto)."""
    capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    azar = random.Random(7)  # siempre igual
    x0, y0 = (ANCHO - SEGURA[0]) / 2, (ALTO - SEGURA[1]) / 2
    colocadas = 0
    while colocadas < 26:
        x, y = azar.uniform(40, ANCHO - 40), azar.uniform(40, ALTO - 40)
        if x0 - 60 < x < x0 + SEGURA[0] + 60 and y0 - 60 < y < y0 + SEGURA[1] + 60:
            continue  # no tapar el contenido
        radio = azar.uniform(8, 30)
        alfa = int(azar.uniform(60, 170))
        logo.chispa(d, x, y, radio, logo.DORADO + (alfa,), 0.25)
        colocadas += 1
    img.paste(Image.alpha_composite(img.convert("RGBA"), capa).convert("RGB"))


def crear() -> Image.Image:
    img = fondo()
    chispas_decorativas(img)

    d = ImageDraw.Draw(img)
    # Todo (logo + texto) tiene que caber en la zona segura con margen: se reduce hasta que quepa.
    for escala in [1 - i * 0.04 for i in range(15)]:
        tam_logo = round(300 * escala)
        f_nombre = fuente("ariblk.ttf", round(118 * escala))
        f_lema = fuente("segoeui.ttf", round(40 * escala))
        separacion = round(40 * escala)
        ancho_texto = max(d.textlength(NOMBRE, font=f_nombre), d.textlength(LEMA, font=f_lema))
        total = tam_logo + separacion + ancho_texto
        if total <= SEGURA[0] - 90 and tam_logo <= SEGURA[1] - 20:
            break

    # Logo: la foto de perfil recortada en círculo con borde suave, a la izquierda del texto.
    icono = logo.crear().resize((tam_logo, tam_logo), Image.LANCZOS)
    mascara = Image.new("L", (tam_logo, tam_logo), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, tam_logo, tam_logo), fill=255)
    mascara = mascara.filter(ImageFilter.GaussianBlur(14))
    x = (ANCHO - total) / 2
    cy = ALTO / 2
    img.paste(icono, (round(x), round(cy - tam_logo / 2)), mascara)

    tx = x + tam_logo + separacion
    alto_nombre = f_nombre.size
    d.text((tx, cy - alto_nombre * 0.92), NOMBRE, font=f_nombre, fill=(255, 255, 255))
    d.text((tx + 4, cy + alto_nombre * 0.36), LEMA, font=f_lema, fill=logo.DORADO)
    return img


def vista_previa(banner: Image.Image) -> Image.Image:
    """Tres recortes: TV (entera), ordenador (franja) y móvil (zona segura)."""
    escala = 0.3
    tv = banner.resize((round(ANCHO * escala), round(ALTO * escala)), Image.LANCZOS)

    def recorte(ancho, alto):
        x0, y0 = (ANCHO - ancho) // 2, (ALTO - alto) // 2
        parte = banner.crop((x0, y0, x0 + ancho, y0 + alto))
        return parte.resize((round(ancho * escala), round(alto * escala)), Image.LANCZOS)

    pc, movil = recorte(*ESCRITORIO), recorte(*SEGURA)
    hoja = Image.new("RGB", (tv.width + 40, tv.height + pc.height + movil.height + 160), (245, 245, 245))
    d = ImageDraw.Draw(hoja)
    f = fuente("segoeui.ttf", 18)
    y = 10
    for titulo, parte in (("TV (imagen entera)", tv), ("Ordenador", pc), ("Móvil (zona segura)", movil)):
        d.text((20, y), titulo, font=f, fill=(40, 40, 40))
        hoja.paste(parte, (20, y + 26))
        y += parte.height + 50
    return hoja


if __name__ == "__main__":
    banner = crear()
    banner.save(CARPETA / "banner_youtube.png", optimize=True)
    vista_previa(banner).save(CARPETA / "vista_previa_banner.png")
    print("Creado:", CARPETA / "banner_youtube.png",
          f"({(CARPETA / 'banner_youtube.png').stat().st_size / 1024 / 1024:.1f} MB)")
