# MIT License © 2025 Motohiro Suzuki
"""
protocol.errors (Stage178 shim)

qsp.rekey が `from protocol.errors import RekeyError` を期待するため、
最小の互換エラー型を提供する。
"""


class RekeyError(Exception):
    pass
