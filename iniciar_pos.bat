@echo off
chcp 65001 >nul
title POS La Loma
cd /d "%~dp0"
python main.py
echo.
pause
