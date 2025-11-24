# qkd43.py  — 段階43 修正版（鍵枯渇エラー対応）

import numpy as np
from typing import List

# ===== 簡易 QKD 鍵レジャー =====
class QKDKeyLedger:
    def __init__(self, pool_bits: int = 0):
        self.qkd_bytes = np.random.randint(0, 2, pool_bits, dtype=np.uint8).tolist()

    def add_keys(self, n_bits: int):
        # 疑似的に pipeline で新しい鍵を補充したことにする
        new_bits = np.random.randint(0, 2, n_bits, dtype=np.uint8).tolist()
        self.qkd_bytes.extend(new_bits)

    def need(self, n_bits: int):
        if len(self.qkd_bytes) < n_bits:
            raise RuntimeError("QKD鍵が不足 (レジャー)")

    def take(self, n_bits: int) -> List[int]:
        self.need(n_bits)
        out = self.qkd_bytes[:n_bits]
        self.qkd_bytes = self.qkd_bytes[n_bits:]
        return out

    def remaining(self) -> int:
        return len(self.qkd_bytes)

# ===== 簡易 チャネル（AES-GCM風ダミー） =====
class SecureChannel:
    def __init__(self, ledger: QKDKeyLedger, ikm_len: int = 32):
        self.ledger = ledger
        self.ikm_len = ikm_len
        self.epoch = 0
        self.counter = 0

    def start_epoch(self):
        # 鍵不足なら自動補充してから処理
        if self.ledger.remaining() < self.ikm_len:
            self.ledger.add_keys(2048)   # 2kビット補充
        self.ledger.need(self.ikm_len)
        self.ledger.take(self.ikm_len)
        self.epoch += 1
        self.counter = 0

    def encrypt(self, msg: bytes, aad: bytes = b"meta"):
        self.counter += 1
        return msg[::-1]  # ダミー暗号（逆順にするだけ）

    def decrypt(self, ct: bytes, aad: bytes = b"meta"):
        return ct[::-1]

# ===== コントローラ（メッセージ自動処理） =====
class AutoQKDController:
    def __init__(self, ledger: QKDKeyLedger, chan: SecureChannel):
        self.ledger = ledger
        self.chan = chan
        self.queue = []

    def enqueue(self, msg: bytes, aad: bytes):
        self.queue.append((msg, aad))

    def process_queue(self):
        results = []
        for i, (msg, aad) in enumerate(self.queue):
            try:
                ct = self.chan.encrypt(msg, aad=aad)
                pt = self.chan.decrypt(ct, aad=aad)
                results.append(pt.decode("utf-8"))
            except RuntimeError:
                # 鍵不足なら新しいエポックで補充して再試行
                print("[AutoQKD] QKD鍵不足 → 自動rekeyで補充します")
                self.chan.start_epoch()
                ct = self.chan.encrypt(msg, aad=aad)
                pt = self.chan.decrypt(ct, aad=aad)
                results.append(pt.decode("utf-8"))
        return results

# ===== メイン =====
def main():
    ledger = QKDKeyLedger(pool_bits=1024)   # 初期 1024ビット
    chan = SecureChannel(ledger, ikm_len=32)
    ctrl = AutoQKDController(ledger, chan)

    # 10個のメッセージを投入
    for i in range(10):
        ctrl.enqueue(f"メッセージ{i+1}".encode("utf-8"),
                     aad=f"hdr{i+1}".encode("utf-8"))

    print("\n=== 通信開始 ===")
    results = ctrl.process_queue()
    for i, r in enumerate(results, 1):
        print(f"[受信{i}] {r}")

    print(f"\n残り鍵 = {ledger.remaining()} ビット")

if __name__ == "__main__":
    main()

