"""El nombre del canal, en un solo sitio: sale en la pantalla final de los vídeos, en la app y en los avisos.

Se cambia con NOMBRE_CANAL en .env. Los nombres internos (tareas de Windows, accesos directos) no dependen de esto.
"""
import os

from dotenv import load_dotenv

load_dotenv()

NOMBRE = (os.getenv("NOMBRE_CANAL") or "Neón y Gasolina").strip()
HANDLE = (os.getenv("HANDLE_CANAL") or "@NeonYGasolina").strip()
INICIALES = "".join(p[0] for p in NOMBRE.replace(" y ", " ").split()[:2]).upper() or "NG"
