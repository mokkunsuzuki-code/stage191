# qkd35.py
# 段階35：高速&安定版（NumPy高速モード + Qiskit厳密モードの両対応）
# - 目的：E91/BB84風の誤り率・CHSH・統計区間から、教育用の鍵長見積もり
# - 速い：FAST=True だと NumPy だけで数秒以内に完了
# - 厳密：FAST=False にすると Qiskit を用いたサンプル生成（注意：時間がかかる）

from __future__ import annotations
import math
import numpy as np

# ====== 設定 ======
FAST = True            # True: NumPyだけで高速に; False: Qiskitで厳密サンプルを生成
SHOW_PLOT = False      # True: グラフ表示（ブロッキング）; False: 何も表示しない

# サンプル数（FASTで十分小さく、必要なら増やす）
N_PAIRS_TOTAL = 200_000      # 総ペア数
TEST_FRACTION = 0.2          # CHSH等のテストに割く比率（鍵に回るのは 1-TEST_FRACTION）

# 物理パラメータ（教育用）
QBER_TRUE     = 0.03         # 実際の誤り率（誤りビットの確率）
LEAK_EC       = 0.05         # 誤り訂正で公開される情報量 [bits/bit] の代表値（教育用）
SAFETY_BITS   = 40           # 安全余裕（プライバシー増幅で削る固定分）

# 乱数
SEED = 35

# ====== ユーティリティ ======
def h2(p: float) -> float:
    p = min(max(p, 1e-12), 1 - 1e-12)
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))

def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """
    Wilsonの二項信頼区間（正規近似より安定）
    参考: https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval
    """
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    # 正規分位（z_{1-alpha/2}）。SciPyなしの近似：1.96 でOK（95%）
    z = 1.959963984540054
    den = 1 + z*z/n
    center = (p + z*z/(2*n)) / den
    half = (z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / den
    lo, hi = center - half, center + half
    return (max(0.0, lo), min(1.0, hi))

def clopper_pearson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """
    SciPy があれば Clopper-Pearson（正確区間）を使い、無ければ Wilson にフォールバック。
    """
    try:
        from scipy.stats import beta
        if n == 0:
            return (0.0, 1.0)
        a = k + 1
        b = (n - k) + 1
        lo = beta.ppf(alpha/2,      a, b) if k > 0   else 0.0
        hi = beta.ppf(1 - alpha/2,  a, b) if k < n   else 1.0
        return (float(lo), float(hi))
    except Exception:
        return wilson_ci(k, n, alpha)

def devetak_winter_key_bits(m_key: int, qber_hat: float, leak_ec_per_bit: float, safety_bits: int) -> int:
    """
    教育用の簡易鍵長：m_key * max(0, 1 - 2 h2(Q)) - m_key * leak_EC - safety
    """
    r_single = max(0.0, 1.0 - 2.0 * h2(qber_hat))
    est = m_key * r_single - m_key * leak_ec_per_bit - safety_bits
    return int(max(0, math.floor(est)))

# ====== サンプル生成（高速: NumPy / 厳密: Qiskit） ======
def generate_samples_numpy(n_pairs: int, qber: float, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """
    0/1 のビット列 A, B を生成。誤り確率 qber で A != B にする単純モデル。
    """
    A = rng.integers(0, 2, size=n_pairs, dtype=np.uint8)
    flips = (rng.random(n_pairs) < qber).astype(np.uint8)
    B = A ^ flips
    return A, B

def generate_samples_qiskit(n_pairs: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """
    EPR生成 + 測定を Qiskit でモデル化（遅いのでデモ用）。
    transpile 一括 & run 一括で高速化。
    """
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator

    sim = AerSimulator(method="stabilizer")  # EPR/パウリ測定なら高速
    circs = []
    for _ in range(n_pairs):
        qc = QuantumCircuit(2, 2)
        # EPR（ベル状態）
        qc.h(0); qc.cx(0, 1)
        # 誤りを確率的に入れる（Xフリップ）
        if rng.random() < QBER_TRUE:
            qc.x(1)
        qc.measure([0, 1], [0, 1])
        circs.append(qc)

    tcircs = transpile(circs, sim, optimization_level=0)
    res = sim.run(tcircs, shots=1).result()
    A = np.empty(n_pairs, dtype=np.uint8)
    B = np.empty(n_pairs, dtype=np.uint8)
    for i in range(n_pairs):
        c = res.get_counts(i)
        # 例: {'00': 1} or {'11':1} など
        bitstr = next(iter(c.keys()))
        A[i] = int(bitstr[-1])      # qiskit の順序に合わせる（clbit index）
        B[i] = int(bitstr[-2])
    return A, B

# ====== メイン ======
def main():
    rng = np.random.default_rng(SEED)

    # サンプル生成
    if FAST:
        A, B = generate_samples_numpy(N_PAIRS_TOTAL, QBER_TRUE, rng)
    else:
        print("[INFO] Qiskit厳密モードで回します（時間がかかります）")
        A, B = generate_samples_qiskit(N_PAIRS_TOTAL, rng)

    # テスト/鍵に分割
    n_test = int(N_PAIRS_TOTAL * TEST_FRACTION)
    n_key  = N_PAIRS_TOTAL - n_test

    A_test, B_test = A[:n_test], B[:n_test]
    A_key,  B_key  = A[n_test:], B[n_test:]

    # QBER 推定（テスト部）
    errors = np.count_nonzero(A_test ^ B_test)
    q_lo, q_hi = clopper_pearson_ci(errors, n_test, alpha=0.05)
    q_hat = errors / n_test if n_test > 0 else 0.0

    # 教育用 CHSH 近似：S ≈ 2√2 * (1 - 2Q)
    S_hat = 2.0 * math.sqrt(2.0) * max(0.0, (1.0 - 2.0 * q_hat))

    # 鍵長見積
    key_bits = devetak_winter_key_bits(
        m_key=n_key,
        qber_hat=q_hat,
        leak_ec_per_bit=LEAK_EC,
        safety_bits=SAFETY_BITS,
    )

    # ===== レポート =====
    print("\n=== 段階35 レポート（高速版）===")
    print(f"総ペア数         : {N_PAIRS_TOTAL:,}")
    print(f"テスト / 鍵      : {n_test:,} / {n_key:,}")
    print(f"QBER 推定        : {q_hat:.3%}  (95% CI: {q_lo:.3%} .. {q_hi:.3%})")
    print(f"CHSH 期待 S_hat  : {S_hat:.3f}  （>2 でベル不等式違反）")
    print(f"ECリーク/bit     : {LEAK_EC:.3f}  | 安全余裕: {SAFETY_BITS} bits")
    print(f"推定 鍵長        : {key_bits:,} bits")

    # ===== 任意の簡易可視化 =====
    if SHOW_PLOT:
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
        # 日本語フォント（Mac/Win共通のフォールバック）
        for fam in ["Hiragino Sans", "Yu Gothic", "Meiryo", "IPAexGothic"]:
            try:
                rcParams["font.family"] = fam; break
            except Exception:
                pass
        rcParams["axes.unicode_minus"] = False

        labels = ["QBER下限", "QBER推定", "QBER上限"]
        vals   = [q_lo*100, q_hat*100, q_hi*100]
        plt.figure(figsize=(6,4))
        plt.bar(labels, vals)
        plt.ylabel("QBER [%]")
        plt.title("QBERの95%信頼区間（Wilson/Clopper-Pearson）")
        plt.grid(True, axis="y", alpha=0.3)
        plt.show()

if __name__ == "__main__":
    main()

