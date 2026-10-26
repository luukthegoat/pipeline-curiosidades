"""Notificaciones de Windows (las que salen abajo a la derecha) para los vídeos programados."""
import os
import subprocess

# Notificación «toast» con lo que trae Windows PowerShell 5.1 (sin instalar nada). El texto va por variables
# de entorno para no tener problemas con comillas o acentos.
_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$plantilla = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textos = $plantilla.GetElementsByTagName("text")
$textos.Item(0).AppendChild($plantilla.CreateTextNode($env:AVISO_TITULO)) > $null
$textos.Item(1).AppendChild($plantilla.CreateTextNode($env:AVISO_TEXTO)) > $null
$aviso = [Windows.UI.Notifications.ToastNotification]::new($plantilla)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe").Show($aviso)
"""


def notificar(titulo: str, texto: str) -> bool:
    """Muestra una notificación de Windows. Devuelve False si no se pudo (no es grave)."""
    entorno = {**os.environ, "AVISO_TITULO": titulo[:120], "AVISO_TEXTO": texto[:400]}
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT],
            env=entorno, capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return resultado.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def copiar_al_portapapeles(texto: str) -> bool:
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:AVISO_TEXTO"],
                       env={**os.environ, "AVISO_TEXTO": texto}, capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except (OSError, subprocess.SubprocessError):
        return False
