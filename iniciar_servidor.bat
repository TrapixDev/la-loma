@echo off
setlocal
chcp 65001 >nul
title Servidor POS La Loma

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

echo ============================================
echo  Servidor POS La Loma
echo  NO CIERRE ESTA VENTANA mientras se use el POS
echo ============================================
echo.

%PY% server.py
echo.
echo El servidor se detuvo (codigo %ERRORLEVEL%).
echo Revise el detalle en:  %APPDATA%\PosLaLoma\logs\app.log
pause
exit /b 0

:sin_python
echo [ERROR] No se encontro Python en esta PC.
echo         Ejecute primero:  instalar_dependencias.bat
echo.
pause
exit /b 1
