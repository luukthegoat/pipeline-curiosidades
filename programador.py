"""Activa o desactiva las tareas diarias del piloto automático en el Programador de tareas de Windows.

Crea dos tareas (se ven en «Programador de tareas» de Windows, carpeta raíz):
  - «Mente Inquieta - crear video»          → automatico.py a la hora de creación
  - «Mente Inquieta - recordatorio TikTok»  → recordatorio_tiktok.py a la hora de TikTok
Si el ordenador está apagado a esa hora, se ejecutan en cuanto se encienda (StartWhenAvailable).
Se ejecutan con tu usuario y solo con la sesión iniciada; no necesitan tu contraseña.

Uso:
    python programador.py activar
    python programador.py desactivar
    python programador.py estado
"""
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PYTHONW = RAIZ / ".venv" / "Scripts" / "pythonw.exe"  # sin ventana negra
TAREAS = {
    "crear": ("Mente Inquieta - crear video", "automatico.py", "hora_creacion",
              "Crea el vídeo del día, lo programa en YouTube y apunta el recordatorio de TikTok."),
    "tiktok": ("Mente Inquieta - recordatorio TikTok", "recordatorio_tiktok.py", "hora_tiktok",
               "Avisa de los vídeos pendientes de subir a TikTok."),
}

_REGISTRAR = r"""
$accion = New-ScheduledTaskAction -Execute $env:T_EXE -Argument ('"' + $env:T_SCRIPT + '"') -WorkingDirectory $env:T_DIR
$disparador = New-ScheduledTaskTrigger -Daily -At $env:T_HORA
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $env:T_NOMBRE -Action $accion -Trigger $disparador -Settings $ajustes -Description $env:T_DESC -Force | Out-Null
"""
_BORRAR = r"Unregister-ScheduledTask -TaskName $env:T_NOMBRE -Confirm:$false -ErrorAction SilentlyContinue"
_ESTADO = r"""
$t = Get-ScheduledTask -TaskName $env:T_NOMBRE -ErrorAction SilentlyContinue
if ($t) {
  $i = $t | Get-ScheduledTaskInfo
  @{ existe = $true; proxima = "$($i.NextRunTime)"; ultima = "$($i.LastRunTime)"; resultado = $i.LastTaskResult } | ConvertTo-Json
} else { @{ existe = $false } | ConvertTo-Json }
"""


def _powershell(script: str, **variables) -> subprocess.CompletedProcess:
    entorno = {**os.environ, **{k: str(v) for k, v in variables.items()}}
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                          env=entorno, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def activar(config: dict) -> list:
    """Registra (o actualiza) las dos tareas con las horas de la configuración. Devuelve los errores."""
    errores = []
    ejecutable = PYTHONW if PYTHONW.exists() else Path(sys.executable)
    for nombre, script, clave_hora, descripcion in TAREAS.values():
        resultado = _powershell(_REGISTRAR, T_EXE=ejecutable, T_SCRIPT=RAIZ / script, T_DIR=RAIZ,
                                T_HORA=config.get(clave_hora, "10:00"), T_NOMBRE=nombre, T_DESC=descripcion)
        if resultado.returncode != 0:
            errores.append(f"{nombre}: {resultado.stderr.strip()[-300:]}")
    return errores


def desactivar() -> None:
    for nombre, *_ in TAREAS.values():
        _powershell(_BORRAR, T_NOMBRE=nombre)


def estado() -> dict:
    """{clave: {"existe", "proxima", "ultima", "resultado"}} de cada tarea."""
    datos = {}
    for clave, (nombre, *_) in TAREAS.items():
        resultado = _powershell(_ESTADO, T_NOMBRE=nombre)
        try:
            datos[clave] = json.loads(resultado.stdout or "{}")
        except ValueError:
            datos[clave] = {"existe": False}
        if "1999" in str(datos[clave].get("ultima", "")):  # así marca Windows «nunca se ha ejecutado»
            datos[clave]["ultima"] = ""
    return datos


if __name__ == "__main__":
    import automatico
    orden = sys.argv[1] if len(sys.argv) > 1 else "estado"
    if orden == "activar":
        fallos = activar(automatico.configuracion())
        print("\n".join(fallos) if fallos else "✔ Tareas programadas en Windows")
    elif orden == "desactivar":
        desactivar()
        print("✔ Tareas quitadas del Programador de tareas")
    else:
        print(json.dumps(estado(), ensure_ascii=False, indent=2))
