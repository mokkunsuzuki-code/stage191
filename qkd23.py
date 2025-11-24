# qkd23_multiobjective.py
# 段階23：E91 有限サイズ・多目的最適化
# 目的：m を最大化。ただし CHSH下界 S_LB > 2、および m ≥ m_min を満たす設定のみ採用。
# 依存：SciPyがあれば Clopper–Pearson（厳密）、無ければ Wilson 近似に自動フォールバック。

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
    print("[INFO] matplotlib なし：表ベースの出力のみ行います。")

# ===== Utilities =====
def h2(x: float) -> float:
    if x <= 0.0 or x >= 1.0: return 0.0
    return -(x*math.log2(x) + (1-x)*math.log2(1-x))

def clopper_pearson_interval(k: int, n: int, alpha: float):
    """CP区間（SciPy あり）/ Wilson近似（fallback）。戻り (lo, hi)"""
    if n == 0:
        return (0.0, 1.0)
    if HAVE_SCIPY:
        lo = 0.0 if k == 0 else float(sp_beta.ppf(alpha/2, k,   n-k+1))
        hi = 1.0 if k == n else float(sp_beta.ppf(1-alpha/2, k+1, n-k))
        return (lo, hi)
    # Wilson fallback
    p = k/n
    # ざっくり z(α/2) テーブル
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

def E_from_q_upper(q_upper: float) -> float:
    """不一致率 q の上側限界から E=1-2q の下界を作る"""
    q = min(max(q_upper, 0.0), 1.0)
    return 1.0 - 2.0*q

def E_from_q_lower(q_lower: float) -> float:
    """不一致率 q の下側限界から E=1-2q の上界を作る"""
    q = min(max(q_lower, 0.0), 1.0)
    return 1.0 - 2.0*q

# ===== E91簡易生成器（有限サイズ用） =====
def gen_bits_e91(pairs: int, p_err: float, key_fraction: float, rng: np.random.Generator):
    """
    - 鍵用：a=b=0（理想一致）+ 確率 p_err でボブ反転
    - CHSH用：3設定は一致寄り(≈0.85)、(a1,b1)は不一致寄り(≈0.15) + p_err
    """
    recs = []
    for _ in range(pairs):
        if rng.random() < key_fraction:
            a = rng.integers(0,2)
            b = a
            if rng.random() < p_err: b ^= 1
            recs.append(('key', 0,0, a,b))
        else:
            ai = rng.integers(0,2); bi = rng.integers(0,2)
            base_match = 0.85 if (ai,bi) in [(0,0),(0,1),(1,0)] else 0.15
            a = rng.integers(0,2)
            b = a if rng.random() < base_match else (a ^ 1)
            if rng.random() < p_err: b ^= 1
            recs.append(('chsh', ai,bi, a,b))
    return np.array(recs, dtype=object)

# ===== QBER（CP上限）と最終鍵長 m =====
def final_key_stats(records, test_frac: float, f_ec: float, eps_sec: float, alpha_CI: float, rng: np.random.Generator):
    key_mask = (records[:,0]=='key')
    K = records[key_mask][:,3:5].astype(int)
    keyN = len(K)
    if keyN == 0:
        return dict(m=0, qhat=0.0, e_u=1.0, n_keep=0, testN=0)
    testN = max(1, int(keyN*test_frac))
    idx = rng.choice(keyN, size=testN, replace=False)
    keep_mask = np.ones(keyN, dtype=bool); keep_mask[idx] = False

    a_test, b_test = K[idx,0], K[idx,1]
    a_keep, b_keep = K[keep_mask,0], K[keep_mask,1]

    k_err = int(np.sum(a_test ^ b_test))
    qhat  = k_err/testN if testN>0 else 0.0
    _, q_upper = clopper_pearson_interval(k_err, testN, alpha_CI)
    e_u = q_upper

    n_keep = len(a_keep)
    leak_ec = int(math.ceil(f_ec * n_keep * h2(qhat)))
    delta   = int(math.ceil(2 * math.log2(1/eps_sec)))
    m = max(0, int(math.floor(n_keep * (1 - h2(e_u)) - leak_ec - delta)))
    return dict(m=m, qhat=qhat, e_u=e_u, n_keep=n_keep, testN=testN)

# ===== CHSH の有限サイズ下界 S_LB =====
def chsh_lower_bound(records, alpha_CI: float):
    ch = records[records[:,0]=='chsh']
    S_terms = {}
    for ai, bi in [(0,0),(0,1),(1,0),(1,1)]:
        sub = ch[(ch[:,1]==ai) & (ch[:,2]==bi)][:,3:5].astype(int)
        n = len(sub)
        if n == 0:
            # データ無しは保守的に最悪側へ
            S_terms[(ai,bi)] = (-1.0 if (ai,bi)!=(1,1) else +1.0)
            continue
        mism = int(np.sum(sub[:,0] ^ sub[:,1]))
        lo, hi = clopper_pearson_interval(mism, n, alpha_CI)
        if (ai,bi)!=(1,1):
            # 正符号の3項：Eの下界が必要 → qの上限 hi から E_LB を作る
            S_terms[(ai,bi)] = E_from_q_upper(hi)
        else:
            # 負符号の1項：-Eの下界が必要 → Eの上界を使う → qの下限 lo から E_UB
            S_terms[(ai,bi)] = -E_from_q_lower(lo)
    return S_terms[(0,0)] + S_terms[(0,1)] + S_terms[(1,0)] + S_terms[(1,1)]

# ===== 多目的最適化（制約付き） =====
def optimize_multi(
    pairs_total=20000, p_noise=0.03, f_ec=1.16, eps_sec=1e-6,
    key_grid=np.linspace(0.30, 0.80, 11),
    test_grid=np.linspace(0.05, 0.35, 13),
    alpha_list=(1e-2, 5e-3, 2e-3, 1e-3),
    m_min=128,           # 最低でもこのビット数の鍵が欲しい（目的に合わせて調整）
    repeats=3, seed=2025
):
    rng = np.random.default_rng(seed)
    feasible = []  # (m_avg, S_LB_avg, kf, tf, alpha, qhat_avg, n_keep_avg, testN_avg)
    infeasible = []  # 制約を満たさないもの（参考）
    for alpha in alpha_list:
        for kf in key_grid:
            for tf in test_grid:
                m_runs=[]; s_runs=[]; q_runs=[]; nk_runs=[]; nt_runs=[]
                for r in range(repeats):
                    rec = gen_bits_e91(pairs_total, p_noise, kf, rng)
                    stats = final_key_stats(rec, tf, f_ec, eps_sec, alpha, rng)
                    S_LB = chsh_lower_bound(rec, alpha)
                    m_runs.append(stats['m'])
                    s_runs.append(S_LB)
                    q_runs.append(stats['qhat'])
                    nk_runs.append(stats['n_keep'])
                    nt_runs.append(stats['testN'])
                m_avg=float(np.mean(m_runs)); S_avg=float(np.mean(s_runs))
                q_avg=float(np.mean(q_runs)); nk_avg=float(np.mean(nk_runs)); nt_avg=float(np.mean(nt_runs))
                row=(m_avg, S_avg, kf, tf, alpha, q_avg, nk_avg, nt_avg)
                if (S_avg > 2.0) and (m_avg >= m_min):
                    feasible.append(row)
                else:
                    infeasible.append(row)
    feasible.sort(key=lambda x: x[0], reverse=True)
    infeasible.sort(key=lambda x: (x[1], x[0]), reverse=True)  # 参考：まず S_LB で

    return feasible, infeasible

def main():
    # ===== ユーザー調整ゾーン =====
    pairs_total = 20000   # 総EPRペア（増やすと有限サイズの不利が減りやすい）
    p_noise     = 0.03    # 実験ノイズ（QBERの主因）
    f_ec        = 1.16    # 誤り訂正冗長度
    eps_sec     = 1e-6    # 安全余裕（小さいほど安全→鍵は減る）
    key_grid    = np.linspace(0.30, 0.80, 11)
    test_grid   = np.linspace(0.05, 0.35, 13)
    alpha_list  = (1e-2, 5e-3, 2e-3, 1e-3)
    m_min       = 128     # 最低確保したい鍵長
    repeats     = 3

    feasible, infeasible = optimize_multi(
        pairs_total, p_noise, f_ec, eps_sec,
        key_grid, test_grid, alpha_list,
        m_min=m_min, repeats=repeats, seed=2025
    )

    print("=== (制約付き) 可行解 TOP-5  — maximize m with S_LB>2 and m>=m_min ===")
    print("   m_avg |  S_LB | key_frac | test_frac | alpha_CI | QBER(avg) | n_keep | testN")
    if feasible:
        for i in range(min(5, len(feasible))):
            m,S,kf,tf,a,q,nk,nt = feasible[i]
            print(f"{m:7.1f} | {S:5.2f} |   {kf:0.2f}   |   {tf:0.2f}   | {a:6.1e} |  {q*100:6.2f}% | {int(nk):6d} | {int(nt):6d}")
        best = feasible[0]
        print("\n>>> 推奨設定（教育用）")
        print(f"- key_fraction ≈ {best[2]:0.2f}")
        print(f"- test_frac    ≈ {best[3]:0.2f}")
        print(f"- alpha_CI     ≈ {best[4]:0.1e}")
        print(f"- 期待m        ≈ {best[0]:.0f}  （S_LB≈{best[1]:.2f} > 2）")
    else:
        print("可行解なし：S_LB>2 と m≥m_min を同時に満たす組が見つかりませんでした。")
        print("対策：pairs_total を増やす / p_noise を下げる / m_min を下げる / alpha_CI を緩める などを検討。")

    # 参考：非可行の上位（S_LBやmが惜しい例）
    if infeasible:
        print("\n=== 非可行だが参考になる設定（上位5） ===")
        print("   m_avg |  S_LB | key_frac | test_frac | alpha_CI | QBER(avg) | n_keep | testN")
        for i in range(min(5, len(infeasible))):
            m,S,kf,tf,a,q,nk,nt = infeasible[i]
            print(f"{m:7.1f} | {S:5.2f} |   {kf:0.2f}   |   {tf:0.2f}   | {a:6.1e} |  {q*100:6.2f}% | {int(nk):6d} | {int(nt):6d}")

    # 可視化（任意）：可行領域の散布図（alpha を一つに固定して比較）
    if HAVE_MPL and feasible:
        alpha_plot = alpha_list[-1]  # もっとも厳しい側（例：1e-3）
        xs=[]; ys=[]; cs=[]
        for (m,S,kf,tf,a,q,nk,nt) in feasible:
            if abs(a - alpha_plot) < 1e-12:
                xs.append(kf); ys.append(tf); cs.append(m)
        if xs:
            import matplotlib.pyplot as plt
            plt.figure()
            sc = plt.scatter(xs, ys, c=cs, cmap='viridis')
            plt.colorbar(sc, label="m_avg (feasible)")
            plt.xlabel("key_fraction"); plt.ylabel("test_frac")
            plt.title(f"Feasible region (alpha_CI={alpha_plot:0.1e})")
            plt.grid(True); plt.show()

if __name__ == "__main__":
    main()

