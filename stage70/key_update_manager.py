# -*- coding: utf-8 -*-
# key_update_manager.py
import struct
import time
from dataclasses import dataclass
from typing import Optional

from crypto_primitives import hkdf_extract, hkdf_expand
from qkd_buffer import QKDKeyBuffer

# 学習版はモックを使用（本番では tls_binding に切り替える）
from tls_binding_mock import tls_exporter, tls_key_update

EPOCH_LABEL = b"qkd-epoch-v1"
EPOCH_CONTEXT_FMT = "!Q"  # 8 bytes unsigned long long


@dataclass
class RekeyPolicy:
    max_bytes: int = 64 * 1024 * 1024  # 64MB
    max_seconds: int = 300             # 5 minutes


class KeyUpdateManager:
    def __init__(self, ssl_obj, qkd_buf: QKDKeyBuffer, policy: RekeyPolicy):
        self.ssl = ssl_obj
        self.qkd = qkd_buf
        self.policy = policy
        self.epoch = 0
        self.tx_bytes = 0
        self.last_rekey_ts = self.now()

    @staticmethod
    def now() -> int:
        return int(time.time())

    @staticmethod
    def _epoch_context(epoch: int) -> bytes:
        return struct.pack(EPOCH_CONTEXT_FMT, epoch)

    def _derive_epoch_secret(self, epoch: int) -> bytes:
        context = self._epoch_context(epoch)
        exp_secret = tls_exporter(self.ssl, label=EPOCH_LABEL, context=context, outlen=32)
        qkd_slice = self.qkd.get_slice(epoch)
        if qkd_slice is None:
            qkd_slice = b"\x00" * 32  # フォールバック
        return hkdf_extract(salt=qkd_slice, ikm=exp_secret)  # 32 bytes

    def derive_app_keys(self, epoch: Optional[int] = None):
        if epoch is None:
            epoch = self.epoch
        prk = self._derive_epoch_secret(epoch)
        c_write = hkdf_expand(prk, b"client_write_key_v1", 32)
        s_write = hkdf_expand(prk, b"server_write_key_v1", 32)
        return c_write, s_write

    def should_rekey(self) -> bool:
        time_ok = (self.now() - self.last_rekey_ts) >= self.policy.max_seconds
        size_ok = self.tx_bytes >= self.policy.max_bytes
        return time_ok or size_ok

    def on_send(self, nbytes: int):
        self.tx_bytes += nbytes
        if self.should_rekey():
            self.rekey()

    def rekey(self):
        self.epoch += 1
        self._send_epoch_control(self.epoch)
        tls_key_update(self.ssl, request_peer_update=True)
        self.tx_bytes = 0
        self.last_rekey_ts = self.now()

    def _send_epoch_control(self, epoch: int):
        from app_wire import send_control_message
        msg = {"type": "epoch_notice", "epoch": epoch}
        send_control_message(self.ssl, msg)
