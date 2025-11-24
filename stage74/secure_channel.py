# -*- coding: utf-8 -*-
# secure_channel.py
import base64
import json
from typing import Optional

from aead import AEAD
from quic_qkd_common import derive_epoch_keys


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


class SecureChannel:
    """
    アプリ層の「もう一段の鍵」。
    - 送信側: AES-GCMで暗号化（鍵/nonceは epoch ごとに再生成）
    - 受信側: AES-GCMで検証付き復号
    - リプレイ防止: シーケンス番号の単調増加をチェック
    役割:
      role="client" → 送信鍵=client_write, 受信鍵=server_write
      role="server" → 送信鍵=server_write, 受信鍵=client_write
    """
    def __init__(self, quic_connection, qkd_buf, role: str):
        assert role in ("client", "server")
        self.conn = quic_connection
        self.qkd = qkd_buf
        self.role = role

        self.epoch = 0
        self.send_seq = 0
        self.recv_highest = -1  # 受信済み最大シーケンス（リプレイ拒否）

        # 現在の鍵素材
        self._send_aead: Optional[AEAD] = None
        self._recv_aead: Optional[AEAD] = None
        self._send_nonce_base: Optional[bytes] = None  # 12B
        self._recv_nonce_base: Optional[bytes] = None  # 12B

    def install_epoch(self, epoch: int):
        """epoch切り替え時に鍵・ノンス基底を更新し、シーケンスをリセット。"""
        self.epoch = epoch
        self.send_seq = 0
        self.recv_highest = -1

        ckey, skey, cnb, snb = derive_epoch_keys(self.conn, self.qkd, epoch)
        if self.role == "client":
            self._send_aead = AEAD(ckey)
            self._recv_aead = AEAD(skey)
            self._send_nonce_base = cnb
            self._recv_nonce_base = snb
        else:
            self._send_aead = AEAD(skey)
            self._recv_aead = AEAD(ckey)
            self._send_nonce_base = snb
            self._recv_nonce_base = cnb

    # === 送信 ===
    def build_encrypted_record(self, kind: str, payload: bytes) -> bytes:
        """
        kind: "data" など（AADに入れて改ざん検知に利用）
        返り値: 1行JSON（\n で区切って送る）
        """
        assert self._send_aead and self._send_nonce_base
        seq = self.send_seq
        self.send_seq += 1

        # ノンス = nonce_base XOR seq(12B big-endian)
        nonce = _xor(self._send_nonce_base, seq.to_bytes(12, "big"))
        aad = f"{kind}|epoch={self.epoch}|seq={seq}|role={self.role}".encode()
        ct = self._send_aead.encrypt(nonce, payload, aad)

        rec = {
            "type": "enc",
            "kind": kind,
            "epoch": self.epoch,
            "seq": seq,
            "ct": base64.b64encode(ct).decode(),
        }
        return (json.dumps(rec, separators=(",", ":")).encode() + b"\n")

    # === 受信 ===
    def try_decrypt_record(self, line: bytes):
        """
        受け取った1行JSONを復号。
        成功: (kind:str, plaintext:bytes)
        失敗/自分向けでない: None
        """
        try:
            obj = json.loads(line.decode())
        except Exception:
            return None

        if obj.get("type") != "enc":
            return None

        epoch = int(obj["epoch"])
        seq = int(obj["seq"])
        kind = str(obj.get("kind", "data"))
        ct = base64.b64decode(obj["ct"])

        # epoch が違えば受け付けない（先に phase_notice を処理して install_epoch 済みの想定）
        if epoch != self.epoch or self._recv_aead is None or self._recv_nonce_base is None:
            # 後続の処理系にまかせる
            return None

        # リプレイ防止：新しいseqのみ通す
        if seq <= self.recv_highest:
            # すでに見た or 古い
            return None

        nonce = _xor(self._recv_nonce_base, seq.to_bytes(12, "big"))
        aad = f"{kind}|epoch={epoch}|seq={seq}|role={'client' if self.role=='server' else 'server'}".encode()
        try:
            pt = self._recv_aead.decrypt(nonce, ct, aad)
        except Exception:
            return None

        self.recv_highest = seq
        return kind, pt

