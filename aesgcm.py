"""AES-256-GCM en Python pur (dechiffrement des cookies Chromium v10/v11).

Sans dependance : AES (FIPS-197) + GHASH/CTR (SP 800-38D). Le PC de dev a
refuse BCrypt AES-GCM, d'ou l'implementation locale.
"""


def _mul(a, b):
    product = 0
    for _ in range(8):
        if b & 1:
            product ^= a
        high = a & 0x80
        a = (a << 1) & 0xFF
        if high:
            a ^= 0x1B
        b >>= 1
    return product


def _inv(a):
    if a == 0:
        return 0
    result, base, exp = 1, a, 254
    while exp:
        if exp & 1:
            result = _mul(result, base)
        base = _mul(base, base)
        exp >>= 1
    return result


def _rotl(value, shift):
    return ((value << shift) | (value >> (8 - shift))) & 0xFF


def _build_sbox():
    box = []
    for value in range(256):
        inv = _inv(value)
        box.append(inv ^ _rotl(inv, 1) ^ _rotl(inv, 2) ^ _rotl(inv, 3) ^ _rotl(inv, 4) ^ 0x63)
    return box


SBOX = _build_sbox()
RCON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def expand_key(key):
    nk = len(key) // 4
    if nk not in (4, 8) or len(key) != nk * 4:
        raise ValueError("cle AES-128 ou AES-256 attendue")
    rounds = nk + 6
    words = [list(key[i * 4:i * 4 + 4]) for i in range(nk)]
    for i in range(nk, 4 * (rounds + 1)):
        temp = list(words[i - 1])
        if i % nk == 0:
            temp = [SBOX[temp[1]], SBOX[temp[2]], SBOX[temp[3]], SBOX[temp[0]]]
            temp[0] ^= RCON[i // nk]
        elif i % nk == 4:
            temp = [SBOX[b] for b in temp]
        words.append([words[i - nk][j] ^ temp[j] for j in range(4)])
    return words, rounds


def _add_round_key(state, words, round_index):
    for column in range(4):
        word = words[round_index * 4 + column]
        for row in range(4):
            state[column * 4 + row] ^= word[row]


def _shift_rows(state):
    out = [0] * 16
    for column in range(4):
        for row in range(4):
            out[column * 4 + row] = state[((column + row) % 4) * 4 + row]
    return out


def _mix_columns(state):
    for column in range(4):
        a0, a1, a2, a3 = state[column * 4:column * 4 + 4]
        state[column * 4] = _mul(a0, 2) ^ _mul(a1, 3) ^ a2 ^ a3
        state[column * 4 + 1] = a0 ^ _mul(a1, 2) ^ _mul(a2, 3) ^ a3
        state[column * 4 + 2] = a0 ^ a1 ^ _mul(a2, 2) ^ _mul(a3, 3)
        state[column * 4 + 3] = _mul(a0, 3) ^ a1 ^ a2 ^ _mul(a3, 2)


def encrypt_block(words, rounds, block):
    state = list(block)
    _add_round_key(state, words, 0)
    for rnd in range(1, rounds):
        state = [SBOX[b] for b in state]
        state = _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, words, rnd)
    state = [SBOX[b] for b in state]
    state = _shift_rows(state)
    _add_round_key(state, words, rounds)
    return bytes(state)


def _ghash_mul(x, y):
    z, v = 0, y
    for i in range(128):
        if (x >> (127 - i)) & 1:
            z ^= v
        if v & 1:
            v = (v >> 1) ^ (0xE1 << 120)
        else:
            v >>= 1
    return z


def _ghash(h, data):
    y = 0
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16].ljust(16, b"\0")
        y = _ghash_mul(y ^ int.from_bytes(chunk, "big"), h)
    return y


def _gctr(words, rounds, counter, data):
    out = bytearray()
    for offset in range(0, len(data), 16):
        stream = encrypt_block(words, rounds, counter.to_bytes(16, "big"))
        chunk = data[offset:offset + 16]
        out.extend(b ^ s for b, s in zip(chunk, stream))
        counter = (counter & ~0xFFFFFFFF) | ((counter + 1) & 0xFFFFFFFF)
    return bytes(out)


def _tag(words, rounds, h, nonce, aad, ciphertext):
    length_block = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    padded = aad + b"\0" * (-len(aad) % 16) + ciphertext + b"\0" * (-len(ciphertext) % 16)
    mask = encrypt_block(words, rounds, nonce + b"\0\0\0\1")
    return (_ghash(h, padded + length_block) ^ int.from_bytes(mask, "big")).to_bytes(16, "big")


def encrypt(key, nonce, plaintext, aad=b""):
    words, rounds = expand_key(key)
    h = int.from_bytes(encrypt_block(words, rounds, bytes(16)), "big")
    j0 = int.from_bytes(nonce + b"\0\0\0\1", "big")
    counter = (j0 & ~0xFFFFFFFF) | ((j0 + 1) & 0xFFFFFFFF)
    ciphertext = _gctr(words, rounds, counter, plaintext)
    return ciphertext, _tag(words, rounds, h, nonce, aad, ciphertext)


def decrypt(key, nonce, ciphertext, tag, aad=b""):
    words, rounds = expand_key(key)
    h = int.from_bytes(encrypt_block(words, rounds, bytes(16)), "big")
    if _tag(words, rounds, h, nonce, aad, ciphertext) != tag:
        raise ValueError("tag AES-GCM invalide")
    j0 = int.from_bytes(nonce + b"\0\0\0\1", "big")
    counter = (j0 & ~0xFFFFFFFF) | ((j0 + 1) & 0xFFFFFFFF)
    return _gctr(words, rounds, counter, ciphertext)
