# qkd25_compare.py  —  同じグラフで「衛星」と「光ファイバー」を比較（教育用モデル）
# 使い方: python qkd25_compare.py
import numpy as np
import math
import matplotlib.pyplot as plt

# ==== 調整しやすいパラメータ（教育用の簡略モデル） =========================
# 共通（送信レートを「1ペアあたりの秘密鍵ビット/秒」に換算するための基準）
R0_fiber = 1.0e4      # 0km の理想ファイバーでの基準レート（相対値）
R0_sat   = 5.0e4      # 500km 近辺の衛星での基準レート（相対値）

# ファイバー損失（典型：0.2 dB/km）
alpha_db_per_km = 0.20

# 衛星リンク（教育用）：距離^2の幾何減衰 + 薄い大気減衰
#   T_sat(d) ~ (d0/d)^2 * 10^(-alpha_atm * airmass(d))
d0_km      = 500.0    # 参照距離[km]（これでスケール）
alpha_atm  = 0.005    # 大気の追加減衰（ゆるめ）
def airmass(slant_km: float) -> float:
    # 超簡略：遠いほど少しだけ通過空気が増えるイメージ
    return 1.0 + 0.0005*(slant_km-500.0)

# ==== 変換関数（相対レートを出すだけ。絶対値でなく比較目的） ================
def fiber_key_rate(distance_km: np.ndarray) -> np.ndarray:
    """
    ファイバー：T = 10^(-alpha[dB/km] * d / 10)
    ここでは E91 の“1ペアあたり秘密鍵率”に比例とみなして相対値を返す
    """
    trans = 10 ** (-(alpha_db_per_km * distance_km) / 10.0)
    return R0_fiber * trans

def satellite_key_rate(slant_km: np.ndarray) -> np.ndarray:
    """
    衛星（ダウンリンク）：幾何減衰 (d0/d)^2 と、弱い大気減衰を合成（教育用）
    """
    geom = (d0_km / slant_km)**2
    atm  = 10 ** (-(alpha_atm * np.vectorize(airmass)(slant_km)))
    return R0_sat * geom * atm

# ==== 距離軸の用意 ============================================================
fiber_dists = np.linspace(10, 300, 16)     # 10〜300 km
sat_slants  = np.linspace(500, 1200, 15)   # 500〜1200 km

# ==== 計算 ====================================================================
R_fiber = fiber_key_rate(fiber_dists)
R_sat   = satellite_key_rate(sat_slants)

# ==== 図：同じキャンバスに重ね描き（対数Y軸） ================================
plt.figure(figsize=(7.2, 4.6))
# 衛星：丸印
plt.semilogy(sat_slants, R_sat, "o-", label="Satellite downlink (E91, edu.)")
# ファイバー：四角印
plt.semilogy(fiber_dists, R_fiber, "s-", label="Fiber (E91 over fiber, edu.)")

plt.xlabel("Distance (km)  ← Fiber distance / Satellite slant range →")
plt.ylabel("Secret key rate (per pair, relative, log scale)")
plt.title("E91: Satellite vs Fiber (educational comparison)")
plt.grid(True, which="both", alpha=0.4)
plt.legend()
plt.tight_layout()
plt.show()

# ==== 参考：表でざっくり値を表示 =============================================
print("\n=== Sample points (relative rates) ===")
for d, r in zip(fiber_dists[::3], R_fiber[::3]):
    print(f"Fiber {d:4.0f} km : {r:8.2f} (rel.)")
for d, r in zip(sat_slants[::4], R_sat[::4]):
    print(f"Sat   {d:4.0f} km : {r:8.2f} (rel.)")

