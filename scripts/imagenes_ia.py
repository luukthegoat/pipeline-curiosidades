"""Genera con IA (Pollinations, gratis y sin cuenta) las imágenes de las escenas de un diario.

Solo para el formato «Diario de…»: en vídeos de hechos reales se usan imágenes reales, porque una
imagen inventada de un suceso histórico puede engañar. Cada escena usa su prompt («visual») precedido
de la descripción del personaje, y todas la misma «semilla» para que el personaje se parezca entre sí.
Las imágenes llevan la marca de agua de Pollinations (obligatoria sin cuenta).

Uso:
    python scripts/imagenes_ia.py <guion> [<guion> …]     # nombre del guion (sin .json) o su ruta
    python scripts/imagenes_ia.py <guion> --rehacer       # vuelve a generarlas aunque ya existan
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote

import requests

import wikimedia  # mismas reglas de ritmo, caché y esperas para cualquier servidor externo

URL = "https://image.pollinations.ai/prompt/{prompt}?width=768&height=1365&seed={semilla}&model=flux&nologo=true"
CARPETA = Path("salida/imagenes_ia")
CARPETA_GUIONES = Path("salida/guiones")
ESTILO = "3D animated Pixar style, expressive cartoon character, comedic, cinematic lighting, vertical 9:16"
wikimedia.INTERVALO["image.pollinations.ai"] = 47.0  # gratis: 1 imagen cada 45 s por IP


def _ruta_guion(guion: str) -> Path:
    ruta = Path(guion)
    if ruta.suffix != ".json":
        ruta = CARPETA_GUIONES / f"{guion}.json"
    if not ruta.exists():
        raise ValueError(f"no existe el guion {ruta}")
    return ruta


def semilla(texto: str) -> int:
    """Siempre la misma para el mismo personaje: así se parece de una escena (y de un día) a otro."""
    return int(hashlib.sha1(texto.encode()).hexdigest()[:8], 16) % 1_000_000


def generar(ruta_guion: Path, rehacer: bool = False) -> int:
    """Genera las imágenes que falten y las asigna a sus escenas. Devuelve cuántas ha generado."""
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    diario = guion.get("diario")
    if not diario:
        raise ValueError("solo se generan imágenes con IA para el formato «Diario de…»")
    personaje = guion.get("personaje_visual") or diario["personaje"]
    numero_semilla = semilla(diario["personaje"])
    carpeta = CARPETA / ruta_guion.stem
    hechas = 0
    for escena in guion["escenas"]:
        actual = escena.get("imagen") or {}
        if actual and not (rehacer and actual.get("ia")):
            continue  # ya tiene imagen (elegida a mano o generada antes)
        prompt = f"{personaje}. {escena.get('visual', '')}. {ESTILO}"[:900]
        destino = carpeta / f"escena_{escena['numero']:02d}.jpg"
        if rehacer and destino.exists():
            destino.unlink()
        print(f"  escena {escena['numero']}: generando…", flush=True)
        wikimedia.archivo(URL.format(prompt=quote(prompt), semilla=numero_semilla), destino)
        escena["imagen"] = {
            "archivo": f"Imagen IA escena {escena['numero']}",
            "ruta": destino.as_posix(),
            "autor": "Generada con IA (Pollinations)",
            "licencia": "imagen generada con IA",
            "pagina": "https://pollinations.ai",
            "ia": True,
        }
        hechas += 1
    ruta_guion.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    return hechas


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Genera con IA las imágenes de un diario")
    parser.add_argument("guiones", nargs="+")
    parser.add_argument("--rehacer", action="store_true", help="vuelve a generar las imágenes hechas con IA")
    args = parser.parse_args(argv)
    fallidos = 0
    for guion in args.guiones:
        print(f"· {guion}")
        try:
            print(f"  {generar(_ruta_guion(guion), args.rehacer)} imágenes generadas")
        except (ValueError, requests.RequestException, OSError) as error:
            print(f"  error: {error}", file=sys.stderr)
            fallidos += 1
    return 0 if fallidos == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
