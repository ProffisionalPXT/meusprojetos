@echo off
title Leitura Rapida de Documentos - GW Motorista
cd /d "%~dp0"

echo.
echo  =============================================================
echo   LEITURA ULTRARRAPIDA DE DOCUMENTOS (1 SEGUNDO)
echo  =============================================================
echo.

python ler_documentos_rapido.py
if errorlevel 1 py -3 ler_documentos_rapido.py
if errorlevel 1 (
  echo.
  echo  ERRO ao executar o leitor rapido.
  pause
  exit /b 1
)

echo.
echo  =============================================================
echo   Dados gerados e salvos com sucesso!
echo   Pressione qualquer tecla para fechar ou inicie INICIAR_ROBO.bat
echo  =============================================================
pause
