"""Installation des cookies YouTube par simple depot de fichier dans Discord."""

import os
import tempfile

import config

COOKIES_PATH = os.path.join(tempfile.gettempdir(), "ytdl-cookies.txt")
_RESTORED = {"done": False}


def apply_bytes(data):
    """Ecrit le cookies.txt decode et branche yt-dlp dessus."""
    if b"Netscape HTTP Cookie File" not in data[:200] and b"\t" not in data[:4000]:
        return False
    with open(COOKIES_PATH, "wb") as handle:
        handle.write(data)
    config.COOKIES_PATH = COOKIES_PATH
    return True


async def install_from_message(message):
    """Recupere un .txt joint, le valide, l'installe pour la session en cours."""
    for attachment in message.attachments:
        if not attachment.filename.lower().endswith(".txt"):
            continue
        try:
            data = await attachment.read()
        except Exception:
            continue
        if apply_bytes(data):
            return True
    return False


async def _scan_channel(channel, history_limit):
    try:
        for message in await channel.pins():
            if await install_from_message(message):
                print(f"[cookies] installes depuis {channel} (epingle)")
                return True
    except Exception:
        pass
    try:
        async for message in channel.history(limit=history_limit):
            if message.attachments and await install_from_message(message):
                print(f"[cookies] installes depuis {channel} (historique)")
                return True
    except Exception:
        pass
    return False


async def restore(client, max_channels=20, history_limit=50):
    """Au demarrage : relit groupes prives, DM et salons a la recherche du fichier."""
    if _RESTORED["done"] or config.COOKIES_PATH:
        return False
    _RESTORED["done"] = True
    channels = list(getattr(client, "private_channels", []))
    for guild in client.guilds:
        channels.extend(getattr(guild, "text_channels", []))
    seen = 0
    for channel in channels:
        if seen >= max_channels:
            return False
        if not hasattr(channel, "history"):
            continue
        seen += 1
        if await _scan_channel(channel, history_limit):
            return True
    return False
