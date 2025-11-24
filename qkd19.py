# qkd20_e91_satellite.py
# 段階20：E91版・衛星QKD＋リピータ（教育用シンプルモデル）

import math
import numpy as np
import matplotlib.pyplot as plt

# === 共通パラメータ ===
f_ec = 1.16
ed   = 0.015   # 誤り率（ミスアライン）
p_dc = 1e-6    # 暗計数/パルス
pairs = 1e6    # 送信するEPRペア数（基準）

def h2(x):
    if x<=0 or x>=1: return 0
    return -(x*math.log2(x)+(1-x)*math.log2(1-x))

# === ファイバ ===
alpha_db_per_km = 0.2
eta_det_fiber   = 0.2

def eta_fiber(distance_km):
    eta_ch = 10**(-alpha_db_per_km*distance_km/10)
    return eta_det_fiber * eta_ch

# === 衛星 ===
lambda_nm = 850
lambda_m  = lambda_nm*1e-9
extra_losses_db = 12.0
eta_det_sat     = 0.5

def free_space_loss_db(range_km):
    R = range_km*1000
    return 20*math.log10(4*math.pi*R/lambda_m)

def eta_satellite(range_km):
    Lfs = free_space_loss_db(range_km)
    Ltot_db = Lfs + extra_losses_db
    eta_ch = 10**(-Ltot_db/10)
    return eta_det_sat * eta_ch

# === E91鍵率モデル（教育用近似） ===
def e91_keyrate(etaA, etaB):
    """
    etaA, etaB: アリス・ボブのチャネル透過率
    両方届いたペアだけが鍵候補。
    """
    eta_pair = etaA * etaB
    sifted = pairs * eta_pair
    if sifted == 0: return 0,0,0

    qber = ed
    CHSH = 2.7 * (1 - qber)   # ノイズがなければ ~2.7
    R = 0.5 * eta_pair * (1 - 2*h2(qber))   # 簡易鍵率
    return R, CHSH, qber

# === リピータ（距離分割モデル） ===
def repeater_eta(distance_km, segments=2, eta_det=eta_det_fiber):
    segL = distance_km/segments
    eta_ch = 10**(-alpha_db_per_km*segL/10)
    eta_seg = eta_det * eta_ch
    # 成功率 = (η_seg^2)^segments （両端に届くペアが必要）
    eta_total = (eta_seg**2)**segments
    # スワップ成功率のペナルティ
    swap = 0.9**(segments-1)
    return eta_total * swap

# === スイープ ===
fiber_d = np.arange(0,301,50)
sat_d   = np.arange(500,2001,250)

R_fiber=[]; R_rep2=[]; R_rep4=[]; R_sat=[]
CH_fiber=[]; CH_sat=[]

for L in fiber_d:
    R,CH,Q = e91_keyrate(eta_fiber(L), eta_fiber(L))
    R_fiber.append(R); CH_fiber.append(CH)
    R2,_,_ = e91_keyrate(math.sqrt(repeater_eta(L,2)), math.sqrt(repeater_eta(L,2)))
    R_rep2.append(R2)
    R4,_,_ = e91_keyrate(math.sqrt(repeater_eta(L,4)), math.sqrt(repeater_eta(L,4)))
    R_rep4.append(R4)

for Rng in sat_d:
    R,CH,Q = e91_keyrate(eta_satellite(Rng), eta_satellite(Rng))
    R_sat.append(R); CH_sat.append(CH)

# === プロット ===
plt.figure()
plt.semilogy(fiber_d, R_fiber, 'o-', label="Fiber E91")
plt.semilogy(fiber_d, R_rep2, 'o-', label="Fiber + repeater x2")
plt.semilogy(fiber_d, R_rep4, 'o-', label="Fiber + repeater x4")
plt.xlabel("Fiber distance (km)")
plt.ylabel("Secret key rate (per pair, log)")
plt.title("E91 over Fiber vs Repeaters")
plt.grid(True,which="both"); plt.legend()

plt.figure()
plt.semilogy(sat_d, R_sat, 'o-', color="tab:purple", label="Satellite downlink E91")
plt.xlabel("Satellite slant range (km)")
plt.ylabel("Secret key rate (per pair, log)")
plt.title("E91 over Satellite link")
plt.grid(True,which="both"); plt.legend()

plt.show()
