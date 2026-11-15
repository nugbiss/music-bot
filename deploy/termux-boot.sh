#!/data/data/com.termux/files/usr/bin/bash
# A placer dans ~/.termux/boot/ (app Termux:Boot installee) pour relancer au demarrage du telephone.
termux-wake-lock
cd "$HOME/discord-music-selfbot"
nohup python -u bot.py >> bot.log 2>&1 &
