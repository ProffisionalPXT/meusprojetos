@echo off
chcp 65001 >nul
title [ESCRITÓRIO] Enviar Atualizações para Casa
color 0A
cls
echo =====================================================================
echo       🚀 [ESCRITÓRIO] ENVIANDO PROJETOS ATUALIZADOS PARA CASA
echo =====================================================================
echo.
cd /d "C:\Users\TRANSRAP05\Desktop\gabriel\meusprojetos"

:: Registrar no Diário de Bordo
echo - [%%date%% %%time:~0,5%%] Sincronização enviada do ESCRITÓRIO para CASA >> DIARIO_DE_BORDO.md

echo [1/3] Preparando arquivos modificados...
git add .

echo [2/3] Criando ponto de sincronização...
git commit -m "sync: atualizacao enviada do escritorio em %date% as %time:~0,5%" >nul 2>&1

echo [3/3] Enviando para a nuvem (GitHub)...
git push origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo =====================================================================
    echo    ✅ PRONTO! Tudo foi enviado para a nuvem com sucesso!
    echo       Quando chegar em casa, basta clicar em "1_PUXAR_DO_ESCRITORIO".
    echo       Pode desligar o computador do trabalho com segurança.
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo    ⚠️ Ops! Verifique se a internet está conectada ou tente novamente.
    echo =====================================================================
)

echo.
pause
