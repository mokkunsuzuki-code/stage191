# -*- coding: utf-8 -*-
from pathlib import Path

def load_key_auto(key_path: str | None = None) -> bytes:
    """
    final_key.bin を次の優先度で探索してロードする：
    1) 引数で渡されたパス
    2) カレントディレクトリの final_key.bin
    3) ../stage83/final_key.bin
    見つからなければ FileNotFoundError
    """
    candidates = []
    if key_path:
        candidates.append(Path(key_path))
    candidates += [Path("final_key.bin"), Path("../stage83/final_key.bin")]
    for p in candidates:
        if p.exists():
            return p.read_bytes()
    raise FileNotFoundError("量子鍵 final_key.bin が見つかりません。stage83 で生成し、"
                            "同じフォルダ or ../stage83 に置いてください。")

def xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR（排他的論理和）：同じ関数で暗号化・復号の両方が可能"""
    k = key
    return bytes(d ^ k[i % len(k)] for i, d in enumerate(data))
