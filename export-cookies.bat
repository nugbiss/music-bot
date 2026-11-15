@echo off
chcp 65001 >nul
pushd "%~dp0"
python cookies_export.py
if errorlevel 4 (
  echo.
  choice /C ON /N /M "Le navigateur verrouille sa base de cookies. Le fermer, exporter, le rouvrir ? [O/N] "
  if errorlevel 2 goto fin
  python cookies_export.py --force-close
)
:fin
echo.
pause
popd
