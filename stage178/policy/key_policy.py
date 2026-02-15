# MIT License © 2025 Motohiro Suzuki
"""
policy.key_policy (Stage178 shim, compat++)

Stage178 rekey_engine._get_policy(cfg) が KeyPolicy を生成する際、
ステージ差で追加のキーワード引数を渡すことがある（例: qber_max）。
壊れないように、互換受け口として **kwargs を許容**する。
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any


class QKDState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class QKDMetrics:
    available: bool = False
    reason: str = "QKD_UNAVAILABLE"
    # optional fields (future)
    qber: Optional[float] = None


class KeyPolicy:
    """
    Minimal policy used by handshake/rekey paths.

    Accepts both naming styles:
      - rekey_seconds / rekey_bytes
      - rekey_max_seconds / rekey_max_bytes
    Also accepts extra stage-dependent kwargs like:
      - qber_max
      - ... future keys (ignored unless we decide to use them)
    """

    def __init__(
        self,
        require_qkd: bool = False,
        fail_closed: bool = True,
        rekey_bytes: int = 0,
        rekey_seconds: int = 0,
        rekey_max_bytes: Optional[int] = None,
        rekey_max_seconds: Optional[int] = None,
        qber_max: Optional[float] = None,
        **_extra: Any,
    ) -> None:
        if rekey_max_bytes is not None:
            rekey_bytes = int(rekey_max_bytes)
        if rekey_max_seconds is not None:
            rekey_seconds = int(rekey_max_seconds)

        self.require_qkd = bool(require_qkd)
        self.fail_closed = bool(fail_closed)
        self.rekey_bytes = int(rekey_bytes)
        self.rekey_seconds = int(rekey_seconds)

        # optional guardrail (not enforced by shim yet)
        self.qber_max = None if qber_max is None else float(qber_max)

    def qkd_state(self, metrics: Optional[QKDMetrics] = None) -> QKDState:
        if metrics is None:
            return QKDState.UNAVAILABLE
        return QKDState.AVAILABLE if metrics.available else QKDState.UNAVAILABLE

    def allow_pqc_only(self, metrics: Optional[QKDMetrics] = None) -> bool:
        return not self.require_qkd
