# qkd17_distance.py — 段階17：距離と鍵生成率のシミュレーション

import numpy as np
import math, hashlib
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
import matplotlib.pyplot as plt

SIM = AerSimulator()
rng = np.random.default_rng(0)

# 光ファイバー損失 [dB/km]
LOSS_DB_PER_KM = 0.2
# 検出効率
DETECT_EFF = 0.9

# SHA256プライバシー増幅（簡易）
def privacy_amp_sha256(bits, m):
    if m <= 0 or len(bits) == 0:
        return np.array([], dtype=np.uint8)
    raw = bytes(bits.tolist())
    out = bytearray()
    c = 0
    while len(out)*8 < m:
        out.extend(hashlib.sha256(raw + c.to_bytes(4,"big")).digest())
        c += 1
    bitstr = "".join(f"{b:08b}" for b in out)[:m]
    return np.fromiter((1 if ch=="1" else 0 for ch in bitstr), dtype=np.uint8)

# EPRペア1回の生成＋検出（距離kmを考慮）
def generate_pair(distance_km):
    # 光ファイバー損失確率
    loss_prob = 1 - 10**(-LOSS_DB_PER_KM*distance_km/10)
    if rng.random() < loss_prob: return None
    if rng.random() < loss_prob: return None
    # 検出効率
    if rng.random() > DETECT_EFF: return None
    if rng.random() > DETECT_EFF: return None

    # 理想状態：完全相関（ノイズなし）
    a_bit = rng.integers(0,2)
    b_bit = a_bit
    return a_bit, b_bit

# 距離を変えて平均鍵長を測定
def simulate(distance_list, N=2000):
    results = []
    for d in distance_list:
        key_a, key_b = [], []
        for _ in range(N):
            pair = generate_pair(d)
            if pair is not None:
                a,b = pair
                key_a.append(a); key_b.append(b)
        key_a = np.array(key_a, dtype=np.uint8)
        key_b = np.array(key_b, dtype=np.uint8)

        # QBER
        if len(key_a)>0:
            qber = float(np.mean(key_a ^ key_b))
        else:
            qber = 1.0

        # プライバシー増幅後の鍵長
        m = max(0, len(key_a) - 40)  # safety=40と仮定
        key_a_final = privacy_amp_sha256(key_a, m)
        key_b_final = privacy_amp_sha256(key_b, m)
        equal = np.array_equal(key_a_final, key_b_final)

        results.append((d, len(key_a), m, qber, equal))
        print(f"d={d}km: sifted={len(key_a)}, m={m}, QBER={qber:.2%}, equal={equal}")
    return results

def main():
    distances = list(range(0, 101, 10))  # 0〜100kmを10km刻み
    results = simulate(distances, N=5000)

    xs = [r[0] for r in results]
    ms = [r[2] for r in results]
    qbers = [100*r[3] for r in results]

    plt.figure()
    plt.plot(xs, ms, marker="o")
    plt.xlabel("Distance (km)")
    plt.ylabel("Final key length m")
    plt.title("Distance vs Key length")
    plt.grid()

    plt.figure()
    plt.plot(xs, qbers, marker="o")
    plt.xlabel("Distance (km)")
    plt.ylabel("QBER (%)")
    plt.title("Distance vs QBER")
    plt.grid()
    plt.show()

if __name__ == "__main__":
    main()

