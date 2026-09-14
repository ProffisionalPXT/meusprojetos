@echo off
chcp 65001 >nul
title [CASA] Puxar Atualizações do Escritório
color 0B
cls
echo =====================================================================
echo       🔄 [CASA] PUXANDO ATUALIZAÇÕES DO ESCRITÓRIO
echo =====================================================================
echo.
:: Pega o diretório atual onde o script está rodando
cd /d "%~dp0"

echo [1/2] Baixando novidades do GitHub...
git pull --rebase origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo =====================================================================
    echo    ✅ SUCESSO! Tudo o que você fez no escritório acabou de chegar!
    echo       Abra o VS Code / Antigravity e continue de onde parou.
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo    ⚠️ Houve um aviso durante o download. Verifique as mensagens acima.
    echo =====================================================================
)

echo.
pause
