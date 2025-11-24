# decrypt_cert.py
# -*- coding: utf-8 -*-

from pathlib import Path
import os
from Crypto.Cipher import AES

KEY_DIR = Path("certs")
ENCRYPTED_KEY = KEY_DIR / "server.key.enc"
DECRYPTED_TMP = KEY_DIR / "server.key.tmp"   # 一時鍵
QKD_KEY = KEY_DIR / "qkd_key.bin"

def read_qkd_key() -> bytes:
    if not QKD_KEY.exists():
        raise FileNotFoundError(f"[decrypt] QKD鍵がありません: {QKD_KEY}")
    key = QKD_KEY.read_bytes()
    if len(key) != 32:
        raise ValueError(f"[decrypt] QKD鍵は32バイト必須ですが {len(key)} バイトでした: {QKD_KEY}")
    return key

def decrypt_to_file() -> str:
    if not ENCRYPTED_KEY.exists():
        raise FileNotFoundError(f"[decrypt] 暗号化鍵が見つかりません: {ENCRYPTED_KEY}")

    key = read_qkd_key()
    raw = ENCRYPTED_KEY.read_bytes()
    if len(raw) < (12 + 16):
        raise ValueError("[decrypt] 暗号化ファイルのサイズが不正です（短すぎます）")

    nonce = raw[:12]
    tag = raw[-16:]
    ct = raw[12:-16]

    aes = AES.new(key, AES.MODE_GCM, nonce=nonce)
    dec = aes.decrypt_and_verify(ct, tag)

    DECRYPTED_TMP.write_bytes(dec)
    try:
        os.chmod(DECRYPTED_TMP, 0o600)
    except Exception:
        pass

    print(f"[decrypt] 復号完了: 一時鍵 -> {DECRYPTED_TMP}")
    return str(DECRYPTED_TMP)

if __name__ == "__main__":
    decrypt_to_file()
