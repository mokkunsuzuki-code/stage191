# qkd20_e91_satellite.py
# 段階20：E91（もつれ型）で「ファイバ vs リピータ vs 衛星」を教育用モデルで比較

import math
import numpy as np

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
    print("[INFO] matplotlib が無いので表だけ出力します。pip install matplotlib で追加可。")

# ===== 共通パラメータ（教育用の素直な近似） =====
f_ec = 1.16        # 誤り訂正冗長度
ed   = 0.015       # ミスアライン誤り（QBERの主因）
pairs = 1e6        # 実験で扱うEPRペア数の目安（統計量）

def h2(x):
    if x <= 0 or x >= 1: return 0.0
    return -(x*math.log2(x) + (1-x)*math.log2(1-x))

# ===== ファイバ（地上）モデル =====
alpha_db_per_km = 0.2  # ファイバ損失[dB/km]
eta_det_fiber   = 0.20 # 受信側の総合効率（結合+検出）

def eta_fiber(distance_km: float) -> float:
    """全距離Lの伝送効率（検出効率込み）"""
    eta_ch = 10**(-alpha_db_per_km * distance_km / 10.0)
    return eta_det_fiber * eta_ch

# ===== 衛星ダウンリンク（自由空間）モデル =====
lambda_nm = 850
lambda_m  = lambda_nm * 1e-9
extra_losses_db = 12.0   # 大気・指向・光学などのまとめ損失
eta_det_sat     = 0.50   # 受信光学〜検出の効率

def free_space_loss_db(range_km: float) -> float:
    """自由空間損失：20log10(4πR/λ)"""
    R = range_km * 1000.0
    return 20.0 * math.log10(4.0 * math.pi * R / lambda_m)

def eta_satellite(range_km: float) -> float:
    Lfs_db  = free_space_loss_db(range_km)
    Ltot_db = Lfs_db + extra_losses_db
    eta_ch  = 10**(-Ltot_db/10.0)
    return eta_det_sat * eta_ch

# ===== E91の“鍵率”近似（教育用） =====
def e91_keyrate(etaA: float, etaB: float):
    """
    E91では“両端に届いたペア”が鍵候補：割合 ~ etaA * etaB
    QBER ≈ ed、CHSH はノイズが小さければ ~2.7 を想定
    """
    eta_pair = max(0.0, min(1.0, etaA * etaB))
    if eta_pair == 0.0:
        return 0.0, 0.0, 0.0
    qber  = ed
    chsh  = 2.7 * (1.0 - qber)     # ざっくり低下モデル
    # 教育用の鍵率近似： sift(=eta_pair) × 1/2 × [1 - 2 h2(Q)]
    # （1/2 は基底の選び方・検査ビット分の定数近似として扱う）
    R = 0.5 * eta_pair * max(0.0, 1.0 - 2.0*h2(qber))
    return R, chsh, qber

# ===== 量子リピータ（距離分割）簡易モデル =====
def repeater_eta(distance_km: float, segments: int = 2, swap_success: float = 0.90) -> float:
    """
    距離を 'segments' に分割。各区間の効率を eta_seg とし、
    “両端に届いたペア”の総効率を (eta_seg^2)^segments × swap_success^(segments-1) と近似。
    返却値は「両端ペア効率 = etaA*etaB」に相当する量（= eta_pair）。
    """
    segL    = distance_km / segments
    eta_seg = eta_fiber(segL)           # 片腕の効率
    eta_pair_seg = (eta_seg**2)         # 1区間で“両端到達”する効率
    eta_total = (eta_pair_seg**segments) * (swap_success**(segments-1))
    return max(0.0, min(1.0, eta_total))

# ===== スイープ設定 =====
fiber_d = np.arange(0, 301, 50)     # 地上ファイバ距離 0〜300 km
sat_d   = np.arange(500, 2001, 250) # 衛星スラント距離 500〜2000 km

# 地上：リピータ無し / 2分割 / 4分割
R_fiber, R_rep2, R_rep4 = [], [], []
CH_fiber = []

for L in fiber_d:
    # リピータ無し（左右同じチャネル）
    RA, CH, Q = e91_keyrate(eta_fiber(L), eta_fiber(L))
    R_fiber.append(RA); CH_fiber.append(CH)

    # リピータあり：返ってくるのは eta_pair（=etaA*etaB）相当
    eta_pair2 = repeater_eta(L, segments=2, swap_success=0.90)
    eta_pair4 = repeater_eta(L, segments=4, swap_success=0.90)
    # これを e91_keyrate に渡すため、左右対称の sqrt を取って分配（etaA=etaB=√eta_pair）
    R2,_,_ = e91_keyrate(math.sqrt(eta_pair2), math.sqrt(eta_pair2))
    R4,_,_ = e91_keyrate(math.sqrt(eta_pair4), math.sqrt(eta_pair4))
    R_rep2.append(R2); R_rep4.append(R4)

# 衛星
R_sat, CH_sat = [], []
for Rng in sat_d:
    RB, CH, Q = e91_keyrate(eta_satellite(Rng), eta_satellite(Rng))
    R_sat.append(RB); CH_sat.append(CH)

# ===== テーブル出力（代表値） =====
print("=== Fiber (E91) ===")
print(" L[km] | KeyRate(per pair) ")
for L, r in zip(fiber_d, R_fiber):
    print(f"{L:5.0f} | {r: .3e}")
print("\n=== Fiber + Repeater x2 ===")
for L, r in zip(fiber_d, R_rep2):
    print(f"{L:5.0f} | {r: .3e}")
print("\n=== Fiber + Repeater x4 ===")
for L, r in zip(fiber_d, R_rep4):
    print(f"{L:5.0f} | {r: .3e}")
print("\n=== Satellite (downlink, E91) ===")
print(" Range[km] | KeyRate(per pair) ")
for d, r in zip(sat_d, R_sat):
    print(f"{d:9.0f} | {r: .3e}")

# ===== グラフ =====
if HAS_MPL:
    import matplotlib.pyplot as plt

    # 地上：ファイバ vs リピータ
    plt.figure()
    plt.semilogy(fiber_d, R_fiber, 'o-', label="Fiber (E91)")
    plt.semilogy(fiber_d, R_rep2,  'o-', label="Fiber + Repeater x2")
    plt.semilogy(fiber_d, R_rep4,  'o-', label="Fiber + Repeater x4")
    plt.xlabel("Fiber distance (km)")
    plt.ylabel("Secret key per pair (log)")
    plt.title("E91 over fiber vs repeaters (education)")
    plt.grid(True, which='both'); plt.legend()

    # 衛星
    plt.figure()
    plt.semilogy(sat_d, R_sat, 'o-', color='tab:purple', label="Satellite downlink (E91)")
    plt.xlabel("Satellite slant range (km)")
    plt.ylabel("Secret key per pair (log)")
    plt.title("E91 over satellite (education)")
    plt.grid(True, which='both'); plt.legend()

    # 代表比較（1枚に）
    plt.figure()
    plt.semilogy(fiber_d, R_fiber, 'o-', label="Fiber (E91)")
    plt.semilogy(fiber_d, R_rep4,  'o-', label="Fiber + Repeater x4")
    plt.semilogy(sat_d,  R_sat,    'o-', label="Satellite (500–2000 km)")
    plt.xlabel("Distance (km)")
    plt.ylabel("Secret key per pair (log)")
    plt.title("E91: Satellite vs Ground (education)")
    plt.grid(True, which='both'); plt.legend()

    plt.tight_layout(); plt.show()

