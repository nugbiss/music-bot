"""Extrait les cookies YouTube du navigateur vers un cookies.txt au format Netscape.

Edge, Brave, Chrome et Opera (Chromium) chiffrent les cookies (DPAPI + AES-GCM) :
le script lit la cle dans Local State, dechiffre via CNG, et n'ecrit que les
domaines youtube.com / google.com. Aucune dependance externe.
"""

import base64
import ctypes
import ctypes.wintypes as wintypes
import glob
import json
import os
import sqlite3
import sys

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

crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
bcrypt = ctypes.WinDLL("bcrypt", use_last_error=True)


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


class AUTH_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.ULONG),
        ("dwInfoVersion", wintypes.ULONG),
        ("pbNonce", ctypes.c_void_p),
        ("cbNonce", wintypes.ULONG),
        ("pbAuthData", ctypes.c_void_p),
        ("cbAuthData", wintypes.ULONG),
        ("pbTag", ctypes.c_void_p),
        ("cbTag", wintypes.ULONG),
        ("pbMacContext", ctypes.c_void_p),
        ("cbMacContext", wintypes.ULONG),
        ("cbAAD", wintypes.ULONG),
        ("cbData", wintypes.ULONG),
        ("dwFlags", wintypes.ULONG),
    ]


crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptUnprotectData.restype = wintypes.BOOL

bcrypt.BCryptOpenAlgorithmProvider.argtypes = [
    ctypes.POINTER(ctypes.c_void_p), wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.ULONG,
]
bcrypt.BCryptOpenAlgorithmProvider.restype = wintypes.LONG
bcrypt.BCryptSetProperty.argtypes = [
    ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG,
]
bcrypt.BCryptSetProperty.restype = wintypes.LONG
bcrypt.BCryptGenerateSymmetricKey.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
    wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG,
]
bcrypt.BCryptGenerateSymmetricKey.restype = wintypes.LONG
bcrypt.BCryptDecrypt.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p,
    ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
    ctypes.POINTER(wintypes.ULONG), wintypes.ULONG,
]
bcrypt.BCryptDecrypt.restype = wintypes.LONG
bcrypt.BCryptDestroyKey.argtypes = [ctypes.c_void_p]
bcrypt.BCryptCloseAlgorithmProvider.argtypes = [ctypes.c_void_p, wintypes.ULONG]


def dpapi(data):
    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.c_void_p))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def gcm_decrypt(key, nonce, ciphertext, tag):
    alg = ctypes.c_void_p()
    if bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(alg), "AES", None, 0):
        raise OSError("BCryptOpenAlgorithmProvider")
    try:
        mode = ctypes.create_unicode_buffer("ChainingModeGCM")
        if bcrypt.BCryptSetProperty(alg, "ChainingMode", ctypes.cast(mode, ctypes.c_void_p),
                                    ctypes.sizeof(mode), 0):
            raise OSError("ChainingModeGCM")
        key_buf = ctypes.create_string_buffer(key, len(key))
        hkey = ctypes.c_void_p()
        if bcrypt.BCryptGenerateSymmetricKey(alg, ctypes.byref(hkey), None, 0, key_buf, len(key), 0):
            raise OSError("BCryptGenerateSymmetricKey")
        try:
            nonce_buf = ctypes.create_string_buffer(nonce, len(nonce))
            tag_buf = ctypes.create_string_buffer(tag, len(tag))
            info = AUTH_INFO()
            info.cbSize = ctypes.sizeof(AUTH_INFO)
            info.dwInfoVersion = 1
            info.pbNonce = ctypes.cast(nonce_buf, ctypes.c_void_p)
            info.cbNonce = len(nonce)
            info.pbTag = ctypes.cast(tag_buf, ctypes.c_void_p)
            info.cbTag = len(tag)
            body = ctypes.create_string_buffer(ciphertext, len(ciphertext)) if ciphertext else ctypes.create_string_buffer(1)
            out = ctypes.create_string_buffer(len(ciphertext) or 1)
            done = wintypes.ULONG()
            if bcrypt.BCryptDecrypt(hkey, body, len(ciphertext), ctypes.byref(info), None, 0,
                                    out, len(ciphertext), ctypes.byref(done), 0):
                raise OSError("BCryptDecrypt")
            return out.raw[:done.value]
        finally:
            bcrypt.BCryptDestroyKey(hkey)
    finally:
        bcrypt.BCryptCloseAlgorithmProvider(alg, 0)


def local_key(root):
    state = os.path.join(root, "Local State")
    if not os.path.isfile(state):
        return None
    with open(state, "r", encoding="utf-8") as handle:
        raw = json.load(handle).get("os_crypt", {}).get("encrypted_key")
    if not raw:
        return None
    return dpapi(base64.b64decode(raw)[5:])


def decrypt_value(blob, key, opener):
    if not blob:
        return opener()
    if blob[:3] in (b"v10", b"v11"):
        return gcm_decrypt(key, blob[3:15], blob[15:-16], blob[-16:]).decode("utf-8", "replace")
    if blob[:3] == b"v20":
        raise ValueError("app-bound")
    return dpapi(blob).decode("utf-8", "replace")


def profiles(root):
    found = [os.path.join(root, "Default")]
    found += sorted(glob.glob(os.path.join(root, "Profile *")))
    if not os.path.isdir(os.path.join(root, "Default")) and os.path.isdir(os.path.join(root, "Network")):
        found = [root]
    return [p for p in found if os.path.isdir(p)]


def read_profile(db, key):
    uri = "file:" + db.replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=3)
    try:
        rows = con.execute(
            "select host_key, name, value, encrypted_value, path, expires_utc, is_secure "
            "from cookies where host_key like '%youtube.com' or host_key like '%google.com'"
        ).fetchall()
    finally:
        con.close()
    out, blocked = [], 0
    for host, name, value, blob, path, expires, secure in rows:
        if not value:
            try:
                value = decrypt_value(blob, key, lambda: "")
            except ValueError:
                blocked += 1
                continue
            except OSError:
                continue
        if not value or "\t" in value or "\n" in value or "\r" in value:
            continue
        expiry = int(expires / 1000000 - 11644473600) if expires else 0
        out.append((host, name, value, path or "/", int(bool(secure)), max(expiry, 0)))
    return out, blocked


def collect():
    best = None
    for label, root in BROWSERS:
        if not root or not os.path.isdir(root):
            continue
        try:
            key = local_key(root)
        except OSError:
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
            except sqlite3.Error:
                continue
            score = sum(1 for r in rows if r[1] in AUTH_NAMES)
            if rows and (best is None or score > best[3]):
                best = (label, os.path.basename(profile), rows, score, blocked)
                if score >= 2:
                    return best
    return best


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


def main():
    found = collect()
    if not found:
        print("Aucun profil de navigateur lisible. Ouvre Edge, connecte-toi a youtube.com, relance.")
        return 1
    label, profile, rows, score, blocked = found
    total = write_netscape(rows)
    print(f"Navigateur : {label} / {profile}")
    print(f"Cookies youtube.com + google.com : {total}")
    print(f"Session connectee : {'oui' if score else 'AUCUNE - connecte-toi a youtube.com dans ' + label}")
    if blocked:
        print(f"Cookies app-bound illisibles (version recente du navigateur) : {blocked}")
    print(f"Fichier : {OUT_PATH}")
    return 0 if score else 2


if __name__ == "__main__":
    sys.exit(main())
