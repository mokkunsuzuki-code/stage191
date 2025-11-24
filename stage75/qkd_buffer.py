# -*- coding: utf-8 -*-
# qkd_buffer.py
import threading

class QKDKeyBuffer:
    def __init__(self):
        self._lock = threading.Lock()
        self._store = {}

    def feed(self, epoch: int, slice_bytes: bytes):
        assert isinstance(slice_bytes, (bytes, bytearray)) and len(slice_bytes) == 32
        with self._lock:
            self._store[epoch] = bytes(slice_bytes)

    def get_slice(self, epoch: int):
        with self._lock:
            return self._store.get(epoch, None)
