"""Etat du mode musique."""

MUSIC = False


def set_music(enabled: bool) -> None:
    global MUSIC
    MUSIC = enabled
