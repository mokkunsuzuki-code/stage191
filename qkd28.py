# qkd28.py
# 段階28: 複数地上局 M のときの 1日あたり鍵ビット量（天候独立 vs 相関）
# - 天候の「晴れ確率」を地上局ごとに与える
# - 独立モデル: p_eff = 1 - Π(1 - p_i)
# - 相関モデル: ガウス・コピュラで相関ρを入れ、Monte Carloで p_eff を推定
# - 1パスで得られる鍵ビット数 × 1日の可視パス数 × 有効晴天確率 p_eff を「bits/day」として比較

from __future__ import annotations
import math
import numpy as np
import matplotlib.pyplot as plt

# ========= ユーティリティ =========
def norm_cdf(x):
    """標準正規 Φ(x) を配列対応で計算（SciPyなし）。"""
    x = np.asarray(x, dtype=float)
    erf_vec = np.vectorize(math.erf)       # math.erf はスカラー専用 -> ベクトル化して使う
    return 0.5 * (1.0 + erf_vec(x / np.sqrt(2.0)))

def effective_clear_prob_independent(p_list):
    """独立モデル: 晴れ確率 p_list の地上局が M局ある時の有効晴天確率 p_eff."""
    p = np.clip(np.asarray(p_list, dtype=float), 0.0, 1.0)
    return float(1.0 - np.prod(1.0 - p))

def simulate_effective_clear_prob_correlated(
    station_p_list,
    rho: float,
    trials: int = 20000,
    seed: int = 12344,
):
    """
    相関モデル（ガウス・コピュラ）で p_eff をMonte Carlo推定。
    - 相関係数 rho を全オフ対角要素に入れた相関行列を構成（-1/(M-1) < rho < 1 にクリップ）
    - Z ~ N(0, Sigma) を生成 → U = Φ(Z) → 各局 i の U_i < p_i なら「晴れ」
    - 1試行で「少なくとも1局晴れ」なら1カウント → 平均が p_eff 推定
    """
    p = np.clip(np.asarray(station_p_list, dtype=float), 0.0, 1.0)
    M = p.size
    if M == 0:
        return 0.0

    # 相関の安定化: 一様相関行列が半正定値になる範囲にクリップ
    # 一様相関での下限は -1/(M-1)
    rho_min = -1.0 / (M - 1) + 1e-9 if M > 1 else -0.999999
    rho = float(np.clip(rho, rho_min, 0.999999))

    # 相関行列（対角1、オフ対角rho）
    Sigma = np.full((M, M), rho, dtype=float)
    np.fill_diagonal(Sigma, 1.0)

    # コレスキー（微小の数値誤差対策で対角にεを足す場合あり）
    eps = 1e-12
    try:
        L = np.linalg.cholesky(Sigma)
    except np.linalg.LinAlgError:
        L = np.linalg.cholesky(Sigma + eps * np.eye(M))

    rng = np.random.default_rng(seed)
    # 標準正規 N(0, I) → 相関付き N(0, Sigma)
    Z = rng.standard_normal(size=(trials, M)) @ L.T
    U = norm_cdf(Z)  # [trials, M] に 0..1 の一様乱数（相関あり）

    clear_mat = (U < p)          # True=晴れ
    any_clear = np.any(clear_mat, axis=1)  # 少なくとも1局晴れ
    p_eff_hat = float(np.mean(any_clear))
    return p_eff_hat

# ========= ここから “モデル本体” =========
def main():
    # --- 日次スループットの基本パラメータ（教育用にまとめ値） ---
    passes_per_day = 6        # 1日の可視パス数
    pass_time      = 300      # 1パスの可視時間 [s]
    bits_per_pass  = 1.0e8    # 1パスで得られる鍵ビット数（代表値, 例: 100 Mbit）
    base_ps = 0.5             # 各局の「晴れ確率」の基本値（同一とする）
    rho_dep = 0.5             # 相関モデルの相関係数 ρ（都市部で天候が似るイメージ）

    # --- M（地上局数）を 1..M_max まで掃引 ---
    M_max = 20
    Ms = np.arange(1, M_max + 1)

    indep_curve = []   # 独立モデルの bits/day
    mc_curve    = []   # 相関モデルの bits/day（Monte Carlo）

    for M in Ms:
        # 各局の晴れ確率リスト（ここでは全て同じ base_ps）
        p_list = np.full(M, base_ps, dtype=float)

        # 独立モデル
        p_eff_ind = effective_clear_prob_independent(p_list)
        bits_day_ind = bits_per_pass * passes_per_day * p_eff_ind
        indep_curve.append(bits_day_ind)

        # 相関モデル（ガウス・コピュラ）
        p_eff_mc = simulate_effective_clear_prob_correlated(
            station_p_list=p_list,
            rho=rho_dep,
            trials=20000,
            seed=12345,
        )
        bits_day_mc = bits_per_pass * passes_per_day * p_eff_mc
        mc_curve.append(bits_day_mc)

    indep_curve = np.asarray(indep_curve)
    mc_curve    = np.asarray(mc_curve)

    # --- 図示 ---
    plt.figure(figsize=(8,5))
    plt.plot(Ms, indep_curve, marker='o', label="Independent (analytic)")
    plt.plot(Ms, mc_curve,    marker='s', label=f"Correlated MC (rho={rho_dep})")
    plt.xlabel("Number of ground stations (M)")
    plt.ylabel("Daily secure key [bits/day]")
    plt.title("Independent vs Correlated weather model")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()

    # --- コンソールへ一部サンプル出力 ---
    print("\n--- Sample numbers ---")
    print(f"passes/day={passes_per_day}, pass_time={pass_time}s, bits/pass={bits_per_pass:.2e}")
    for M in [1, 2, 5, 10, 20]:
        p_list = np.full(M, base_ps, dtype=float)
        p_ind = effective_clear_prob_independent(p_list)
        p_mc  = simulate_effective_clear_prob_correlated(p_list, rho=rho_dep, trials=20000, seed=2028)
        bd_ind = bits_per_pass * passes_per_day * p_ind
        bd_mc  = bits_per_pass * passes_per_day * p_mc
        print(f"M={M:>2d}: p_eff(indep)={p_ind:.3f}, p_eff(corr@rho={rho_dep})={p_mc:.3f} | "
              f"bits/day(ind)={bd_ind:.2e}, corr={bd_mc:.2e}")

if __name__ == "__main__":
    main()

