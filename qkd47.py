# qkd47.py — 段階47 完全修正版（InvalidTag根絶・Double Ratchet 簡約デモ）
# 依存: cryptography (ChaCha20Poly1305), 標準ライブラリ

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
import secrets, struct, hmac, hashlib, time

# AEAD
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


# ========= KDF（HKDF + HMAC-SHA256） =========

def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()

def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    # HKDF-Expand (単一ブロックで32バイト)
    T1 = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()
    return T1[:length]

def hkdf(ikm: bytes, info: bytes, length: int = 32, salt: bytes | None = None) -> bytes:
    if salt is None:
        salt = b"\x00" * 32
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)

def kdf_ck(ck: bytes) -> tuple[bytes, bytes]:
    """
    チェーンKDF: (ck', mk) を返す
    ck' = HMAC(ck, b'ck')
    mk  = HMAC(ck', b'mk')
    """
    ck_p = hmac.new(ck, b"ck", hashlib.sha256).digest()
    mk   = hmac.new(ck_p, b"mk", hashlib.sha256).digest()  # 32 bytes
    return ck_p, mk


# ========= 片方向ラチェット =========

@dataclass
class OneWayRatchet:
    """
    片方向チェーン。
    send 側と recv 側は独立インスタンスにすること（鍵衝突防止）。
    """
    ck: bytes    # 現在のチェーンキー
    seq: int = 0 # 送受それぞれ独立のカウンタ

    def next_key(self) -> tuple[bytes, int]:
        self.ck, mk = kdf_ck(self.ck)
        s = self.seq
        self.seq += 1
        return mk, s


# ========= 双方向チャンネル（簡約 Double Ratchet・DH無し） =========

class DRChannel:
    """
    A と B の両端で、方向ごとに send/recv チェーンを分離。
    ルートキー R(32B) から方向シードを導出:
      seed_AB = HKDF(R, b'AB'), seed_BA = HKDF(R, b'BA')
    A: send=seed_AB, recv=seed_BA
    B: send=seed_BA, recv=seed_AB
    """
    NONCE = b"\x00" * 12  # メッセージ鍵 mk が毎回ユニークなので固定ノンスでOK

    def __init__(self, root_key: bytes, side: str):
        assert side in ("A", "B")
        seed_AB = hkdf(root_key, b"AB")
        seed_BA = hkdf(root_key, b"BA")

        if side == "A":
            self.send = OneWayRatchet(seed_AB, 0)  # A->B
            self.recv = OneWayRatchet(seed_BA, 0)  # B->A
        else:
            self.send = OneWayRatchet(seed_BA, 0)  # B->A
            self.recv = OneWayRatchet(seed_AB, 0)  # A->B

    @staticmethod
    def aad(direction: int, seq: int) -> bytes:
        # 方向 (0=AB,1=BA) と seq を AAD として使う（ヘッダ互換）
        return struct.pack("!BI", direction, seq)

    # ---- 送信 ----
    def encrypt(self, direction: int, pt: bytes) -> tuple[int, int, bytes, bytes]:
        mk, seq = self.send.next_key()
        aead = ChaCha20Poly1305(mk)
        aad = self.aad(direction, seq)
        ct = aead.encrypt(self.NONCE, pt, aad)
        return direction, seq, aad, ct

    # ---- 受信 ----
    def decrypt(self, direction: int, seq: int, aad: bytes, ct: bytes) -> bytes:
        # 順序前提（Stop-and-Wait）なので受信側も next_key() で同じ seq に到達する
        mk, expect = self.recv.next_key()
        if expect != seq:
            raise RuntimeError(f"seq mismatch: expect {expect}, got {seq}")
        aead = ChaCha20Poly1305(mk)
        return aead.decrypt(self.NONCE, ct, aad)


# ========= ネットワーク模型 =========

class Link:
    def __init__(self): self.q: List[tuple] = []
    def send(self, pkt: tuple) -> None: self.q.append(pkt)
    def recv_ready(self) -> List[tuple]:
        out = self.q[:]; self.q.clear(); return out

class Net:
    def __init__(self): self.AB, self.BA = Link(), Link()


# ========= 送受デバイス (Stop-and-Wait) =========

def xor(a: bytes, b: bytes) -> bytes:  # 使わないが残しておく
    return bytes([x ^ y for x, y in zip(a, b)])

class Sender:
    def __init__(self, name: str, out: Link, chan: DRChannel, direction: int, app_msgs: List[bytes]):
        self.name, self.out, self.chan = name, out, chan
        self.direction = direction  # 0=AB, 1=BA
        self.msgs = app_msgs
        self.next_idx = 0
        self.in_flight: Optional[tuple] = None  # (seq, ct, aad)

    def can_send(self) -> bool:
        return self.in_flight is None and self.next_idx < len(self.msgs)

    def send_next(self):
        if not self.can_send(): return
        pt = self.msgs[self.next_idx]
        direction, seq, aad, ct = self.chan.encrypt(self.direction, pt)
        self.out.send(("DATA", direction, seq, aad, ct))
        self.in_flight = (seq, ct, aad)

    def on_ack(self, seq: int):
        if self.in_flight and seq == self.in_flight[0]:
            self.in_flight = None
            self.next_idx += 1

class Receiver:
    def __init__(self, name: str, in_link: Link, out_back: Link, chan: DRChannel,
                 direction_recv: int, log_store: List[bytes]):
        self.name, self.in_link, self.out_back = name, in_link, out_back
        self.chan = chan
        self.dir = direction_recv  # 受け取る方向（0=AB を受信、つまり A→B）
        self.log = log_store

    def on_packet(self, pkt: tuple) -> Optional[tuple]:
        kind, direction, seq, aad, ct = pkt
        if kind != "DATA": return None
        # この受信機は direction==self.dir のパケットだけ処理
        if direction != self.dir: return None
        pt = self.chan.decrypt(direction, seq, aad, ct)
        self.log.append(pt)
        ack = ("ACK", seq)
        self.out_back.send(ack)
        return ack


# ========= デモ =========

class DoubleRatchetDemo:
    MSG_COUNT = 8

    def __init__(self):
        # 共有ルートキー（本来はQKDの最終鍵から供給）
        root = secrets.token_bytes(32)

        # 双方のチャネル状態
        self.chan_A = DRChannel(root, side="A")
        self.chan_B = DRChannel(root, side="B")

        # ネットワーク
        self.net = Net()

        # アプリメッセージ
        self.toB_msgs = [f"Aから{i:02d}".encode("utf-8") for i in range(self.MSG_COUNT)]
        self.toA_msgs = [f"Bから{i:02d}".encode("utf-8") for i in range(self.MSG_COUNT)]

        # ログ
        self.log_A: List[bytes] = []  # Aが受け取った（B->A）
        self.log_B: List[bytes] = []  # Bが受け取った（A->B）

        # 送受器
        # A->B は direction=0 を使用、B->A は direction=1
        self.sender_AB   = Sender("A->B", self.net.AB, self.chan_A, direction=0, app_msgs=self.toB_msgs)
        self.receiver_AB = Receiver("RecvOnB", self.net.AB, self.net.BA, self.chan_B, direction_recv=0, log_store=self.log_B)

        self.sender_BA   = Sender("B->A", self.net.BA, self.chan_B, direction=1, app_msgs=self.toA_msgs)
        self.receiver_BA = Receiver("RecvOnA", self.net.BA, self.net.AB, self.chan_A, direction_recv=1, log_store=self.log_A)

    def run(self) -> Tuple[List[bytes], List[bytes]]:
        # 最初の送信を両方向で出す
        self.sender_AB.send_next()
        self.sender_BA.send_next()

        safety = 10_000  # デッドロック保険
        while safety > 0:
            progressed = False

            # AB到着
            for pkt in self.net.AB.recv_ready():
                if pkt[0] == "DATA":
                    self.receiver_AB.on_packet(pkt)
                elif pkt[0] == "ACK":
                    self.sender_BA.on_ack(pkt[1])
                progressed = True

            # BA到着
            for pkt in self.net.BA.recv_ready():
                if pkt[0] == "DATA":
                    self.receiver_BA.on_packet(pkt)
                elif pkt[0] == "ACK":
                    self.sender_AB.on_ack(pkt[1])
                progressed = True

            # 送信可能なら次を送る
            if self.sender_AB.can_send():
                self.sender_AB.send_next(); progressed = True
            if self.sender_BA.can_send():
                self.sender_BA.send_next(); progressed = True

            done_ab = (self.sender_AB.next_idx >= self.MSG_COUNT and self.sender_AB.in_flight is None)
            done_ba = (self.sender_BA.next_idx >= self.MSG_COUNT and self.sender_BA.in_flight is None)
            net_empty = (len(self.net.AB.q) == 0 and len(self.net.BA.q) == 0)
            if done_ab and done_ba and net_empty:
                break

            if not progressed:
                break

            safety -= 1
            time.sleep(0.001)

        return self.log_A, self.log_B


# ========= 実行 =========

if __name__ == "__main__":
    demo = DoubleRatchetDemo()
    toA, toB = demo.run()

    print("=== Aが受信した（B->A）===")
    print(" ".join(b.decode("utf-8") for b in toA))

    print("=== Bが受信した（A->B）===")
    print(" ".join(b.decode("utf-8") for b in toB))

    okA = len(toA) == demo.MSG_COUNT
    okB = len(toB) == demo.MSG_COUNT
    print(f"結果: A側={'成功' if okA else '不完全'} / B側={'成功' if okB else '不完全'}")

