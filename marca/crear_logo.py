"""Foto de perfil de «MenteInquieta67»: bombilla dorada con una chispa dentro, sobre fondo oscuro.

Crea en esta carpeta:
  - perfil_1080.png          : foto de perfil para TikTok / Instagram (1080x1080)
  - perfil_youtube_800.png   : versión para YouTube (800x800, con margen para el recorte en círculo)
  - vista_previa*.png        : cómo se ven recortadas en círculo, en grande y en pequeño

Uso (desde la carpeta principal):  .venv\\Scripts\\python.exe marca\\crear_logo.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

CARPETA = Path(__file__).resolve().parent
TAM = 1080
S = 4  # se dibuja a 4x y se reduce: bordes suaves
DORADO = (255, 196, 0)       # el mismo amarillo de los subtítulos
DORADO_CLARO = (255, 226, 120)
FONDO_CENTRO = (30, 36, 54)
FONDO_BORDE = (10, 12, 20)


def fondo() -> Image.Image:
    """Degradado radial oscuro (más claro en el centro)."""
    pequeno = 270
    img = Image.new("RGB", (pequeno, pequeno))
    pix = img.load()
    c = pequeno / 2
    for y in range(pequeno):
        for x in range(pequeno):
            t = min(1.0, math.hypot(x - c, y - c) / (pequeno * 0.62))
            pix[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(FONDO_CENTRO, FONDO_BORDE))
    return img.resize((TAM * S, TAM * S), Image.BICUBIC)


def silueta_bombilla(d: ImageDraw.ImageDraw, color, encoger: float = 0) -> None:
    """Cristal (círculo) + cuello que se estrecha hacia la rosca. `encoger` la reduce para hacer el contorno."""
    cx, cy, r = 540 * S, 455 * S, 235 * S
    r -= encoger
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    arriba, abajo = cy + 150 * S, 735 * S
    ancho_arriba, ancho_abajo = 150 * S - encoger, 92 * S - encoger
    d.polygon([(cx - ancho_arriba, arriba), (cx + ancho_arriba, arriba),
               (cx + ancho_abajo, abajo - encoger * 0.3), (cx - ancho_abajo, abajo - encoger * 0.3)], fill=color)


def chispa(d: ImageDraw.ImageDraw, cx, cy, radio, color, delgadez: float = 0.22) -> None:
    """Destello de cuatro puntas."""
    puntos = []
    for i in range(8):
        angulo = math.pi / 4 * i - math.pi / 2
        r = radio if i % 2 == 0 else radio * delgadez
        puntos.append((cx + r * math.cos(angulo), cy + r * math.sin(angulo)))
    d.polygon(puntos, fill=color)


def crear() -> Image.Image:
    lienzo = fondo().convert("RGBA")

    # Halo dorado suave detrás de la bombilla
    halo = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((540 * S - 330 * S, 455 * S - 330 * S, 540 * S + 330 * S, 455 * S + 330 * S),
                                 fill=DORADO + (70,))
    lienzo = Image.alpha_composite(lienzo, halo.filter(ImageFilter.GaussianBlur(90 * S)))

    capa = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    # Contorno de la bombilla: silueta dorada y, encima, la misma silueta más pequeña en oscuro
    silueta_bombilla(d, DORADO + (255,))
    silueta_bombilla(d, (22, 26, 40, 255), encoger=30 * S)
    # Rosca: tres franjas redondeadas
    for i, ancho in enumerate((96, 86, 70)):
        y = (752 + i * 42) * S
        d.rounded_rectangle((540 * S - ancho * S, y, 540 * S + ancho * S, y + 28 * S), radius=14 * S,
                            fill=DORADO + (255,))
    # La chispa dentro del cristal (la «idea») y dos pequeñas fuera (la mente «inquieta»)
    chispa(d, 540 * S, 450 * S, 150 * S, DORADO_CLARO + (255,))
    chispa(d, 820 * S, 235 * S, 52 * S, DORADO + (255,), 0.28)
    chispa(d, 268 * S, 250 * S, 34 * S, DORADO + (255,), 0.3)
    lienzo = Image.alpha_composite(lienzo, capa)
    return lienzo.resize((TAM, TAM), Image.LANCZOS).convert("RGB")


def crear_youtube(tam: int = 800, escala: float = 0.82) -> Image.Image:
    """Versión para YouTube (800x800): el dibujo algo más pequeño y centrado para que el recorte en
    círculo no toque las chispas en ningún dispositivo (móvil, TV, ordenador)."""
    base = crear()
    fondo_limpio = fondo().resize((TAM, TAM), Image.LANCZOS)
    # El dibujo es lo que se diferencia del fondo: se reduce y se pega centrado sobre un fondo nuevo.
    reducido = base.resize((round(TAM * escala), round(TAM * escala)), Image.LANCZOS)
    mascara = Image.new("L", reducido.size, 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, *reducido.size), fill=255)
    mascara = mascara.filter(ImageFilter.GaussianBlur(reducido.width * 0.06))  # borde invisible
    margen = (TAM - reducido.width) // 2
    fondo_limpio.paste(reducido, (margen, margen), mascara)
    return fondo_limpio.resize((tam, tam), Image.LANCZOS)


def vista_previa(perfil: Image.Image) -> Image.Image:
    """La foto recortada en círculo (como en TikTok/YouTube) a 300 px y a 80 px."""
    hoja = Image.new("RGB", (520, 320), (245, 245, 245))
    for tam, x in ((300, 10), (80, 360)):
        foto = perfil.resize((tam, tam), Image.LANCZOS)
        mascara = Image.new("L", (tam * 4, tam * 4), 0)
        ImageDraw.Draw(mascara).ellipse((0, 0, tam * 4, tam * 4), fill=255)
        hoja.paste(foto, (x, 10), mascara.resize((tam, tam), Image.LANCZOS))
    return hoja


if __name__ == "__main__":
    perfil = crear()
    perfil.save(CARPETA / "perfil_1080.png")
    vista_previa(perfil).save(CARPETA / "vista_previa.png")
    youtube = crear_youtube()
    youtube.save(CARPETA / "perfil_youtube_800.png")
    vista_previa(youtube).save(CARPETA / "vista_previa_youtube.png")
    print("Creado:", CARPETA / "perfil_1080.png", "y", CARPETA / "perfil_youtube_800.png")
