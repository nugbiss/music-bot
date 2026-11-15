import time

import discord
from discord.ext import commands

import config
import modes
from player import find_player_in_guild, fmt_duration, get_player, resolve, search

HELP_TEXT = """**Mode**
`{p}music` — active / coupe le bot musique

**Lecture**
`{p}play <titre ou URL>` — YouTube, SoundCloud, Spotify, lien direct
`{p}pn <titre ou URL>` — ajoute en tete de file
`{p}search <titre>` puis `{p}pick <n>` — choisit parmi 5 resultats
`{p}pause` / `{p}resume` — pause et reprise
`{p}seek <mm:ss>` — saute a un moment du titre
`{p}skip [n]` — passe n titre(s)
`{p}stop` — arrete et vide la file

**File**
`{p}queue` — file en cours
`{p}shuffle` — melange la file
`{p}remove <n>` — retire un titre de la file
`{p}clear` — vide la file (le titre en cours continue)
`{p}loop [off|one|all]` — boucle
`{p}np` — titre en cours et position
`{p}volume <0-100>` — volume
`{p}history` — derniers titres joues
`{p}ping` / `{p}help`"""

SEARCH_TTL = 120

LOOP_LABELS = {"off": "desactivee", "one": "titre en boucle", "all": "file en boucle"}


def music_mode_check():
    async def predicate(ctx):
        if not modes.MUSIC:
            await ctx.send(
                f"❌ Mode musique inactif — `{config.PREFIX}music` pour l'activer."
            )
            return False
        return True

    return commands.check(predicate)


def _is_dm_context(ctx):
    return ctx.guild is None and isinstance(ctx.channel, (discord.DMChannel, discord.GroupChannel))


def _play_target(ctx):
    if ctx.guild is None:
        if _is_dm_context(ctx):
            return ctx.channel
        return None
    voice_state = getattr(ctx.author, "voice", None)
    if not voice_state or not voice_state.channel:
        return "voice_manquant"
    return voice_state.channel


def _control_player(bot, ctx):
    if ctx.guild is None:
        if not _is_dm_context(ctx):
            return None
        return bot.players.get(ctx.channel.id)
    voice_state = getattr(ctx.author, "voice", None)
    if voice_state and voice_state.channel:
        player = bot.players.get(voice_state.channel.id)
        if player is not None:
            return player
    return find_player_in_guild(bot, ctx.guild)


def _parse_time(value):
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3:
        return None
    total = 0
    for part in parts:
        if not part.isdigit():
            return None
        total = total * 60 + int(part)
    return total


def _queue_total(queue, current=None):
    seconds = sum(t.duration or 0 for t in queue)
    if current is not None:
        seconds += current.duration or 0
    return seconds


def _short_error(exc):
    """Résume une exception en une ligne lisible pour Discord.

    Entrée : exception levée par yt-dlp ou le réseau.
    Sortie : chaîne courte ; signale le blocage d'IP quand cookies absents.
    """
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    if "Sign in" in text or "not a bot" in text or "reloaded" in text:
        return text + " — YouTube bloque l'IP du serveur, ajoute YTDL_COOKIES_B64"
    return text[:180]


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._searches = {}

    @commands.command(name="music", aliases=["musique"])
    async def music(self, ctx):
        if modes.MUSIC:
            modes.set_music(False)
            return await ctx.send("🎵 Mode musique desactive.")
        modes.set_music(True)
        await ctx.send(
            f"🎵 Mode musique actif. `{config.PREFIX}play <titre>` pour lancer."
        )

    async def _attach(self, ctx):
        target = _play_target(ctx)
        if target is None:
            await ctx.send("❌ Salon texte inattendu pour les commandes musique.")
            return None
        if target == "voice_manquant":
            await ctx.send("❌ Rejoins d'abord un salon vocal.")
            return None
        player = get_player(self.bot, target)
        try:
            await player.connect()
        except Exception as exc:
            await ctx.send(f"❌ Connexion vocale impossible : `{exc}`")
            return None
        return player

    async def _queue_track(self, ctx, query, next_=False):
        player = await self._attach(ctx)
        if player is None:
            return
        note = await ctx.send(f"🔎 Recherche : `{query[:100]}`")
        try:
            track = await resolve(query, ctx.author)
        except Exception as exc:
            return await note.edit(content=f"❌ Rien trouve pour `{query[:100]}` : `{_short_error(exc)}`")
        was_idle = player.current is None and not player.is_playing and not player.queue
        await player.enqueue(track, next_=next_)
        duration = fmt_duration(track.duration)
        if was_idle:
            await note.edit(content=f"▶️ **{track.title}** `[{duration}]`")
        elif next_:
            await note.edit(content=f"⏭️ **{track.title}** `[{duration}]` — joue juste apres le titre en cours")
        else:
            await note.edit(content=f"➕ **{track.title}** `[{duration}]` — position {len(player.queue)}")

    @commands.command(name="play", aliases=["p", "joue"])
    @music_mode_check()
    async def play(self, ctx, *, query: str = None):
        if not query:
            return await ctx.send(f"❌ Utilisation : `{config.PREFIX}play <nom ou URL>`")
        await self._queue_track(ctx, query)

    @commands.command(name="playnext", aliases=["pn", "suivant"])
    @music_mode_check()
    async def playnext(self, ctx, *, query: str = None):
        if not query:
            return await ctx.send(f"❌ Utilisation : `{config.PREFIX}pn <nom ou URL>`")
        await self._queue_track(ctx, query, next_=True)

    @commands.command(name="search", aliases=["cherche"])
    @music_mode_check()
    async def search_cmd(self, ctx, *, query: str = None):
        if not query:
            return await ctx.send(f"❌ Utilisation : `{config.PREFIX}search <titre>`")
        note = await ctx.send(f"🔎 Recherche : `{query[:100]}`")
        try:
            results = await search(query, 5)
        except Exception as exc:
            return await note.edit(content=f"❌ Recherche impossible : `{_short_error(exc)}`")
        if not results:
            return await note.edit(content=f"❌ Aucun resultat pour `{query[:100]}`")
        self._searches[ctx.channel.id] = (results, time.time())
        lines = [f"**Resultats** pour `{query[:80]}` — `{config.PREFIX}pick <n>`"]
        for index, item in enumerate(results, start=1):
            lines.append(f"`{index}.` {item['title'][:90]} `[{fmt_duration(item['duration'])}]`")
        await note.edit(content="\n".join(lines))

    @commands.command(name="pick", aliases=["choix", "choisir"])
    @music_mode_check()
    async def pick(self, ctx, index: int = None):
        entry = self._searches.get(ctx.channel.id)
        if entry is None:
            return await ctx.send(f"❌ Aucune recherche recente — `{config.PREFIX}search <titre>`.")
        results, stamp = entry
        if time.time() - stamp > SEARCH_TTL:
            self._searches.pop(ctx.channel.id, None)
            return await ctx.send(f"❌ Recherche expiree — refais `{config.PREFIX}search`.")
        if index is None or not 1 <= index <= len(results):
            return await ctx.send(f"❌ Choisis un numero entre 1 et {len(results)}.")
        await self._queue_track(ctx, results[index - 1]["url"])

    @commands.command(name="skip", aliases=["s", "next"])
    @music_mode_check()
    async def skip(self, ctx, count: int = 1):
        player = _control_player(self.bot, ctx)
        if player is None or (not player.current and not player.queue and not player.is_playing):
            return await ctx.send("❌ Rien en lecture.")
        await player.skip(count)
        if count > 1:
            await ctx.send(f"⏭️ {count} titres passes.")
        else:
            await ctx.send("⏭️ Titre passe.")

    @commands.command(name="stop", aliases=["st"])
    async def stop(self, ctx):
        player = _control_player(self.bot, ctx)
        if player is None:
            return await ctx.send("❌ Rien en lecture.")
        await player.stop()
        await ctx.send("⏹️ Lecture arretee, file videe.")

    @commands.command(name="pause")
    @music_mode_check()
    async def pause(self, ctx):
        player = _control_player(self.bot, ctx)
        if player is None:
            return await ctx.send("❌ Rien en lecture.")
        if await player.pause():
            return await ctx.send("⏸️ Lecture en pause.")
        await ctx.send("❌ Rien a mettre en pause.")

    @commands.command(name="resume", aliases=["reprendre"])
    @music_mode_check()
    async def resume(self, ctx):
        player = _control_player(self.bot, ctx)
        if player is None:
            return await ctx.send("❌ Rien en lecture.")
        if await player.resume():
            return await ctx.send("▶️ Lecture reprise.")
        await ctx.send("❌ La lecture n'est pas en pause.")

    @commands.command(name="seek", aliases=["avance"])
    @music_mode_check()
    async def seek(self, ctx, position: str = None):
        player = _control_player(self.bot, ctx)
        if player is None or not player.current:
            return await ctx.send("❌ Rien en lecture.")
        if not position:
            return await ctx.send(f"❌ Utilisation : `{config.PREFIX}seek <mm:ss>`")
        seconds = _parse_time(position)
        if seconds is None:
            return await ctx.send("❌ Format attendu : `90`, `1:30` ou `1:02:03`.")
        if player.current.duration and seconds >= player.current.duration:
            return await ctx.send(f"❌ Le titre dure `{fmt_duration(player.current.duration)}`.")
        await player.seek(seconds)
        await ctx.send(f"⏩ Position : `{fmt_duration(seconds)}`")

    @commands.command(name="queue", aliases=["q", "file"])
    @music_mode_check()
    async def queue_cmd(self, ctx):
        player = _control_player(self.bot, ctx)
        if player is None or (not player.current and not player.queue):
            return await ctx.send("📭 File vide.")
        lines = []
        if player.current:
            position = player.elapsed
            stamp = f" `[{fmt_duration(position)} / {fmt_duration(player.current.duration)}]`" if position is not None else ""
            lines.append(f"▶️ **{player.current.title}**{stamp}")
        for index, track in enumerate(player.queue[:20], start=1):
            lines.append(f"`{index:02d}.` {track.title} `[{fmt_duration(track.duration)}]`")
        if len(player.queue) > 20:
            lines.append(f"… et {len(player.queue) - 20} autre(s)")
        total = _queue_total(player.queue, player.current)
        if total:
            lines.append(f"\n**Durée totale** `{fmt_duration(total)}` — {len(player.queue)} en file")
        await ctx.send("\n".join(lines))

    @commands.command(name="np", aliases=["nowplaying", "encours"])
    @music_mode_check()
    async def nowplaying(self, ctx):
        player = _control_player(self.bot, ctx)
        if player is None or not player.current:
            return await ctx.send("❌ Rien en lecture.")
        track = player.current
        position = player.elapsed
        if position is not None:
            text = f"🎵 **{track.title}** `[{fmt_duration(position)} / {fmt_duration(track.duration)}]` — volume {int(player.volume * 100)}%"
        else:
            text = f"🎵 **{track.title}** `[{fmt_duration(track.duration)}]` — volume {int(player.volume * 100)}%"
        if player.loop != "off":
            text += f"\n🔁 Boucle : {LOOP_LABELS[player.loop]}"
        if track.uploader:
            text += f"\n📺 {track.uploader}"
        if track.webpage_url:
            text += f"\n🔗 {track.webpage_url}"
        if track.requester:
            text += f"\n👤 Demande par {track.requester.mention}"
        await ctx.send(text)

    @commands.command(name="volume", aliases=["vol"])
    @music_mode_check()
    async def volume(self, ctx, value: str = None):
        player = _control_player(self.bot, ctx)
        if player is None:
            return await ctx.send("❌ Rien en lecture.")
        if value is None:
            return await ctx.send(f"🔊 Volume actuel : {int(player.volume * 100)}%")
        try:
            level = int(value)
        except ValueError:
            return await ctx.send(f"❌ Utilisation : `{config.PREFIX}volume <0-100>`")
        if not 0 <= level <= 100:
            return await ctx.send("❌ Le volume doit etre entre 0 et 100.")
        player.set_volume(level / 100)
        await ctx.send(f"🔊 Volume regle sur {level}%")

    @commands.command(name="loop", aliases=["boucle", "repeat"])
    @music_mode_check()
    async def loop(self, ctx, mode: str = None):
        player = _control_player(self.bot, ctx)
        if player is None:
            return await ctx.send("❌ Rien en lecture.")
        if mode is None:
            order = ("off", "one", "all")
            current = order.index(player.loop) if player.loop in order else 0
            mode = order[(current + 1) % len(order)]
        mode = mode.lower()
        mode = {"track": "one", "titre": "one", "queue": "all", "file": "all", "non": "off"}.get(mode, mode)
        if mode not in ("off", "one", "all"):
            return await ctx.send(f"❌ Utilisation : `{config.PREFIX}loop [off|one|all]`")
        player.set_loop(mode)
        symbols = {"off": "➡️", "one": "🔂", "all": "🔁"}
        await ctx.send(f"{symbols[mode]} Boucle : {LOOP_LABELS[mode]}")

    @commands.command(name="shuffle", aliases=["melange"])
    @music_mode_check()
    async def shuffle(self, ctx):
        player = _control_player(self.bot, ctx)
        if player is None or not player.queue:
            return await ctx.send("📭 File vide.")
        count = player.shuffle()
        await ctx.send(f"🔀 File melangee — {count} titre(s).")

    @commands.command(name="remove", aliases=["retire"])
    @music_mode_check()
    async def remove(self, ctx, index: int = None):
        player = _control_player(self.bot, ctx)
        if player is None or not player.queue:
            return await ctx.send("📭 File vide.")
        if index is None or not 1 <= index <= len(player.queue):
            return await ctx.send(f"❌ Choisis un numero entre 1 et {len(player.queue)}.")
        track = player.remove(index)
        await ctx.send(f"🗑️ **{track.title}** retire de la file.")

    @commands.command(name="clear", aliases=["vide"])
    @music_mode_check()
    async def clear(self, ctx):
        player = _control_player(self.bot, ctx)
        if player is None or not player.queue:
            return await ctx.send("📭 File deja vide.")
        count = player.clear()
        await ctx.send(f"🧹 {count} titre(s) retires de la file.")

    @commands.command(name="history", aliases=["historique"])
    @music_mode_check()
    async def history(self, ctx):
        player = _control_player(self.bot, ctx)
        if player is None or not player.history:
            return await ctx.send("📭 Aucun titre joue.")
        lines = ["**Derniers titres**"]
        for index, track in enumerate(player.history[:10], start=1):
            lines.append(f"`{index:02d}.` {track.title} `[{fmt_duration(track.duration)}]`")
        await ctx.send("\n".join(lines))

    @commands.command(name="ping", aliases=["latence", "pong"])
    async def ping(self, ctx):
        started = time.perf_counter()
        message = await ctx.send("🏓 …")
        elapsed = (time.perf_counter() - started) * 1000
        ws = self.bot.latency * 1000
        await message.edit(content=f"🏓 Pong — aller-retour {elapsed:.0f} ms | websocket {ws:.0f} ms")

    @commands.command(name="help", aliases=["h", "aide"])
    async def help_cmd(self, ctx):
        await ctx.send(HELP_TEXT.format(p=config.PREFIX))
