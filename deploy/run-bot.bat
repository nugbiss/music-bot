@echo off
cd /d "%~dp0.."
python -u bot.py >> bot.log 2>&1
