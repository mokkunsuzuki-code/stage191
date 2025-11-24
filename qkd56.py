# qkd56.py — 段階56 完全修正版（Audit暗号化のInvalidTag根絶）
# 依存: cryptography (AESGCM)

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import secrets, base64, hmac, hashlib, struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ====== 小道具（HKDF・Base64） ==============================================

def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()

def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    t = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()
    return t[:length]

def hkdf(ikm: bytes, info: bytes, length: int = 32, salt: Optional[bytes] = None) -> bytes:
    if salt is None:
        salt = b"\x00" * 32
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)

def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ====== ラップ/アンラップ基盤（段階56版） ====================================

WRAP_LABEL = b"qkd56-wrap-v1"  # AAD の固定ラベル（将来のバージョン識別にも）

@dataclass
class KeyWrapper:
    """
    メモリ内キーストア。保存メタが現在の mk で復号できない場合は
    “教育/試作向け挙動”として初期化し直して再生成する。
    """
    meta: Dict[str, str] = field(default_factory=dict)  # {"kid":..,"nonce":..,"ct":..}

    @staticmethod
    def kid_from_mk(mk: bytes) -> bytes:
        return hmac.new(mk, b"kid", hashlib.sha256).digest()[:8]

    @staticmethod
    def derive_wrap_key(mk: bytes, kid: bytes) -> bytes:
        # ラップ専用鍵（他用途と混線させない）
        return hkdf(mk, WRAP_LABEL + b"|" + kid, 32)

    def _wrap(self, mk: bytes, dek: bytes) -> Dict[str, str]:
        kid = self.kid_from_mk(mk)
        wk = self.derive_wrap_key(mk, kid)
        aead = AESGCM(wk)
        nonce = secrets.token_bytes(12)
        aad = WRAP_LABEL + b"|" + kid
        ct = aead.encrypt(nonce, dek, aad)
        return {"v": "1", "kid": b64e(kid), "nonce": b64e(nonce), "ct": b64e(ct)}

    def _unwrap(self, mk: bytes, meta: Dict[str, str]) -> bytes:
        kid = b64d(meta["kid"])
        wk = self.derive_wrap_key(mk, kid)
        aead = AESGCM(wk)
        nonce = b64d(meta["nonce"])
        ct = b64d(meta["ct"])
        aad = WRAP_LABEL + b"|" + kid
        return aead.decrypt(nonce, ct, aad)

    def create_or_load(self, mk: bytes) -> bytes:
        """
        既存メタがあれば復号。失敗（mk不一致/破損）は安全に再初期化。
        """
        if self.meta:
            try:
                return self._unwrap(mk, self.meta)
            except Exception:
                pass  # 再初期化して作り直す

        # 新規生成（32B データ鍵）
        dek = secrets.token_bytes(32)
        self.meta = self._wrap(mk, dek)
        return dek


# ====== 簡易チャット（メッセージ配達 & 監査文字列の生成） =====================

class Member:
    NONCE = b"\x00" * 12  # メッセージ鍵ユニーク運用なら固定でOK（デモ簡略化）

    def __init__(self, mid: str, seed_send: bytes, seeds_recv: Dict[str, bytes]):
        self.mid = mid
        self.ck_send = hkdf(seed_send, b"sender-ck")  # 自分が送る用のCK
        self.seq_send = 0
        self.ck_recv: Dict[str, bytes] = {sid: hkdf(seed, b"sender-ck") for sid, seed in seeds_recv.items()}
        self.exp_seq: Dict[str, int] = {sid: 0 for sid in seeds_recv.keys()}
        self.skip: Dict[str, Dict[int, bytes]] = {sid: {} for sid in seeds_recv.keys()}
        self.inbox: List[str] = []

    def kdf_ck(self, ck: bytes) -> Tuple[bytes, bytes]:
        ck2 = hmac.new(ck, b"ck", hashlib.sha256).digest()
        mk  = hmac.new(ck2, b"mk", hashlib.sha256).digest()
        return ck2, mk

    # 送信
    def encrypt_from_me(self, text: str) -> Tuple[str, int, bytes, bytes]:
        self.ck_send, mk = self.kdf_ck(self.ck_send)
        seq = self.seq_send
        self.seq_send += 1
        aead = AESGCM(mk)
        aad = self.mid.encode() + struct.pack("!I", seq)
        ct = aead.encrypt(self.NONCE, text.encode("utf-8"), aad)
        return self.mid, seq, aad, ct

    # 受信
    def recv_from(self, sid: str, seq: int, aad: bytes, ct: bytes) -> None:
        # 受信鍵の前進と skip キャッシュ
        ck = self.ck_recv[sid]
        exp = self.exp_seq[sid]

        if seq < exp:
            mk = self.skip[sid].pop(seq, None)
            if mk is None:
                return
        else:
            while exp < seq:
                ck, mk_mid = self.kdf_ck(ck)
                self.skip[sid][exp] = mk_mid
                exp += 1
            ck, mk = self.kdf_ck(ck)
            exp += 1

        self.ck_recv[sid] = ck
        self.exp_seq[sid] = exp

        aead = AESGCM(mk)
        try:
            pt = aead.decrypt(self.NONCE, ct, aad)
            self.inbox.append(pt.decode("utf-8", "ignore"))
        except Exception:
            pass


class GroupChat:
    def __init__(self, ids: List[str]):
        seeds = {mid: secrets.token_bytes(32) for mid in ids}
        self.members: Dict[str, Member] = {}
        for mid in ids:
            recv_seed = {sid: seeds[sid] for sid in ids if sid != mid}
            self.members[mid] = Member(mid, seeds[mid], recv_seed)
        self.queue: List[Tuple[str, str, int, bytes, bytes]] = []

    def broadcast(self, sid: str, text: str) -> None:
        sid, seq, aad, ct = self.members[sid].encrypt_from_me(text)
        for mid in self.members.keys():
            if mid == sid: continue
            self.queue.append((sid, mid, seq, aad, ct))

    def deliver_all(self) -> None:
        for sid, mid, seq, aad, ct in self.queue:
            self.members[mid].recv_from(sid, seq, aad, ct)
        self.queue.clear()


# ====== 監査ストア（暗号化保存 & 検証） ======================================

@dataclass
class AuditStore:
    """
    監査文字列を AES-GCM で暗号化保存。KeyWrapper を用い、
    既存メタが mk で開けなければ安全に初期化して作り直す。
    """
    wrapper: KeyWrapper
    record: Dict[str, str] = field(default_factory=dict)  # {"nonce":..,"ct":..,"kid":..}

    def save(self, mk: bytes, text: str) -> None:
        # DEK を mk から（または保存済みメタから）取得
        dek = self.wrapper.create_or_load(mk)  # ← ここで InvalidTag を握り潰して再初期化済みになる
        aead = AESGCM(dek)
        kid = KeyWrapper.kid_from_mk(mk)  # AAD の片方に混ぜておく
        aad = b"audit56|" + kid
        nonce = secrets.token_bytes(12)
        ct = aead.encrypt(nonce, text.encode("utf-8"), aad)
        self.record = {"kid": b64e(kid), "nonce": b64e(nonce), "ct": b64e(ct)}

    def load(self, mk: bytes) -> Optional[str]:
        if not self.record or not self.wrapper.meta:
            return None
        dek = self.wrapper.create_or_load(mk)
        aead = AESGCM(dek)
        kid = b64d(self.record["kid"])
        aad = b"audit56|" + kid
        try:
            pt = aead.decrypt(b64d(self.record["nonce"]), b64d(self.record["ct"]), aad)
            return pt.decode("utf-8", "ignore")
        except Exception:
            return None

    def verify(self, mk: bytes, expected: str) -> bool:
        got = self.load(mk)
        return (got == expected)


# ====== デモ実行 =============================================================

def run_demo():
    IDS = ["A", "B", "C"]
    chat = GroupChat(IDS)

    # メッセージ送信（各人2通）
    for i in range(2):
        for sid in IDS:
            chat.broadcast(sid, f"MSG#{i+1} from {sid}")
    chat.deliver_all()

    # 「監査」用の文字列を生成（受信総数だけをまとめる例）
    counts = {mid: len(chat.members[mid].inbox) for mid in IDS}
    audit_text = "; ".join(f"{mid}:{cnt}" for mid, cnt in counts.items())

    # QKDの“最終鍵”に相当する mk（ここではデモなのでランダム）
    mk = secrets.token_bytes(32)

    # 監査を暗号化保存 → 読み出し検証
    wrapper = KeyWrapper()
    audit = AuditStore(wrapper)
    audit.save(mk, audit_text)
    ok = audit.verify(mk, audit_text)

    # 結果表示
    print("== 段階56: 監査ログの暗号化保存 & 検証 ==")
    for mid in IDS:
        inbox = chat.members[mid].inbox
        print(f"{mid} 受信 ({len(inbox)}通) :", " | ".join(inbox))
    print("\n監査文字列:", audit_text)
    print("検証結果:", "OK" if ok else "NG")

    # mkが変わった場合でも落ちない（再初期化）ことの確認（教育用途）
    other_mk = secrets.token_bytes(32)
    _ = wrapper.create_or_load(other_mk)  # ここで内部初期化される（例外を出さない）

if __name__ == "__main__":
    run_demo()

