@echo off
rem Cree une tache "DiscordMusicSelfbot" lancee a l'ouverture de session.
schtasks /Create /TN "DiscordMusicSelfbot" /TR "\"%~dp0run-bot.bat\"" /SC ONLOGON /F
schtasks /Run /TN "DiscordMusicSelfbot"
echo.
echo Demarre. Verifie avec : type "%~dp0..\bot.log"
pause
