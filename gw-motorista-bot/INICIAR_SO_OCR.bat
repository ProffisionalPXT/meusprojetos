@echo off
title GW - So OCR (sem abrir GW)
cd /d "%~dp0"

echo.
echo  ============================================
echo   SO OCR + CONFIRMACAO (nao entra no GW)
echo  ============================================
echo.
pause

python testar_ocr_local.py
if errorlevel 1 py -3 testar_ocr_local.py
if errorlevel 1 (
  echo.
  echo  ERRO: Python nao encontrado.
  echo  Instale Python ou rode: python testar_ocr_local.py
  pause
  exit /b 1
)

echo.
echo  --------------------------------------------
echo   Fim do OCR.
echo  --------------------------------------------
pause