"""Extrait les cookies YouTube du navigateur vers un cookies.txt au format Netscape.

Edge, Brave, Chrome et Opera (Chromium) chiffrent les cookies : DPAPI pour la cle
maitresse, AES-256-GCM pour chaque valeur. Le script lit la cle dans Local State,
dechiffre, et n'ecrit que les domaines youtube.com / google.com. Aucune dependance.
"""

import base64
import ctypes
import ctypes.wintypes as wintypes
import glob
import json
import os
import sqlite3
import subprocess
import sys
import time

import aesgcm

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "cookies.txt")

LOCAL = os.environ.get("LOCALAPPDATA", "")
ROAM = os.environ.get("APPDATA", "")

BROWSERS = (
    ("Edge", os.path.join(LOCAL, r"Microsoft\Edge\User Data")),
    ("Brave", os.path.join(LOCAL, r"BraveSoftware\Brave-Browser\User Data")),
    ("Chrome", os.path.join(LOCAL, r"Google\Chrome\User Data")),
    ("Opera GX", os.path.join(ROAM, r"Opera Software\Opera GX Stable")),
    ("Opera", os.path.join(ROAM, r"Opera Software\Opera Stable")),
)

AUTH_NAMES = {
    "SID", "HSID", "SSID", "APISID", "SAPISID",
    "LOGIN_INFO", "SIDCC", "SSIDCC",
    "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PAPISID", "__Secure-3PAPISID",
}

PROCESSES = {
    "Edge": "msedge",
    "Brave": "brave",
    "Chrome": "chrome",
    "Opera GX": "opera",
    "Opera": "opera",
}


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptUnprotectData.restype = wintypes.BOOL
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p


def dpapi(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.c_void_p))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def local_key(root):
    state = os.path.join(root, "Local State")
    if not os.path.isfile(state):
        return None
    with open(state, "r", encoding="utf-8") as handle:
        raw = json.load(handle).get("os_crypt", {}).get("encrypted_key")
    return dpapi(base64.b64decode(raw)[5:]) if raw else None


def decrypt_value(blob, key):
    if not blob:
        return ""
    if blob[:3] in (b"v10", b"v11"):
        return aesgcm.decrypt(key, blob[3:15], blob[15:-16], blob[-16:]).decode("utf-8", "replace")
    if blob[:3] == b"v20":
        raise RuntimeError("app-bound")
    return dpapi(blob).decode("utf-8", "replace")


def profiles(root):
    found = [os.path.join(root, "Default")] + sorted(glob.glob(os.path.join(root, "Profile *")))
    found = [p for p in found if os.path.isdir(p)]
    if not found and os.path.isdir(os.path.join(root, "Network")):
        found = [root]
    return found


def read_profile(db, key):
    rows, last = None, None
    for params in ("?mode=ro", "?mode=ro&immutable=1"):
        try:
            con = sqlite3.connect("file:" + db.replace("\\", "/") + params, uri=True, timeout=2)
            try:
                rows = con.execute(
                    "select host_key, name, value, encrypted_value, path, expires_utc, is_secure "
                    "from cookies where host_key like '%youtube.com' or host_key like '%google.com'"
                ).fetchall()
            finally:
                con.close()
            break
        except sqlite3.Error as exc:
            last = exc
    if rows is None:
        raise last
    out, blocked = [], 0
    for host, name, value, blob, path, expires, secure in rows:
        if not value:
            try:
                value = decrypt_value(blob, key)
            except RuntimeError:
                blocked += 1
                continue
            except (OSError, ValueError):
                continue
        if not value or any(c in value for c in "\t\r\n"):
            continue
        expiry = int(expires / 1000000 - 11644473600) if expires else 0
        out.append((host, name, value, path or "/", int(bool(secure)), max(expiry, 0)))
    return out, blocked


def collect():
    best, notes = None, []
    for label, root in BROWSERS:
        if not root or not os.path.isdir(root):
            continue
        try:
            key = local_key(root)
        except (OSError, ValueError):
            notes.append(f"{label} : cle DPAPI illisible")
            continue
        if not key:
            continue
        for profile in profiles(root):
            db = os.path.join(profile, "Network", "Cookies")
            if not os.path.isfile(db):
                db = os.path.join(profile, "Cookies")
            if not os.path.isfile(db):
                continue
            try:
                rows, blocked = read_profile(db, key)
            except sqlite3.Error as exc:
                notes.append(f"{label} / {os.path.basename(profile)} : base illisible ({exc})")
                continue
            if blocked:
                notes.append(f"{label} / {os.path.basename(profile)} : {blocked} cookies app-bound")
            score = sum(1 for row in rows if row[1] in AUTH_NAMES)
            if rows and (best is None or score > best[3]):
                best = (label, os.path.basename(profile), rows, score)
                if score >= 2:
                    return best, notes
    return best, notes


def write_netscape(rows):
    seen, lines = set(), []
    for host, name, value, path, secure, expiry in rows:
        ident = (host, name, path)
        if ident in seen:
            continue
        seen.add(ident)
        flag = "TRUE" if host.startswith(".") else "FALSE"
        lines.append("\t".join((host, flag, path, "TRUE" if secure else "FALSE", str(expiry), name, value)))
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Netscape HTTP Cookie File\n")
        handle.write("# https://curl.haxx.se/docs/http-cookies.html\n\n")
        handle.write("\n".join(lines))
        handle.write("\n")
    return len(lines)


def is_running(exe):
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}.exe", "/NH"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return exe.lower() in out.lower()


def close_browsers():
    killed = []
    for label, exe in PROCESSES.items():
        if not any(label == name for name, _ in BROWSERS):
            continue
        if is_running(exe) and exe not in killed:
            subprocess.run(["taskkill", "/IM", f"{exe}.exe", "/F"], capture_output=True, timeout=15)
            killed.append(exe)
    if killed:
        time.sleep(2)
    return killed


def reopen_browsers(killed):
    for exe in killed:
        subprocess.run(["cmd", "/c", "start", "", exe], capture_output=True, timeout=15)


def main(force_close=False):
    killed = close_browsers() if force_close else []
    try:
        found, notes = collect()
        for note in notes:
            print(f"  ! {note}")
        if not found:
            locked = any("illisible" in note for note in notes)
            if locked and not force_close:
                print("La base des cookies est verrouillee par le navigateur ouvert.")
                return 4
            if locked:
                print("Bases toujours verrouillees apres fermeture (autre profil ou antivirus).")
                return 1
            print("Aucun profil de navigateur trouve. Ouvre Edge, connecte-toi sur youtube.com, relance.")
            return 1
        label, profile, rows, score = found
        total = write_netscape(rows)
        print(f"Navigateur : {label} / {profile}")
        print(f"Cookies youtube.com + google.com : {total}")
        print("Session connectee : " + ("oui" if score else f"AUCUNE - connecte-toi sur youtube.com dans {label}"))
        print(f"Fichier : {OUT_PATH}")
        if not score:
            return 2
        print("OK - glisse ce fichier en piece jointe dans la conversation Discord du bot.")
        return 0
    finally:
        reopen_browsers(killed)


if __name__ == "__main__":
    try:
        sys.exit(main("--force-close" in sys.argv[1:]))
    except Exception as exc:
        print(f"ECHEC : {type(exc).__name__} : {exc}")
        sys.exit(3)
