@echo off
rem Compila "Mente Inquieta.exe" en la carpeta principal con el compilador de C# que trae Windows (.NET Framework 4).
cd /d "%~dp0.."
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
"%CSC%" /nologo /target:winexe /optimize /win32icon:menu\static\icono.ico /reference:System.Windows.Forms.dll /out:"Mente Inquieta.exe" lanzador\MenteInquieta.cs
if errorlevel 1 (pause & exit /b 1)
echo Creado: "Mente Inquieta.exe"
