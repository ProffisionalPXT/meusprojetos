@echo off
title GW - Cadastro de Motorista
cd /d "%~dp0"

echo.
echo  ============================================
echo   ROBO GW - Cadastro de Motorista
echo  ============================================
echo.
echo  Pasta de documentos: input\
echo  (coloque a pasta do motorista ANTES de continuar)
echo.
echo  O robo vai:
echo    1. Ler os documentos
echo    2. Mostrar os dados para VOCE conferir/corrigir
echo    3. So depois preencher o GW
echo.
echo  --------------------------------------------
pause

REM So Python (sem PowerShell - antvirus da empresa bloqueia PS)
python main.py
if errorlevel 1 py -3 main.py
if errorlevel 1 (
  echo.
  echo  ERRO: Python nao encontrado.
  echo  Instale Python ou rode: py -3 main.py
  pause
  exit /b 1
)

echo.
echo  --------------------------------------------
echo   Fim. Se travou: Ctrl+C  ou  feche a janela.
echo   (nao estraga o PC; no maximo fecha Chrome/Python)
echo  --------------------------------------------
pause