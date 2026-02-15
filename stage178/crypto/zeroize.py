# MIT License © 2025 Motohiro Suzuki
"""
crypto.zeroize (Stage178 shim)

Stage170-A 以降の一部コードが `from crypto.zeroize import wipe_bytes_like`
を期待するため、最小の互換実装を提供する。

注意:
Pythonのbytesは不変なので「完全なゼロ化」は保証できない。
ただし bytearray / writable memoryview など可変バッファには可能な限りゼロ書きする。
"""

from __future__ import annotations
from typing import Any


def wipe_bytes_like(x: Any) -> None:
    """
    Best-effort zeroization.
    - bytearray: in-place overwrite
    - writable memoryview: in-place overwrite
    - bytes/readonly: no-op
    Never raises.
    """
    try:
        if isinstance(x, bytearray):
            for i in range(len(x)):
                x[i] = 0
            return

        if isinstance(x, memoryview) and not x.readonly:
            x[:] = b"\x00" * len(x)
            return

        # bytes / readonly / unknown => cannot safely mutate
        return
    except Exception:
        return
