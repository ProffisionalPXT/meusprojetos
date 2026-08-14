@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "%~dp0_criar_atalho.py"
if errorlevel 1 py -3 "%~dp0_criar_atalho.py"
pause
