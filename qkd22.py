# qkd22_optimize_finite.py
# 段階22：E91 有限サイズで m を最大化するための最適化（key_fraction, test_frac, alpha_CI）
# - QBER上限は Clopper–Pearson（scipy）/ Wilson 近似の自動フォールバック
# - 乱数ばらつきを抑えるために複数試行の平均で評価
# - ヒートマップ（matplotlib があれば）

import math
import numpy as np

# ===== Optional deps =====
HAVE_SCIPY = False
try:
    from scipy.stats import beta as sp_beta
    HAVE_SCIPY = True
except Exception:
    pass

HAVE_MPL = False
try:
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:
    print("[INFO] matplotlib なし：表と推奨値の出力のみ行います。")

# ===== Common utils =====
def h2(x: float) -> float:
    if x <= 0.0 or x >= 1.0:
        return 0.0
    return -(x*math.log2(x) + (1-x)*math.log2(1-x))

def clopper_pearson_interval(k: int, n: int, alpha: float):
    """CP区間（scipyあり）/ Wilson近似（fallback）"""
    if n == 0:
        return (0.0, 1.0)
    if HAVE_SCIPY:
        lo = 0.0 if k == 0 else float(sp_beta.ppf(alpha/2, k,   n-k+1))
        hi = 1.0 if k == n else float(sp_beta.ppf(1-alpha/2, k+1, n-k))
        return (lo, hi)
    # Wilson fallback
    p = k/n
    def z_from_alpha(a):
        if a <= 1e-3: return 3.29
        if a <= 1e-2: return 2.58
        if a <= 2e-2: return 2.33
        if a <= 5e-2: return 1.96
        return 1.64
    z = z_from_alpha(alpha/2)
    denom = 1 + z*z/n
    center = (p + z*z/(2*n))/denom
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/denom
    return (max(0.0, center-half), min(1.0, center+half))

# ===== Experiment generator (E91簡易) =====
def gen_bits_e91(pairs: int, p_err: float, key_fraction: float, rng: np.random.Generator):
    """
    - 鍵用：a=b=0（理想一致）。確率 p_err でボブ側を反転。
    - 検査(CHSH)：3設定は一致寄り、1設定は不一致寄り + p_err 上乗せ（鍵率最適化の主役はQBER側）
    """
    recs = []
    for _ in range(pairs):
        if rng.random() < key_fraction:
            a = rng.integers(0,2)
            b = a
            if rng.random() < p_err:
                b ^= 1
            recs.append(('key', 0,0, a,b))
        else:
            ai = rng.integers(0,2)
            bi = rng.integers(0,2)
            base_match = 0.85 if (ai,bi) in [(0,0),(0,1),(1,0)] else 0.15
            a = rng.integers(0,2)
            b = a if rng.random() < base_match else (a ^ 1)
            if rng.random() < p_err:
                b ^= 1
            recs.append(('chsh', ai,bi, a,b))
    return np.array(recs, dtype=object)

def compute_final_key_length(records, test_frac: float, f_ec: float, eps_sec: float, alpha_CI: float, rng: np.random.Generator):
    """有限サイズ評価：CPで e_u、leak_ec、Δ を用いて m を算出"""
    key_mask = (records[:,0] == 'key')
    K = records[key_mask][:, 3:5].astype(int)
    keyN = len(K)
    if keyN == 0: return 0, 0.0, 0, 0  # m, qhat, testN, n_keep

    testN = max(1, int(keyN * test_frac))
    idx = rng.choice(keyN, size=testN, replace=False)
    keep_mask = np.ones(keyN, dtype=bool); keep_mask[idx] = False

    a_test, b_test = K[idx,0], K[idx,1]
    a_keep, b_keep = K[keep_mask,0], K[keep_mask,1]

    k_err = int(np.sum(a_test ^ b_test))
    qhat  = k_err / testN if testN>0 else 0.0
    _, q_upper = clopper_pearson_interval(k_err, testN, alpha_CI)
    e_u = q_upper

    n_keep = len(a_keep)
    leak_ec = int(math.ceil(f_ec * n_keep * h2(qhat)))
    delta   = int(math.ceil(2 * math.log2(1/eps_sec)))

    m = max(0, int(math.floor(n_keep * (1 - h2(e_u)) - leak_ec - delta)))
    return m, qhat, testN, n_keep

# ===== Optimization driver =====
def optimize_params(
    pairs_total=20000, p_noise=0.03, f_ec=1.16, eps_sec=1e-6,
    key_grid=np.linspace(0.3, 0.8, 11),    # 0.30〜0.80
    test_grid=np.linspace(0.05, 0.35, 13), # 0.05〜0.35
    alpha_list=(1e-2, 5e-3, 2e-3, 1e-3),   # 99%〜99.9% 程度
    repeats=3, seed=1234
):
    rng = np.random.default_rng(seed)
    results = []  # (m_avg, key_fraction, test_frac, alpha_CI, m_list_avg, qhat_avg, n_keep_avg, testN_avg)
    for alpha in alpha_list:
        for kf in key_grid:
            row_ms, row_qh, row_nk, row_nt = [], [], [], []
            for tf in test_grid:
                m_runs, qh_runs, nk_runs, nt_runs = [], [], [], []
                for r in range(repeats):
                    recs = gen_bits_e91(pairs_total, p_noise, kf, rng)
                    m, qhat, testN, n_keep = compute_final_key_length(
                        recs, tf, f_ec, eps_sec, alpha, rng
                    )
                    m_runs.append(m); qh_runs.append(qhat); nk_runs.append(n_keep); nt_runs.append(testN)
                m_avg  = float(np.mean(m_runs))
                qh_avg = float(np.mean(qh_runs))
                nk_avg = float(np.mean(nk_runs))
                nt_avg = float(np.mean(nt_runs))
                results.append((m_avg, kf, tf, alpha, qh_avg, nk_avg, nt_avg))
    # ベスト選択
    results.sort(key=lambda x: x[0], reverse=True)
    return results

def main():
    # ===== ユーザ調整パラメータ =====
    pairs_total = 20000   # 総EPRペア
    p_noise     = 0.03    # 実験ノイズ（QBERの主因）
    f_ec        = 1.16    # 誤り訂正の冗長度
    eps_sec     = 1e-6    # プライバシー増幅の安全余裕
    key_grid    = np.linspace(0.3, 0.8, 11)
    test_grid   = np.linspace(0.05, 0.35, 13)
    alpha_list  = (1e-2, 5e-3, 2e-3, 1e-3)  # 信頼区間の厳しさ
    repeats     = 3

    results = optimize_params(
        pairs_total=pairs_total, p_noise=p_noise, f_ec=f_ec, eps_sec=eps_sec,
        key_grid=key_grid, test_grid=test_grid, alpha_list=alpha_list,
        repeats=repeats, seed=2025
    )

    # 上位5件を表示
    print("=== TOP-5 configurations (maximize final key length m) ===")
    print("   m_avg | key_fraction | test_frac | alpha_CI | qhat_avg | n_keep_avg | testN_avg")
    for i in range(min(5, len(results))):
        m_avg, kf, tf, alpha, qh, nk, nt = results[i]
        print(f"{m_avg:7.1f} |     {kf:0.2f}     |   {tf:0.2f}   | {alpha:6.1e} |  {qh*100:5.2f}% |  {int(nk):6d}    |  {int(nt):6d}")

    best = results[0]
    m_best, kf_best, tf_best, alpha_best, qh_best, nk_best, nt_best = best
    print("\n=== Recommended setting (education) ===")
    print(f"- key_fraction ≈ {kf_best:0.2f}   （鍵用に回す割合）")
    print(f"- test_frac    ≈ {tf_best:0.2f}   （鍵のうち検査に出す割合）")
    print(f"- alpha_CI     ≈ {alpha_best:0.1e}（CP/Wilsonの信頼区間の有意水準：小さいほど厳しめ）")
    print(f"- Expected m   ≈ {m_best:.0f}     （平均最終鍵長の見込み）")
    print(f"- Observed QBER (avg) ≈ {qh_best*100:.2f}%   （検査部分の平均）")
    print(f"- n_keep(avg)  ≈ {int(nk_best)}   , testN(avg) ≈ {int(nt_best)}")

    # ===== ヒートマップ（alphaを1つ固定して描画）=====
    if HAVE_MPL:
        alpha_plot = alpha_list[-1]  # 最も厳しめ（例：1e-3）
        KF, TF = np.meshgrid(key_grid, test_grid, indexing='xy')
        M = np.zeros_like(KF, dtype=float)
        rng = np.random.default_rng(42)
        for i, kf in enumerate(key_grid):
            for j, tf in enumerate(test_grid):
                ms=[]
                for r in range(repeats):
                    recs = gen_bits_e91(pairs_total, p_noise, kf, rng)
                    m, qhat, testN, n_keep = compute_final_key_length(recs, tf, f_ec, eps_sec, alpha_plot, rng)
                    ms.append(m)
                M[j,i] = float(np.mean(ms))  # 注意：j行i列（test_fracが縦、key_fracが横）

        plt.figure(figsize=(7,5))
        im = plt.imshow(M, origin='lower', aspect='auto',
                        extent=[key_grid[0], key_grid[-1], test_grid[0], test_grid[-1]])
        plt.colorbar(im, label="final key length m (avg)")
        plt.xlabel("key_fraction")
        plt.ylabel("test_frac")
        plt.title(f"Heatmap of m (alpha_CI={alpha_plot:0.1e}, pairs={pairs_total}, p_noise={p_noise})")
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    main()
