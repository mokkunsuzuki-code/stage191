# qkd49.py — 段階49 完全修正版（skip cache 安全化 & rekey 時系列ずれ対応）
# 依存: cryptography (ChaCha20Poly1305)

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import secrets, hmac, hashlib, struct

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


# ===== KDF（HKDF + HMAC-SHA256） =====
def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()

def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    t = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()
    return t[:length]

def hkdf(ikm: bytes, info: bytes, length: int = 32, salt: bytes | None = None) -> bytes:
    if salt is None:
        salt = b"\x00" * 32
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)

def kdf_ck(ck: bytes) -> tuple[bytes, bytes]:
    """チェーンKDF: (次のチェーンキー, メッセージ鍵) を返す"""
    ck_p = hmac.new(ck, b"ck", hashlib.sha256).digest()
    mk   = hmac.new(ck_p, b"mk", hashlib.sha256).digest()  # 32B
    return ck_p, mk


# ===== 送信者の送信用チェーン =====
@dataclass
class SenderChain:
    sid: str
    ck: bytes
    seq: int = 0

    def next_key(self) -> tuple[int, bytes]:
        self.ck, mk = kdf_ck(self.ck)
        s = self.seq
        self.seq += 1
        return s, mk


# ===== 受信者が各送信者ごとに持つ状態 =====
@dataclass
class ReceiverState:
    sid: str
    ck: bytes
    exp_seq: int = 0
    skip_cache: Dict[int, bytes] = field(default_factory=dict)  # seq -> mk

    def key_for(self, seq: int) -> bytes:
        """
        与えられた seq のメッセージ鍵を返す。
        - seq < exp_seq : 既に過ぎたものなので skip_cache から取り出す（無ければ捨てる）
        - seq > exp_seq : exp_seq..seq-1 の鍵を生成し skip_cache に貯めてから seq の鍵を返す
        - seq = exp_seq : 1ステップ進めて返す
        """
        # 過去
        if seq < self.exp_seq:
            mk = self.skip_cache.pop(seq, None)  # ← KeyError対策
            if mk is None:
                raise ValueError(f"stale or already used: sid={self.sid} seq={seq}")
            return mk

        # 未来 → 足りない分をキャッシュ
        while self.exp_seq < seq:
            self.ck, mk_mid = kdf_ck(self.ck)
            self.skip_cache[self.exp_seq] = mk_mid
            self.exp_seq += 1

        # ちょうど次
        self.ck, mk = kdf_ck(self.ck)
        self.exp_seq += 1
        return mk


# ===== メンバー =====
class Member:
    NONCE = b"\x00" * 12  # 毎回鍵がユニークなので固定ノンスでOK

    def __init__(self, mid: str):
        self.mid = mid
        self.sender: SenderChain | None = None
        self.receivers: Dict[str, ReceiverState] = {}  # sid -> state
        self.inbox: List[str] = []

    # 送信用チェーン設定 / 受信用チェーン設定
    def install_sender_key(self, seed: bytes) -> None:
        self.sender = SenderChain(self.mid, hkdf(seed, b"sender-ck"), seq=0)

    def install_receiver_key(self, sid: str, seed: bytes) -> None:
        self.receivers[sid] = ReceiverState(sid, hkdf(seed, b"sender-ck"), exp_seq=0)

    # 送信（ブロードキャスト用）
    def encrypt_from_me(self, text: str) -> tuple[str, int, bytes, bytes]:
        assert self.sender is not None, "sender key not installed"
        seq, mk = self.sender.next_key()
        aead = ChaCha20Poly1305(mk)
        # AAD: 送信者ID + seq
        aad = self.mid.encode("utf-8") + struct.pack("!I", seq)
        ct = aead.encrypt(self.NONCE, text.encode("utf-8"), aad)
        return self.mid, seq, aad, ct

    # 受信
    def recv_data(self, sid: str, seq: int, nonce: bytes, ct: bytes, aad: bytes) -> None:
        st = self.receivers.get(sid)
        if st is None:
            return  # まだ鍵配布を受けていない
        try:
            mk = st.key_for(seq)
        except ValueError:
            return  # 古すぎる or 既に消費済み → 破棄
        aead = ChaCha20Poly1305(mk)
        try:
            pt = aead.decrypt(nonce, ct, aad)
            self.inbox.append(pt.decode("utf-8", "ignore"))
        except Exception:
            # AAD/ノンス不一致など → 破棄
            pass


# ===== グループ・ブロードキャスト（Sender Keys 簡約） =====
class GroupChat:
    def __init__(self, member_ids: List[str]):
        self.members: Dict[str, Member] = {mid: Member(mid) for mid in member_ids}
        self.queue: List[tuple] = []  # (sid, dst, seq, nonce, ct, aad)
        self.rekey()  # 初期鍵配布

    def rekey(self):
        # 各メンバー用に sender seed を新規発行
        seeds: Dict[str, bytes] = {mid: secrets.token_bytes(32) for mid in self.members.keys()}
        # 送信用
        for mid, m in self.members.items():
            m.install_sender_key(seeds[mid])
        # 受信用（全員分インストール）
        for dst_id, dst in self.members.items():
            for src_id, seed in seeds.items():
                if src_id == dst_id:
                    continue
                dst.install_receiver_key(src_id, seed)

    def broadcast(self, sid: str, text: str) -> None:
        sid, seq, aad, ct = self.members[sid].encrypt_from_me(text)
        nonce = Member.NONCE
        for mid in self.members.keys():
            if mid == sid:
                continue
            self.queue.append((sid, mid, seq, nonce, ct, aad))

    def deliver_all(self) -> None:
        for sid, mid, seq, nonce, ct, aad in self.queue:
            self.members[mid].recv_data(sid, seq, nonce, ct, aad)
        self.queue.clear()


# ===== デモ =====
def run_demo():
    IDS = ["A", "B", "C"]
    MSG_PER_SENDER = 6
    REKEY_AFTER = 3

    chat = GroupChat(IDS)

    # ラウンドロビン送信
    for i in range(MSG_PER_SENDER):
        for sid in IDS:
            chat.broadcast(sid, f"MSG#{i+1} from {sid}")
        # 途中で一度 rekey（必ず配達後に実施）
        if (i + 1) == REKEY_AFTER:
            chat.deliver_all()
            chat.rekey()

    # 残りを配達
    chat.deliver_all()

    # 結果表示（存在しないIDを入れても落ちないように防御）
    for mid in ["A", "B", "C"]:
        if mid in chat.members:
            inbox = chat.members[mid].inbox
            print(f"=== {mid} が受け取ったメッセージ ===")
            print(" | ".join(inbox) if inbox else "(なし)")
            print()

if __name__ == "__main__":
    run_demo()
