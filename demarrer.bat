@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python introuvable dans le PATH. Installe Python 3.10+ puis relance.
    pause
    exit /b 1
)

python setup.py
if errorlevel 1 (
    echo Setup en echec.
    pause
    exit /b 1
)

python bot.py
pause
exit /b 0
