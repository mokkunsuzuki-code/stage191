# -*- coding: utf-8 -*-
"""
共通関数（暗号化・復号と鍵のロード）
"""
from pathlib import Path

def load_key_auto() -> bytes:
    """final_key.bin を探してロード"""
    candidates = [Path("final_key.bin"), Path("../stage83/final_key.bin")]
    for p in candidates:
        if p.exists():
            return p.read_bytes()
    raise FileNotFoundError("final_key.bin が見つかりません")

def xor_bytes(data: bytes, key: bytes) -> bytes:
    """排他的論理和で暗号化／復号"""
    return bytes(d ^ key[i % len(key)] for i, d in enumerate(data))
