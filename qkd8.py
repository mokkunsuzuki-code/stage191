# qkd8_sweep.py  —  段階8：flip_noise を変えて QBER と 最終鍵長 m を可視化
# 使い方:
#   1) 必要なら: pip install matplotlib
#   2) python qkd8_sweep.py
#
# 何をする？
#   ・BB84 →（擬似ノイズ）→ Sifting → QBER推定 → 教育用EC → SHA-256によるプライバシー増幅
#   ・flip_noise を 0%〜15% まで変えて、平均 QBER と 平均 m（最終鍵長）を記録・グラフ化
#   ・試行回数 trials で平均化（デフォルト5回）

import numpy as np
import math, hashlib, csv, os

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# ====== グラフ用（matplotlib が無い環境でも動くように try/except） ======
try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
    print("[INFO] matplotlib が見つかりません。表とCSVは出力します（グラフはスキップ）。")
    print("       インストールするには:  pip install matplotlib")


# ====== ユーティリティ ======
def parity(arr: np.ndarray) -> int:
    return int(np.bitwise_xor.reduce(arr) if len(arr) else 0)

def block_parity_ec(a_key: np.ndarray, b_key: np.ndarray, block_size: int = 8):
    """
    教育用・簡易誤り訂正：
    各ブロックのパリティが違えば二分探索で“1bitだけ”修正。
    漏洩量は公開パリティ回数（ざっくり1bit/回）でカウント。
    """
    a = a_key.copy()
    b = b_key.copy()
    leakage = 0
    n = len(a)
    for s in range(0, n, block_size):
        e = min(s + block_size, n)
        if parity(a[s:e]) != parity(b[s:e]):
            l, r = s, e
            leakage += 1
            while r - l > 1:
                m = (l + r) // 2
                leakage += 1
                if parity(a[l:m]) != parity(b[l:m]):
                    r = m
                else:
                    l = m
            b[l] ^= 1
    return b, leakage

def privacy_amp_sha256(bits: np.ndarray, m: int) -> np.ndarray:
    """
    教育用プライバシー増幅（簡易）：
    入力 bits(np.uint8; 0/1) を SHA-256 連結で mビットに短縮。
    """
    if m <= 0 or len(bits) == 0:
        return np.array([], dtype=np.uint8)
    raw = bytes(bits.tolist())
    out = bytearray()
    counter = 0
    while len(out) * 8 < m:
        out.extend(hashlib.sha256(raw + counter.to_bytes(4, "big")).digest())
        counter += 1
    bitstr = "".join(f"{b:08b}" for b in out)[:m]
    return np.fromiter((1 if c == "1" else 0 for c in bitstr), dtype=np.uint8)


# ====== 1回分の実験 ======
def run_once(n=800, flip_noise=0.0, seed=0, test_frac=0.20, block_size=8, eps_sec=1e-6):
    rng = np.random.default_rng(seed)

    # 送信ビット & 基底（0=Z, 1=X）
    alice_bits  = rng.integers(0, 2, size=n, dtype=np.uint8)
    alice_basis = rng.integers(0, 2, size=n, dtype=np.uint8)
    bob_basis   = rng.integers(0, 2, size=n, dtype=np.uint8)

    # 送受信
    circs = []
    for b, ba, bb in zip(alice_bits, alice_basis, bob_basis):
        qc = QuantumCircuit(1, 1)
        if b == 1:  qc.x(0)   # まずビット
        if ba == 1: qc.h(0)   # アリス基底
        if bb == 1: qc.h(0)   # 測定基底
        qc.measure(0, 0)
        circs.append(qc)

    sim = AerSimulator()
    res = sim.run(transpile(circs, sim), shots=1).result()
    bob_bits = np.array([1 if res.get_counts(i).get("1", 0) else 0 for i in range(n)], dtype=np.uint8)

    # 擬似ノイズ（Bobの測定結果に反転を注入）
    if flip_noise > 0:
        flips = rng.random(len(bob_bits)) < flip_noise
        bob_bits ^= flips.astype(np.uint8)

    # Sifting（基底一致のみ抽出）
    match = (alice_basis == bob_basis)
    idx = np.where(match)[0]
    a_sift = alice_bits[idx]
    b_sift = bob_bits[idx]

    # QBER推定（検査 test_frac を公開）
    if len(a_sift) == 0:
        return 0.0, 0, 0, True  # 何も一致しなかった場合（ほぼ起きない）

    k = max(1, int(len(a_sift) * test_frac))
    rng2 = np.random.default_rng(1)
    test_idx = rng2.choice(len(a_sift), size=k, replace=False)
    qber = float(np.mean(a_sift[test_idx] ^ b_sift[test_idx]))

    # 検査に使ったビットは除外
    mask = np.ones(len(a_sift), dtype=bool)
    mask[test_idx] = False
    a_key = a_sift[mask]
    b_key = b_sift[mask]

    # 教育用・誤り訂正
    b_corr, leak_ec = block_parity_ec(a_key, b_key, block_size=block_size)

    # プライバシー増幅（検査後の長さをベースに）
    safety = int(math.ceil(2 * math.log2(1 / eps_sec)))
    m = max(0, len(a_key) - leak_ec - safety)

    a_final = privacy_amp_sha256(a_key, m)
    b_final = privacy_amp_sha256(b_corr, m)
    equal = bool(np.array_equal(a_final, b_final))

    return qber, int(len(a_sift)), int(m), equal


# ====== スイープ実験（0%〜15%） ======
def main():
    noises = [i / 100 for i in range(0, 16)]  # 0%〜15%（1%刻み）
    trials = 5                                 # 平均化のための試行回数

    results = []  # (noise_pct, avg_qber, avg_m, success_rate, avg_sifted)

    print("noise(%) | QBER(%) | m(avg) | success(%) | sifted(avg)")
    print("---------+---------+--------+------------+------------")

    for p in noises:
        q_list, m_list, ok_list, s_list = [], [], [], []

        # 複数シードで平均
        for t in range(trials):
            q, sifted, m, equal = run_once(
                n=800, flip_noise=p, seed=100 + t, test_frac=0.20, block_size=8, eps_sec=1e-6
            )
            q_list.append(q)
            m_list.append(m)
            ok_list.append(1 if equal else 0)
            s_list.append(sifted)

        avg_q = 100 * float(np.mean(q_list))            # %
        avg_m = int(np.mean(m_list))
        succ  = 100 * float(np.mean(ok_list))           # %
        avg_s = int(np.mean(s_list))

        results.append((p * 100, avg_q, avg_m, succ, avg_s))
        print(f"{p*100:7.1f} | {avg_q:7.2f} | {avg_m:6d} | {succ:10.1f} | {avg_s:10d}")

    # CSV保存
    csv_path = "qkd8_sweep_results.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flip_noise_%", "avg_QBER_%", "avg_final_key_m", "success_%", "avg_sifted"])
        w.writerows(results)
    print(f"\n[保存] 結果CSV: {os.path.abspath(csv_path)}")

    # グラフ
    if HAS_MPL:
        xs = [r[0] for r in results]
        qy = [r[1] for r in results]
        my = [r[2] for r in results]
        sy = [r[3] for r in results]

        # QBER
        plt.figure()
        plt.plot(xs, qy, marker="o")
        plt.xlabel("Flip noise (%)")
        plt.ylabel("QBER (%)")
        plt.title("Noise vs QBER")
        plt.grid(True)

        # 最終鍵長 m
        plt.figure()
        plt.plot(xs, my, marker="o")
        plt.xlabel("Flip noise (%)")
        plt.ylabel("Final key length m (avg)")
        plt.title("Noise vs Final key length")
        plt.grid(True)

        # 成功率（equal==True の割合）
        plt.figure()
        plt.plot(xs, sy, marker="o")
        plt.xlabel("Flip noise (%)")
        plt.ylabel("Equal(success) (%)")
        plt.title("Noise vs Success rate (keys equal)")
        plt.grid(True)

        # 画像保存 + 画面表示
        plt.tight_layout()
        plt.savefig("qkd8_sweep_plots.png")  # まとめて1枚に保存（上書きOK）
        print(f"[保存] グラフ画像: {os.path.abspath('qkd8_sweep_plots.png')}")
        plt.show()


if __name__ == "__main__":
    main()
