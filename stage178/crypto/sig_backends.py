# MIT License © 2025 Motohiro Suzuki
"""
crypto.sig_backends (Stage178 shim)

qsp.handshake が `import crypto.sig_backends as sb` を期待するため、
最小の互換実装を提供する。

注意:
- ここは「import が通る」「PoCが動く」ことを優先した shim。
- 実運用グレードの署名（Dilithium/Ed25519等）に差し替える前提。
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Protocol


class SigBackend(Protocol):
    name: str

    def sign(self, msg: bytes) -> bytes: ...
    def verify(self, msg: bytes, sig: bytes) -> bool: ...


@dataclass
class HMACSHA256Backend:
    """
    Minimal backend: HMAC-SHA256 as a stand-in "signature".
    This is NOT a public-key signature scheme.
    Used only as a compatibility shim to unblock imports and demos.
    """
    key: bytes
    name: str = "HMAC-SHA256-SHIM"

    def sign(self, msg: bytes) -> bytes:
        return hmac.new(self.key, msg, hashlib.sha256).digest()

    def verify(self, msg: bytes, sig: bytes) -> bool:
        good = self.sign(msg)
        return hmac.compare_digest(good, sig)


def default_backend() -> SigBackend:
    """
    Returns the default signature backend.
    Key is taken from env var `QSP_SIG_SHIM_KEY` if set, else a fixed dev key.
    """
    k = os.environ.get("QSP_SIG_SHIM_KEY", "dev-key-do-not-use").encode("utf-8")
    return HMACSHA256Backend(k)


# Common helper names (in case qsp.handshake expects these)
def sign(msg: bytes) -> bytes:
    return default_backend().sign(msg)


def verify(msg: bytes, sig: bytes) -> bool:
    return default_backend().verify(msg, sig)
