@echo off
setlocal
title POS La Loma - Instalador de dependencias

echo ============================================================
echo   POS La Loma - Instalacion de dependencias
echo ============================================================
echo.

rem ---------- 1) Buscar Python ----------
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto sin_python

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto python_viejo

echo Python encontrado:
%PY% --version
echo.

cd /d "%~dp0"

if not exist "requirements.txt" goto sin_requirements

rem ---------- 2) pip ----------
echo [1/4] Actualizando pip...
%PY% -m pip install --upgrade pip

echo.
echo [2/4] Instalando dependencias de la aplicacion (PyQt6, requests)...
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto pip_usuario
goto deps_ok

:pip_usuario
echo.
echo [AVISO] Fallo la instalacion normal. Reintentando solo para este usuario...
%PY% -m pip install --user -r requirements.txt
if errorlevel 1 goto pip_error
goto deps_ok

:pip_error
echo.
echo [ERROR] No se pudieron instalar las dependencias.
echo         Revise la conexion a Internet o los permisos del equipo.
echo.
pause
exit /b 1

rem ---------- 3) Dependencias de desarrollo (opcional) ----------
:deps_ok
if /I "%~1"=="dev" goto dev_deps

echo.
echo [3/4] Dependencias de desarrollo omitidas.
echo       Para instalarlas use:  instalar_dependencias.bat dev
goto verificar

:dev_deps
echo.
echo [3/4] Instalando dependencias de desarrollo (tests / empaquetado)...
if exist "requirements-dev.txt" %PY% -m pip install -r requirements-dev.txt

rem ---------- 4) Verificacion ----------
:verificar
echo.
echo [4/5] Verificando la instalacion...
%PY% -c "from PyQt6.QtCore import PYQT_VERSION_STR; import requests; print('PyQt6', PYQT_VERSION_STR, '| requests', requests.__version__)"
if errorlevel 1 goto verificacion_error

echo.
echo [5/5] Autocomprobacion del POS (base, datos y servicios)...
%PY% main.py --selftest

echo.
echo ============================================================
echo   LISTO. Para abrir el POS ejecute:
echo.
echo       iniciar_pos.bat
echo   o bien:
echo       %PY% main.py
echo.
echo   Si esta PC es una CAJA, cree antes
echo   %APPDATA%\PosLaLoma\config.ini  con:
echo       [pos]
echo       server_url = http://IP-DEL-SERVIDOR:8000
echo       station = CAJA2
echo       docs_path = \\IP-DEL-SERVIDOR\documentos
echo.
echo   El servidor central se ejecuta con:  iniciar_pos.bat --server
echo ============================================================
echo.
pause
exit /b 0

:sin_python
echo [ERROR] No se encontro Python en esta PC.
echo.
echo   1. Descargue Python 3.11 o superior de:
echo      https://www.python.org/downloads/windows/
echo   2. Al instalar, marque la casilla "Add python.exe to PATH".
echo   3. Vuelva a ejecutar este archivo.
echo.
pause
exit /b 1

:python_viejo
echo [ERROR] Se necesita Python 3.10 o superior.
%PY% --version
echo.
pause
exit /b 1

:sin_requirements
echo [ERROR] No se encuentra requirements.txt junto a este archivo.
echo         Ejecute este .bat desde la carpeta del proyecto.
echo.
pause
exit /b 1

:verificacion_error
echo.
echo [ERROR] La verificacion fallo. Revise los mensajes anteriores.
echo.
pause
exit /b 1
