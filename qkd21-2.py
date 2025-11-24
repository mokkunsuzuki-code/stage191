# qkd21_finite_strict.py
# 有限サイズ“ガチ寄り”版：
# ・QBER: Clopper–Pearson (CP) で上側限界 e_u（scipy 無ければ Wilson 近似）
# ・CHSH: 各設定(ai,bi)の不一致率に対する CP 区間から下界を合成
# ・最終鍵長: m >= n_keep * (1 - h2(e_u)) - leak_ec - Δ

import math
import numpy as np

# ==== オプション依存 ====
HAVE_SCIPY = False
try:
    from scipy.stats import beta as sp_beta
    HAVE_SCIPY = True
except Exception:
    pass

try:
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False
    print("[INFO] matplotlib なし: グラフはスキップします。")

# ===== ユーティリティ =====
def h2(x: float) -> float:
    if x <= 0.0 or x >= 1.0:
        return 0.0
    return -(x*math.log2(x) + (1-x)*math.log2(1-x))

def clopper_pearson_interval(k: int, n: int, alpha: float):
    """
    二項比率 k/n の CP(α) 区間。SciPyがあれば厳密、無ければ Wilson 近似にフォールバック。
    戻り値: (lower, upper)
    """
    if n == 0:
        return (0.0, 1.0)
    if HAVE_SCIPY:
        # CP: [BetaInv(alpha/2; k, n-k+1), BetaInv(1-alpha/2; k+1, n-k)]
        lo = 0.0 if k == 0 else float(sp_beta.ppf(alpha/2, k,   n-k+1))
        hi = 1.0 if k == n else float(sp_beta.ppf(1-alpha/2, k+1, n-k))
        return (lo, hi)
    # Wilson 近似（フォールバック）
    p = k/n
    from math import sqrt
    # 片側α/2を両側に使う（少し保守的）
    # 正規分位は近似値（SciPyなし）：z≈2.575で ~99%（alpha=0.01）など
    def z_from_alpha(a):
        # ざっくりの近似（αに応じたテーブル）
        # 0.10→1.64, 0.05→1.96, 0.02→2.33, 0.01→2.58, 0.001→3.29
        if a <= 1e-3: return 3.29
        if a <= 1e-2: return 2.58
        if a <= 2e-2: return 2.33
        if a <= 5e-2: return 1.96
        return 1.64
    z = z_from_alpha(alpha/2)
    denom = 1 + z*z/n
    center = (p + z*z/(2*n))/denom
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))

def bernoulli_E_from_mismatch_CI_upper(q_upper: float) -> float:
    """
    不一致率 q の上側限界から E=1-2q の下界を作る。
    """
    q_upper = min(max(q_upper, 0.0), 1.0)
    return 1.0 - 2.0*q_upper

def bernoulli_E_from_mismatch_CI_lower(q_lower: float) -> float:
    """
    不一致率 q の下側限界から E=1-2q の上界を作る（CHSHの最後の -E11 で使う）。
    """
    q_lower = min(max(q_lower, 0.0), 1.0)
    return 1.0 - 2.0*q_lower

# ===== 実験パラメータ =====
pairs_total  = 20000   # 総EPRペア数（有限サイズ効果のため控えめ）
key_fraction = 0.5     # 鍵用に回す割合
test_frac    = 0.2     # 鍵用のうちQBER推定に使う公開割合
p_noise      = 0.03    # ノイズ（3%）
eps_sec      = 1e-6    # セキュリティ（PAの安全余裕）
alpha_CI     = 1e-3    # 信頼区間の有意水準（両側）例: 0.001 ≒ 99.9%
f_ec         = 1.16    # 誤り訂正の冗長度

rng = np.random.default_rng(0)

# ===== データ生成（E91の簡易モデル） =====
def gen_bits_e91(pairs: int, p_err: float):
    """
    - 鍵用：a=b=0（理想一致）。確率 p_err でビット反転。
    - 検査用(CHSH)：(a0,b0),(a0,b1),(a1,b0) は一致寄り、(a1,b1) は不一致寄り。
      そこに p_err を上乗せ。
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

records = gen_bits_e91(pairs_total, p_noise)

# ===== 鍵用データの抽出とQBER（CP区間） =====
key_mask = (records[:,0]=='key')
K = records[key_mask][:,3:5].astype(int)
keyN = len(K)
if keyN == 0:
    raise RuntimeError("鍵用データがありません。key_fraction を上げてください。")

testN = max(1, int(keyN*test_frac))
idx = rng.choice(keyN, size=testN, replace=False)
keep_mask = np.ones(keyN, dtype=bool); keep_mask[idx] = False

a_test, b_test = K[idx,0], K[idx,1]
a_keep, b_keep = K[keep_mask,0], K[keep_mask,1]

# 観測QBERとCP上側限界
k_err = int(np.sum(a_test ^ b_test))        # エラー数
qhat  = k_err / testN if testN>0 else 0.0
_, q_upper = clopper_pearson_interval(k_err, testN, alpha_CI)  # 上側限界
e_u = q_upper

# ===== 誤り訂正の漏洩 & 安全余裕 =====
n_keep = len(a_keep)
leak_ec = int(math.ceil(f_ec * n_keep * h2(qhat)))
delta   = int(math.ceil(2 * math.log2(1/eps_sec)))  # 教育用

# ===== 最終鍵長下界（CPを使う） =====
m = max(0, int(math.floor(n_keep * (1 - h2(e_u)) - leak_ec - delta)))
equal_possible = (m > 0)

# ===== CHSH の有限サイズ下界 =====
# 各設定の不一致率 q_ij = (#xor=1)/n_ij に対して CP 区間を出し、
# S_LB = LB(E00)+LB(E01)+LB(E10) - UB(E11) を構成
ch = records[records[:,0]=='chsh']
def chsh_lower_bound_CI(ch_recs, alpha):
    # カウント
    S_terms = {}
    for ai, bi in [(0,0),(0,1),(1,0),(1,1)]:
        sub = ch_recs[(ch_recs[:,1]==ai) & (ch_recs[:,2]==bi)][:,3:5].astype(int)
        n = len(sub)
        if n == 0:
            # データが無い場合は最悪側（保守的）に倒す
            if (ai,bi)!=(1,1):
                S_terms[(ai,bi)] = -1.0  # LB(E)= -1 に
            else:
                S_terms[(ai,bi)] = +1.0  # UB(E)= +1 に
            continue
        mism = int(np.sum(sub[:,0] ^ sub[:,1]))
        lo, hi = clopper_pearson_interval(mism, n, alpha)
        # E = 1 - 2q
        if (ai,bi)!=(1,1):
            # 正符号の3項 → E の下界にしたい → q の上側限界から作る
            E_LB = bernoulli_E_from_mismatch_CI_upper(hi)  # hi = q_upper
            S_terms[(ai,bi)] = E_LB
        else:
            # 負符号の1項 → -E の下界 = -(E の上界)
            E_UB = bernoulli_E_from_mismatch_CI_lower(lo)  # lo = q_lower → E_upper
            S_terms[(ai,bi)] = -E_UB
    return S_terms[(0,0)] + S_terms[(0,1)] + S_terms[(1,0)] + S_terms[(1,1)]

S_LB = chsh_lower_bound_CI(ch, alpha_CI)

# ===== 結果表示 =====
print("=== E91 finite-size (strict CP + CHSH LB) ===")
print(f"pairs_total     = {pairs_total}")
print(f"key_pairs       = {keyN} (kept={n_keep}, test={testN})")
print(f"QBER_hat        = {qhat:.3%}")
print(f"CP upper e_u    = {e_u:.3%}  (alpha={alpha_CI})  [{'CP' if HAVE_SCIPY else 'Wilson-approx'}]")
print(f"leak_ec         = {leak_ec}  (f_ec={f_ec})")
print(f"safety Δ        = {delta}    (eps_sec={eps_sec:g})")
print(f"final key m     = {m}  (equal_possible={equal_possible})")
print(f"CHSH lower bound (S_LB) = {S_LB:.3f}  ( > 2 なら非局所性を有限サイズで確認)")

# ===== 参考グラフ：alpha と m（CPを使った時の影響） =====
if HAVE_MPL:
    alphas = [1e-1, 5e-2, 2e-2, 1e-2, 5e-3, 2e-3, 1e-3, 5e-4, 1e-4]
    ms = []
    for a in alphas:
        _, qU = clopper_pearson_interval(k_err, testN, a)
        m_a = max(0, int(math.floor(n_keep * (1 - h2(qU)) - leak_ec - delta)))
        ms.append(m_a)
    import matplotlib.pyplot as plt
    plt.figure()
    plt.plot([math.log10(a) for a in alphas], ms, marker='o')
    plt.xlabel("log10(alpha)  (小さいほど厳しく安全側)")
    plt.ylabel("final key length m (CP upper bound)")
    plt.title("Effect of CI confidence (Clopper–Pearson)")
    plt.grid(True)
    plt.show()

