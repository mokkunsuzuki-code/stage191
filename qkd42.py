# qkd42_auto_refill.py
# 段階42：QKD鍵レジャー + 自動補充 + エポック切替 + AEAD暗号（AAD対応）
# 依存：標準ライブラリのみ

from __future__ import annotations
import hmac, hashlib, secrets, struct
from typing import Tuple, Optional

# ================= ユーティリティ（HKDF / PRF / XOR） =================

def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()  # 32 bytes

def hkdf_expand(prk: bytes, info: bytes, out_len: int) -> bytes:
    out = b""; t = b""; ctr = 1
    while len(out) < out_len:
        t = hmac.new(prk, t + info + bytes([ctr]), hashlib.sha256).digest()
        out += t; ctr += 1
    return out[:out_len]

def hmac256(key: bytes, *chunks: bytes) -> bytes:
    hm = hmac.new(key, b"", hashlib.sha256)
    for c in chunks: hm.update(c)
    return hm.digest()

def xor_bytes(a: bytes, b: bytes) -> bytes:
    m = min(len(a), len(b))
    return bytes([a[i] ^ b[i] for i in range(m)])

# ======================= QKD 鍵レジャー（消費型） ======================

class QKDLedger:
    """QKD鍵バイトを先頭から消費・追加できる簡易レジャー。"""
    def __init__(self, qkd_bytes: bytes = b""):
        self._buf = bytearray(qkd_bytes)
        self._pos = 0

    # 情報表示
    def remaining_bits(self) -> int:
        return 8 * (len(self._buf) - self._pos)

    def remaining_bytes(self) -> int:
        return (len(self._buf) - self._pos)

    # 操作
    def can_take(self, n_bytes: int) -> bool:
        return self.remaining_bytes() >= n_bytes

    def take(self, n_bytes: int) -> bytes:
        if not self.can_take(n_bytes): return b""
        s, e = self._pos, self._pos + n_bytes
        self._pos = e
        return bytes(self._buf[s:e])

    def add(self, more: bytes) -> None:
        """末尾に追記して残量を増やす"""
        self._buf.extend(more)

# ========================= QKD 供給元（自動補充） =====================

class QKDSource:
    """必要に応じて新しいQKD鍵バイト列を供給する抽象クラス。"""
    def fetch(self, min_bytes: int) -> bytes:
        """少なくとも min_bytes を返すのが理想。供給不可なら b'' を返す。"""
        raise NotImplementedError

class RandomQKDSource(QKDSource):
    """デモ用：乱数で鍵を供給。チャンク単位で最大回数まで。"""
    def __init__(self, chunk_size: int = 1024, max_chunks: int = 8):
        self.chunk = chunk_size
        self.max_chunks = max_chunks
        self.used = 0

    def fetch(self, min_bytes: int) -> bytes:
        if self.used >= self.max_chunks:
            return b""
        need = max(min_bytes, self.chunk)
        # 複数チャンクまとめて用意（回数制限も管理）
        n_chunks = (need + self.chunk - 1) // self.chunk
        n_chunks = min(n_chunks, self.max_chunks - self.used)
        if n_chunks <= 0:
            return b""
        self.used += n_chunks
        return secrets.token_bytes(self.chunk * n_chunks)

# ======================= エポック付き AEAD チャネル ===================

class AEADChannel:
    """
    各エポックで IKM(=QKD鍵の一部) を消費し、HKDFで (enc_key, mac_key) を導出。
    暗号：XORストリーム（HMACベースPRF）＋ HMAC-SHA256 タグ（先頭16B）。
    AAD対応。counterは64bit。rekey時に不足なら QKDSource から自動補充。
    """
    IKM_LEN  = 32     # 1エポックで消費する IKM バイト数
    TAG_LEN  = 16
    NONCE_LEN = 12

    def __init__(self, ledger: QKDLedger, source: Optional[QKDSource] = None, context: bytes = b"AEAD-CHAN"):
        self.ledger = ledger
        self.source = source
        self.context = context
        self.epoch = -1
        self.counter = 0
        self.enc_key = b""
        self.mac_key = b""

    # ---- 内部：鍵導出・ノンス・キーストリーム ----
    def _derive_from_ikm(self, ikm: bytes, epoch: int) -> Tuple[bytes, bytes]:
        prk = hkdf_extract(salt=f"epoch:{epoch}".encode(), ikm=ikm)
        okm = hkdf_expand(prk, self.context + b"|keys", 64)
        return okm[:32], okm[32:]

    def _nonce(self, epoch: int, counter: int) -> bytes:
        m = struct.pack(">Q", counter) + struct.pack(">I", epoch & 0xffffffff)
        return hashlib.sha256(m).digest()[:self.NONCE_LEN]

    def _keystream(self, key: bytes, nonce: bytes, n: int) -> bytes:
        out = b""; blk = 0
        while len(out) < n:
            out += hmac256(key, nonce, struct.pack(">I", blk))
            blk += 1
        return out[:n]

    # ---- 公開API ----
    def start_epoch(self, auto_refill: bool = True) -> bool:
        """新エポック。足りなければ source から補充を試み、それでも不足ならスキップ。"""
        need = self.IKM_LEN
        if not self.ledger.can_take(need) and auto_refill and self.source is not None:
            lack = need - self.ledger.remaining_bytes()
            got = self.source.fetch(lack)
            if got:
                self.ledger.add(got)
                print(f"[rekey] 自動補充: +{len(got)}B（残り {self.ledger.remaining_bytes()}B）")
        if not self.ledger.can_take(need):
            print(f"[rekey] スキップ：QKD鍵が不足（必要 {need}B, 残り {self.ledger.remaining_bytes()}B）")
            return False

        ikm = self.ledger.take(need)
        next_epoch = self.epoch + 1
        enc, mac = self._derive_from_ikm(ikm, next_epoch)
        self.epoch = next_epoch
        self.counter = 0
        self.enc_key, self.mac_key = enc, mac
        print(f"[rekey] 新エポックへ切替：epoch={self.epoch}, 残り鍵={self.ledger.remaining_bits()}ビット")
        return True

    def verify_key_confirmation(self) -> bool:
        # 実運用では HMAC 交換で確認。デモは常に True。
        return True

    def encrypt(self, pt: bytes, aad: bytes = b"") -> Tuple[int, int, bytes]:
        assert self.epoch >= 0 and self.enc_key and self.mac_key, "先に start_epoch() を呼んでください"
        nonce = self._nonce(self.epoch, self.counter)
        ks = self._keystream(self.enc_key, nonce, len(pt))
        ct = xor_bytes(pt, ks)
        tag = hmac256(self.mac_key, aad, nonce, ct)[:self.TAG_LEN]
        out = ct + tag
        ep, cnt = self.epoch, self.counter
        self.counter += 1
        return ep, cnt, out

    def decrypt(self, epoch: int, counter: int, ct_and_tag: bytes, aad: bytes = b"") -> bytes:
        assert epoch == self.epoch, "現在のエポックと一致しません"
        nonce = self._nonce(epoch, counter)
        ct, tag = ct_and_tag[:-self.TAG_LEN], ct_and_tag[-self.TAG_LEN:]
        chk = hmac256(self.mac_key, aad, nonce, ct)[:self.TAG_LEN]
        if not hmac.compare_digest(tag, chk):
            raise ValueError("認証タグ不一致（破損 or 改ざん）")
        ks = self._keystream(self.enc_key, nonce, len(ct))
        return xor_bytes(ct, ks)

# ============================== デモ ===============================

def main():
    # レジャー初期化：わざと少ない 16B から開始 → rekey時に自動補充が走る
    ledger = QKDLedger(secrets.token_bytes(16))
    # 供給元：64B チャンクを最大 10 回まで供給（合計最大 640B）
    source = RandomQKDSource(chunk_size=64, max_chunks=10)

    print(f"初期残り鍵 = {ledger.remaining_bits()} ビット（{ledger.remaining_bytes()}B）")

    chan = AEADChannel(ledger, source)

    # エポック0（足りなければ自動補充して開始）
    chan.start_epoch(auto_refill=True)
    aad = "meta1".encode("utf-8")
    msg = "最初のメッセージ（エポック0）".encode("utf-8")
    ep, cnt, ct = chan.encrypt(msg, aad=aad)
    pt = chan.decrypt(ep, cnt, ct, aad=aad)
    print(f"[送信] epoch={ep}, counter={cnt}, ct_len={len(ct)}")
    print(f"[受信] {pt.decode('utf-8')}")
    print(f"残り鍵 = {ledger.remaining_bits()}ビット（{ledger.remaining_bytes()}B）\n")

    # 複数回 rekey を試す（自動補充が足りなければスキップ表示）
    for i in range(1, 5):
        ok = chan.start_epoch(auto_refill=True)
        print(f"[鍵確認] => {'成功' if ok and chan.verify_key_confirmation() else 'スキップ/不足'}")

        aad_i = f"meta{i+1}".encode("utf-8")
        msg_i = f"rekey後のメッセージ #{i}".encode("utf-8")
        ep2, cnt2, ct2 = chan.encrypt(msg_i, aad=aad_i)
        pt2 = chan.decrypt(ep2, cnt2, ct2, aad=aad_i)
        print(f"[送信{i}] epoch={ep2}, counter={cnt2}, ct_len={len(ct2)}")
        print(f"[受信{i}] {pt2.decode('utf-8')}")
        print(f"残り鍵 = {ledger.remaining_bits()}ビット（{ledger.remaining_bytes()}B）\n")

if __name__ == "__main__":
    main()

