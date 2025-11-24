# encrypt_cert.py
# -*- coding: utf-8 -*-

from pathlib import Path
import os
from Crypto.Cipher import AES

KEY_DIR = Path("certs")
PLAIN_KEY = KEY_DIR / "server.key"
ENCRYPTED_KEY = KEY_DIR / "server.key.enc"
QKD_KEY = KEY_DIR / "qkd_key.bin"

def read_qkd_key() -> bytes:
    if not QKD_KEY.exists():
        raise FileNotFoundError(f"[encrypt] QKD鍵がありません: {QKD_KEY}")
    key = QKD_KEY.read_bytes()
    if len(key) != 32:
        raise ValueError(f"[encrypt] QKD鍵は32バイト必須ですが {len(key)} バイトでした: {QKD_KEY}")
    return key

def main() -> None:
    # 前提チェック
    if not PLAIN_KEY.exists():
        raise FileNotFoundError(f"[encrypt] サーバ秘密鍵が見つかりません: {PLAIN_KEY}")

    key = read_qkd_key()

    # 平文秘密鍵を読み込み
    raw = PLAIN_KEY.read_bytes()

    # AES-GCM で暗号化（nonce 12 bytes）
    nonce = os.urandom(12)
    aes = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ct, tag = aes.encrypt_and_digest(raw)

    # 保存形式: [nonce(12)][ciphertext][tag(16)]
    ENCRYPTED_KEY.write_bytes(nonce + ct + tag)

    # 平文秘密鍵は残しておいてもよいが、実運用では削除推奨
    # PLAIN_KEY.unlink(missing_ok=True)

    try:
        os.chmod(ENCRYPTED_KEY, 0o600)
    except Exception:
        pass

    print(f"[encrypt] 完了: {PLAIN_KEY} -> {ENCRYPTED_KEY}  (nonce={len(nonce)}B, tag=16B, ct={len(ct)}B)")

if __name__ == "__main__":
    main()
