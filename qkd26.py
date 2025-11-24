# qkd26_hybrid.py
# 段階26: ハイブリッドQKD (ファイバ + 衛星リンク + 天候可視性)

import numpy as np
import matplotlib.pyplot as plt

# 2値エントロピー
def h2(p: float) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(p * np.log2(p) + (1 - p) * np.log2(1 - p))

# ------------------------------------------------
# シミュレーション関数
# ------------------------------------------------
def simulate(kind: str, length_km: float, R_pulse: float, T: float, p_noise: float) -> dict:
    """
    kind = "fiber" または "sat"
    length_km: ファイバ長[km] or 衛星斜距離[km]
    R_pulse: 送信パルスレート[Hz]
    T: 観測時間[s]
    p_noise: 実効ノイズ（QBER加算）
    """

    # 共通パラメータ
    sift_factor = 0.5    # BB84基底一致率
    p_dark = 1e-6        # ダークカウント確率

    if kind == "fiber":
        alpha_db = 0.2    # dB/km
        eta_det = 0.2
        eta_ch = 10 ** (-(alpha_db * length_km) / 10.0)
        rsift = R_pulse * sift_factor * eta_ch * eta_det
        qber_dark = 0.5 * (p_dark / (eta_ch * eta_det + p_dark))

    elif kind == "sat":
        base_loss_db_500km = 40.0
        eta_rx = 0.2
        Rm = length_km * 1e3
        loss_db = base_loss_db_500km + 20.0 * np.log10(max(Rm, 1.0) / 5.0e5)
        eta_ch = (10 ** (-loss_db / 10.0)) * eta_rx
        rsift = R_pulse * sift_factor * eta_ch
        qber_dark = 0.5 * (p_dark / (eta_ch + p_dark))

    else:
        raise ValueError("kind must be 'fiber' or 'sat'")

    q = np.clip(p_noise + qber_dark, 0.0, 0.5 - 1e-9)
    r_bit = max(0.0, 1.0 - 2.0 * h2(q))
    R = rsift * r_bit

    return {
        "QBER": q,
        "R": R,         # [bit/s]
        "Rsift": rsift,
        "bits": R * T,  # 秘密鍵ビット数
    }

# ------------------------------------------------
# メイン処理
# ------------------------------------------------
def main():
    # 共通パラメータ
    R_pulse = 1e9
    p_noise = 0.03

    # ファイバ (常時利用)
    fiber_local = 50  # km
    res_local = simulate(
        kind="fiber", length_km=fiber_local,
        R_pulse=R_pulse, T=1.0, p_noise=p_noise
    )
    R_fiber = res_local["R"]

    # 衛星リンク (都市間)
    sat_range = 1000  # km
    res_sat = simulate(
        kind="sat", length_km=sat_range,
        R_pulse=R_pulse, T=1.0, p_noise=p_noise
    )
    R_sat = res_sat["R"]

    # 衛星パスモデル
    pass_time = 300        # 1パスの時間 [s]
    passes_per_day = 6     # 1日のパス数
    T_pass_total = pass_time * passes_per_day

    # 可用性（天候）
    p_clear = 0.5  # 晴天率50%
    T_eff = T_pass_total * p_clear

    # 1日のスループット
    R_day_fiber = R_fiber * 86400.0
    R_day_sat   = R_sat   * T_eff
    R_day_total = R_day_fiber + R_day_sat

    # 結果表示
    print("=== Hybrid QKD throughput (段階26) ===")
    print(f"Fiber {fiber_local} km : {R_day_fiber:.2e} bits/day")
    print(f"Satellite {sat_range} km (×{passes_per_day}, clear={p_clear*100:.0f}%) : {R_day_sat:.2e} bits/day")
    print(f"Total per day : {R_day_total:.2e} bits/day")

    # 簡易プロット
    plt.bar(["Fiber/day", "Satellite/day", "Total/day"],
            [R_day_fiber, R_day_sat, R_day_total])
    plt.ylabel("Secret key bits per day (log scale)")
    plt.yscale("log")
    plt.title("Hybrid QKD Throughput (Fiber + Satellite, 段階26)")
    plt.show()

# ------------------------------------------------
if __name__ == "__main__":
    main()

