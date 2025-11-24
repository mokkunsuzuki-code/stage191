# e91_key_fraction_tradeoff_demo.py
# ---------------------------------------------------------
# E91（Ekert91）鍵生成の「鍵に回す割合 key_fraction」と
# 「安全に残せる鍵効率（相対値 %）」のトレードオフを可視化する教育用コード。
# - CHSH: a0=0, a1=π/4, b0=π/8, b1=-π/8（理想で S=2√2）
# - 統計誤差: 2値(±1)平均 E の分散 ≈ (1-E^2)/N を用いたガウス近似
# - 安全判定: S_LB = S - z * sqrt(var(S)) が 2 を超えなければ鍵は 0
# - 鍵効率: key_fraction * ((S_LB-2)/(2√2-2)) を 0〜1 にクリップ
# - 相対表示: 最大値で割って 0〜100(%) に正規化して表示
# ---------------------------------------------------------

import numpy as np
import math
import matplotlib.pyplot as plt

# 乱数
rng = np.random.default_rng(42)

# 総EPRペア数（サンプル数が多いほどテストが安定→高い key_fraction でも耐える）
N_pairs = 4000

# CHSH 最適角
a0 = 0.0
a1 = np.pi/4
b0 = np.pi/8
b1 = -np.pi/8
S_max = 2*math.sqrt(2)

# 教育用ノイズ（0で理想）。小さく入れるとSが少し下がる
flip_noise = 0.0  # 0〜0.05 くらいまでで遊べる

# 信頼係数 z（99% ≈ 2.58, 95% ≈ 1.96）。厳しくするほどテスト用サンプルが必要。
z_score = 2.58  # 99%

# θ差から「同一結果の確率」を与える（理想EPRの偏光モデル）
# P(same) = 0.5*(1 + cos(2Δθ))。ノイズは同/異をランダム反転。
def sample_same_diff(N, theta_a, theta_b, rng):
    delta = theta_a - theta_b
    p_same_ideal = 0.5*(1 + math.cos(2*delta))
    # ノイズでフリップ
    # 実効 p_same = (1 - flip_noise)*p_same_ideal + flip_noise*(1 - p_same_ideal)
    p_same = (1 - flip_noise)*p_same_ideal + flip_noise*(1 - p_same_ideal)
    n_same = rng.binomial(N, p_same)
    n_diff = N - n_same
    return n_same, n_diff

# E と 分散近似（±1 変数の平均）
def est_E_and_var(n_same, n_diff):
    N = n_same + n_diff
    if N == 0:
        return np.nan, np.nan
    E_hat = (n_same - n_diff) / N
    var = (1 - E_hat**2) / max(N, 1)  # ガウス近似
    return E_hat, var

# CHSH をテスト分割で推定
def chsh_test(n_test, rng):
    # 4組 (a0,b0),(a0,b1),(a1,b0),(a1,b1) をほぼ均等に割る
    N_each = [n_test//4]*4
    for i in range(n_test % 4):
        N_each[i] += 1

    settings = [(a0,b0), (a0,b1), (a1,b0), (a1,b1)]
    Es = []
    Vars = []
    for N, (ta, tb) in zip(N_each, settings):
        n_same, n_diff = sample_same_diff(N, ta, tb, rng)
        E_hat, var = est_E_and_var(n_same, n_diff)
        Es.append(E_hat)
        Vars.append(var)

    # CHSH S = E00 + E01 + E10 - E11
    S_hat = Es[0] + Es[1] + Es[2] - Es[3]
    var_S = Vars[0] + Vars[1] + Vars[2] + Vars[3]  # 相関の和の分散（独立近似）
    S_LB = S_hat - z_score*math.sqrt(max(var_S, 0.0))
    return S_hat, S_LB

# 教育用の鍵効率（0〜1）: S_LB<=2 なら 0、超えれば (S_LB-2)/(S_max-2) に比例
def secure_key_efficiency_frac(key_fraction, S_LB):
    if np.isnan(S_LB) or S_LB <= 2.0:
        return 0.0
    strength = (S_LB - 2.0) / (S_max - 2.0)
    strength = float(np.clip(strength, 0.0, 1.0))
    return key_fraction * strength

# 走査
fractions = np.linspace(0.20, 0.80, 17)  # 0.20, 0.23, ..., 0.80
raw_eff = []
S_vals = []
S_LBs = []
for f in fractions:
    n_key  = int(round(N_pairs * f))
    n_test = max(0, N_pairs - n_key)

    S_hat, S_LB = chsh_test(n_test, rng)
    e = secure_key_efficiency_frac(f, S_LB)

    raw_eff.append(e)
    S_vals.append(S_hat)
    S_LBs.append(S_LB)

raw_eff = np.array(raw_eff, dtype=float)

# 相対化（最大を100%）
if raw_eff.max() > 0:
    rel_eff = 100.0 * raw_eff / raw_eff.max()
else:
    rel_eff = np.zeros_like(raw_eff)

# 最適点
best_idx = int(np.argmax(rel_eff))
best_f = float(fractions[best_idx])
best_rel = float(rel_eff[best_idx])

# 個別に 0.30 と 0.65 を評価
def evaluate_at(f_target):
    n_key  = int(round(N_pairs * f_target))
    n_test = max(0, N_pairs - n_key)
    S_hat, S_LB = chsh_test(n_test, rng)
    e = secure_key_efficiency_frac(f_target, S_LB)
    rel = 100.0 * e / (raw_eff.max() if raw_eff.max() > 0 else 1.0)
    return S_hat, S_LB, e, rel

S30, SLB30, e30, rel30 = evaluate_at(0.30)
S65, SLB65, e65, rel65 = evaluate_at(0.65)

# 結果の表示
print("=== E91 教育用トレードオフ解析 ===")
print(f"総EPRペア数           : {N_pairs}")
print(f"信頼係数 z            : {z_score}（≈99%）")
print(f"ノイズ率              : {flip_noise:.3f}")
print(f"最適 key_fraction     : {best_f:.2f}")
print(f"最適 相対効率(%)      : {best_rel:.1f}%")
print("--- 指定点の比較 ---")
print(f"f=0.30: S≈{S30:.3f}, S_LB≈{SLB30:.3f}, 相対効率≈{rel30:.1f}%")
print(f"f=0.65: S≈{S65:.3f}, S_LB≈{SLB65:.3f}, 相対効率≈{rel65:.1f}%")

# グラフ
plt.figure(figsize=(8,5))
plt.plot(fractions, rel_eff, marker='o')
plt.scatter([best_f], [best_rel], s=120, marker='*')  # 最適点
plt.scatter([0.30, 0.65], [rel30, rel65], s=80, marker='x')

plt.title("最終：安全に残せる鍵効率（相対）と 鍵に回す割合 key_fraction（教育用モデル）", fontname="Hiragino Sans")
plt.xlabel("鍵に回す割合 (key_fraction)", fontname="Hiragino Sans")
plt.ylabel("安全に残せる鍵効率（相対 %）", fontname="Hiragino Sans")
plt.grid(True, which="both", linestyle="--", alpha=0.4)

# 注釈
plt.annotate(f"最適: key_fraction={best_f:.2f}\n相対効率≈{best_rel:.1f}%",
             xy=(best_f, best_rel),
             xytext=(best_f+0.02, best_rel-10),
             arrowprops=dict(arrowstyle="->"))

plt.annotate(f"f=0.30\n相対効率≈{rel30:.1f}%",
             xy=(0.30, rel30),
             xytext=(0.22, rel30+10),
             arrowprops=dict(arrowstyle="->"))

plt.annotate(f"f=0.65\n相対効率≈{rel65:.1f}%",
             xy=(0.65, rel65),
             xytext=(0.68, rel65+10),
             arrowprops=dict(arrowstyle="->"))

plt.tight_layout()
plt.show()

