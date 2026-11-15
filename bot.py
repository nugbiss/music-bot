import asyncio
import ctypes.util
import os
import sys

import discord
import discord.opus
from discord.ext import commands

import config
import cookies
import dave_fix
import health
import taps
from commands import Music
from player import get_player

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _load_opus():
    if discord.opus.is_loaded():
        return True
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "libs", "libopus-0.x64.dll"),
        os.path.join(os.path.dirname(discord.opus.__file__), "bin", "libopus-0.x64.dll"),
        "/usr/lib/aarch64-linux-gnu/libopus.so.0",
        "/usr/lib/x86_64-linux-gnu/libopus.so.0",
        "/usr/lib/libopus.so.0",
        "/data/data/com.termux/files/usr/lib/libopus.so",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                discord.opus.load_opus(path)
                return discord.opus.is_loaded()
            except Exception:
                continue
    name = ctypes.util.find_library("opus")
    if name:
        try:
            discord.opus.load_opus(name)
            return discord.opus.is_loaded()
        except Exception:
            pass
    return False


OPUS_OK = _load_opus()
DAVE_FIX_OK = dave_fix.apply()
TAPS_OK = taps.install()

bot = commands.Bot(
    command_prefix=config.PREFIX,
    user_bot=True,
    help_command=None,
)
bot.players = {}
bot.stay_task = None


async def _stay_247():
    channel_id = config.AUTO_JOIN_CHANNEL_ID
    if not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    except Exception as exc:
        print(f"[bot] auto-join : salon {channel_id} introuvable ({exc})")
        return
    await get_player(bot, channel).keepalive()


@bot.event
async def on_ready():
    print(f"[bot] connecte : {bot.user} ({bot.user.id})")
    print(f"[bot] prefixe : {config.PREFIX}")
    print(f"[bot] ffmpeg : {config.FFMPEG_PATH}")
    print(f"[bot] serveurs : {len(bot.guilds)} | messages en console : {'oui' if config.DEBUG else 'non'}")
    print(f"[bot] opus : {'charge' if OPUS_OK else 'ABSENT - installe libs/libopus-0.x64.dll'}")
    print(f"[bot] dave : {'correctif actif' if DAVE_FIX_OK else 'non applique'}")
    print(f"[bot] sonde vocale : {'active' if TAPS_OK else 'inactive'}")
    print(f"[bot] 24/7 : {'salon ' + str(config.AUTO_JOIN_CHANNEL_ID) if config.AUTO_JOIN_CHANNEL_ID else 'desactive'}"
          f" | ring : {'oui' if config.RING else 'non'} | inactivite : "
          f"{'jamais' if config.IDLE_TIMEOUT <= 0 else str(config.IDLE_TIMEOUT) + 's'}")
    if config.AUTO_JOIN_CHANNEL_ID and (bot.stay_task is None or bot.stay_task.done()):
        bot.stay_task = bot.loop.create_task(_stay_247())
    if config.COOKIES_PATH:
        print("[cookies] charges")
    else:
        bot.loop.create_task(cookies.restore(bot))


@bot.event
async def on_message(message):
    if config.DEBUG and not message.author.bot:
        allowed = message.author.id in config.ALLOWED_IDS
        print(f"[msg] {message.channel} | {message.author} ({message.author.id}) | "
              f"{'ok' if allowed else 'ignore'} | {message.content[:100]!r}")
    if message.author.id not in config.ALLOWED_IDS:
        return
    if message.attachments and await cookies.install_from_message(message):
        print("[cookies] installes depuis un message")
        await message.channel.send("🍪 Cookies YouTube charges : les recherches passent par YouTube.")
    await bot.process_commands(message)


@bot.event
async def on_command(ctx):
    print(f"[cmd] {ctx.command} par {ctx.author}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"[bot] erreur commande : {error!r}")
    try:
        await ctx.send(f"❌ `{type(error).__name__}` : {error}")
    except Exception:
        pass


async def main():
    health.start_if_needed()
    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    if not config.TOKEN:
        print("Token absent : renseigne TOKEN dans .env ou dans la variable d'environnement TOKEN.")
        sys.exit(1)
    asyncio.run(main())
