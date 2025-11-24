# -*- coding: utf-8 -*-
# crypto_primitives.py
from hashlib import sha256
import hmac

_DEF_DIGEST_SIZE = 32

def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if salt is None:
        salt = b"\x00" * _DEF_DIGEST_SIZE
    return hmac.new(salt, ikm, sha256).digest()

def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    assert len(prk) == _DEF_DIGEST_SIZE
    out = b""
    t = b""
    counter = 1
    while len(out) < length:
        t = hmac.new(prk, t + info + bytes([counter]), sha256).digest()
        out += t
        counter += 1
    return out[:length]

