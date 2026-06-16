@echo off
cd /d "%~dp0"
echo Instalando dependencias, se necessario...
python -m pip install -r requirements.txt
echo.
echo Abrindo dashboard em http://localhost:3000
echo.
python app.py
pause
