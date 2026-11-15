# Discord Music Selfbot

Bot musique vocal Discord en français, qui tourne sur un compte utilisateur via
`discord.py-self`. Il rejoint le salon vocal de l'auteur de la commande (ou un
appel/groupe DM) et joue l'audio avec FFmpeg et Opus.

## Ce qu'il fait

- Lecture YouTube, SoundCloud, Spotify et liens directs via `yt-dlp`.
- File d'attente : ajout en fin ou en tête, recherche interactive sur 5 résultats,
  shuffle, retrait, vidage, historique.
- Contrôle : pause, reprise, skip multiple, seek, volume, boucle (off / titre / file).
- Mode musique commutable (`!music`) : sans lui, les commandes de lecture sont
  refusées.
- 24/7 : rejoint au démarrage le salon défini par `AUTO_JOIN_CHANNEL_ID` et y reste.
- Chiffrement vocal DAVE : correctif `dave_fix.py` qui complète la poignée de main
  manquante dans `discord.py-self`.
- Accès restreint : seuls les comptes listés dans `ALLOWED_IDS` (dans `config.py`)
  déclenchent des commandes.
- Préfixe `!` (`play`, `pn`, `search`, `pick`, `pause`, `resume`, `seek`, `skip`,
  `stop`, `queue`, `shuffle`, `remove`, `clear`, `loop`, `np`, `volume`, `history`,
  `ping`, `help`).

## Installation locale

```bash
pip install -r requirements.txt
```

Crée un fichier `.env` à la racine et mets-y ton token :

```
TOKEN=ton_token
```

Puis lance :

```bash
python bot.py
```

Sous Windows, `python setup.py` télécharge FFmpeg et libopus dans le projet, et
`demarrer.bat` installe les dépendances puis démarre le bot.

Le dossier `ffmpeg/` (489 Mo de binaires) n'est pas versionné : `.gitignore` l'exclut,
`setup.py` le retélécharge en local, et Railway l'installe par `nixpacks.toml`.

Le token n'est jamais écrit dans le code : il vient de la variable d'environnement
`TOKEN`, ou du fichier `.env` chargé au démarrage.

## Deploy Railway

1. Upload sur GitHub — pousse le dossier du projet (`.env` est ignoré par
   `.gitignore`).
2. Connecter Railway au repo — New Project → Deploy from GitHub repo → sélectionne
   le repo.
3. Ajouter variable TOKEN dans Railway Variables — onglet Variables → `TOKEN` =
   ton token Discord.
4. Deploy — Railway exécute `worker: python bot.py` (Procfile) et installe FFmpeg
   et libopus via `nixpacks.toml`.

## Deploy Render

Render ne fournit ni FFmpeg ni libopus en runtime Python natif, et un Web Service
doit ouvrir un port : le `Dockerfile` règle les deux, `health.py` répond sur `PORT`.

1. Repo GitHub avec `Dockerfile` et `health.py` à la racine.
2. New → Web Service → connecte le repo → Language : **Docker**.
3. Branch `main`, Root Directory vide, Build Command et Start Command vides.
4. Instance : **Starter** (le plan Free s'endort après 15 min sans requête HTTP).
5. Environment → `TOKEN` = ton token Discord.
6. Deploy.

`health.py` ouvre un port seulement si la variable `PORT` existe : en local, rien
ne change.

## Fichiers

| fichier | rôle |
|---|---|
| `bot.py` | point d'entrée, client, événements, 24/7 |
| `commands.py` | cog des commandes musique |
| `player.py` | connexion vocale, file, lecture FFmpeg |
| `config.py` | token, préfixe, IDs autorisés, FFmpeg |
| `dave_fix.py` | correctif chiffrement vocal DAVE |
| `modes.py` | état du mode musique |
| `setup.py` | installation Windows (FFmpeg, libopus, deps) |
