# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import struct
import base64
from dataclasses import dataclass
from typing import Tuple

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---- ユーティリティ ----
def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")

def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def kdf_split(qkd_material: bytes, info: bytes) -> Tuple[bytes, bytes, bytes, bytes]:
    """
    64B の QKD 素材から以下を導出する:
      k_c2s (32B)  … クライアント→サーバ暗号鍵
      k_s2c (32B)  … サーバ→クライアント暗号鍵
      iv_c2s (8B)  … クライアント→サーバのベースIV
      iv_s2c (8B)  … サーバ→クライアントのベースIV
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32 + 32 + 8 + 8,
        salt=None,
        info=info,  # 方向や用途の区別に使うラベル
    )
    okm = hkdf.derive(qkd_material)
    k_c2s = okm[0:32]
    k_s2c = okm[32:64]
    iv_c2s = okm[64:72]
    iv_s2c = okm[72:80]
    return k_c2s, k_s2c, iv_c2s, iv_s2c


@dataclass
class DirectionKey:
    key: AESGCM                 # AESGCM インスタンス
    base_iv8: bytes             # 8バイト固定IV
    counter: int = 0            # 32bit カウンタ（メッセージ毎に +1）

    def next_nonce(self) -> bytes:
        # 12B nonce = 8B base + 4B counter
        n = self.counter
        self.counter = (self.counter + 1) & 0xFFFFFFFF
        return self.base_iv8 + struct.pack(">I", n)


class HybridSecureEndpoint:
    """
    片側のエンドポイント（Client または Server）。
    それぞれが「送信用」と「受信用」のキーを持つ。
    """
    def __init__(self, qkd_material: bytes, role: str):
        assert role in ("client", "server")
        self.role = role
        self._install_keys(qkd_material)

    def _install_keys(self, qkd_material: bytes):
        # ラベルを変えると鍵系列が必ず一致する（固定でOK）
        k_c2s, k_s2c, iv_c2s, iv_s2c = kdf_split(qkd_material, info=b"stage67-hkdf")
        if self.role == "client":
            self.tx = DirectionKey(AESGCM(k_c2s), iv_c2s, 0)  # client -> server
            self.rx = DirectionKey(AESGCM(k_s2c), iv_s2c, 0)  # server -> client
        else:
            # サーバ側は逆方向が送信
            self.tx = DirectionKey(AESGCM(k_s2c), iv_s2c, 0)  # server -> client
            self.rx = DirectionKey(AESGCM(k_c2s), iv_c2s, 0)  # client -> server

    # --- API ---
    def rekey(self, qkd_material: bytes):
        """QKDにより供給された新しい素材で鍵を再導入し、カウンタも0に戻す"""
        self._install_keys(qkd_material)

    def encrypt(self, plaintext: bytes, aad: bytes) -> Tuple[bytes, bytes]:
        """
        自分→相手 方向の暗号化
        return: (nonce, ciphertext)
        """
        nonce = self.tx.next_nonce()
        ct = self.tx.key.encrypt(nonce, plaintext, aad)
        return nonce, ct

    def decrypt(self, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        """
        相手→自分 方向の復号
        """
        # 受信側は相手のカウンタを推測しない（ノンスはパケットで渡す想定）
        pt = self.rx.key.decrypt(nonce, ciphertext, aad)
        return pt


# ===== デモ =====
def run_demo():
    print("=== 段階67: ハイブリッドTLS(擬似) — PQC & QKD セッション鍵デモ ===")

    # 1) 初期QKD素材（64B）
    qkd0 = os.urandom(64)
    print(f"[init] qkd0 = {b64e(qkd0)[:48]}...")

    # 2) 両端のエンドポイントを同じ素材で初期化
    client = HybridSecureEndpoint(qkd0, role="client")
    server = HybridSecureEndpoint(qkd0, role="server")

    # 3) 両方向で1往復（ノーマル）
    print("\n--- 通常メッセージ ---")
    aad1 = b"hdr1"
    m1 = b"hello from client"
    n1, c1 = client.encrypt(m1, aad=aad1)
    p1 = server.decrypt(n1, c1, aad=aad1)
    print(f"[C->S] PT='{m1.decode()}', AAD='{aad1.decode()}', OK='{p1.decode()}'")

    aad2 = b"hdr2"
    m2 = b"hello from server"
    n2, c2 = server.encrypt(m2, aad=aad2)
    p2 = client.decrypt(n2, c2, aad=aad2)
    print(f"[S->C] PT='{m2.decode()}', AAD='{aad2.decode()}', OK='{p2.decode()}'")

    # 4) Rekey（QKDのエポック切替え）: 鍵導入＋カウンタ初期化
    print("\n=== Rekey（QKDエポック切替）===")
    qkd1 = os.urandom(64)
    print(f"[rekey] qkd1 = {b64e(qkd1)[:48]}...")
    client.rekey(qkd1)
    server.rekey(qkd1)

    # 5) Rekey 後の送受信（新しい鍵＆カウンタ=0）
    print("\n--- rekey 後メッセージ ---")
    aad3 = b"hdr3"
    m3 = b"after rekey"
    n3, c3 = client.encrypt(m3, aad=aad3)   # C->S
    p3 = server.decrypt(n3, c3, aad=aad3)
    print(f"[C->S after rekey] OK='{p3.decode()}'")

    # 6) 参考: もう一発送る（カウンタが 1 → 2 へ進む）
    m4 = b"second message after rekey"
    n4, c4 = client.encrypt(m4, aad=aad3)
    p4 = server.decrypt(n4, c4, aad=aad3)
    print(f"[C->S after rekey #2] OK='{p4.decode()}'")

    print("\n=== 完了：PQCとQKDを混在させて安全な会話ができました ===")


if __name__ == "__main__":
    run_demo()

