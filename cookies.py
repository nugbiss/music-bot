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


async def restore(client, max_channels=20):
    """Au demarrage : cherche un cookies.txt epingle."""
    if _RESTORED["done"] or config.COOKIES_PATH:
        return False
    _RESTORED["done"] = True
    seen = 0
    for guild in client.guilds:
        for channel in getattr(guild, "text_channels", []):
            if seen >= max_channels:
                return False
            seen += 1
            try:
                pins = await channel.pins()
            except Exception:
                continue
            for message in pins:
                if await install_from_message(message):
                    print(f"[cookies] installes depuis {channel} (message epingle)")
                    return True
    return False
