@echo off
cd /d "%~dp0"
set DRY_RUN=true
set LIMITE_PRODUTOS_TESTE=20
echo Instalando dependencias, se necessario...
python -m pip install -r requirements.txt
echo.
echo Rodando simulacao Woo -> SGI...
echo.
python main.py
pause
