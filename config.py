import os
import shutil

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env_file():
    """Charge les paires CLE=valeur du fichier .env local dans os.environ.

    Entrée : aucune (lit ./.env s'il existe).
    Sortie : aucune ; les variables deja presentes dans l'environnement priment.
    """
    path = os.path.join(_HERE, ".env")
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

TOKEN = os.getenv("TOKEN", "")
PREFIX = "!"
IDLE_TIMEOUT = 0             # 0 = ne quitte jamais le vocal ; >0 = secondes d'inactivite avant de raccrocher
RING = False                 # False = rejoint sans sonner (aucun appel sortant vers les autres)
AUTO_JOIN_CHANNEL_ID = 1571221475564986469  # appel/DM/groupe rejoint au demarrage, 0 = desactive
VOLUME_DEFAULT = 0.5         # 0.0 - 1.0
DEBUG = False                # True = chaque message recu s'affiche en console

# Seuls ces comptes declenchent des commandes. Retire une ligne pour fermer l'acces.
ALLOWED_IDS = {
    788880843493343242,      # compte du bot
    340157235554418689,
    927201944056004638,
    926267849243234375,
    1077293871177924718,
    1317914204971204641,
}

_LOCAL_FFMPEG = os.path.join(_HERE, "ffmpeg", "bin", "ffmpeg.exe")


def _resolve_ffmpeg():
    if os.path.isfile(_LOCAL_FFMPEG):
        return _LOCAL_FFMPEG
    return shutil.which("ffmpeg") or "ffmpeg"


FFMPEG_PATH = _resolve_ffmpeg()
