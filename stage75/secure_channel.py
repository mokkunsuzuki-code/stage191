# -*- coding: utf-8 -*-
# secure_channel.py
import base64, json, hashlib, os
from typing import Optional, Tuple
from aead import AEAD
from quic_qkd_common import derive_epoch_keys
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)

def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))

def _sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()

class SecureChannel:
    """
    - AES-GCMで暗号化（epochごとに鍵/nonceベース更新）
    - 署名: Ed25519（送信者認証）
    - リプレイ防止: シーケンス単調増加
    kind:
      "data" … 文字列など
      "file" … ファイル分割チャンク
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

        # ファイル受信の組み立て
        self._file_buf = {}  # fname -> {"total":N, "chunks":dict(idx->bytes)}

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

    # ===== 署名対象（短い・衝突しにくい）=====
    def _sign_input(self, kind: str, epoch: int, seq: int, ct: bytes) -> bytes:
        # AADはAES-GCMにも渡す（改ざん検知の二重化）
        aad = f"{kind}|epoch={epoch}|seq={seq}|role={self.role}".encode()
        return aad + _sha256(ct)

    # ===== 送信（data/file 共通）=====
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
        return (json.dumps(rec, separators=(",", ":")).encode() + b"\n")

    # ===== 受信（検証→復号→処理）=====
    def try_decrypt_record(self, line: bytes):
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

        # epoch未同期や順序違反は拒否
        if epoch != self.epoch or self._recv_aead is None or self._recv_nonce_base is None:
            return None
        if seq <= self.recv_highest:
            return None

        # 署名検証（送信者認証）
        try:
            self.peer_pub.verify(sig, self._sign_input(kind, epoch, seq, ct))
        except Exception:
            return None  # 署名が違う → なりすまし/改ざん

        # 復号
        aad = f"{kind}|epoch={epoch}|seq={seq}|role={'client' if self.role=='server' else 'server'}".encode()
        nonce = _xor(self._recv_nonce_base, seq.to_bytes(12, "big"))
        try:
            pt = self._recv_aead.decrypt(nonce, ct, aad)
        except Exception:
            return None

        self.recv_highest = seq

        if kind == "file":
            meta_len = int.from_bytes(pt[:2], "big")
            meta = json.loads(pt[2:2+meta_len].decode())
            chunk = pt[2+meta_len:]
            return ("file", (meta, chunk))
        else:
            return ("data", pt)

    # ===== file: 送信用（分割）=====
    def make_file_chunks(self, file_path: str, chunk_size: int = 900) -> Tuple[str, int, list]:
        fname = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            data = f.read()
        chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
        total = len(chunks)
        recs = []
        for idx, ch in enumerate(chunks):
            meta = {"fname": fname, "idx": idx, "total": total}
            meta_b = json.dumps(meta, separators=(",", ":")).encode()
            # 平文には meta_len(2B) + meta + chunk を入れて暗号化
            pt = len(meta_b).to_bytes(2, "big") + meta_b + ch
            recs.append(self.build_encrypted_record("file", pt))
        return fname, total, recs

    # ===== file: 受信用（組み立て）=====
    def assemble_file_piece(self, meta: dict, chunk: bytes):
        fname = meta["fname"]; idx = int(meta["idx"]); total = int(meta["total"])
        st = self._file_buf.get(fname)
        if st is None:
            st = {"total": total, "chunks": {}}
            self._file_buf[fname] = st
        st["chunks"][idx] = bytes(chunk)
        if len(st["chunks"]) == total:
            # 全部届いた → 書き出し
            ordered = b"".join(st["chunks"][i] for i in range(total))
            outname = "recv_" + fname
            with open(outname, "wb") as f:
                f.write(ordered)
            del self._file_buf[fname]
            return outname
        return None
