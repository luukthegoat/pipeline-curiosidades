@echo off
rem Crea los accesos directos "MenteInquieta67" (carpeta del proyecto, escritorio y menu Inicio).
rem Abren menu\aplicacion.py con el Python del entorno .venv, que esta firmado: asi funcionan aunque Windows tenga
rem activado el "Control inteligente de aplicaciones", que bloquea MenteInquieta67.exe por no llevar firma digital.
rem (Sin tildes ni comillas angulares: la consola de Windows no lee este archivo en UTF-8.)
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo No encuentro .venv\Scripts\pythonw.exe: crea antes el entorno con python -m venv .venv
  pause & exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$raiz = (Get-Location).Path; $shell = New-Object -ComObject WScript.Shell;" ^
  "$destinos = @($raiz, [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'));" ^
  "foreach ($carpeta in $destinos) {" ^
  "  $acceso = $shell.CreateShortcut((Join-Path $carpeta 'MenteInquieta67.lnk'));" ^
  "  $acceso.TargetPath = Join-Path $raiz '.venv\Scripts\pythonw.exe';" ^
  "  $acceso.Arguments = '\"' + (Join-Path $raiz 'menu\aplicacion.py') + '\"';" ^
  "  $acceso.WorkingDirectory = $raiz;" ^
  "  $acceso.IconLocation = (Join-Path $raiz 'menu\static\icono.ico') + ',0';" ^
  "  $acceso.Description = 'Abre MenteInquieta67';" ^
  "  $acceso.Save(); Write-Host ('Creado: ' + (Join-Path $carpeta 'MenteInquieta67.lnk'))" ^
  "}"
if errorlevel 1 (pause & exit /b 1)
