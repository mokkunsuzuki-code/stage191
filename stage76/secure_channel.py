# -*- coding: utf-8 -*-
# secure_channel.py
import base64, json, hashlib
from typing import Optional, Tuple
from aead import AEAD
from quic_qkd_common import derive_epoch_keys
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)

def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))

def _sha256(b: bytes) -> bytes:
    import hashlib as _h
    return _h.sha256(b).digest()

class SecureChannel:
    """
    - AES-GCMで暗号化（epochごとに鍵/nonceベース更新）
    - 署名: Ed25519（送信者認証）
    - リプレイ防止: シーケンス単調増加
    kind:
      "data" … 文字列など
    """
    def __init__(self, quic_connection, qkd_buf, role: str,
                 my_sign: Ed25519PrivateKey, peer_pub: Ed25519PublicKey):
        assert role in ("client", "server")
        self.conn = quic_connection
        self.qkd = qkd_buf
        self.role = role
        self.my_sign = my_sign
        self.peer_pub = peer_pub

        self.epoch = 0
        self.send_seq = 0
        self.recv_highest = -1

        self._send_aead: Optional[AEAD] = None
        self._recv_aead: Optional[AEAD] = None
        self._send_nonce_base: Optional[bytes] = None
        self._recv_nonce_base: Optional[bytes] = None

    def install_epoch(self, epoch: int):
        self.epoch = epoch
        self.send_seq = 0
        self.recv_highest = -1
        ckey, skey, cnb, snb = derive_epoch_keys(self.conn, self.qkd, epoch)
        if self.role == "client":
            self._send_aead, self._recv_aead = AEAD(ckey), AEAD(skey)
            self._send_nonce_base, self._recv_nonce_base = cnb, snb
        else:
            self._send_aead, self._recv_aead = AEAD(skey), AEAD(ckey)
            self._send_nonce_base, self._recv_nonce_base = snb, cnb

    def _sign_input(self, kind: str, epoch: int, seq: int, ct: bytes) -> bytes:
        aad = f"{kind}|epoch={epoch}|seq={seq}|role={self.role}".encode()
        return aad + _sha256(ct)

    # === 送信 ===
    def build_encrypted_record(self, kind: str, plaintext: bytes) -> bytes:
        assert self._send_aead and self._send_nonce_base
        seq = self.send_seq
        self.send_seq += 1

        nonce = _xor(self._send_nonce_base, seq.to_bytes(12, "big"))
        aad = f"{kind}|epoch={self.epoch}|seq={seq}|role={self.role}".encode()
        ct = self._send_aead.encrypt(nonce, plaintext, aad)
        sig = self.my_sign.sign(self._sign_input(kind, self.epoch, seq, ct))

        rec = {
            "type": "enc",
            "kind": kind,
            "epoch": self.epoch,
            "seq": seq,
            "ct": base64.b64encode(ct).decode(),
            "sig": base64.b64encode(sig).decode(),
        }
        return json.dumps(rec, separators=(",", ":")).encode() + b"\n"

    # === 受信 ===
    def try_decrypt_record(self, line: bytes) -> Optional[Tuple[str, bytes]]:
        try:
            obj = json.loads(line.decode())
        except Exception:
            return None
        if obj.get("type") != "enc":
            return None

        epoch = int(obj["epoch"])
        seq   = int(obj["seq"])
        kind  = str(obj.get("kind", "data"))
        ct    = base64.b64decode(obj["ct"])
        sig   = base64.b64decode(obj["sig"])

        if epoch != self.epoch or self._recv_aead is None or self._recv_nonce_base is None:
            return None
        if seq <= self.recv_highest:
            return None

        try:
            self.peer_pub.verify(sig, self._sign_input(kind, epoch, seq, ct))
        except Exception:
            return None

        aad = f"{kind}|epoch={epoch}|seq={seq}|role={'client' if self.role=='server' else 'server'}".encode()
        nonce = _xor(self._recv_nonce_base, seq.to_bytes(12, "big"))
        try:
            pt = self._recv_aead.decrypt(nonce, ct, aad)
        except Exception:
            return None

        self.recv_highest = seq
        return (kind, pt)

