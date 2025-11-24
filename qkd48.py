# qkd48.py — 段階48 完全修正版（skip cache 安全化 & rekey 対応）
# 依存: cryptography (ChaCha20Poly1305), 標準ライブラリ

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import secrets, hmac, hashlib, struct

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


# ========== 共通KDF ==========
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
    """チェーンKDF: 次のチェーンキーとメッセージ鍵."""
    ck_p = hmac.new(ck, b"ck", hashlib.sha256).digest()
    mk   = hmac.new(ck_p, b"mk", hashlib.sha256).digest()  # 32B
    return ck_p, mk


# ========== 送信者側 Sender Key チェーン ==========
@dataclass
class SenderChain:
    sid: str                # 送信者ID
    epoch: int              # エポック番号（rekeyで+1）
    ck: bytes               # 現在のチェーンキー
    seq: int = 0            # 自分が送った通し番号

    def next_key(self) -> tuple[int, bytes]:
        """次の（seq, mk）を払い出して seq++"""
        self.ck, mk = kdf_ck(self.ck)
        s = self.seq
        self.seq += 1
        return s, mk


# ========== 受信者側の追跡状態 ==========
@dataclass
class ReceiverState:
    """受信者が各送信者ごとに持つ状態（エポック毎）"""
    sid: str
    epoch: int
    ck: bytes
    exp_seq: int = 0
    skip_cache: Dict[int, bytes] = field(default_factory=dict)  # seq -> mk（将来用）

    def get_key_for(self, seq: int) -> bytes:
        """
        受信したメッセージの seq に対応する mk を返す。
        - すでに過去（seq < exp_seq）: skip_cache から取り出す。無ければ stale として捨てる。
        - ちょうど次（seq == exp_seq）: 1ステップ進めて mk を返す。
        - 未来（seq > exp_seq）: exp_seq まで前進しながら不足分を skip_cache に入れ、目的の mk を返す。
        """
        # 1) 過去
        if seq < self.exp_seq:
            mk = self.skip_cache.pop(seq, None)
            if mk is None:
                raise ValueError(f"stale or already used: sid={self.sid} seq={seq}")
            return mk

        # 2) 未来: exp_seq .. seq-1 を cache に詰める
        while self.exp_seq < seq:
            self.ck, mk_mid = kdf_ck(self.ck)
            self.skip_cache[self.exp_seq] = mk_mid
            self.exp_seq += 1

        # 3) ちょうど次（= seq）
        self.ck, mk = kdf_ck(self.ck)
        self.exp_seq += 1
        return mk


# ========== メンバー ==========
class Member:
    NONCE = b"\x00" * 12  # メッセージ鍵が毎回一意なので固定ノンスで良い

    def __init__(self, mid: str):
        self.mid = mid
        self.sender: SenderChain | None = None          # 自分が送る用チェーン
        self.receivers: Dict[Tuple[str, int], ReceiverState] = {}  # (sid, epoch) -> state
        self.inbox: List[str] = []                      # 平文ログ

    # --- 送信者キーの配布（rekey時もこれ） ---
    def install_sender_key(self, epoch: int, seed: bytes) -> None:
        """自分の送信用チェーンを seed から初期化"""
        ck0 = hkdf(seed, b"sender-ck")
        self.sender = SenderChain(self.mid, epoch, ck0, seq=0)

    def install_receiver_key(self, sid: str, epoch: int, seed: bytes) -> None:
        """sid の送信を受け取るための追跡状態を seed から初期化/更新"""
        ck0 = hkdf(seed, b"sender-ck")
        self.receivers[(sid, epoch)] = ReceiverState(sid, epoch, ck0, exp_seq=0)

    # --- 送信 ---
    def encrypt_from_me(self, pt: str) -> tuple[str, int, int, bytes, bytes]:
        assert self.sender is not None, "sender key not installed"
        seq, mk = self.sender.next_key()
        aead = ChaCha20Poly1305(mk)
        aad = struct.pack("!H", self.sender.epoch) + self.mid.encode("utf-8") + struct.pack("!I", seq)
        ct  = aead.encrypt(self.NONCE, pt.encode("utf-8"), aad)
        return self.mid, self.sender.epoch, seq, aad, ct

    # --- 受信 ---
    def decrypt_from(self, sid: str, epoch: int, seq: int, aad: bytes, ct: bytes) -> None:
        st = self.receivers.get((sid, epoch))
        if st is None:
            # 未知のエポック → 無視（配布前に飛んできた等）
            return
        try:
            mk = st.get_key_for(seq)  # ここで skip_cache を安全に扱う
        except ValueError:
            # 古すぎる／既に消費済み → 破棄
            return
        aead = ChaCha20Poly1305(mk)
        try:
            pt = aead.decrypt(self.NONCE, ct, aad)
            self.inbox.append(pt.decode("utf-8", "ignore"))
        except Exception:
            # AAD不一致等は破棄（グループの堅牢性のため握りつぶす）
            pass


# ========== チャット（ブロードキャスト + rekey） ==========
class GroupChat:
    def __init__(self, member_ids: List[str]):
        self.epoch = 0
        self.members: Dict[str, Member] = {mid: Member(mid) for mid in member_ids}

        # 初回配布
        self.rekey()

    def rekey(self):
        """新しいエポックを開始（全員に Sender Key を配布し直す）"""
        self.epoch += 1
        # 各メンバーごとに新しい seed を作り、本人は SenderChain に、他メンバーは ReceiverState に反映
        sender_seeds: Dict[str, bytes] = {mid: secrets.token_bytes(32) for mid in self.members.keys()}

        # 送信用
        for mid, m in self.members.items():
            m.install_sender_key(self.epoch, sender_seeds[mid])

        # 受信用（全員が全員の sender を受け取れるように）
        for dst_id, dst in self.members.items():
            for src_id, seed in sender_seeds.items():
                if src_id == dst_id:
                    continue
                dst.install_receiver_key(src_id, self.epoch, seed)

    def broadcast(self, sid: str, text: str) -> List[tuple]:
        """sid が text を全員へブロードキャスト。戻りは配送キュー。"""
        sender = self.members[sid]
        sid, epoch, seq, aad, ct = sender.encrypt_from_me(text)
        packets = []
        for mid in self.members.keys():
            if mid == sid:
                continue
            packets.append((sid, mid, epoch, seq, aad, ct))
        return packets

    def deliver_all(self, packets: List[tuple]) -> None:
        """配送キューを全件配達"""
        for sid, mid, epoch, seq, aad, ct in packets:
            self.members[mid].decrypt_from(sid, epoch, seq, aad, ct)


# ========== デモ ==========
def run_demo():
    # パラメータ
    IDS = ["A", "B", "C"]
    MSG_PER_SENDER = 6
    REKEY_AFTER = 3  # 各送信者がこの回数を送った後で rekey を1回入れる

    chat = GroupChat(IDS)
    queue: List[tuple] = []

    # ラウンドロビンで送信
    for i in range(MSG_PER_SENDER):
        for sid in IDS:
            queue += chat.broadcast(sid, f"MSG#{i+1} from {sid}")

        # 途中で rekey（配布→チェーン更新）。配達漏れを防ぐため、まず配達してから rekey。
        if (i + 1) == REKEY_AFTER:
            chat.deliver_all(queue)
            queue = []
            chat.rekey()

    # 残りを配達
    chat.deliver_all(queue)

    # 結果表示
    for mid in IDS:
        print(f"=== {mid} が受け取ったメッセージ ===")
        print(" | ".join(chat.members[mid].inbox))
        print()

if __name__ == "__main__":
    run_demo()

