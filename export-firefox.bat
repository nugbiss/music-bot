@echo off
chcp 65001 >nul
pushd "%~dp0"
set "FF=%ProgramFiles%\Mozilla Firefoxirefox.exe"
if not exist "%FF%" set "FF=%ProgramFiles(x86)%\Mozilla Firefoxirefox.exe"
if not exist "%FF%" set "FF=%LOCALAPPDATA%\Mozilla Firefoxirefox.exe"
if not exist "%FF%" (
  echo Firefox absent, installation via winget...
  winget install --id Mozilla.Firefox -e --accept-source-agreements --accept-package-agreements
)
start "" "%FF%" https://www.youtube.com
echo.
echo Connecte-toi a YouTube dans Firefox, puis appuie sur une touche ici.
pause >nul
python cookies_export.py
echo.
pause
popd
