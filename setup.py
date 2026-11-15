import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR = os.path.join(PROJECT_DIR, "ffmpeg")
FFMPEG_BIN = os.path.join(FFMPEG_DIR, "bin", "ffmpeg.exe")
FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
    "ffmpeg-master-latest-win64-gpl.zip"
)


def log(message):
    print(message, flush=True)


def install_deps():
    log("==> Installation des dependances pip")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", os.path.join(PROJECT_DIR, "requirements.txt")]
    )


def find_ffmpeg():
    if os.path.isfile(FFMPEG_BIN):
        return FFMPEG_BIN
    return shutil.which("ffmpeg")


def download_ffmpeg():
    log("==> FFmpeg absent, telechargement (~150 Mo, une seule fois)")
    os.makedirs(FFMPEG_DIR, exist_ok=True)
    archive = os.path.join(FFMPEG_DIR, "ffmpeg.zip")

    def progress(blocks, block_size, total):
        if total > 0:
            done = min(blocks * block_size, total)
            percent = done * 100 // total
            mb_done = done // (1024 * 1024)
            mb_total = total // (1024 * 1024)
            sys.stdout.write(f"\r    {percent:3d}%  {mb_done} / {mb_total} Mo")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(FFMPEG_URL, archive, reporthook=progress)
        print()
        log("==> Extraction de ffmpeg.exe / ffprobe.exe")
        with zipfile.ZipFile(archive) as zf:
            for member in zf.namelist():
                name = member.replace("\\", "/")
                if "/bin/" in name and name.lower().endswith(".exe"):
                    target_dir = os.path.join(FFMPEG_DIR, "bin")
                    os.makedirs(target_dir, exist_ok=True)
                    target = os.path.join(target_dir, os.path.basename(name))
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    finally:
        if os.path.isfile(archive):
            os.remove(archive)


def ensure_libopus():
    target_dir = os.path.join(PROJECT_DIR, "libs")
    target = os.path.join(target_dir, "libopus-0.x64.dll")
    if os.path.isfile(target):
        log("==> libopus deja present")
        return True
    os.makedirs(target_dir, exist_ok=True)
    temp_dir = tempfile.mkdtemp()
    try:
        log("==> libopus absent, recuperation depuis le wheel py-cord")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "download", "py-cord", "--no-deps", "-d", temp_dir],
            stdout=subprocess.DEVNULL,
        )
        for name in os.listdir(temp_dir):
            if not name.endswith(".whl"):
                continue
            with zipfile.ZipFile(os.path.join(temp_dir, name)) as zf:
                for member in zf.namelist():
                    if member.endswith("libopus-0.x64.dll"):
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        return os.path.isfile(target)
    except Exception as exc:
        log(f"libopus introuvable : {exc}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return False


def main():
    if find_ffmpeg():
        log("==> FFmpeg deja disponible")
    else:
        try:
            download_ffmpeg()
        except Exception as exc:
            log(f"Telechargement FFmpeg impossible : {exc}")
            log("Installe-le a la main (winget install Gyan.FFmpeg) puis relance ce script.")
            sys.exit(1)

    try:
        install_deps()
    except subprocess.CalledProcessError as exc:
        log(f"Installation des dependances en echec : {exc}")
        log("Relance le terminal en administrateur si pip refuse d'ecrire.")
        sys.exit(1)

    if not find_ffmpeg():
        log("FFmpeg introuvable apres installation.")
        sys.exit(1)

    if not ensure_libopus():
        log("libopus absent : le vocal restera muet. Place libopus-0.x64.dll dans libs/.")
        sys.exit(1)

    log("✅ Setup terminé — lance bot.py pour démarrer")


if __name__ == "__main__":
    main()
