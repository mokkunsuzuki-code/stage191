# -*- coding: utf-8 -*-
"""
qkd_buffer.py — QKDの鍵スライス(32B)を epoch(int) ごとに保存/取得する
スレッドセーフな超シンプルバッファ
"""

from __future__ import annotations
import threading
from typing import Dict, Optional


class QKDKeyBuffer:
    """Thread-safe store: epoch -> 32-byte slice"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: Dict[int, bytes] = {}

    def feed(self, epoch: int, slice_bytes: bytes) -> None:
        """指定epochに32バイトの鍵スライスを格納"""
        if not isinstance(slice_bytes, (bytes, bytearray)):
            raise TypeError("slice_bytes must be bytes or bytearray")
        if len(slice_bytes) != 32:
            raise ValueError(f"slice_bytes must be 32 bytes, got {len(slice_bytes)}")
        with self._lock:
            self._store[epoch] = bytes(slice_bytes)

    def get_slice(self, epoch: int) -> Optional[bytes]:
        """指定epochの鍵スライスを返す（無ければNone）"""
        with self._lock:
            return self._store.get(epoch)


# 単体テスト（直接実行したときだけ動作）
if __name__ == "__main__":
    buf = QKDKeyBuffer()
    buf.feed(100, b"\x00" * 32)
    assert buf.get_slice(100) == b"\x00" * 32
    print("QKDKeyBuffer self-test: OK")
