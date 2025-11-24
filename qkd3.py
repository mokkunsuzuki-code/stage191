# qkd3.py（完全版：生成→シフティング→QBER→保存）
import numpy as np
from pathlib import Path

rng = np.random.default_rng(1)
N = 1000

# 送信ビットと基底
alice_bits  = rng.integers(0, 2, size=N, dtype=np.uint8)
alice_bases = rng.integers(0, 2, size=N, dtype=np.uint8)
bob_bases   = rng.integers(0, 2, size=N, dtype=np.uint8)

# 伝送路の簡易ノイズ（0/1で反転）
channel_noise = rng.integers(0, 2, size=N, dtype=np.uint8)
received = alice_bits ^ channel_noise

# Bobの測定（基底一致なら受信ビット、違えばランダム）
bob_bits = np.where(alice_bases == bob_bases,
                    received,
                    rng.integers(0, 2, size=N, dtype=np.uint8))

# ---- sifting ----
match = (alice_bases == bob_bases)
idx = np.where(match)[0]
a_sift = alice_bits[idx].copy()
b_sift = bob_bits[idx].copy()

if len(a_sift) == 0:
    print("QBER=NA, sifted=0（基底一致が0件）")
else:
    # ---- QBER推定（20%を検査）----
    k = max(1, int(len(a_sift) * 0.2))
    test_idx = rng.choice(len(a_sift), size=k, replace=False)
    qber = float(np.mean(a_sift[test_idx] ^ b_sift[test_idx]))

    # 検査に使ったビットを除外して鍵に
    mask = np.ones(len(a_sift), dtype=bool)
    mask[test_idx] = False
    a_key = a_sift[mask]
    b_key = b_sift[mask]

    print(f"QBER={qber:.2%}, sifted={len(a_key)}")

    # ---- 保存（★同じスコープで実行する）----
    here = Path(__file__).resolve().parent
    np.savez(here / "sifted_keys.npz", a_key=a_key, b_key=b_key)
    print("saved:", here / "sifted_keys.npz")
