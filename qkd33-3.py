# e91_stage33_compare.py
# 同一条件で「絶対効率（段階33）」と「相対効率（段階33-2）」を同時表示する教育用コード
# Author: ChatGPT（教育用モデル）

import numpy as np
import math
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# =========================
# 表示用（日本語フォント）
# =========================
try:
    plt.rcParams['font.family'] = 'Hiragino Sans'  # mac の標準
except Exception:
    pass
plt.rcParams['axes.unicode_minus'] = False

# =========================
# 教育モデルのパラメータ（同一条件で固定）
# =========================
SEED = 42
rng = np.random.default_rng(SEED)

N_PAIRS = 6000        # 総EPRペア数（テスト＋鍵）
NOISE_P_FLIP = 0.0    # 量子ビット反転ノイズ（教育用：0〜0.05くらいで試せる）

# CHSH最適角度（E91）
a0 = 0.0
a1 = np.pi/4
b0 = np.pi/8
b1 = -np.pi/8

# キー用測定角度（同方向）
theta_key_a = 0.0
theta_key_b = 0.0

# 教育用の“合格度”係数パラメータ
S_CLASSICAL = 2.0
S_QUANTUM_MAX = 2.0 * np.sqrt(2)  # ≈ 2.828
# S の点推定を [2, 2√2] で 0〜1 に線形正規化
def chsh_confidence(S):
    S_clamped = max(S_CLASSICAL, min(S, S_QUANTUM_MAX))
    return (S_clamped - S_CLASSICAL) / (S_QUANTUM_MAX - S_CLASSICAL)

# 2値エントロピー h2
def h2(p):
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p*math.log2(p) - (1-p)*math.log2(1-p)

# 1回のEPR測定（教育用：Y軸周り回転→Z測定、簡易ノイズ付き）
sim = AerSimulator()

def epr_once(theta_a: float, theta_b: float, p_flip: float = 0.0) -> tuple[int, int]:
    qc = QuantumCircuit(2, 2)
    # |Φ+> を生成
    qc.h(0)
    qc.cx(0, 1)
    # 測定基底回転
    if theta_a != 0.0:
        qc.ry(-2*theta_a, 0)
    if theta_b != 0.0:
        qc.ry(-2*theta_b, 1)
    # （教育用）古典側でビットフリップ雑音を近似注入
    # 実機ではチャンネル/ゲートノイズで表すが、ここでは簡便のため測定後に反転
    qc.measure(0, 0)
    qc.measure(1, 1)

    tqc = transpile(qc, sim, optimization_level=0)
    result = sim.run(tqc, shots=1, memory=True).result()
    mem = result.get_memory()[0]  # 'ab' where a=q0, b=q1
    a = int(mem[0])
    b = int(mem[1])

    # 簡略ノイズ：独立なビット反転
    if p_flip > 0.0:
        if rng.random() < p_flip:
            a ^= 1
        if rng.random() < p_flip:
            b ^= 1

    return a, b

# CHSH用バケット
def corr_bucket():
    return {"n00":0, "n01":0, "n10":0, "n11":0, "N":0}

def E_from_bucket(b):
    if b["N"] == 0:
        return np.nan
    return (b["n00"] + b["n11"] - b["n01"] - b["n10"]) / b["N"]

# 教育用“絶対効率”の計算
# 直感： (鍵に回せた割合) × (CHSHの合格度) × (1 - h2(QBER)) を掛け合わせる簡略式
def compute_absolute_efficiency(N_pairs, key_len, qber, S):
    if N_pairs == 0:
        return 0.0
    frac_key = key_len / N_pairs
    conf = chsh_confidence(S)     # 0〜1
    privacy = max(0.0, 1.0 - h2(qber))  # 0〜1
    return 100.0 * frac_key * conf * privacy  # [%]

# 指定 key_fraction で1回の実験（同一条件）
def run_once(key_fraction: float):
    bucket_map = {
        0: (a0, b0),
        1: (a0, b1),
        2: (a1, b0),
        3: (a1, b1),
    }
    b_a0b0 = corr_bucket()
    b_a0b1 = corr_bucket()
    b_a1b0 = corr_bucket()
    b_a1b1 = corr_bucket()
    buckets = [b_a0b0, b_a0b1, b_a1b0, b_a1b1]

    key_a = []
    key_b = []

    for _ in range(N_PAIRS):
        is_key = (rng.random() < key_fraction)
        if is_key:
            a_bit, b_bit = epr_once(theta_key_a, theta_key_b, NOISE_P_FLIP)
            key_a.append(a_bit)
            key_b.append(b_bit)
        else:
            idx = rng.integers(0, 4)
            th_a, th_b = bucket_map[idx]
            a_bit, b_bit = epr_once(th_a, th_b, NOISE_P_FLIP)
            ba = buckets[idx]
            if   a_bit == 0 and b_bit == 0: ba["n00"] += 1
            elif a_bit == 0 and b_bit == 1: ba["n01"] += 1
            elif a_bit == 1 and b_bit == 0: ba["n10"] += 1
            else:                           ba["n11"] += 1
            ba["N"] += 1

    # CHSH 点推定
    E_a0b0 = E_from_bucket(b_a0b0)
    E_a0b1 = E_from_bucket(b_a0b1)
    E_a1b0 = E_from_bucket(b_a1b0)
    E_a1b1 = E_from_bucket(b_a1b1)
    S = E_a0b0 + E_a0b1 + E_a1b0 - E_a1b1

    key_a = np.array(key_a, dtype=int)
    key_b = np.array(key_b, dtype=int)
    key_len = len(key_a)
    if key_len > 0:
        qber = 1.0 - np.mean(key_a == key_b)  # 誤り率
    else:
        qber = 0.5

    abs_eff = compute_absolute_efficiency(N_PAIRS, key_len, qber, S)  # [%]
    return {
        "S": S,
        "qber": qber,
        "key_len": key_len,
        "abs_eff": abs_eff,   # 段階33の“絶対効率”
    }

# =========================
# スイープとプロット
# =========================
def main():
    # 同一条件で key_fraction を同じ列で評価
    key_fracs = np.linspace(0.2, 0.8, 13)  # 0.2〜0.8 を 0.05刻みに近い間隔で
    results = []
    # 乱数の再現性のため、各fごとにサブseedを派生
    for i, f in enumerate(key_fracs):
        # サブシード固定（同一性の担保）
        global rng
        rng = np.random.default_rng(SEED + i*1000)
        r = run_once(f)
        r["f"] = f
        results.append(r)

    f_list = np.array([r["f"] for r in results])
    abs_eff = np.array([r["abs_eff"] for r in results])  # 段階33：絶対効率 [%]

    # 段階33-2：相対効率（同じ配列を最大値で正規化して100%表示）
    max_abs = abs_eff.max() if abs_eff.size > 0 else 1.0
    rel_eff = 100.0 * abs_eff / max_abs

    # 最良点
    best_idx = int(np.argmax(abs_eff))
    f_best = f_list[best_idx]
    abs_best = abs_eff[best_idx]
    rel_best = rel_eff[best_idx]  # == 100

    # 任意の比較点（スクショに合わせて）
    mark_f1 = 0.30
    mark_f2 = 0.65
    def interp(xarr, yarr, x):
        # 簡易補間（最も近い点）
        j = np.argmin(np.abs(xarr - x))
        return yarr[j], xarr[j]  # y, 実際に使われたf

    abs_m1, f1 = interp(f_list, abs_eff, mark_f1)
    abs_m2, f2 = interp(f_list, abs_eff, mark_f2)
    rel_m1, _ = interp(f_list, rel_eff, mark_f1)
    rel_m2, _ = interp(f_list, rel_eff, mark_f2)

    # ========= 図の作成（同時表示：左=絶対効率, 右=相対効率） =========
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=120)
    ax1, ax2 = axes

    # --- 左：段階33（絶対効率） ---
    ax1.plot(f_list, abs_eff, marker='o')
    ax1.set_title("段階33：安全に残せる鍵効率（絶対値, 教育用モデル）")
    ax1.set_xlabel("鍵に回す割合 (key_fraction)")
    ax1.set_ylabel("安全に残せる鍵効率（%）")
    ax1.grid(True, alpha=0.3)

    # ベスト印
    ax1.scatter([f_best], [abs_best], s=120, marker='*')
    ax1.annotate(f"最良: f={f_best:.2f}\n効率={abs_best:.1f}%",
                 (f_best, abs_best),
                 textcoords="offset points", xytext=(8, 8))

    # 比較点（f=0.30, 0.65）
    ax1.scatter([f1], [abs_m1], marker='x', s=90)
    ax1.annotate(f"f≈0.30\n{abs_m1:.1f}%",
                 (f1, abs_m1), textcoords="offset points", xytext=(8, -18))
    ax1.scatter([f2], [abs_m2], marker='x', s=90)
    ax1.annotate(f"f≈0.65\n{abs_m2:.1f}%",
                 (f2, abs_m2), textcoords="offset points", xytext=(8, -18))

    # --- 右：段階33-2（相対効率） ---
    ax2.plot(f_list, rel_eff, marker='o')
    ax2.set_title("段階33-2：安全に残せる鍵効率（相対, ベスト=100%）")
    ax2.set_xlabel("鍵に回す割合 (key_fraction)")
    ax2.set_ylabel("相対効率（%）")
    ax2.grid(True, alpha=0.3)

    ax2.scatter([f_best], [rel_best], s=120, marker='*')
    ax2.annotate(f"最良: f={f_best:.2f}\n100.0%",
                 (f_best, rel_best), textcoords="offset points", xytext=(8, 8))

    ax2.scatter([f1], [rel_m1], marker='x', s=90)
    ax2.annotate(f"f≈0.30\n{rel_m1:.1f}%",
                 (f1, rel_m1), textcoords="offset points", xytext=(8, -18))
    ax2.scatter([f2], [rel_m2], marker='x', s=90)
    ax2.annotate(f"f≈0.65\n{rel_m2:.1f}%",
                 (f2, rel_m2), textcoords="offset points", xytext=(8, -18))

    plt.suptitle("同一条件での比較：段階33（絶対）と 段階33-2（相対）", y=1.02, fontsize=12)
    plt.tight_layout()
    plt.show()

    # 参考出力
    print("=== 実験条件（共通） ===")
    print(f"N_PAIRS={N_PAIRS}, NOISE_P_FLIP={NOISE_P_FLIP}, SEED={SEED}")
    print("角度: a0=0, a1=π/4, b0=π/8, b1=−π/8（E91標準）")
    print("\n=== ベスト点（絶対効率で定義） ===")
    print(f"f_best={f_best:.2f}, 絶対効率={abs_best:.2f}%, 相対=100%")

if __name__ == "__main__":
    main()

