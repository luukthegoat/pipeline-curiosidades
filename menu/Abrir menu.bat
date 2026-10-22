@echo off
rem Doble clic para abrir el menu en el navegador. Cierra esta ventana para apagarlo.
chcp 65001 >nul
title Menu - Videos de historia (cierra esta ventana para apagarlo)
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo No encuentro el entorno .venv en la carpeta principal.
    echo Crea el entorno con:  python -m venv .venv
    echo y despues:            .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "menu\app.py"
if errorlevel 1 pause
