@echo off
chcp 65001 >nul
title TriCoach Pro - Triathlon Platform

set "PATH=%USERPROFILE%\.local\bin;%PATH%"

echo ==============================================================
echo   Iniciando TriCoach Pro (Garmin + Intervals.icu + Coach IA)
echo ==============================================================
echo.
echo Preparando entorno y servidor...
echo.

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro 'uv' en la ruta.
    echo Asegurate de que uv esta instalado en %USERPROFILE%\.local\bin
    echo.
    pause
    exit /b 1
)

uv run --python 3.12 --with-requirements requirements.txt python run.py

if %errorlevel% neq 0 (
    echo.
    echo [AVISO] El servidor se detuvo o encontro un problema.
    echo.
    pause
)
