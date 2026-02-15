# MIT License © 2025 Motohiro Suzuki
"""
crypto/kdf.py  (Stage178)

Purpose:
- Provide the exact symbols expected by qsp/handshake.py:
    - hkdf_sha256
    - build_ikm
- Keep dependencies minimal (stdlib only), to make Stage178 Core(LTS) robust.

Notes:
- HKDF is implemented with HMAC-SHA256 (RFC 5869 style).
- build_ikm uses length-prefix concatenation to avoid ambiguity.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any


def build_ikm(*parts: bytes) -> bytes:
    """
    Compatibility API expected by qsp.handshake:
      build_ikm(part1, part2, ...) -> bytes

    We define it as a stable concatenation with 4-byte big-endian length prefixes.
    This avoids ambiguity (e.g., [b"ab", b"c"] vs [b"a", b"bc"]).
    """
    out = b""
    for p in parts:
        if p is None:
            p = b""
        if not isinstance(p, (bytes, bytearray, memoryview)):
            raise TypeError("build_ikm parts must be bytes-like")
        b = bytes(p)
        out += len(b).to_bytes(4, "big") + b
    return out


def _hkdf_extract_sha256(salt: bytes, ikm: bytes) -> bytes:
    # RFC5869: PRK = HMAC(salt, IKM)
    if salt is None:
        salt = b""
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand_sha256(prk: bytes, info: bytes, length: int) -> bytes:
    # RFC5869: OKM = T(1) || T(2) || ... ; T(i)=HMAC(PRK, T(i-1) | info | i)
    if info is None:
        info = b""
    if length < 0:
        raise ValueError("length must be >= 0")
    if length == 0:
        return b""

    out = b""
    t = b""
    counter = 1
    while len(out) < length:
        if counter > 255:
            # HKDF limitation (max 255 blocks)
            raise ValueError("HKDF length too large")
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        out += t
        counter += 1
    return out[:length]


def hkdf_sha256(
    *,
    salt: bytes,
    ikm: bytes,
    info: bytes = b"",
    length: int = 32,
) -> bytes:
    """
    Compatibility API expected by qsp.handshake:
      hkdf_sha256(salt=..., ikm=..., info=b"...", length=N) -> okm

    Uses HMAC-SHA256 HKDF (RFC5869).
    """
    if not isinstance(salt, (bytes, bytearray, memoryview)):
        raise TypeError("salt must be bytes-like")
    if not isinstance(ikm, (bytes, bytearray, memoryview)):
        raise TypeError("ikm must be bytes-like")
    if not isinstance(info, (bytes, bytearray, memoryview)):
        raise TypeError("info must be bytes-like")
    if not isinstance(length, int):
        raise TypeError("length must be int")

    prk = _hkdf_extract_sha256(bytes(salt), bytes(ikm))
    return _hkdf_expand_sha256(prk, bytes(info), length)
