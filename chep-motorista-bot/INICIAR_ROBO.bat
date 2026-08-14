@echo off
color 0A
title Robo CHEP - Monitoramento
echo ========================================================
echo           INICIANDO O ROBO DO CHEP
echo ========================================================
echo.
echo O robo esta monitorando a pasta 'input'...
echo Para testar, tire um print e cole no Painel que acabou de abrir!
echo.
start /B python painel.py
python main.py
pause
