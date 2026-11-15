"""Compteurs et capture d'erreurs pour diagnostiquer le vocal en production."""

import logging
import time
from collections import deque

from discord.voice_client import VoiceClient

ERRORS = deque(maxlen=8)
PACKETS = {"count": 0, "last_ts": 0.0, "last_error": None}


class _ErrorTap(logging.Handler):
    def emit(self, record):
        if record.levelno < logging.ERROR:
            return
        try:
            text = record.getMessage()
        except Exception:
            text = ""
        ERRORS.append(f"{record.name}: {text[:180]}")


def install():
    """Capture les erreurs de log et compte les paquets audio envoyes."""
    root = logging.getLogger()
    if not any(isinstance(handler, _ErrorTap) for handler in root.handlers):
        root.addHandler(_ErrorTap())
        if root.level > logging.WARNING:
            root.setLevel(logging.WARNING)
    for name in ("discord.player", "discord.voice_client", "discord.voice_state", "dave_fix"):
        logging.getLogger(name).setLevel(logging.DEBUG)

    original = VoiceClient.send_audio_packet
    if getattr(original, "_tapped", False):
        return True

    def send_audio_packet(self, data, *, encode=True):
        try:
            original(self, data, encode=encode)
        except Exception as exc:
            PACKETS["last_error"] = f"{type(exc).__name__}: {exc}"[:160]
            raise
        PACKETS["count"] += 1
        PACKETS["last_ts"] = time.time()

    send_audio_packet._tapped = True
    VoiceClient.send_audio_packet = send_audio_packet
    return True


def packet_line():
    count = PACKETS["count"]
    if not count:
        return "paquets audio : aucun envoye"
    age = time.time() - PACKETS["last_ts"]
    line = f"paquets audio : {count} (dernier il y a {age:.1f}s)"
    if PACKETS["last_error"]:
        line += f" | erreur: {PACKETS['last_error']}"
    return line


def error_lines(limit=3):
    if not ERRORS:
        return ["logs : aucune erreur"]
    return ["logs : " + item for item in list(ERRORS)[-limit:]]
