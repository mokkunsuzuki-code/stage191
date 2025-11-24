import numpy as np
from pathlib import Path

HERE = Path(__file__).resolve().parent
NPZ = HERE / "sifted_keys.npz"
if not NPZ.exists():
    raise FileNotFoundError(f"鍵ファイルが見つかりません: {NPZ}\n先に qkd3.py を実行してください。")


# qkd3.py で保存した鍵を読み込む
data = np.load("sifted_keys.npz")
a_key = data["a_key"].astype(np.uint8)
b_key = data["b_key"].astype(np.uint8)


def parity(arr): return int(np.bitwise_xor.reduce(arr) if len(arr) else 0)

def block_parity_ec(a_key, b_key, block_size=8):
    a, b = a_key.copy(), b_key.copy()
    leakage = 0
    n = len(a)
    for s in range(0, n, block_size):
        e = min(s+block_size, n)
        if parity(a[s:e]) != parity(b[s:e]):
            l, r = s, e
            leakage += 1
            while r-l > 1:
                m = (l+r)//2
                leakage += 1
                if parity(a[l:m]) != parity(b[l:m]): r = m
                else: l = m
            b[l] ^= 1
    return b, leakage

b_corr, leak_ec = block_parity_ec(a_key, b_key, block_size=32)
print("EC後の一致:", np.array_equal(a_key, b_corr), "EC漏洩:", leak_ec)
