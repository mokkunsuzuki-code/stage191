# qkd21_e91_finite.py
# 段階21：有限サイズ効果つき E91（教育用）
# ・EPRペア生成 → 鍵用/検査(CHSH)/QBERテストに分配
# ・QBERの上側信頼限界 e_u を計算（正規近似＋クリップ）
# ・誤り訂正の漏洩 + 安全マージンを差し引き、最終鍵長 m を算出
# ※厳密なセキュリティ証明の定数とは異なります（学習用の素直な近似）

import math
import numpy as np

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
    print("[INFO] matplotlib なし：グラフはスキップします。")

# ===== パラメータ =====
pairs_total   = 10000      # 送信EPRペア数（有限サイズ感を出すため1e4程度）
key_fraction  = 0.5        # 鍵用に回す割合（残りはCHSH用）
test_frac     = 0.2        # 鍵用のうちQBER推定に使う割合（公開→削除）
p_noise       = 0.03       # 回路・測定ノイズ（3%）→ QBERの主因
eps_sec       = 1e-6       # セキュリティ指標（安全余裕計算に使用）
f_ec          = 1.16       # 誤り訂正の冗長度（実測QBERに対して多めに送る比率）

rng = np.random.default_rng(0)

# ===== 1) データ生成（E91っぽく：理想EPR + ノイズでフリップ） =====
# アリス/ボブは「鍵用：同一設定（0°）」と「CHSH用：4設定」をランダムに選ぶ
# ここでは鍵率に集中するので、CHSH値は参考表示に留めます。
def gen_bits_e91(pairs, p_err):
    """
    鍵用（a=b）では理想一致、誤りは確率 p_err でXOR=1。
    CHSH用では ±相関を角度で割り当てたうえに p_err を上乗せ（簡易）。
    """
    data = []
    for _ in range(pairs):
        if rng.random() < key_fraction:
            # 鍵用（a=b=0）: 理想相関は一致（XOR=0）
            a = rng.integers(0,2)
            b = a
            # ノイズでビットフリップ
            if rng.random() < p_err:
                b ^= 1
            data.append(('key', 0,0, a,b))
        else:
            # CHSH用（a∈{0,1}, b∈{0,1}）
            ai = rng.integers(0,2)
            bi = rng.integers(0,2)
            # 典型設定： (a0,b0),(a0,b1),(a1,b0) は強い相関、一方 (a1,b1) は反相関寄り
            # ここでは簡易に「一致寄り/不一致寄り」の確率を設定し、p_err を上乗せ
            base_match = 0.85 if (ai,bi) in [(0,0),(0,1),(1,0)] else 0.15
            # サンプル生成
            a = rng.integers(0,2)
            # “一致する確率”で b を a と同じにする → その後 p_err を上乗せ
            b = a if rng.random() < base_match else (a ^ 1)
            if rng.random() < p_err:
                b ^= 1
            data.append(('chsh', ai,bi, a,b))
    return np.array(data, dtype=object)

records = gen_bits_e91(pairs_total, p_noise)

# ===== 2) QBER推定（鍵用データの一部だけ公開） =====
key_mask = (records[:,0] == 'key')
key_bits = records[key_mask][:, 3:5].astype(int)   # columns: a_bit, b_bit
keyN = len(key_bits)
if keyN == 0:
    raise RuntimeError("鍵用データがありません。key_fraction を上げてください。")

# テストに回すインデックス
testN = max(1, int(keyN * test_frac))
test_idx = rng.choice(keyN, size=testN, replace=False)
keep_mask = np.ones(keyN, dtype=bool); keep_mask[test_idx] = False

a_key = key_bits[:,0]
b_key = key_bits[:,1]
a_test = a_key[test_idx]; b_test = b_key[test_idx]      # 公開してQBER推定
a_keep = a_key[keep_mask]; b_keep = b_key[keep_mask]    # 残す鍵候補

# 観測QBER（検査部分）
qhat = float(np.mean(a_test ^ b_test)) if testN > 0 else 0.0

# ===== 3) QBERの上側信頼限界 e_u（正規近似＋クリップ） =====
# 片側(1-ε)上側信頼限界： qhat + z * sqrt(qhat(1-qhat)/n)
# （小標本では保守的に少し大きく出ます。厳密にはClopper-Pearsonなどを使います。）
eps_qber = 1e-9
from math import erf, sqrt
def z_from_eps(eps):
    # 片側：Φ(z)=1-ε → z = sqrt(2)*erfc^-1(2ε) ≒  inverse CDF
    # 近似式：z ≈ sqrt(2) * erfc^{-1}(2ε)。ここでは二分探索で数値的に求める。
    lo, hi = 0.0, 10.0
    for _ in range(60):
        mid = (lo+hi)/2
        # tail ≈ 1 - Φ(mid) = 0.5*(1 - erf(mid/√2))
        tail = 0.5*(1 - erf(mid/sqrt(2)))
        if tail > eps:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2

z = z_from_eps(eps_qber)
var = max(qhat*(1-qhat)/max(1,testN), 1e-12)
e_u = min(1.0, max(0.0, qhat + z*math.sqrt(var)))  # 上側限界（0〜1にクリップ）

# ===== 4) 誤り訂正の漏洩（概算） =====
# 教育用：leak_ec ≈ f_ec * n_keep * h2(qhat)
def h2(x):
    if x <= 0 or x >= 1: return 0.0
    return -(x*math.log2(x) + (1-x)*math.log2(1-x))

n_keep = len(a_keep)
leak_ec = int(math.ceil(f_ec * n_keep * h2(qhat)))

# ===== 5) 安全余裕（プライバシー増幅の補正） =====
# 教育用：Δ ≈ 2*log2(1/eps_sec)
delta = int(math.ceil(2 * math.log2(1/eps_sec)))

# ===== 6) 最終鍵長 m の下界（教育用近似） =====
# Devetak–Winter 風の形： m ≥ n_keep * [1 - h2(e_u)] - leak_ec - delta
m = max(0, int(math.floor(n_keep * (1 - h2(e_u)) - leak_ec - delta)))

# ===== 7) “成功/不成功”の目安 =====
equal_possible = (m > 0)  # ここではECの詳細手順は省略し、PA以降の見積もりに集中

# ===== 8) 参考：CHSH の観測（検査に回した分） =====
def chsh_from_records(recs):
    ch = recs[recs[:,0] == 'chsh']
    if len(ch) == 0:
        return 0.0
    def E(ai,bi):
        sub = ch[(ch[:,1]==ai) & (ch[:,2]==bi)][:, 3:5].astype(int)
        if len(sub) == 0: return 0.0
        xor = np.mean(sub[:,0] ^ sub[:,1])
        return 1 - 2*xor  # 一致:+1, 不一致:-1
    return E(0,0) + E(0,1) + E(1,0) - E(1,1)

chsh_obs = chsh_from_records(records)

# ===== 9) 結果表示 =====
print("=== E91 finite-size (educational) ===")
print(f"pairs_total = {pairs_total}")
print(f"key_pairs   = {keyN} (kept={n_keep}, test={testN})")
print(f"QBER_hat    = {qhat:.2%}  (upper bound e_u={e_u:.2%} @ eps={eps_qber:g})")
print(f"leak_ec     = {leak_ec}  (f_ec={f_ec})")
print(f"safety Δ    = {delta}  (eps_sec={eps_sec:g})")
print(f"final m     = {m}  (equal_possible={equal_possible})")
print(f"CHSH_obs    = {chsh_obs:.3f}")

# ===== 10) 参考グラフ（n と m の関係をざっくり） =====
if HAS_MPL:
    sizes = np.linspace(2000, 40000, 10, dtype=int)
    ms = []
    for N in sizes:
        # 同じ qhat と e_u を仮定してスケール（教育用）
        n_keep_s = int(N*key_fraction*(1-test_frac))
        leak_ec_s = int(math.ceil(f_ec * n_keep_s * h2(qhat)))
        m_s = max(0, int(math.floor(n_keep_s * (1 - h2(e_u)) - leak_ec_s - delta)))
        ms.append(m_s)
    plt.figure()
    plt.plot(sizes, ms, marker='o')
    plt.xlabel("Total EPR pairs (N)")
    plt.ylabel("Lower-bound final key length m")
    plt.title("Finite-size effect (educational)")
    plt.grid(True)
    plt.show()
