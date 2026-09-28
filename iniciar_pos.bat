@echo off
setlocal
chcp 65001 >nul
title POS La Loma

cd /d "%~dp0"

rem ---------- Buscar Python ----------
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto sin_python

if not exist "main.py" goto sin_main

rem ---------- Verificar dependencias ----------
%PY% -c "import PyQt6, requests" >nul 2>nul
if errorlevel 1 goto sin_dependencias

echo Abriendo POS La Loma...
%PY% main.py %*
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" goto con_error
exit /b 0

:con_error
echo.
echo ============================================================
echo   El POS termino con un error (codigo %CODIGO%).
echo.
echo   Detalle en:  %APPDATA%\PosLaLoma\logs\app.log
echo.
echo   Diagnostico:  %PY% main.py --selftest
echo ============================================================
echo.
pause
exit /b %CODIGO%

:sin_dependencias
echo ============================================================
echo   [ERROR] Faltan las dependencias (PyQt6 / requests).
echo.
echo   Ejecute primero:  instalar_dependencias.bat
echo ============================================================
echo.
pause
exit /b 1

:sin_python
echo ============================================================
echo   [ERROR] No se encontro Python en esta PC.
echo.
echo   Ejecute primero:  instalar_dependencias.bat
echo   (si Python no esta instalado, ese .bat le indica de donde bajarlo)
echo ============================================================
echo.
pause
exit /b 1

:sin_main
echo [ERROR] No se encuentra main.py junto a este archivo.
echo         Ejecute este .bat desde la carpeta del proyecto.
echo.
pause
exit /b 1
