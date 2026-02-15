# MIT License © 2025 Motohiro Suzuki
"""
protocol.rekey (Stage178 shim)

qsp.rekey_engine が `from protocol.rekey import ...` を期待するため、
実体である `qsp.rekey` を re-export する。
"""
from qsp.rekey import *  # noqa: F401,F403
