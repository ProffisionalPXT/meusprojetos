@echo off
chcp 65001 >nul
title [ESCRITÓRIO] Puxar Atualizações de Casa
color 0B
cls
echo =====================================================================
echo       🔄 [ESCRITÓRIO] PUXANDO ATUALIZAÇÕES FEITAS EM CASA
echo =====================================================================
echo.
cd /d "C:\Users\TRANSRAP05\Desktop\gabriel\meusprojetos"

echo [1/2] Verificando conexão com o GitHub...
git pull --rebase origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo =====================================================================
    echo    ✅ SUCESSO! Todos os códigos e melhorias de casa foram baixados!
    echo       Seus robôs no escritório estão 100%% atualizados.
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo    ⚠️ Houve um aviso ou pendência durante a sincronização.
    echo       Verifique as mensagens acima.
    echo =====================================================================
)

echo.
pause
