# qkd18_decoy_pns.py  — 段階18：デコイ状態BB84とPNS攻撃（教育用）
import numpy as np
import math

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
    print("[INFO] matplotlib が無いので表だけ出力します。 pip install matplotlib で追加可")

def h2(x):
    x = np.clip(x, 1e-12, 1-1e-12)
    return -(x*np.log2(x) + (1-x)*np.log2(1-x))

# ---- 物理パラメータ（お好みで調整） ----------------
alpha_db_per_km = 0.2     # ファイバ損失 [dB/km]
eta_det         = 0.15    # 検出器効率（総合）
p_dc            = 1e-6    # 暗計数/パルス
ed              = 0.015   # ミスアラインメント誤り（1.5%）
f_ec            = 1.16    # 誤り訂正の冗長度係数

mu_signal = 0.5           # 信号強度（平均光子数）
mu_decoy  = 0.1           # デコイ強度（参考：今回は“概念説明”で計算には直接使わない）

# ---- 解析式（教育版） --------------------------------
def total_eta(distance_km):
    """距離→総合透過率 η = η_det * 10^(-αL/10)"""
    eta_ch = 10**(-alpha_db_per_km * distance_km / 10.0)
    return eta_det * eta_ch

def gains_and_error(mu, eta):
    """
    Poisson源＋単純モデル
    総ゲイン Qμ ≈ 1 - exp(-ημ) + p_dc
    誤り率 eμ ≈ [ ed*(1-exp(-ημ)) + 0.5*p_dc ] / Qμ
    単光子寄与 Q1 ≈ P1*Y1, P1=μ e^{-μ}, Y1≈η + p_dc
    """
    Q = 1 - np.exp(-eta*mu) + p_dc
    E = (ed*(1-np.exp(-eta*mu)) + 0.5*p_dc) / Q
    P1 = mu*np.exp(-mu)
    Y1 = eta + p_dc                   # 教育用近似
    Q1 = P1 * Y1
    e1 = ed                           # 単光子の誤りは主にミスアライン由来
    return Q, E, Q1, e1

def key_rate_GLLP(mu, eta):
    """
    デコイ“思想”での安全鍵率（教育用近似）:
    R ≈ 1/2 * [ - Qμ f h2(Eμ) + Q1 (1 - h2(e1)) ]   [bit / 送信パルス]
    """
    Q, E, Q1, e1 = gains_and_error(mu, eta)
    R = 0.5 * (- Q * f_ec * h2(E) + Q1 * (1 - h2(e1)))
    return max(0.0, R), Q, E, Q1

def key_rate_under_PNS(mu, eta):
    """
    PNS攻撃（Eveが単光子を潰し、多光子だけで検出を“維持”）の概念デモ。
    ここでは「観測される Qμ と Eμ はほぼ変わらないが、Q1 ≈ 0」とみなす。
    → 安全鍵率 R ≈ 0（下式は0でクリップ）
    """
    Q, E, _, _ = gains_and_error(mu, eta)
    R = 0.5 * (- Q * f_ec * h2(E) + 0.0)  # Q1=0
    return max(0.0, R), Q, E

# ---- スイープ ------------------------------------------------
def main():
    distances = np.arange(0, 101, 5)   # 0〜100kmを5km刻み
    R_safe, R_pns = [], []
    Qs, Es = [], []
    for L in distances:
        eta = total_eta(L)
        r, Q, E, Q1 = key_rate_GLLP(mu_signal, eta)
        R_safe.append(r); Qs.append(Q); Es.append(E)

        r_p, Qp, Ep = key_rate_under_PNS(mu_signal, eta)
        R_pns.append(r_p)

    # 表示
    print(" L(km) |  eta   |   QBER(%) |  KeyRate_safe | KeyRate_(PNS, naive観測)")
    print("-------+--------+-----------+---------------+--------------------------")
    for L, eta, E, r, rp in zip(distances, map(total_eta, distances), Es, R_safe, R_pns):
        print(f"{L:5.0f}  | {eta:0.4f} | {E*100:8.2f} | {r:13.5e} | {rp:23.5e}")

    if HAS_MPL:
        import matplotlib.pyplot as plt
        # QBER
        plt.figure()
        plt.plot(distances, np.array(Es)*100, marker='o')
        plt.xlabel("Distance (km)"); plt.ylabel("QBER (%)")
        plt.title("BB84 (WCP) : Distance vs QBER (ed=1.5%)"); plt.grid(True)

        # 鍵率
        plt.figure()
        plt.plot(distances, R_safe, marker='o', label="Decoy思想での安全鍵率（正しい）")
        plt.plot(distances, R_pns,  marker='o', label="PNS下で“観測だけを見る”場合", linestyle='--')
        plt.xlabel("Distance (km)"); plt.ylabel("Secret key per pulse")
        plt.title("Decoy vs PNS（教育用）")
        plt.legend(); plt.grid(True)
        plt.tight_layout(); plt.show()

if __name__ == "__main__":
    main()

