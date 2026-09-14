@echo off
chcp 65001 >nul
title [CASA] Enviar Atualizações para o Escritório
color 0A
cls
echo =====================================================================
echo       🚀 [CASA] ENVIANDO PROJETOS PARA O ESCRITÓRIO
echo =====================================================================
echo.
:: Pega o diretório atual onde o script está rodando
cd /d "%~dp0"

:: Registrar no Diário de Bordo
echo - [%%date%% %%time:~0,5%%] Sincronização enviada de CASA para o ESCRITÓRIO >> DIARIO_DE_BORDO.md

echo [1/3] Preparando arquivos modificados...
git add .

echo [2/3] Criando ponto de sincronização...
git commit -m "sync: atualizacao enviada de casa em %date% as %time:~0,5%" >nul 2>&1

echo [3/3] Enviando para o GitHub...
git push origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo =====================================================================
    echo    ✅ PERFEITO! Suas melhorias feitas em casa foram enviadas!
    echo       Amanhã no escritório, basta rodar "1_PUXAR_DE_CASA".
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo    ⚠️ Ops! Verifique se a internet está conectada ou tente novamente.
    echo =====================================================================
)

echo.
pause
