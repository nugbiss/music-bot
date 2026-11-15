"""Convertit un cookies.txt YouTube en valeur pour YTDL_COOKIES_B64.

Entrée : fichier cookies.txt placé à côté de ce script.
Sortie : YTDL_COOKIES_B64.txt (la chaîne) + copie dans le presse-papier.
"""

import base64
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "cookies.txt")
OUT = os.path.join(HERE, "YTDL_COOKIES_B64.txt")


def main():
    if not os.path.isfile(SRC):
        print("cookies.txt introuvable.")
        print(f"Place-le ici : {SRC}")
        print("Export : extension 'Get cookies.txt LOCALLY', connecte a youtube.com.")
        return 1

    with open(SRC, "rb") as handle:
        raw = handle.read()

    if b"Netscape HTTP Cookie File" not in raw[:200] and b"\t" not in raw[:2000]:
        print("Ce fichier ne ressemble pas a un cookies.txt Netscape.")
        return 1

    encoded = base64.b64encode(raw).decode("ascii")

    with open(OUT, "w", encoding="ascii") as handle:
        handle.write(encoded)

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
            input=encoded.encode("ascii"),
            check=True,
        )
        copied = True
    except Exception:
        copied = False

    print(f"OK - {len(encoded)} caracteres")
    print(f"Fichier : {OUT}")
    print("Copie dans le presse-papier." if copied else "Copie manuelle : ouvre le fichier et Ctrl+A, Ctrl+C.")
    print("Render > Environment > YTDL_COOKIES_B64 > colle la valeur > Save.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
