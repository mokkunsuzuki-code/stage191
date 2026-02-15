# MIT License © 2025 Motohiro Suzuki
"""
keysources.qkd_factory (Stage178 shim)

qsp.rekey_engine が `from keysources.qkd_factory import make_qkd_source`
を期待するため、最小の互換実装を提供する。

方針:
- まず「QKDが無い/使えない」前提の NullQKDSource を返せるようにする。
- 将来、本物のQKDソース（ETSI API等）が入ったらここから差し替える。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class NullQKDSource:
    """
    Always-unavailable QKD source.
    This keeps the protocol running in PQC-only / failover paths.
    """
    reason: str = "QKD_UNAVAILABLE"

    def available(self) -> bool:
        return False

    def get_bytes(self, n: int) -> bytes:
        # No QKD bytes available; callers should treat as unavailable.
        return b""


def make_qkd_source(*args, **kwargs) -> Optional[NullQKDSource]:
    """
    Factory expected by qsp.rekey_engine.

    We keep the signature flexible (*args/**kwargs) because Stage178 code may call it with
    various config parameters across stages.

    Returns:
      - NullQKDSource (unavailable) by default
      - (Future) real QKD source when implemented
    """
    return NullQKDSource()
