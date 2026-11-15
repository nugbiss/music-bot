@echo off
cd /d "%~dp0"
where python >/dev/null 2>&1 && (python cookies_export.py) || (py -3 cookies_export.py)
echo.
pause
