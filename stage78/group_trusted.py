# -*- coding: utf-8 -*-
"""
Trusted Repeater: Bob generates K_AC and sends it encrypted (XOR) under link keys.
Alice receives payload_A = K_AC XOR K_AB -> recovers K_AC
Charlie receives payload_C = K_AC XOR K_BC -> recovers K_AC
Public messages are HMAC-authenticated to prevent tampering.
"""
import os, hmac
from hashlib import sha256
from dataclasses import dataclass
from typing import Tuple
from crypto_primitives import hkdf_extract, hkdf_expand

def xor_bytes(a: bytes, b: bytes) -> bytes:
    assert len(a) == len(b), "xor_bytes: length mismatch"
    return bytes(x ^ y for x, y in zip(a, b))

@dataclass
class Node:
    name: str
    def qkd_with(self, peer: "Node", bits: int = 256) -> bytes:
        # デモ用：OS乱数で QKD 後の共有鍵を代用（本来は装置から）
        return os.urandom(bits // 8)  # 32B

def hmac_tag(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, sha256).digest()

def privacy_amplify(k_raw: bytes, context: bytes) -> bytes:
    # HKDF-based privacy amplification -> 32B
    prk = hkdf_extract(salt=sha256(context).digest(), ikm=k_raw)
    okm = hkdf_expand(prk, b"group-qkd-ac-v1", 32)
    return okm

@dataclass
class TrustedRepeaterSetup:
    alice: Node
    bob: Node
    charlie: Node
    auth_key: bytes  # 公開経路メッセージ認証用（32B）

    def run_once(self) -> Tuple[bytes, bytes, bytes]:
        """
        Returns (K_AB, K_BC, K_AC_final)
        - K_AB: Alice-Bob link key (32B)
        - K_BC: Bob-Charlie link key (32B)
        - K_AC_final: final A<->C shared key after privacy amplification (32B)
        """
        # 1) 各リンク鍵（32B）を取得（デモは乱数）
        k_ab = self.alice.qkd_with(self.bob)
        k_bc = self.bob.qkd_with(self.charlie)

        # 2) Bob がエンド間鍵 K_AC を生成（信頼ノードなので Bob が作る）
        k_ac = os.urandom(32)  # Bob が決める共有鍵（32B）

        # 3) Bob が Alice/Charlie 向けのペイロードを作る（XOR暗号化）
        payload_a = xor_bytes(k_ac, k_ab)   # Bob -> Alice (公開しても安全性はK_AB次第)
        payload_c = xor_bytes(k_ac, k_bc)   # Bob -> Charlie

        # 4) Bob はペイロードをまとめて HMAC を付けて公開（改ざん防止）
        frame = b"PAYLOADS|" + payload_a + b"|" + payload_c
        tag = hmac_tag(self.auth_key, frame)
        public_frame = frame + b"|" + tag  # これが公開される（あるいは配布される）

        # 5) Alice 側: 検証して復号
        frame_a, tag_a = public_frame.rsplit(b"|", 1)
        if not hmac.compare_digest(hmac_tag(self.auth_key, frame_a), tag_a):
            raise ValueError("Alice: public frame authentication failed")
        # frame_a = b"PAYLOADS|{payload_a}|{payload_c}"
        _, payload_a_recv, _ = frame_a.split(b"|", 2)
        k_ac_a_raw = xor_bytes(payload_a_recv, k_ab)  # recover k_ac

        # 6) Charlie 側: 検証して復号
        frame_c, tag_c = public_frame.rsplit(b"|", 1)
        if not hmac.compare_digest(hmac_tag(self.auth_key, frame_c), tag_c):
            raise ValueError("Charlie: public frame authentication failed")
        _, _, payload_c_recv = frame_c.split(b"|", 2)
        k_ac_c_raw = xor_bytes(payload_c_recv, k_bc)  # recover k_ac

        # 7) 生鍵一致確認（デモでは必ず一致するはず）
        if k_ac_a_raw != k_ac_c_raw:
            raise ValueError("Key mismatch before privacy amplification")

        # 8) プライバシー増幅（HKDF）して最終鍵を作る
        context = public_frame
        k_ac_final = privacy_amplify(k_ac_a_raw, context)  # 32B

        # Bob は k_ac_final を知り得る（trusted repeaterモデル）
        return k_ab, k_bc, k_ac_final

# 直接実行時の簡易デモ（任意）
if __name__ == "__main__":
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    auth_key = os.urandom(32)
    setup = TrustedRepeaterSetup(alice, bob, charlie, auth_key)
    kab, kbc, kac = setup.run_once()
    with open("group_key_ac.bin", "wb") as f:
        f.write(kac)
    print("OK: group_key_ac.bin written (32B).")
