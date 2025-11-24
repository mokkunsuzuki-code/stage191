# qkd_buffer.py
# -*- coding: utf-8 -*-
import threading

class QKDKeyBuffer:
    """超シンプルな: epoch -> 32バイト の保管庫"""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[int, bytes] = {}

    def feed(self, epoch: int, slice_bytes: bytes) -> None:
        assert isinstance(slice_bytes, (bytes, bytearray)) and len(slice_bytes) == 32
        with self._lock:
            self._store[epoch] = bytes(slice_bytes)

    def get_slice(self, epoch: int) -> bytes | None:
        with self._lock:
            return self._store.get(epoch, None)
