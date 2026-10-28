"""Abre el menú como una aplicación de escritorio, en su propia ventana (sin navegador ni consola).

Arranca el servidor del menú dentro de este mismo proceso y lo muestra con pywebview (el motor
WebView2 de Edge que trae Windows). Al cerrar la ventana se apaga todo.

    .venv\\Scripts\\pythonw.exe menu\\aplicacion.py      (o doble clic en «MenteInquieta67.exe»)

- La ventana aparece al momento con una pantalla de carga; el menú se carga mientras tanto.
- Solo hay una copia abierta: si ya lo estaba (o se está abriendo), se trae al frente esa ventana.
"""

import base64
import ctypes
import os
import socket
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

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")
import webview  # noqa: E402

TITULO = "MenteInquieta67"
PUERTO = int(os.getenv("MENU_PUERTO") or 8765)
URL = f"http://127.0.0.1:{PUERTO}"
ESTATICOS = Path(__file__).resolve().parent / "static"
ICONO = ESTATICOS / "icono.ico"
DATOS_VENTANA = RAIZ / "salida" / "_trabajo" / "ventana"  # localStorage (tema claro/oscuro…)

menu = None  # el módulo app.py, que se importa ya con la ventana abierta (tarda unos segundos)
_mutex = None


def aviso(texto, botones=0x40):
    """Cuadro de diálogo nativo de Windows. Devuelve el botón pulsado (6 = Sí)."""
    return ctypes.windll.user32.MessageBoxW(None, texto, TITULO, botones | 0x10000)  # 0x10000: al frente


def ya_abierta() -> bool:
    """¿Hay otra copia de la aplicación abierta (o abriéndose)? Usa un mutex con nombre de Windows."""
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "MenteInquieta.Menu")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def traer_al_frente() -> None:
    """Muestra la ventana de la otra copia (espera un poco por si aún se está abriendo)."""
    u = ctypes.windll.user32
    for _ in range(100):  # hasta 10 s
        ventana = u.FindWindowW(None, TITULO)
        if ventana:
            u.ShowWindow(ventana, 9)  # SW_RESTORE: por si está minimizada
            u.SetForegroundWindow(ventana)
            return
        time.sleep(0.1)


def puerto_ocupado() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PUERTO)) == 0


def pantalla_de_carga() -> str:
    logo = base64.b64encode((ESTATICOS / "logo.png").read_bytes()).decode()
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      :root {{ color-scheme: dark; }}
      body {{ margin: 0; height: 100vh; display: grid; place-items: center; background: #0d0f15; color: #9ba1ae;
             font: 15px "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif; }}
      @media (prefers-color-scheme: light) {{ body {{ background: #f7f7f5; color: #6b6e76; }} }}
      .caja {{ display: grid; justify-items: center; gap: 18px; }}
      img {{ width: 72px; height: 72px; border-radius: 18px; animation: latido 1.6s ease-in-out infinite; }}
      .barra {{ width: 140px; height: 3px; border-radius: 3px; background: rgba(128,128,128,.2); overflow: hidden; }}
      .barra::after {{ content: ""; display: block; width: 40%; height: 100%; border-radius: 3px; background: #ffc400;
                      animation: carga 1.1s ease-in-out infinite; }}
      @keyframes latido {{ 50% {{ transform: scale(1.05); filter: brightness(1.15); }} }}
      @keyframes carga {{ from {{ transform: translateX(-100%); }} to {{ transform: translateX(250%); }} }}
    </style></head><body><div class="caja">
      <img src="data:image/png;base64,{logo}" alt=""><div class="barra"></div><div>Abriendo MenteInquieta67…</div>
    </div></body></html>"""


def arrancar_servidor() -> bool:
    menu.paso3_video.migrar_videos_antiguos()
    menu.musica.asegurar_pistas()
    menu.vigilar_programados()  # sube los vídeos programados cuando toca
    threading.Thread(
        target=lambda: menu.app.run(host="127.0.0.1", port=PUERTO, debug=False, threaded=True),
        daemon=True,
    ).start()
    for _ in range(150):  # hasta 15 s
        if puerto_ocupado():
            return True
        time.sleep(0.1)
    return False


def preparar(ventana, servidor_externo: bool) -> None:
    """Se ejecuta con la ventana ya visible: carga el menú y, cuando está listo, lo muestra."""
    global menu
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import app

        menu = app
        if not servidor_externo and not arrancar_servidor():
            raise RuntimeError(f"no he podido arrancar el menú en el puerto {PUERTO}")
        ventana.load_url(URL)
    except Exception as error:
        import traceback

        traceback.print_exc()
        ventana.load_html(f"""<body style="font: 15px 'Segoe UI', sans-serif; padding: 40px; background: #0d0f15;
            color: #eceef3"><h2>No se ha podido abrir el menú</h2><p>{error}</p>
            <p style="color: #9ba1ae">Detalles en {REGISTRO}</p></body>""")


def al_cerrar():
    """Si hay tareas en marcha, pregunta antes de cerrar (cerrar la ventana las detiene)."""
    if menu is None:
        return True
    activos = menu.cola.activos()
    if not activos:
        return True
    respuesta = aviso(
        f"Hay {len(activos)} tarea(s) en marcha. Si cierras, se detendrán.\n\n¿Cerrar de todos modos?",
        botones=0x04 | 0x30,  # Sí / No, icono de advertencia
    )
    if respuesta != 6:
        return False
    for trabajo in activos:  # para no dejar procesos sueltos (ffmpeg, voz…)
        try:
            menu.cola.cancelar(trabajo.id)
        except Exception:
            pass
    return True


def main():
    # Para que la barra de tareas muestre el icono de la app y no el de Python.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MenteInquieta.Menu")

    if ya_abierta():
        traer_al_frente()
        return
    # Si el menú ya está en marcha con «Abrir menu.bat», la ventana se conecta a ese servidor.
    servidor_externo = puerto_ocupado()

    webview.settings["ALLOW_DOWNLOADS"] = True  # p. ej. el .ics de «Añadir al calendario»
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # YouTube, Google Cloud… en el navegador

    # Tamaño a la medida de la pantalla (en píxeles lógicos, ya con la escala de Windows aplicada).
    pantalla = webview.screens[0] if webview.screens else None
    ancho = min(1280, int(pantalla.width * 0.88)) if pantalla else 1180
    alto = min(860, int(pantalla.height * 0.85)) if pantalla else 760

    ventana = webview.create_window(
        TITULO,
        html=pantalla_de_carga(),
        width=ancho,
        height=alto,
        x=(pantalla.width - ancho) // 2 if pantalla else None,
        y=(pantalla.height - alto) // 2 if pantalla else None,
        min_size=(420, 560),
        background_color="#0d0f15",
        text_select=True,
    )
    if not servidor_externo:
        ventana.events.closing += al_cerrar

    DATOS_VENTANA.mkdir(parents=True, exist_ok=True)
    webview.start(
        preparar, (ventana, servidor_externo),
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
