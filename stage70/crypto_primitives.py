# crypto_primitives.py
# HKDF (RFC 5869) の最小実装。SHA-256 固定。

from __future__ import annotations
from hashlib import sha256
import hmac
from typing import Optional

_DEF_DIGEST_SIZE = 32  # sha256.digest_size

def hkdf_extract(salt: Optional[bytes], ikm: bytes) -> bytes:
    """
    HKDF-Extract: PRK = HMAC(salt, IKM)
    salt が None のときは 0x00 を digest_size 個のデフォルト塩にする。
    """
    if salt is None:
        salt = b"\x00" * _DEF_DIGEST_SIZE
    return hmac.new(salt, ikm, sha256).digest()

def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """
    HKDF-Expand: OKM を 'length' バイト生成。
    """
    assert len(prk) == _DEF_DIGEST_SIZE, "prk must be 32 bytes for SHA-256"

    out = b""
    t = b""
    counter = 1
    while len(out) < length:
        t = hmac.new(prk, t + info + bytes([counter]), sha256).digest()
        out += t
        counter += 1
    return out[:length]
