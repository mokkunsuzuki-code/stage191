# qkd38_realistic.py  —  E91（教育モデル, 実用寄り数値）最終鍵を必ずプラスに
# 依存: numpy だけ。Qiskit不要。日本語表示。

from __future__ import annotations
import math, secrets
import numpy as np

# ===== 基本関数 =====
def h2(x: float) -> float:
    if x <= 0.0 or x >= 1.0: return 0.0
    return - x*math.log2(x) - (1-x)*math.log2(1-x)

def clopper_pearson_upper(k: int, n: int, alpha: float) -> float:
    # 片側上側 (success=k) の上限（失敗=エラー数でも使える）
    # k/n の上方信頼限界  (scipy無しの近似: Wilsonを穏健に利用)
    if n == 0: return 1.0
    p = k/n
    z = abs(np.sqrt(2)*erf_inv(1-2*alpha))  # 正規近似のz
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return min(1.0, center + half)

def confint_E_from_counts(match:int, total:int, alpha:float):
    # 相関E = 一致−不一致 / total = 2*一致/total − 1
    if total == 0:
        return (0.0, 0.0, 0.0)
    p_hat = match/total
    # WilsonでCI
    z = abs(np.sqrt(2)*erf_inv(1-2*alpha))
    denom = 1 + z*z/total
    center = (p_hat + z*z/(2*total))/denom
    half = z*math.sqrt(p_hat*(1-p_hat)/total + z*z/(4*total*total))/denom
    lo_p = max(0.0, center - half)
    hi_p = min(1.0, center + half)
    E_hat = 2*p_hat - 1
    E_lo  = 2*lo_p - 1
    E_hi  = 2*hi_p - 1
    return (E_hat, E_lo, E_hi)

# 誤差関数の逆関数（近似）
def erf_inv(x: float) -> float:
    # Abramowitz–Stegun型の近似で十分
    a = 0.147  # 定数
    sgn = 1 if x>=0 else -1
    ln = math.log(1-x*x)
    term = 2/(math.pi*a) + ln/2
    return sgn*math.sqrt( math.sqrt(term*term - ln/a) - term )

# ===== E91の教育モデル =====
def e91_run(
    N_pairs=300_000,
    key_fraction=0.85,   # 鍵用に回す割合
    p_flip=0.003,        # 反転ノイズ（≈QBER）
    alpha=0.02,          # 信頼区間(片側)
    eps_sec=1e-9,        # 秘密度
    f_ec=1.12,           # 誤り訂正の上乗せ係数
    tag_bits=64,         # 認証タグ長(OTP消費)
    auth_msgs=20,        # 認証する公開メッセージ数の目安
    seed=2025,
):
    rng = np.random.default_rng(seed)

    # --- 可視性とCHSHの理論値 ---
    # depolarizing/bit-flip的な単純モデル: Visibility V ≈ 1 - 2*p_flip
    V = max(0.0, 1.0 - 2.0*p_flip)
    S_true = 2*math.sqrt(2)*V                       # 最適角度のCHSH期待
    E_star  = V/math.sqrt(2)                        # E00=E01=E10=+E*, E11=-E*

    # --- 振り分け ---
    n_key  = int(N_pairs*key_fraction)
    n_test = N_pairs - n_key

    # ===== CHSH テスト（4組に等分）=====
    n_per = n_test//4
    # 不一致確率 p_ij = (1 - E_ij)/2
    # + + + − の組み合わせ（E11は負）
    p00 = (1 - (+E_star))/2
    p01 = (1 - (+E_star))/2
    p10 = (1 - (+E_star))/2
    p11 = (1 - (-E_star))/2  # = (1 + E_star)/2

    # 一致回数を二項分布で生成（"一致" = 1−不一致）
    m00 = n_per - rng.binomial(n_per, p00)
    m01 = n_per - rng.binomial(n_per, p01)
    m10 = n_per - rng.binomial(n_per, p10)
    m11 = n_per - rng.binomial(n_per, p11)

    # 推定と信頼区間
    E00, E00_lo, E00_hi = confint_E_from_counts(m00, n_per, alpha)
    E01, E01_lo, E01_hi = confint_E_from_counts(m01, n_per, alpha)
    E10, E10_lo, E10_hi = confint_E_from_counts(m10, n_per, alpha)
    E11, E11_lo, E11_hi = confint_E_from_counts(m11, n_per, alpha)

    # 点推定 S と 安全側の下界 S_LB（減点方向を考慮）
    S_point = E00 + E01 + E10 - E11
    # 下界: プラスの項は下側、マイナスの項は上側を使う
    S_LB = E00_lo + E01_lo + E10_lo - E11_hi

    # ===== 鍵セットのQBER推定 =====
    # 教育モデル: 鍵セットのエラーは bit-flip p_flip に従う
    errs = rng.binomial(n_key, p_flip)
    # 安全側の上界（Clopper-Pearson/ Wilson）
    Q_UB = clopper_pearson_upper(errs, n_key, alpha)

    # ===== Devetak–Winter: 1bitあたりの安全な率 r =====
    # E91の“敵の情報上界”を CHSH から評価（保守的な近似）
    #   phi(S) = h2( (1 + sqrt( max(0, (S/2)^2 - 1) )) / 2 )
    def phi_from_S(S):
        t = max(0.0, (S/2.0)**2 - 1.0)
        y = (1.0 + math.sqrt(t))/2.0
        return h2(y)

    leak_chsh = phi_from_S(max(0.0, S_LB))
    r = max(0.0, 1.0 - h2(Q_UB) - leak_chsh)

    # ===== 生鍵長 → 各種控除 =====
    ell_raw = int(math.floor(n_key * r))

    # 誤り訂正リーク（教育用）： n_key * f_ec * h2(Q_UB)
    leak_ec = int(math.ceil(n_key * f_ec * h2(Q_UB)))

    # 有限サイズ控えめ（安全パラメータ由来 + サンプル有限ペナルティ）
    safety_bits = int(math.ceil(2*math.log2(1/eps_sec)))   # 例: eps=1e-9 → ≈ 60
    finite_pen  = int(math.ceil(2.0*math.sqrt(n_key)))     # 緩いが効く項
    A = safety_bits + finite_pen

    # 認証で消費（OTPはタグ長だけ消費。Toeplitzは再利用可）
    auth_used = tag_bits * auth_msgs

    ell_final = ell_raw - leak_ec - A
    ell_net   = ell_final - auth_used
    ell_final = max(0, ell_final)
    ell_net   = max(0, ell_net)

    # ===== まとめ =====
    out = {
        "N_pairs": N_pairs,
        "key_fraction": key_fraction,
        "p_flip": p_flip,
        "alpha": alpha,
        "eps_sec": eps_sec,
        "f_ec": f_ec,
        "tag_bits": tag_bits,
        "auth_msgs": auth_msgs,

        "n_key": n_key, "n_test": n_test,
        "S_point": S_point, "S_LB": S_LB,
        "Q_UB": Q_UB,

        "r": r, "ell_raw": ell_raw,
        "leak_ec": leak_ec, "A": A,
        "auth_used": auth_used,

        "ell_final": ell_final,
        "ell_net": ell_net,   # 認証消費まで引いた純増
    }
    return out

# ===== 使い切り暗号（検証デモ）=====
def otp_demo(key_bits: int, msg="E91で作った鍵で暗号化デモ"):
    # key_bits 分のランダム鍵で文字列をXORして復号確認
    kb = secrets.token_bytes((key_bits+7)//8)
    m  = msg.encode("utf-8")
    n  = min(len(m), len(kb))
    c  = bytes([m[i]^kb[i] for i in range(n)])
    p  = bytes([c[i]^kb[i] for i in range(n)])
    return {
        "key_len_bits": 8*n,
        "cipher_hex": c.hex(),
        "recovered": p.decode("utf-8", errors="ignore")
    }

# ===== 実行 =====
if __name__ == "__main__":
    res = e91_run(
        N_pairs       = 300_000,
        key_fraction  = 0.85,
        p_flip        = 0.003,
        alpha         = 0.02,
        eps_sec       = 1e-9,
        f_ec          = 1.12,
        tag_bits      = 64,
        auth_msgs     = 20,
        seed          = 2025,
    )

    print("＝＝ E91（実用寄り・教育モデル）レポート ＝＝")
    print(f"N          = {res['N_pairs']:,}  | 鍵用 = {res['n_key']:,}  | テスト = {res['n_test']:,}")
    print(f"QBER 上限  Q_UB   = {100*res['Q_UB']:.3f} %")
    print(f"CHSH 推定  S      = {res['S_point']:.4f}  | 下限 S_LB = {res['S_LB']:.4f}  (2より大なら量子相関OK)")
    print(f"1bit率     r      = {res['r']:.4f}  （Devetak–Winter）")
    print(f"生鍵長     ell_raw= {res['ell_raw']:,} bit")
    print(f"ECリーク   leak_ec= {res['leak_ec']:,} bit   | 有限サイズ A = {res['A']:,} bit")
    print(f"認証消費   auth   = {res['auth_used']:,} bit  (タグ{res['tag_bits']}bit×{res['auth_msgs']}通)")
    print(f"最終鍵     ell_final = {res['ell_final']:,} bit")
    print(f"純増（認証差引） ell_net   = {res['ell_net']:,} bit")

    if res["ell_final"] > 0:
        demo = otp_demo(res["ell_final"])
        print("\n［OTPデモ］")
        print(f"鍵長         = {demo['key_len_bits']} ビット")
        print(f"暗号文(hex)  = {demo['cipher_hex']}")
        print(f"復号結果     = {demo['recovered']}")
    else:
        print("\n⚠ 最終鍵が残りませんでした。N / key_fraction を増やす・alphaを緩める等を検討してください。")

