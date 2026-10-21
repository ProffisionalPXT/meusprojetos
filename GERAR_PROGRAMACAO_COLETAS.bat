@echo off
chcp 65001 > nul
title Gerador de Programacao de Coletas

set "TARGET_HTML=C:\Users\TRANSRAP05\Desktop\gw-motorista-bot\programacao_coletas\index.html"

if exist "%TARGET_HTML%" (
    start "" "%TARGET_HTML%"
) else (
    start "" "%~dp0programacao_coletas\index.html"
)

exit
