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

### Si YouTube refuse les recherches sur Render

Les IP de datacenter déclenchent « Sign in to confirm you're not a bot ». Le bot
essaie deux jeux de clients YouTube, puis **bascule automatiquement sur
SoundCloud** : `!play` et `!search` continuent de fonctionner depuis Render même
quand YouTube bloque. Pour récupérer YouTube en plus, trois sorties :

**1. Cookies d'un compte YouTube (gratuit, le plus fiable)**

1. Double-clique `export-cookies.bat` : le script lit le navigateur installé
   (Edge, Brave, Chrome, Opera), déchiffre les cookies YouTube et écrit
   `cookies.txt` à côté de `bot.py`. Sans extension. Si le navigateur n'a pas de
   session YouTube ouverte, il le dit.
   Variante manuelle : connecté à YouTube, exporte `cookies.txt` avec
   l'extension « Get cookies.txt LOCALLY ».
2. Double-clique `cookies.bat` → la valeur base64 est copiée dans le
   presse-papier (et écrite dans `YTDL_COOKIES_B64.txt`).
3. Render → Environment → `YTDL_COOKIES_B64` = colle la valeur.
4. Manual Deploy. `config.py` écrit le fichier dans le dossier temporaire au
   démarrage et yt-dlp l'utilise.

`cookies.txt` et `YTDL_COOKIES_B64.txt` sont dans `.gitignore` — ils ne partent
jamais sur GitHub.

**2. Proxy sortant (autre IP pour YouTube)**

Render → Environment → `PROXY_URL` = `http://user:pass@host:port` ou
`socks5://host:port`. yt-dlp fait passer toute l'extraction par cette sortie.

**3. Faire tourner le bot chez toi**

Une IP résidentielle n'est pas bloquée : `python bot.py` en local, ou le même
service lancé sur un PC/VPS perso. Les instances publiques Invidious/Piped ne
sont pas une option — testées hors service ou en 403.

### Les titres s'arretent au bout de 30 s

SoundCloud renvoie un extrait de 30 s pour les titres sous label. Le bot detecte
ces extraits (`cf-preview-media`, `format_id` en `_preview`) et les ecarte : il
essaie les resultats suivants jusqu'a un flux complet, et `!search` ne propose
que des titres jouables en entier.

## Rien ne s'entend dans le vocal

Trois étapes, dans cet ordre.

1. `!test` — le bot génère un sinus 440 Hz en local et le joue. Aucun réseau,
   aucune extraction : si tu l'entends, le pipeline vocal est bon et le problème
   est dans la source ; si tu n'entends rien, c'est opus, FFmpeg ou le chiffrement
   E2EE.
2. `!diag` — affiche la version d'opus, FFmpeg, yt-dlp, davey, le protocole E2EE,
   `can_encrypt`, l'état de la session DAVE et le nombre de trames envoyées.
3. `!test` affiche ensuite le nombre de paquets envoyes et l'etat E2EE ; `!rejoin` coupe et refait le handshake DAVE complet.
4. `!np` — le compteur `trame` monte d'environ 50 par seconde pendant la lecture.
   Il reste à 0 → FFmpeg ne lit pas le flux. Il monte et le silence persiste →
   E2EE : la ligne `e2ee : ... can_encrypt=False` le confirme.

Logs Render utiles : `[bot] opus : charge`, `[bot] dave : correctif actif`,
`[player] E2EE actif`, `[player] erreur flux : ...`.

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
| `cookies.py` | installation des cookies YouTube déposés dans Discord |
| `cookies_export.py` | extraction des cookies YouTube depuis le navigateur local |
| `cookies_to_b64.py` | encode `cookies.txt` pour Render (`cookies.bat`) |
| `diag.py` | état audio pour `!diag` |
| `taps.py` | compteur de paquets audio, capture des erreurs |
