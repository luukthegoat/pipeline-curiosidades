"""Recordatorio para subir a mano a TikTok los vídeos del piloto automático.

Lo ejecuta Windows cada día a la hora de TikTok (y también puedes lanzarlo tú). Para cada vídeo
pendiente cuya hora ha llegado: muestra una notificación, copia el texto de TikTok al portapapeles
y abre su carpeta. Cuando lo hayas subido, márcalo como hecho en el menú → Piloto automático.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
os.chdir(RAIZ)

import avisos  # noqa: E402

PENDIENTES = Path("salida/_trabajo/tiktok_pendientes.json")


def texto_tiktok(ruta_txt: Path) -> str:
    """El bloque de TikTok del .txt del vídeo (lo que hay que pegar como descripción)."""
    try:
        lineas = ruta_txt.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    inicio = next((i for i, l in enumerate(lineas) if l.startswith("TIKTOK")), None)
    if inicio is None:
        return ""
    bloque = []
    for linea in lineas[inicio + 2:]:  # tras el título y la línea de «=»
        if linea.startswith("====="):
            break
        bloque.append(linea)
    return "\n".join(bloque).strip()


def main() -> int:
    try:
        pendientes = json.loads(PENDIENTES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    ahora = datetime.now()
    tocan = [p for p in pendientes if not p.get("hecho") and datetime.fromisoformat(p["hora"]) <= ahora]
    if not tocan:
        return 0
    primero = tocan[0]
    if len(tocan) == 1:
        avisos.notificar("Mente Inquieta · toca subir a TikTok",
                         f"«{primero['titulo']}». Te he copiado el texto y abierto su carpeta: súbelo en tiktok.com/upload.")
    else:
        avisos.notificar("Mente Inquieta · vídeos pendientes de TikTok",
                         f"Tienes {len(tocan)} vídeos por subir. Te copio el texto del primero: «{primero['titulo']}».")
    avisos.copiar_al_portapapeles(texto_tiktok(Path(primero["texto"])))
    carpeta = Path(primero["video"]).parent
    if carpeta.exists():
        os.startfile(carpeta.resolve())
    for p in tocan:
        p["avisado"] = True
    PENDIENTES.write_text(json.dumps(pendientes, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
