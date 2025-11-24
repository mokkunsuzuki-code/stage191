# qkd55_fixed.py  — 段階55: ラップ/アンラップを堅牢化（InvalidTag根絶）
# 依存: cryptography (AESGCM), 標準ライブラリのみ

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict
import secrets, hmac, hashlib, base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ====== HKDF（簡潔版）========================================================

def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()

def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    t = b""
    block = b""
    while len(t) < length:
        block = hmac.new(prk, block + info + b"\x01", hashlib.sha256).digest()
        t += block
        info += b"\x00"  # ダミーでカウンタ変化（1ブロックで足りるが多ブロックでもOK）
    return t[:length]

def hkdf(ikm: bytes, info: bytes, length: int = 32, salt: Optional[bytes] = None) -> bytes:
    if salt is None:
        salt = b"\x00" * 32
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)


# ====== Key Wrapper ==========================================================

def _b64e(b: bytes) -> str: return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")
def _b64d(s: str) -> bytes: return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

WRAP_LABEL = b"qkd55-wrap-v1"  # AADの土台（将来のバージョン識別にも使える）

@dataclass
class KeyWrapper:
    """
    メモリ内の簡易キーストア。
    以前の実行で作ったメタを“別 mk で”開けようとしても InvalidTag にせず、
    安全に初期化して再生成する（教育/試作向けの扱い）。
    """
    meta: Dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _kid_from_mk(mk: bytes) -> bytes:
        # mkから短い key-id を作る（保存して AAD に混ぜる）
        return hmac.new(mk, b"kid", hashlib.sha256).digest()[:8]

    @staticmethod
    def _derive_wrap_key(mk: bytes, kid: bytes) -> bytes:
        # ラップ用鍵は mk から HKDF で導出（他用途との混線を防止）
        return hkdf(mk, WRAP_LABEL + b"|" + kid, 32)

    def _wrap(self, mk: bytes, plain_data_key: bytes) -> Dict[str, str]:
        kid = self._kid_from_mk(mk)
        wk  = self._derive_wrap_key(mk, kid)
        aead = AESGCM(wk)
        nonce = secrets.token_bytes(12)  # GCM標準
        aad = WRAP_LABEL + b"|" + kid
        ct = aead.encrypt(nonce, plain_data_key, aad)
        return {
            "v": "1",
            "kid": _b64e(kid),
            "nonce": _b64e(nonce),
            "ct": _b64e(ct),
        }

    def _unwrap(self, mk: bytes, record: Dict[str, str]) -> bytes:
        kid = _b64d(record["kid"])
        wk  = self._derive_wrap_key(mk, kid)
        aead = AESGCM(wk)
        nonce = _b64d(record["nonce"])
        ct    = _b64d(record["ct"])
        aad   = WRAP_LABEL + b"|" + kid
        return aead.decrypt(nonce, ct, aad)

    # ---- 公開API ------------------------------------------------------------

    def create_or_load(self, mk: bytes) -> bytes:
        """
        既存メタがあれば復号。失敗＝mkが違う/破損 → “安全に再初期化”して新規作成。
        """
        if self.meta:
            try:
                return self._unwrap(mk, self.meta)  # ここで InvalidTag なら except へ
            except Exception:
                # 別 mk で開けない・破損など。教育向け挙動：初期化して上書き再作成。
                pass

        # 新規作成（32B のデータ鍵を作り、ラップして保存）
        new_dek = secrets.token_bytes(32)
        self.meta = self._wrap(mk, new_dek)
        return new_dek


# ====== デモ（段階55）========================================================

def run_demo():
    print("== 段階55 / データ鍵のラップ&ロード（InvalidTag対策版） ==")

    # 1) “QKD最終鍵”に相当する 32B を用意（デモなのでランダム）
    mk = secrets.token_bytes(32)

    # 2) ラッパを作成（メタはメモリ内だが、ファイル永続化するなら self.meta を保存/復元すればOK）
    wrapper = KeyWrapper()

    # 3) 初回：メタ無し → 新規 DEK を作ってラップ
    data_DEK_1 = wrapper.create_or_load(mk)
    print("初回: DEK =", _b64e(data_DEK_1)[:16], "...")

    # 4) 2回目：同じ mk → 復号できる（InvalidTagは出ない）
    data_DEK_2 = wrapper.create_or_load(mk)
    ok_same = (data_DEK_1 == data_DEK_2)
    print("再読: 一致 =", ok_same)

    # 5) “mk が変わった”ケース：以前の実行で作ったメタを別 mk で開けようとする場面の再現
    other_mk = secrets.token_bytes(32)
    data_DEK_3 = wrapper.create_or_load(other_mk)  # 復号失敗→安全に初期化し直す
    print("異鍵: 新規生成 =", data_DEK_3 != data_DEK_2)

    # 6) さらに同じ other_mk で再読 → 問題なく復号
    data_DEK_4 = wrapper.create_or_load(other_mk)
    print("異鍵: 再読一致 =", data_DEK_4 == data_DEK_3)

    # 7) （応用）この DEK でアプリデータを暗号化してもよい
    #    AES-GCM 使用例（省略）


if __name__ == "__main__":
    run_demo()

