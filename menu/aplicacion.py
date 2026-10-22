"""Abre el menú como una aplicación de escritorio, en su propia ventana (sin navegador ni consola).

Arranca el servidor del menú dentro de este mismo proceso y lo muestra con pywebview (el motor
WebView2 de Edge que trae Windows). Al cerrar la ventana se apaga todo.

    .venv\\Scripts\\pythonw.exe menu\\aplicacion.py      (o doble clic en «Mente Inquieta.exe»)
"""

import ctypes
import os
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
os.chdir(RAIZ)

# Con pythonw no hay consola: lo que se imprimiría va a un registro para poder ver errores.
REGISTRO = RAIZ / "salida" / "_trabajo" / "menu.log"
if sys.stdout is None or sys.stderr is None:
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(REGISTRO, "a", encoding="utf-8", buffering=1)
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

import webview  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as menu  # noqa: E402

ICONO = Path(__file__).resolve().parent / "static" / "icono.ico"
DATOS_VENTANA = RAIZ / "salida" / "_trabajo" / "ventana"  # localStorage (tema claro/oscuro…)


def aviso(texto, titulo="Mente Inquieta", botones=0x40):
    """Cuadro de diálogo nativo de Windows. Devuelve el botón pulsado (6 = Sí)."""
    return ctypes.windll.user32.MessageBoxW(None, texto, titulo, botones | 0x10000)  # 0x10000: al frente


def arrancar_servidor():
    menu.paso3_video.migrar_videos_antiguos()
    menu.musica.asegurar_pistas()
    hilo = threading.Thread(
        target=lambda: menu.app.run(host="127.0.0.1", port=menu.PUERTO, debug=False, threaded=True),
        daemon=True,
    )
    hilo.start()
    for _ in range(100):  # hasta 10 s
        if menu.puerto_ocupado():
            return True
        time.sleep(0.1)
    return False


def al_cerrar():
    """Si hay tareas en marcha, pregunta antes de cerrar (cerrar la ventana las detiene)."""
    activos = len(menu.cola.activos())
    if not activos:
        return True
    respuesta = aviso(
        f"Hay {activos} tarea(s) en marcha. Si cierras, se detendrán.\n\n¿Cerrar de todos modos?",
        botones=0x04 | 0x30,  # Sí / No, icono de advertencia
    )
    if respuesta != 6:
        return False
    for trabajo in menu.cola.activos():  # para no dejar procesos sueltos (ffmpeg, voz…)
        try:
            menu.cola.cancelar(trabajo.id)
        except Exception:
            pass
    return True


def main():
    # Para que la barra de tareas muestre el icono de la app y no el de Python.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MenteInquieta.Menu")

    if menu.puerto_ocupado():
        # El menú ya está abierto (otra ventana o «Abrir menu.bat»): esta ventana se conecta a él.
        propio = False
    else:
        propio = True
        if not arrancar_servidor():
            aviso(f"No he podido arrancar el menú en el puerto {menu.PUERTO}.\nMira {REGISTRO}.", botones=0x10)
            return

    webview.settings["ALLOW_DOWNLOADS"] = True  # p. ej. el .ics de «Añadir al calendario»
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # YouTube, Google Cloud… en el navegador

    # Tamaño a la medida de la pantalla (en píxeles lógicos, ya con la escala de Windows aplicada).
    pantalla = webview.screens[0] if webview.screens else None
    ancho = min(1280, int(pantalla.width * 0.88)) if pantalla else 1180
    alto = min(860, int(pantalla.height * 0.85)) if pantalla else 760

    ventana = webview.create_window(
        "Mente Inquieta",
        f"http://127.0.0.1:{menu.PUERTO}",
        width=ancho,
        height=alto,
        x=(pantalla.width - ancho) // 2 if pantalla else None,
        y=(pantalla.height - alto) // 2 if pantalla else None,
        min_size=(420, 560),
        background_color="#0d0f15",
        text_select=True,
    )
    if propio:
        ventana.events.closing += al_cerrar

    DATOS_VENTANA.mkdir(parents=True, exist_ok=True)
    webview.start(
        icon=str(ICONO) if ICONO.exists() else None,
        private_mode=False,
        storage_path=str(DATOS_VENTANA),
    )
    os._exit(0)  # apaga el servidor y cualquier hilo que quede


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # sin consola, el error se vería solo en el registro
        import traceback

        traceback.print_exc()
        aviso(f"El menú se ha cerrado por un error:\n\n{error}\n\nDetalles en {REGISTRO}", botones=0x10)
