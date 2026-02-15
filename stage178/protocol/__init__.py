# MIT License © 2025 Motohiro Suzuki
"""
protocol/  (Stage178 shim)

Stage178 の一部モジュールが `import protocol` を前提にしているため、
Core(LTS)として壊れないように “互換レイヤー” を提供する。

原則：
- 実体は qsp.* にある
- ここは re-export / alias を提供するだけ
"""

from qsp.core import ProtocolCore, ProtocolViolation  # re-export
