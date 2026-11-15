"""Etat des composants audio, lisible depuis Discord."""

import ctypes.util
import subprocess
import sys

import discord
import discord.opus
import yt_dlp

import config
import taps


def _opus_line():
    if not discord.opus.is_loaded():
        found = ctypes.util.find_library("opus")
        return f"non charge (find_library={found})"
    lib = getattr(discord.opus, "_lib", None)
    name = getattr(lib, "_name", None) or "charge"
    return name


def _ffmpeg_line():
    try:
        done = subprocess.run(
            [config.FFMPEG_PATH, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        first = (done.stdout or done.stderr).strip().splitlines()
        return first[0][:90] if first else f"{config.FFMPEG_PATH} muet"
    except Exception as exc:
        return f"introuvable ({config.FFMPEG_PATH}) : {exc.__class__.__name__}"


def _davey_line():
    try:
        import davey
    except Exception as exc:
        return f"absent ({exc.__class__.__name__})"
    return f"{getattr(davey, '__version__', '?')} / protocole {getattr(davey, 'DAVE_PROTOCOL_VERSION', '?')}"


def _voice_lines(player):
    if player is None:
        return ["vocal : aucun lecteur pour ce salon"]
    vc = player.voice
    if vc is None:
        return ["vocal : pas connecte"]
    conn = getattr(vc, "_connection", None)
    channel = getattr(vc, "channel", None)
    label = getattr(channel, "name", None) or "appel DM"
    lines = [
        f"salon : {label} ({getattr(channel, 'id', '?')})",
        f"vocal : connecte={vc.is_connected()} lecture={vc.is_playing()} pause={vc.is_paused()}",
    ]
    if conn is None:
        lines.append("etat interne : absent")
        return lines
    version = getattr(conn, "dave_protocol_version", 0)
    session = getattr(conn, "dave_session", None)
    can_encrypt = bool(getattr(conn, "can_encrypt", False))
    lines.append(f"e2ee : protocole={version} can_encrypt={can_encrypt} downgrade={getattr(conn, 'dave_downgraded', '?')}")
    if session is None:
        lines.append("session dave : absente")
    else:
        try:
            users = len(session.get_user_ids())
        except Exception:
            users = "?"
        lines.append(
            f"session dave : ready={session.ready} epoch={session.epoch} users={users} "
            f"status={getattr(session, 'status', '?')}"
        )
    elapsed = player.elapsed
    frames = player.frames
    if player.current is not None:
        lines.append(
            f"titre : {player.current.title[:60]} | trame={frames} (~{frames / 50:.1f}s)"
            + (f" | position={elapsed:.0f}s" if elapsed is not None else "")
        )
    else:
        lines.append(f"titre : aucun | dernier flux {frames} trames")
    return lines


def report(player):
    lines = [
        f"**opus** : {_opus_line()}",
        f"**ffmpeg** : {_ffmpeg_line()}",
        f"**yt-dlp** : {yt_dlp.version.__version__}",
        f"**davey** : {_davey_line()}",
        f"**python** : {sys.version.split()[0]}",
    ]
    lines.extend(_voice_lines(player))
    lines.append(taps.packet_line())
    lines.extend(taps.error_lines())
    return "\n".join(lines)
