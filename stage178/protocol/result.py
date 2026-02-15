# MIT License © 2025 Motohiro Suzuki
"""
protocol.result (Stage178 shim)

qsp.handshake が `from protocol.result import Result` を期待するため、
実体である `qsp.result` を re-export する。
"""
from qsp.result import *  # noqa: F401,F403
