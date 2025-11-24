# qkd44_superlight.py
# 目的: とにかく速く動く教育用デモ
#  - QKD鍵プール = os.urandom() で高速補充（教育用の模擬）
#  - Ledger で消費/残量管理
#  - AES-GCM (HKDFで鍵派生) + epoch/counter ノンス
#  - 信頼配送: ACK/再送/順序整列/重複排除
# 依存: cryptography
# 実行: pip install cryptography && python qkd44_superlight.py

import os, time, random, hmac, hashlib, collections
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ====== パラメータ（軽量化） ======
MSG_COUNT       = 8      # 送信メッセージ数
DEMO_SECONDS    = 1.5    # ループ上限時間
EPOCH_MSG_LIMIT = 4      # 1エポックで送れる回数
IKM_BYTES       = 32     # 1エポックで消費する素材
POOL_CHUNK_B    = 1024   # 補充時に追加するバイト数（1KB）

# ====== Ledger ======
class KeyLedger:
    def __init__(self, total_bits=0, alert_threshold=2048):
        self.total = total_bits
        self.used  = 0
        self.alert_threshold = alert_threshold
    def add(self, bits, reason="補充"):
        self.total += bits
    def consume(self, bits, reason="消費"):
        if self.used + bits > self.total:
            raise RuntimeError("鍵残量が不足（台帳）！")
        self.used += bits
    def remaining(self):
        return self.total - self.used

# ====== 鍵プール（bytearray） ======
def ensure_min_pool_bytes(pool: bytearray, ledger: KeyLedger, min_bytes: int = IKM_BYTES):
    """プールが min_bytes 未満なら、os.urandom() で一気に補充（教育用の模擬）。"""
    while len(pool) < min_bytes:
        chunk = os.urandom(POOL_CHUNK_B)   # 高速・強乱数
        pool.extend(chunk)
        ledger.add(len(chunk) * 8)

# ====== AES-GCM チャネル ======
class QKDAEADChannel:
    def __init__(self, qkd_pool: bytearray, ledger: KeyLedger,
                 context: bytes = b"QKD-AEAD-SuperLight", epoch_msg_limit: int = EPOCH_MSG_LIMIT):
        self.pool   = qkd_pool
        self.ledger = ledger
        self.context= context
        self.epoch  = -1
        self.counter= 0
        self.aesgcm = None
        self.enc_key= None
        self.auth_key=None
        self.nonce_base=None
        self.epoch_msg_limit = epoch_msg_limit

    def start_epoch(self):
        ensure_min_pool_bytes(self.pool, self.ledger, IKM_BYTES)
        ikm = bytes(self.pool[:IKM_BYTES]); del self.pool[:IKM_BYTES]
        self.ledger.consume(IKM_BYTES*8, "HKDF IKM 消費")
        hkdf = HKDF(algorithm=hashes.SHA256(), length=72, salt=None, info=self.context)
        okm  = hkdf.derive(ikm)
        self.enc_key    = okm[:32]
        self.auth_key   = okm[32:64]
        self.nonce_base = okm[64:72]  # 8B
        self.aesgcm = AESGCM(self.enc_key)
        self.epoch += 1
        self.counter = 0

    def _nonce(self) -> bytes:
        return self.counter.to_bytes(4, "big") + self.nonce_base

    def encrypt(self, pt: bytes, aad: bytes = b""):
        if self.aesgcm is None:
            raise RuntimeError("エポック未開始")
        if self.counter >= self.epoch_msg_limit:
            raise RuntimeError("エポック上限")
        nonce = self._nonce()
        ct = self.aesgcm.encrypt(nonce, pt, aad)
        ep, cnt = self.epoch, self.counter
        self.counter += 1
        return ep, cnt, ct

    def decrypt(self, ep: int, cnt: int, ct: bytes, aad: bytes = b""):
        # デモ簡略：受信側は送信側の ep に合わせる
        self.epoch = ep
        self.counter = cnt
        return self.aesgcm.decrypt(self._nonce(), ct, aad)

# ====== 不安定ネット（ロス・並べ替え・少遅延） ======
class UnreliableChannel:
    def __init__(self, drop=0.10, reorder=0.25, max_delay=0.03):
        random.seed(7)
        self.drop = drop; self.reorder=reorder; self.max_delay=max_delay
        self.buf = []
    def send(self, packet):
        if random.random() < self.drop: return
        d = random.random()*self.max_delay
        if random.random() < self.reorder: d += random.random()*self.max_delay
        self.buf.append((time.time()+d, packet))
    def recv_ready(self):
        now = time.time()
        out, keep = [], []
        for t, pk in self.buf:
            (out if t <= now else keep).append((t, pk))
        self.buf = keep
        return [pk for _, pk in out]

# ====== 信頼配送（ACK/再送/順序整列/重複排除） ======
class ReliableSender:
    def __init__(self, chan: QKDAEADChannel, window=5, timeout=0.15):
        self.chan = chan
        self.window = window
        self.timeout= timeout
        self.base = 0
        self.next = 0
        self.inflight = {}         # seq -> (t_send, (ep,cnt,ct,aad))
        self.pending = collections.deque()
        self.net_send = None       # set from outside

    def ensure_epoch(self):
        if self.chan.aesgcm is None:
            self.chan.start_epoch()

    def queue(self, data: bytes, aad: bytes=b""):
        self.pending.append((data, aad))
        self.try_send()

    def try_send(self):
        self.ensure_epoch()
        while self.pending and (self.next - self.base) < self.window:
            data, aad = self.pending[0]
            try:
                ep, cnt, ct = self.chan.encrypt(data, aad=aad)
            except RuntimeError as e:
                if "上限" in str(e) or "未開始" in str(e):
                    self.chan.start_epoch(); continue
                raise
            seq = self.next
            self.inflight[seq] = (time.time(), (ep, cnt, ct, aad))
            self.pending.popleft()
            self.net_send(("DATA", seq, ep, cnt, ct, aad))
            self.next += 1

    def on_ack(self, seq: int):
        if seq in self.inflight:
            del self.inflight[seq]
            while self.base not in self.inflight and self.base < self.next:
                self.base += 1
            self.try_send()

    def tick(self):
        now = time.time()
        for seq, (t0, payload) in list(self.inflight.items()):
            if now - t0 > self.timeout:
                self.inflight[seq] = (now, payload)
                self.net_send(("DATA", seq, *payload))

class ReliableReceiver:
    def __init__(self, chan: QKDAEADChannel, deliver_cb):
        self.chan = chan
        self.deliver = deliver_cb
        self.expect = 0
        self.buffer = {}
        self.seen = set()  # (ep,cnt,seq)

    def ensure_epoch(self):
        if self.chan.aesgcm is None:
            self.chan.start_epoch()

    def on_packet(self, pkt):
        typ, seq, ep, cnt, ct, aad = pkt
        if typ != "DATA": return None
        key = (ep, cnt, seq)
        if key in self.seen:
            return ("ACK", seq)
        self.ensure_epoch()
        try:
            pt = self.chan.decrypt(ep, cnt, ct, aad=aad)
        except Exception:
            return None
        self.seen.add(key)
        if seq == self.expect:
            self.deliver(pt)
            self.expect += 1
            while self.expect in self.buffer:
                self.deliver(self.buffer.pop(self.expect))
                self.expect += 1
        elif seq > self.expect:
            self.buffer[seq] = pt
        return ("ACK", seq)

# ====== デモ統合 ======
class Demo:
    def __init__(self):
        # 初期プール（空でもOK。start_epoch時に自動補充される）
        self.pool_tx = bytearray()
        self.pool_rx = bytearray()
        self.ledger_tx = KeyLedger(0)
        self.ledger_rx = KeyLedger(0)
        self.chan_tx = QKDAEADChannel(self.pool_tx, self.ledger_tx, epoch_msg_limit=EPOCH_MSG_LIMIT)
        self.chan_rx = QKDAEADChannel(self.pool_rx, self.ledger_rx, epoch_msg_limit=EPOCH_MSG_LIMIT)

        # 擬似ネット
        self.net_txrx = UnreliableChannel(drop=0.10, reorder=0.20, max_delay=0.02)
        self.net_rxtx = UnreliableChannel(drop=0.04, reorder=0.10, max_delay=0.02)

        # 信頼配送
        self.sender = ReliableSender(self.chan_tx, window=4, timeout=0.12)
        self.receiver = ReliableReceiver(self.chan_rx, deliver_cb=self._deliver)
        self.sender.net_send = lambda p: self.net_txrx.send(p)

        self.app_log = []

    def _deliver(self, pt: bytes):
        self.app_log.append(pt.decode("utf-8"))

    def run(self):
        # エポック開始
        self.chan_tx.start_epoch()
        self.chan_rx.start_epoch()

        # メッセージ投入
        for i in range(1, MSG_COUNT + 1):
            self.sender.queue(f"MSG#{i:02d}".encode(), aad=f"HDR#{i:02d}".encode())

        t_end = time.time() + DEMO_SECONDS
        while time.time() < t_end or self.sender.pending or self.sender.inflight:
            # TX->RX
            for pkt in self.net_txrx.recv_ready():
                ack = self.receiver.on_packet(pkt)
                if ack: self.net_rxtx.send(ack)
            # ACK
            for ack in self.net_rxtx.recv_ready():
                if ack and ack[0] == "ACK":
                    self.sender.on_ack(ack[1])
            # タイムアウト再送
            self.sender.tick()
            time.sleep(0.003)

        # 最後の掃き出し
        for pkt in self.net_txrx.recv_ready():
            ack = self.receiver.on_packet(pkt)
            if ack: self.sender.on_ack(ack[1])
        return self.app_log

# ====== 実行 ======
if __name__ == "__main__":
    demo = Demo()
    delivered = demo.run()
    print("=== アプリに届いた順序 ===")
    print(", ".join(delivered))
    ok = delivered == [f"MSG#{i:02d}" for i in range(1, MSG_COUNT + 1)]
    print(f"整列・完全到達: {'成功' if ok else '一部欠落/順序不一致'}")

