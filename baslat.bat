@echo off
echo Medipol İtiraf Ediyor başlatılıyor...
echo Tarayıcıda şu adresi aç: http://localhost:5000
echo Durdurmak için bu pencereyi kapat veya CTRL+C bas.
echo.
cd /d "%~dp0"
python app.py
pause
