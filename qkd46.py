# qkd46.py — 段階46 完全修正版
# 依存: 標準ライブラリのみ

from __future__ import annotations
import secrets
from typing import Optional, Tuple, List

# ========================= 基本部品 ==========================

class KeyLedger:
    """QKD 由来の鍵バイトを先頭から消費・末尾に補充するシンプルなレジャー"""
    def __init__(self, initial_bytes: bytes = b""):
        self._buf = bytearray(initial_bytes)
        self._pos = 0

    def remaining(self) -> int:
        return len(self._buf) - self._pos

    def take(self, n: int) -> bytes:
        if n <= 0:
            return b""
        n = min(n, self.remaining())
        s, e = self._pos, self._pos + n
        self._pos = e
        return bytes(self._buf[s:e])

    def add(self, more: bytes) -> None:
        self._buf.extend(more)

    def ensure(self, n: int) -> None:
        """残量が n 未満ならランダムで補充（デモ用。実運用は最終鍵を追加する）"""
        if self.remaining() < n:
            need = n - self.remaining()
            self.add(secrets.token_bytes(max(need, 1024)))


# ========================= テープ（方向×端点で独立） ==========================

class TapePair:
    """
    AB方向・BA方向の keystream を保持。
    各方向で「送信側用」と「受信側用」を**独立バッファ**として持つ。
      - AB方向: ab_A (A側送信用), ab_B (B側受信用)
      - BA方向: ba_B (B側送信用), ba_A (A側受信用)
    補充時は同じチャンクを**両バッファへ複製**し、両端で同じ鍵を同じ順で使えるようにする。
    """
    def __init__(self, ledger_ab: Optional[KeyLedger] = None,
                       ledger_ba: Optional[KeyLedger] = None):
        self.ledger_ab = ledger_ab
        self.ledger_ba = ledger_ba
        self.ab_A = bytearray()  # A -> B 送信用（A側）
        self.ab_B = bytearray()  # A -> B 受信用（B側）
        self.ba_B = bytearray()  # B -> A 送信用（B側）
        self.ba_A = bytearray()  # B -> A 受信用（A側）

    # ---- 互換的な ensure ----
    def ensure(self, *args, min_bytes: int = 1024,
               src_ab: Optional[KeyLedger] = None,
               src_ba: Optional[KeyLedger] = None) -> Tuple[int, int]:
        """
        呼び方は2通りOK：
          1) ensure(ledger_ab, ledger_ba)            ← 旧式（スクショ互換）
          2) ensure(min_bytes, src_ab=..., src_ba=...)← 新式
        戻り: (AB方向に追加したバイト数, BA方向に追加したバイト数)
        """
        # 旧式を自動判別
        if args and isinstance(args[0], KeyLedger):
            src_ab = args[0]
            src_ba = args[1] if len(args) > 1 else None
        elif args and isinstance(args[0], int):
            min_bytes = args[0]
            if len(args) > 1 and isinstance(args[1], KeyLedger):
                src_ab = args[1]
            if len(args) > 2 and isinstance(args[2], KeyLedger):
                src_ba = args[2]

        # 既定（コンストラクタで渡されていればそれを使う）
        if src_ab is None:
            src_ab = self.ledger_ab
        if src_ba is None:
            src_ba = self.ledger_ba

        add_ab = add_ba = 0

        # --- AB方向 ---
        if src_ab is not None:
            # A側とB側の両バッファが min_bytes 以上になるように“同じ”チャンクを補充
            need_ab = max(0, max(min_bytes - len(self.ab_A), min_bytes - len(self.ab_B)))
            if need_ab > 0:
                src_ab.ensure(need_ab)
                chunk = src_ab.take(need_ab)
                self.ab_A.extend(chunk)
                self.ab_B.extend(chunk)
                add_ab = len(chunk)

        # --- BA方向 ---
        if src_ba is not None:
            need_ba = max(0, max(min_bytes - len(self.ba_B), min_bytes - len(self.ba_A)))
            if need_ba > 0:
                src_ba.ensure(need_ba)
                chunk = src_ba.take(need_ba)
                self.ba_B.extend(chunk)
                self.ba_A.extend(chunk)
                add_ba = len(chunk)

        return add_ab, add_ba

    # ---- 方向×端点別の払い出し ----
    def take_ab_from_A(self, n: int) -> bytes:
        if len(self.ab_A) < n:
            self.ensure(min_bytes=len(self.ab_A) + n)
        out = bytes(self.ab_A[:n]); del self.ab_A[:n]
        return out

    def take_ab_from_B(self, n: int) -> bytes:
        if len(self.ab_B) < n:
            self.ensure(min_bytes=len(self.ab_B) + n)
        out = bytes(self.ab_B[:n]); del self.ab_B[:n]
        return out

    def take_ba_from_B(self, n: int) -> bytes:
        if len(self.ba_B) < n:
            self.ensure(min_bytes=len(self.ba_B) + n)
        out = bytes(self.ba_B[:n]); del self.ba_B[:n]
        return out

    def take_ba_from_A(self, n: int) -> bytes:
        if len(self.ba_A) < n:
            self.ensure(min_bytes=len(self.ba_A) + n)
        out = bytes(self.ba_A[:n]); del self.ba_A[:n]
        return out


# ========================= ネットワーク模型 ==========================

class Link:
    """片方向リンク（キュー）"""
    def __init__(self):
        self.q: List[tuple] = []

    def send(self, pkt: tuple) -> None:
        self.q.append(pkt)

    def recv_ready(self) -> List[tuple]:
        out = self.q[:]
        self.q.clear()
        return out

class Net:
    """A→B を AB、B→A を BA の2リンクとして持つ"""
    def __init__(self):
        self.AB = Link()
        self.BA = Link()


# ======================= 送受信（Stop&Wait） ==========================

def xor(a: bytes, b: bytes) -> bytes:
    m = min(len(a), len(b))
    return bytes([a[i] ^ b[i] for i in range(m)])

class Sender:
    """1方向送信。Stop-and-Wait（1個ずつ送ってACK待ち）"""
    def __init__(self, name: str, out_link: Link, tape: TapePair, direction: str, app_msgs: List[bytes]):
        self.name = name          # "A->B" など表示用
        self.out = out_link
        self.tape = tape
        self.dir = direction      # "AB" or "BA"
        self.msgs = app_msgs
        self.next_idx = 0
        self.in_flight: Optional[tuple] = None  # (seq, ct)
        self.seq = 0

    def _ks(self, n: int) -> bytes:
        if self.dir == "AB":
            return self.tape.take_ab_from_A(n)
        else:
            return self.tape.take_ba_from_B(n)

    def can_send(self) -> bool:
        return self.in_flight is None and self.next_idx < len(self.msgs)

    def send_next(self) -> None:
        if not self.can_send():
            return
        pt = self.msgs[self.next_idx]
        ks = self._ks(len(pt))
        ct = xor(pt, ks)
        pkt = ("DATA", self.seq, ct)
        self.out.send(pkt)
        self.in_flight = (self.seq, ct)

    def on_ack(self, seq: int) -> None:
        if self.in_flight and seq == self.in_flight[0]:
            self.in_flight = None
            self.seq += 1
            self.next_idx += 1


class Receiver:
    """1方向受信。受け取ったらACKを返す"""
    def __init__(self, name: str, in_link: Link, out_link_back: Link, tape: TapePair, direction: str, log_store: List[bytes]):
        self.name = name
        self.in_link = in_link
        self.out_back = out_link_back  # 逆方向にACKを返すリンク
        self.tape = tape
        self.dir = direction           # "AB" なら AB方向の“受信側”テープを使う
        self.log = log_store

    def _ks(self, n: int) -> bytes:
        if self.dir == "AB":
            return self.tape.take_ab_from_B(n)
        else:
            return self.tape.take_ba_from_A(n)

    def on_packet(self, pkt: tuple) -> Optional[tuple]:
        kind, seq, ct = pkt
        if kind != "DATA":
            return None
        ks = self._ks(len(ct))
        pt = xor(ct, ks)
        self.log.append(pt)
        ack = ("ACK", seq)
        self.out_back.send(ack)
        return ack


# ======================= フルデュプレックス・デモ ======================

class FullDuplexDemo:
    def __init__(self):
        # レジャー（方向ごと）
        self.ledger_A_out = KeyLedger(secrets.token_bytes(2048))  # AB方向の元鍵
        self.ledger_B_out = KeyLedger(secrets.token_bytes(2048))  # BA方向の元鍵

        # 方向ペアのテープ（補充は両端に同じチャンクを複製）
        self.tape = TapePair(self.ledger_A_out, self.ledger_B_out)

        # ネットワーク
        self.net = Net()

        # アプリメッセージ（A→B, B→A）
        self.MSG_CNT_AB = 8
        self.MSG_CNT_BA = 8
        self.app_to_B = [f"Aから{i:02d}".encode("utf-8") for i in range(self.MSG_CNT_AB)]
        self.app_to_A = [f"Bから{i:02d}".encode("utf-8") for i in range(self.MSG_CNT_BA)]

        # ログ保存
        self.log_to_A: List[bytes] = []  # B→A の受信ログ（A側が受け取った平文）
        self.log_to_B: List[bytes] = []  # A→B の受信ログ（B側が受け取った平文）

        # 送受信器
        self.sender_AB   = Sender("A->B", self.net.AB, self.tape, "AB", self.app_to_B)
        self.receiver_AB = Receiver("A->B/RecvOnB", self.net.AB, self.net.BA, self.tape, "AB", self.log_to_B)

        self.sender_BA   = Sender("B->A", self.net.BA, self.tape, "BA", self.app_to_A)
        self.receiver_BA = Receiver("B->A/RecvOnA", self.net.BA, self.net.AB, self.tape, "BA", self.log_to_A)

    def handshake(self):
        """開始前に両方向テープを最低長だけ確保（旧式/新式どちらでもOK）"""
        MIN_TAPE = 1024
        self.tape.ensure(self.ledger_A_out, self.ledger_B_out)  # 旧式互換
        self.tape.ensure(MIN_TAPE, src_ab=self.ledger_A_out, src_ba=self.ledger_B_out)  # 明示

    def run(self) -> Tuple[List[bytes], List[bytes]]:
        self.handshake()

        # 両方向で最初の送信を出す
        self.sender_AB.send_next()
        self.sender_BA.send_next()

        # ループ：両方向とも完了し、キューが空なら終了
        safety = 10_000  # 安全ブレーク
        while safety > 0:
            progressed = False

            # A->B 到着分
            for pkt in self.net.AB.recv_ready():
                if pkt[0] == "DATA":
                    self.receiver_AB.on_packet(pkt)
                elif pkt[0] == "ACK":
                    self.sender_BA.on_ack(pkt[1])
                progressed = True

            # B->A 到着分
            for pkt in self.net.BA.recv_ready():
                if pkt[0] == "DATA":
                    self.receiver_BA.on_packet(pkt)
                elif pkt[0] == "ACK":
                    self.sender_AB.on_ack(pkt[1])
                progressed = True

            # 次を送れるなら送る
            if self.sender_AB.can_send():
                self.sender_AB.send_next(); progressed = True
            if self.sender_BA.can_send():
                self.sender_BA.send_next(); progressed = True

            done_ab = (self.sender_AB.next_idx >= len(self.app_to_B) and self.sender_AB.in_flight is None)
            done_ba = (self.sender_BA.next_idx >= len(self.app_to_A) and self.sender_BA.in_flight is None)
            net_empty = (len(self.net.AB.q) == 0 and len(self.net.BA.q) == 0)
            if done_ab and done_ba and net_empty:
                break

            if not progressed:
                break
            safety -= 1

        return self.log_to_A, self.log_to_B


# ============================ 実行部 ============================

if __name__ == "__main__":
    demo = FullDuplexDemo()
    toA, toB = demo.run()

    print("=== A が受け取った順序（B->A）===")
    print([b.decode("utf-8") for b in toA])

    print("=== B が受け取った順序（A->B）===")
    print([b.decode("utf-8") for b in toB])

    okA = toA == [f"Bから{i:02d}".encode("utf-8") for i in range(demo.MSG_CNT_BA)]
    okB = toB == [f"Aから{i:02d}".encode("utf-8") for i in range(demo.MSG_CNT_AB)]
    print(f"結果：完全到達  A側={'成功' if okA else '失敗'}  |  B側={'成功' if okB else '失敗'}")

