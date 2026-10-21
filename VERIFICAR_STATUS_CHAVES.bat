@echo off
chcp 65001 >nul
title Verificador de Status das Chaves de IA - GW Motorista
cd /d "%~dp0"
if not exist "utils\verificar_chaves.py" cd ..
if not exist "utils\verificar_chaves.py" cd ..

python utils\verificar_chaves.py
echo.
pause
