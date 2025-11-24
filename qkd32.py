# qkd32.py — 段階32：key_fraction を掃引して「パス採用率（天候＆CHSH）」を可視化
from __future__ import annotations
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

# ===== 日本語フォント（Mac）=====
rcParams["font.family"] = "Hiragino Sans"   # Windowsなら "Meiryo" など

# ==============================
#  正規CDF（配列OK）— ここが落ちどころの修正点
# ==============================
def norm_cdf(x):
    """標準正規 Φ(x)（SciPyなし・配列対応）"""
    x = np.asarray(x, dtype=float)
    try:
        # SciPy があればそれを使う（高速・高精度）
        from scipy.special import erf as _erf
        return 0.5 * (1.0 + _erf(x / np.sqrt(2.0)))
    except Exception:
        # math.erf はスカラー専用 → ベクトル化で配列対応
        erf_vec = np.vectorize(math.erf)
        return 0.5 * (1.0 + erf_vec(x / np.sqrt(2.0)))

# ==============================
#  天候：相関付き 1 ステップの「少なくとも1局晴れ」
# ==============================
def at_least_one_clear_once(p_list, rho: float, rng: np.random.Generator) -> bool:
    """
    p_list: 各地上局の晴れ確率 [0..1]
    rho   : 一様相関（相関行列のオフ対角を全部 rho）
    戻り値: 少なくとも1局晴れなら True
    """
    p = np.clip(np.asarray(p_list, dtype=float), 0.0, 1.0)
    M = p.size
    if M == 0:
        return False

    # 一様相関が半正定値になる範囲にクリップ（下限 -1/(M-1)）
    rho_min = -1.0 / (M - 1) + 1e-9 if M > 1 else -0.999999
    rho = float(np.clip(rho, rho_min, 0.999999))

    # 相関行列 Σ（対角=1, オフ対角=rho）
    Sigma = np.full((M, M), rho, dtype=float)
    np.fill_diagonal(Sigma, 1.0)

    # コレスキー分解（微小εで安定化）
    eps = 1e-12
    try:
        L = np.linalg.cholesky(Sigma)
    except np.linalg.LinAlgError:
        L = np.linalg.cholesky(Sigma + eps * np.eye(M))

    # 相関付き標準正規 z ~ N(0, Σ) → 一様乱数 u = Φ(z)
    z0 = rng.standard_normal(M)      # (M,)
    z  = L @ z0                      # (M,)
    u  = norm_cdf(z)                 # (M,)

    # 各局：u_i < p_i なら晴れ
    return bool(np.any(u < p))

# ==============================
#  CHSHゲート（教育用の簡易近似）
# ==============================
def chsh_pass_once(qber: float, n_pairs: int, rng: np.random.Generator) -> bool:
    """
    期待値 S ≈ 2√2 * (1 - 2Q)、閾値 2、分散 ~ 1/√N とした粗い正規近似で合否を決定。
    """
    if n_pairs <= 0:
        return False
    S_thr = 2.0
    S_exp = 2.0 * np.sqrt(2.0) * max(0.0, (1.0 - 2.0 * qber))
    z = (S_exp - S_thr) * np.sqrt(float(n_pairs))  # 標準化
    p_pass = float(np.clip(norm_cdf(z), 0.0, 1.0))
    return bool(rng.random() < p_pass)

# ==============================
#  パラメータ
# ==============================
DT_SEC             = 60            # 1分ステップ
SAT_BPS            = 50e6          # 衛星の鍵生成レート [bit/s]（可視かつ採用時）
SAT_QBER           = 0.03          # 衛星のQBER（CHSHモデル用）
N_SAT              = 3
PASSES_PER_DAY     = 4
PASS_TIME_SEC      = 600
PASS_DUTY          = (PASSES_PER_DAY * PASS_TIME_SEC) / (24 * 3600)  # 1日での稼働率
PASS_PROB_PER_STEP = PASS_DUTY                                        # 各分で稼働している確率（ベルヌーイ近似）

GROUND_P_LIST      = [0.5, 0.5, 0.5]  # 地上局の晴れ確率
WEATHER_RHO        = 0.5              # 天候の一様相関

# ==============================
#  評価関数：ある key_fraction での「パス採用率(%)」
# ==============================
def evaluate_day_for_key_fraction(key_fraction: float, trials_weather: int = 2000, seed: int = 2025) -> float:
    """
    key_fraction: 1ステップで得た衛星ビットのうち、鍵に回す割合（残りはCHSH検査用）
    戻り値: 「衛星が稼働していたステップのうち、天候OKかつCHSH合格で“採用”できた割合」[%]
    """
    rng = np.random.default_rng(seed)

    adopted = 0      # 採用できたステップ数（天候OK & CHSH合格）
    possible = 0     # 衛星が「稼働」していたステップ数

    for _ in range(trials_weather):
        # 衛星：N機のうち少なくとも1機が稼働
        active_any_sat = np.any(rng.random(N_SAT) < PASS_PROB_PER_STEP)
        if not active_any_sat:
            continue
        possible += 1

        # 天候：少なくとも1局が晴れ
        weather_ok = at_least_one_clear_once(GROUND_P_LIST, WEATHER_RHO, rng)
        if not weather_ok:
            continue

        # 衛星生産ビット（1分ぶん）
        total_sat_bits = int(SAT_BPS * DT_SEC)
        key_bits_base  = int(total_sat_bits * key_fraction)
        test_bits      = total_sat_bits - key_bits_base

        # CHSH（教育用簡易近似）— テストビット ≒ ペア数として扱う
        chsh_ok = chsh_pass_once(SAT_QBER, n_pairs=test_bits, rng=rng)

        if chsh_ok and key_bits_base > 0:
            adopted += 1

    return 100.0 * (adopted / possible) if possible else 0.0

# ==============================
#  メイン：key_fraction を掃引して可視化
# ==============================
def main():
    # 掃引レンジ（例：0.05〜0.95）
    kfs = np.linspace(0.05, 0.95, 19)

    adm = []  # adoption rate [%]
    for i, kf in enumerate(kfs):
        # シードをずらして安定化
        adm.append(evaluate_day_for_key_fraction(float(kf), trials_weather=4000, seed=2025 + i))

    # ===== グラフ：合格率 vs key_fraction =====
    plt.figure(figsize=(7, 5))
    plt.plot(kfs, np.array(adm), marker="o")
    plt.xlabel("鍵生成に回す割合（key_fraction）")
    plt.ylabel("パス採用率 [%]（天候 & CHSH）")
    plt.title("パス採用率 vs 鍵生成割合")
    plt.grid(True)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()

