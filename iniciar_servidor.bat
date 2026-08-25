@echo off
chcp 65001 >nul
title Servidor POS La Loma
cd /d "%~dp0"
echo ============================================
echo  Servidor POS La Loma
echo  NO CIERRE ESTA VENTANA mientras se use el POS
echo ============================================
echo.
python server.py
echo.
echo El servidor se detuvo.
pause
