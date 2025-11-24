# -*- coding: utf-8 -*-
import threading

class QKDKeyBuffer:
    """epoch -> 32B のシンプル保管庫"""
    def __init__(self):
        self._lock = threading.Lock()
        self._store = {}  # int -> bytes(32)

    def feed(self, epoch: int, slice_bytes: bytes):
        assert isinstance(slice_bytes, (bytes, bytearray)) and len(slice_bytes) == 32
        with self._lock:
            self._store[epoch] = bytes(slice_bytes)

    def get_slice(self, epoch: int):
        with self._lock:
            return self._store.get(epoch, None)
