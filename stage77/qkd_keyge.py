# -*- coding: utf-8 -*-
# qkd_keygen.py : QKD用の32バイト鍵を certs/qkd_key.bin に生成

from pathlib import Path
import os

KEY_DIR = Path("certs")
QKD_KEY = KEY_DIR / "qkd_key.bin"

def main() -> None:
    # certs ディレクトリを必ず用意
    KEY_DIR.mkdir(parents=True, exist_ok=True)

    if QKD_KEY.exists():
        print(f"[keygen] already exists: {QKD_KEY}  (何もしません)")
        return

    key = os.urandom(32)  # 32 bytes = 256-bit
    QKD_KEY.write_bytes(key)
    try:
        os.chmod(QKD_KEY, 0o600)  # owner read/write only (macOS可)
    except Exception:
        pass

    print(f"[keygen] generated 32-byte key -> {QKD_KEY}")

if __name__ == "__main__":
    main()
