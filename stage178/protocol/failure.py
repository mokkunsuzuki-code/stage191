# MIT License © 2025 Motohiro Suzuki
"""
protocol.failure (Stage178 shim)

qsp.result が `from protocol.failure import Failure` を期待するため、
実体である `qsp.failure` を re-export する。
"""
from qsp.failure import *  # noqa: F401,F403
