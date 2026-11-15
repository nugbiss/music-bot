import asyncio
import json
import math
import os
import random
import struct
import tempfile
import time
import urllib.parse
import urllib.request
import wave

import discord
import yt_dlp

import config

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "nocheckcertificate": True,
    "skip_download": True,
    "source_address": "0.0.0.0",
    "socket_timeout": 15,
    "retries": 3,
    "extractor_retries": 3,
}

# Certains clients YouTube passent mieux depuis une IP de datacenter (Render).
CLIENT_SETS = (
    None,
    ("web_safari", "android_vr", "mweb", "ios"),
    ("android_vr",),
)

FFMPEG_BEFORE = "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = "-vn"

LOOP_MODES = ("off", "one", "all")


class Track:
    def __init__(self, title, stream_url, webpage_url=None, duration=None, requester=None, uploader=None):
        self.title = title
        self.stream_url = stream_url
        self.webpage_url = webpage_url
        self.duration = duration
        self.requester = requester
        self.uploader = uploader

    def __repr__(self):
        return f"<Track {self.title!r}>"


class CountedVolume(discord.PCMVolumeTransformer):
    """Transformeur de volume qui compte les trames PCM lues par Discord."""

    def __init__(self, original, volume=0.5):
        super().__init__(original, volume=volume)
        self.frames = 0

    def read(self):
        data = super().read()
        if data:
            self.frames += 1
        return data


def make_tone(path, seconds=8, freq=440):
    """Écrit un sinus mono 48 kHz s16le dans path (test du pipeline vocal)."""
    rate = 48000
    amplitude = 12000
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        payload = bytearray()
        for index in range(rate * seconds):
            payload += struct.pack("<h", int(amplitude * math.sin(2 * math.pi * freq * index / rate)))
        out.writeframes(bytes(payload))


def fmt_duration(seconds):
    if not seconds:
        return "live"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _is_url(text):
    return text.startswith(("http://", "https://"))


REMIX_WORDS = (
    "remix",
    "flip",
    "bootleg",
    "mashup",
    "sped up",
    "slowed",
    "nightcore",
    "instrumental",
    "karaoke",
    "cover",
    "extended",
    "vip mix",
    "live",
    "edit",
    "remake",
    "rework",
    "8d",
)


def _normalize(text):
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text.lower()).split())


def _deezer_lookup(query):
    """Titre et artiste canoniques : l'API publique Deezer sert de reference."""
    url = "https://api.deezer.com/search?limit=1&q=" + urllib.parse.quote(query)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
    except Exception:
        return None
    items = data.get("data") or []
    if not items:
        return None
    item = items[0]
    title = (item.get("title") or "").strip()
    if not title:
        return None
    artist = ((item.get("artist") or {}).get("name") or "").strip()
    return {"title": title, "artist": artist}


def _title_score(title, meta, query):
    """Note un candidat : version studio en haut, remixes et edits en bas."""
    lowered = title.lower()
    norm = _normalize(title)
    base = _normalize(meta["title"]) if meta else _normalize(query)
    score = 0
    if base and norm == base:
        score += 10
    elif base and norm.startswith(base):
        score += 4
    elif base and base in norm:
        score += 2
    if meta and meta["artist"] and _normalize(meta["artist"]) in norm:
        score += 2
    words = [word for word in query.lower().split() if len(word) > 2]
    score += sum(1 for word in words[:3] if word in lowered)
    score -= 3 * sum(lowered.count(char) for char in "([")
    for word in REMIX_WORDS:
        if word in lowered and word not in query.lower():
            score -= 8
    return score


class _SilentLogger:
    """Avale les messages de yt-dlp pendant les listings (DRM, extraits)."""

    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def _opts(flat=False, clients=None):
    """Construit les options yt-dlp pour une passe d'extraction.

    Entrée : flat (recherche légère), clients (liste de player_client YouTube).
    Sortie : dict d'options prêt pour YoutubeDL.
    """
    opts = dict(YTDL_OPTS)
    if flat:
        opts["extract_flat"] = True
    if clients:
        opts["extractor_args"] = {"youtube": {"player_client": list(clients)}}
    if config.COOKIES_PATH:
        opts["cookiefile"] = config.COOKIES_PATH
    if config.PROXY_URL:
        opts["proxy"] = config.PROXY_URL
    return opts


def _snipped(info):
    """Vrai si SoundCloud ne renvoie qu'un extrait de 30 s (titre sous label)."""
    for fmt in info.get("formats") or []:
        if "preview" in str(fmt.get("format_id") or "").lower():
            return True
    url = str(info.get("url") or "")
    return "cf-preview-media" in url or "/preview/" in url


def _full_stream(info):
    """URL de flux complète : celle par défaut si elle n'est pas un extrait."""
    url = str(info.get("url") or "")
    if url and "preview" not in url and "cf-preview-media" not in url:
        return url
    for fmt in info.get("formats") or []:
        candidate = str(fmt.get("url") or "")
        if not candidate:
            continue
        if "preview" in str(fmt.get("format_id") or "").lower():
            continue
        if "cf-preview-media" in candidate or "/preview/" in candidate:
            continue
        if fmt.get("vcodec") in (None, "none"):
            return candidate
    return None


def _track_from(info, query, requester):
    stream = _full_stream(info)
    if not stream:
        return None
    return Track(
        title=info.get("title") or query,
        stream_url=stream,
        webpage_url=info.get("webpage_url") or (query if _is_url(query) else None),
        duration=info.get("duration"),
        requester=requester,
        uploader=info.get("uploader"),
    )


def _soundcloud_listing(query, size):
    """Résultats SoundCloud complets (formats inclus), erreurs avalées."""
    listed = _opts()
    listed["ignoreerrors"] = True
    listed["logger"] = _SilentLogger()
    try:
        with yt_dlp.YoutubeDL(listed) as ydl:
            listing = ydl.extract_info(f"scsearch{size}:{query}", download=False) or {}
    except Exception:
        return []
    return [entry for entry in listing.get("entries") or [] if entry]


def _soundcloud_track(query, requester, meta=None, size=8):
    """Meilleur résultat SoundCloud jouable en entier, originale en tete."""
    ranked = []
    for entry in _soundcloud_listing(query, size):
        if _snipped(entry):
            continue
        score = _title_score(entry.get("title") or "", meta, query)
        ranked.append((score, entry))
    ranked.sort(key=lambda item: item[0], reverse=True)
    for score, entry in ranked[:4]:
        if score < -3:
            continue
        track = _track_from(entry, query, requester)
        if track is not None:
            return track
    return None


def _extract_sync(query, requester):
    """Résout une requête en flux audio : YouTube, puis SoundCloud en entier.

    Entrée : query (titre ou URL), requester (auteur de la commande).
    Sortie : Track jouable ; lève RuntimeError avec la dernière erreur sinon.
    """
    if _is_url(query):
        targets = [query]
    else:
        targets = [f"ytsearch1:{query}"]
    last_error = "aucun resultat"

    for target in targets:
        for clients in CLIENT_SETS:
            try:
                with yt_dlp.YoutubeDL(_opts(clients=clients)) as ydl:
                    info = ydl.extract_info(target, download=False)
                if not info:
                    raise RuntimeError("aucun resultat")
                if "entries" in info:
                    entries = [entry for entry in info["entries"] if entry]
                    if not entries:
                        raise RuntimeError("aucun resultat")
                    info = entries[0]
                if _is_url(query) and "soundcloud.com" in query and _snipped(info):
                    track = _soundcloud_track(info.get("title") or "", requester)
                    if track is not None:
                        return track
                    raise RuntimeError("titre SoundCloud limite a 30 s")
                track = _track_from(info, query, requester)
                if track is not None:
                    return track
                raise RuntimeError("flux audio introuvable")
            except Exception as exc:
                last_error = str(exc).splitlines()[0][:200]

    if not _is_url(query):
        meta = _deezer_lookup(query)
        search = f"{meta['title']} {meta['artist']}".strip() if meta else query
        track = _soundcloud_track(search, requester, meta)
        if track is not None:
            return track
    raise RuntimeError(last_error)


def _spotify_sync(url):
    api = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(url, safe="")
    request = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    title = (data.get("title") or "").strip()
    artist = (data.get("author_name") or "").strip()
    if not title:
        return None
    return f"{title} {artist}".strip()


def _search_sync(query, limit):
    """Liste les résultats d'une recherche, YouTube puis SoundCloud.

    Entrée : query (titre ou URL), limit (nombre de résultats).
    Sortie : liste de dicts {title, url, duration}.
    """
    if _is_url(query):
        targets = [query]
    else:
        targets = [f"ytsearch{limit}:{query}"]
    last_error = "aucun resultat"

    for target in targets:
        for clients in CLIENT_SETS:
            try:
                with yt_dlp.YoutubeDL(_opts(flat=True, clients=clients)) as ydl:
                    info = ydl.extract_info(target, download=False)
                entries = (info or {}).get("entries") or []
                results = []
                for entry in entries:
                    if not entry:
                        continue
                    url = entry.get("webpage_url") or entry.get("url")
                    if not url:
                        continue
                    results.append(
                        {
                            "title": entry.get("title") or "Sans titre",
                            "url": url,
                            "duration": entry.get("duration"),
                        }
                    )
                    if len(results) >= limit:
                        break
                if results:
                    return results
                last_error = "aucun resultat"
            except Exception as exc:
                last_error = str(exc).splitlines()[0][:200]

    if not _is_url(query):
        meta = _deezer_lookup(query)
        search = f"{meta['title']} {meta['artist']}".strip() if meta else query
        results = _soundcloud_results(search, limit, meta)
        if results:
            return results
        last_error = "aucun resultat jouable sur SoundCloud"

    raise RuntimeError(last_error)


def _soundcloud_results(query, limit, meta=None):
    """Résultats SoundCloud jouables en entier, originaux d'abord."""
    ranked = []
    for entry in _soundcloud_listing(query, max(limit * 4, 12)):
        if _snipped(entry):
            continue
        url = entry.get("webpage_url")
        if not url:
            continue
        ranked.append((_title_score(entry.get("title") or "", meta, query), entry, url))
    ranked.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, entry, url in ranked:
        if score < -3:
            continue
        results.append(
            {
                "title": entry.get("title") or "Sans titre",
                "url": url,
                "duration": entry.get("duration"),
            }
        )
        if len(results) >= limit:
            break
    return results


async def resolve(query, requester=None):
    loop = asyncio.get_running_loop()
    if "open.spotify.com" in query:
        try:
            spotted = await loop.run_in_executor(None, _spotify_sync, query)
        except Exception:
            spotted = None
        if spotted:
            query = spotted
    return await loop.run_in_executor(None, _extract_sync, query, requester)


async def search(query, limit=5):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _search_sync, query, limit)


class ChannelPlayer:
    """Joue dans un salon vocal de serveur ou dans l'appel d'un DM / groupe."""

    def __init__(self, bot, channel):
        self.bot = bot
        self.channel = channel
        self.queue = []
        self.current = None
        self.loop = "off"
        self.volume = config.VOLUME_DEFAULT
        self.history = []
        self._cycle = []
        self._skipping = False
        self._suppress = False
        self._seek_base = 0.0
        self._seek_ts = 0.0
        self._idle_task = None
        self._guard_task = None
        self._lock = asyncio.Lock()
        self._source = None

    @property
    def voice(self):
        for vc in self.bot.voice_clients:
            channel = getattr(vc, "channel", None)
            if channel is not None and channel.id == self.channel.id:
                return vc
        return None

    @property
    def guild_voice(self):
        """Premier client vocal du même serveur, quel que soit le salon."""
        guild = getattr(self.channel, "guild", None)
        if guild is None:
            return self.voice
        for vc in self.bot.voice_clients:
            if getattr(vc, "guild", None) is not None and vc.guild.id == guild.id:
                return vc
        return None

    @property
    def is_playing(self):
        vc = self.voice
        return bool(vc and (vc.is_playing() or vc.is_paused()))

    @property
    def frames(self):
        return getattr(self._source, "frames", 0)

    @property
    def elapsed(self):
        if self.current is None:
            return None
        vc = self.voice
        if vc is None or not (vc.is_playing() or vc.is_paused()):
            return None
        return max(0.0, self._seek_base + (time.time() - self._seek_ts))

    async def connect(self):
        if self.voice is not None:
            return
        if isinstance(self.channel, discord.abc.GuildChannel):
            await self.channel.connect(self_deaf=True, self_mute=False)
        else:
            await self.channel.connect(ring=config.RING)

    async def keepalive(self):
        delay = 5
        while not self.bot.is_closed():
            vc = self.guild_voice
            if vc is None or not vc.is_connected():
                try:
                    await self.connect()
                    print(f"[player] 24/7 - present dans {self.channel}")
                    delay = 5
                except Exception as exc:
                    print(f"[player] join impossible : {exc} ; nouvelle tentative dans {delay}s")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
                    continue
            await asyncio.sleep(10)

    async def enqueue(self, track, next_=False):
        if next_:
            self.queue.insert(0, track)
        else:
            self.queue.append(track)
        if self.current is None and not self.is_playing:
            await self._advance()

    async def _advance(self):
        async with self._lock:
            skip_flag = self._skipping
            self._skipping = False
            if self.loop == "one" and self.current is not None and not skip_flag:
                await self._play(self.current)
                return
            if not self.queue and self.loop == "all" and self._cycle:
                self.queue.extend(self._cycle)
                self._cycle = []
            self.current = self.queue.pop(0) if self.queue else None
            if self.current is not None:
                if self.loop == "all":
                    self._cycle.append(self.current)
                await self._play(self.current)
            else:
                self._start_idle()

    async def _play(self, track, start_at=0):
        vc = self.voice
        if vc is None:
            self.current = None
            self._start_idle()
            return
        self._cancel_idle()
        encrypted = await self._wait_encryption(vc)
        conn = getattr(vc, "_connection", None)
        version = getattr(conn, "dave_protocol_version", 0)
        session = getattr(conn, "dave_session", None)
        solo = bool(session and len(session.get_user_ids()) <= 1)
        if version == 0:
            print("[player] appel sans chiffrement E2EE")
        elif encrypted:
            print("[player] E2EE actif")
        elif solo:
            print("[player] seul dans l'appel - E2EE arme des qu'un participant rejoint")
        else:
            print("[player] E2EE en attente - le son peut rester muet")

        self._seek_base = float(start_at or 0)
        self._seek_ts = time.time()
        before = FFMPEG_BEFORE
        if start_at:
            before = f"{FFMPEG_BEFORE} -ss {int(start_at)}"
        try:
            source = CountedVolume(
                discord.FFmpegPCMAudio(
                    track.stream_url,
                    executable=config.FFMPEG_PATH,
                    before_options=before,
                    options=FFMPEG_OPTS,
                ),
                volume=self.volume,
            )
            self._source = source
            vc.play(source, after=self._after)
            self._arm_guard()
            if not (self.history and self.history[0] is track):
                self.history.insert(0, track)
                del self.history[50:]
        except Exception as exc:
            print(f"[player] lecture impossible : {exc}")
            self.current = None
            self.bot.loop.create_task(self._advance())

    async def play_tone(self, seconds=8):
        """Joue un sinus local : isole le pipeline vocal de l'extraction web."""
        vc = self.voice
        if vc is None:
            return False, "pas de connexion vocale"
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        await self._wait_encryption(vc)
        path = os.path.join(tempfile.gettempdir(), "ojbs-tone.wav")
        if not os.path.isfile(path):
            make_tone(path, seconds=seconds)
        try:
            source = CountedVolume(
                discord.FFmpegPCMAudio(path, executable=config.FFMPEG_PATH, options=FFMPEG_OPTS),
                volume=self.volume,
            )
            self._source = source
            self._suppress = True
            vc.play(source, after=self._after)
        except Exception as exc:
            return False, str(exc)
        return True, None

    async def _wait_encryption(self, vc, timeout=5.0):
        conn = getattr(vc, "_connection", None)
        if conn is None or getattr(conn, "dave_protocol_version", 0) == 0:
            return False
        waited = 0.0
        while waited < timeout:
            if conn.can_encrypt:
                return True
            await asyncio.sleep(0.5)
            waited += 0.5
        return conn.can_encrypt

    def _after(self, error):
        if error:
            print(f"[player] erreur flux : {error}")
        if self._suppress:
            self._suppress = False
            return
        try:
            asyncio.run_coroutine_threadsafe(self._advance(), self.bot.loop)
        except Exception:
            pass

    async def skip(self, count=1):
        count = max(1, int(count))
        vc = self.voice
        if vc and (vc.is_playing() or vc.is_paused()):
            if count > 1:
                del self.queue[: count - 1]
            self._skipping = True
            vc.stop()
        else:
            if count > 1:
                del self.queue[: count - 1]
            await self._advance()

    async def stop(self):
        self.queue.clear()
        self._cycle.clear()
        self.loop = "off"
        self._cancel_guard()
        vc = self.voice
        if vc and (vc.is_playing() or vc.is_paused()):
            self._skipping = True
            vc.stop()
        self.current = None
        self._start_idle()

    async def pause(self):
        vc = self.voice
        if vc and vc.is_playing():
            vc.pause()
            return True
        return False

    async def resume(self):
        vc = self.voice
        if vc and vc.is_paused():
            vc.resume()
            return True
        return False

    async def seek(self, seconds):
        if self.current is None:
            return False
        vc = self.voice
        if vc is None:
            return False
        self._suppress = True
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        await asyncio.sleep(0.2)
        await self._play(self.current, start_at=max(0, int(seconds)))
        return True

    def set_volume(self, value):
        self.volume = value
        vc = self.voice
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = value

    def set_loop(self, mode):
        self.loop = mode if mode in LOOP_MODES else "off"
        if self.loop != "all":
            self._cycle.clear()
        return self.loop

    def shuffle(self):
        random.shuffle(self.queue)
        return len(self.queue)

    def remove(self, index):
        if 1 <= index <= len(self.queue):
            return self.queue.pop(index - 1)
        return None

    def clear(self):
        count = len(self.queue)
        self.queue.clear()
        return count

    def _arm_guard(self):
        self._cancel_guard()
        self._guard_task = self.bot.loop.create_task(self._guard_watch())

    def _cancel_guard(self):
        task = self._guard_task
        self._guard_task = None
        if task and not task.done():
            task.cancel()

    async def _guard_watch(self):
        misses = 0
        while True:
            await asyncio.sleep(5)
            if self.current is None:
                return
            vc = self.voice
            if vc is not None and vc.is_connected():
                misses = 0
                continue
            misses += 1
            print(f"[player] connexion vocale perdue ({misses})")
            if misses < 2:
                continue
            try:
                await self.connect()
                if self.current is not None and not self.is_playing:
                    await self._play(self.current)
                misses = 0
            except Exception as exc:
                print(f"[player] reconnexion impossible : {exc}")

    def _start_idle(self):
        if config.IDLE_TIMEOUT <= 0:
            return
        self._cancel_idle()
        self._idle_task = self.bot.loop.create_task(self._idle_watch())

    def _cancel_idle(self):
        task = self._idle_task
        self._idle_task = None
        if task and not task.done():
            task.cancel()

    async def _idle_watch(self):
        try:
            await asyncio.sleep(config.IDLE_TIMEOUT)
        except asyncio.CancelledError:
            return
        vc = self.voice
        if vc and not self.is_playing and self.current is None and not self.queue:
            try:
                await vc.disconnect()
                print(f"[player] deconnexion inactivite : {self.channel}")
            except Exception:
                pass
            self.bot.players.pop(self.channel.id, None)


def get_player(bot, channel):
    player = bot.players.get(channel.id)
    if player is None:
        player = ChannelPlayer(bot, channel)
        bot.players[channel.id] = player
    return player


def find_player_in_guild(bot, guild):
    for player in bot.players.values():
        channel = player.channel
        if getattr(channel, "guild", None) is not None and channel.guild.id == guild.id:
            return player
    return None
