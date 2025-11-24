# qkd25_hybrid.py
# 教育用：光ファイバ区間と衛星リンクのスループット（秘密鍵生成率）を簡易モデルで評価・可視化

from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt

# ---- 基本ユーティリティ ----
def h2(p: float) -> float:
    """2値エントロピー h2(p)（p=0 or 1 の端は0にする）"""
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-(p * np.log2(p) + (1 - p) * np.log2(1 - p)))

# ---- ファイバ区間のシークレットレート ----
def simulate_fiber(
    *,
    fiber_len: float,      # km
    L_pulse: float,        # 送信パルスレート [Hz]
    T: float,              # 観測時間 [s]
    p_noise: float = 0.0,  # 実効雑音項（偏極ずれ/位相ゆらぎ等の寄与をまとめたQBER加算）
    alpha_db: float = 0.2, # ファイバ損失[dB/km] 例: 0.2 dB/km @1550nm
    eta_det: float = 0.2,  # 受光検出効率（APDなど）
    p_dark: float = 1e-6,  # ダークカウント確率（1パルスあたり）
    sift_factor: float = 0.5 # BB84の基底一致率 ≈ 1/2
) -> dict:
    """
    ざっくりBB84近似：
      伝送η_ch = 10^(-αL/10)
      シフティング後の受付レート Rsift ≈ L_pulse * sift_factor * η_ch * η_det
      QBER ≈ p_noise + 0.5 * p_dark / (η_ch * η_det + p_dark)
      シークレット/シフテッドビット ≈ max(0, 1 - 2 h2(Q))
      秘密鍵生成率 R = Rsift * (1 - 2 h2(Q))  （Devetak–Winterの単純形）
    """
    eta_ch = 10 ** (-(alpha_db * fiber_len) / 10.0)
    rsift = L_pulse * sift_factor * eta_ch * eta_det

    qber_dark = 0.5 * (p_dark / (eta_ch * eta_det + p_dark))
    q = float(np.clip(p_noise + qber_dark, 0.0, 0.5 - 1e-9))

    r_bit = max(0.0, 1.0 - 2.0 * h2(q))  # Q≲11%で正
    R = rsift * r_bit                    # [bit/s]

    return {
        "eta_ch": eta_ch,
        "QBER": q,
        "R": R,                 # [bit/s]
        "Rsift": rsift,         # [bit/s]
        "bits": R * T,          # 観測時間Tでの積算bit
        "sift_bits": rsift * T,
    }

# ---- 衛星リンクのシークレットレート（簡易FSOモデル）----
def simulate_satellite(
    *,
    slant_range_km: float, # 斜距離 [km]
    L_pulse: float,        # 送信パルスレート [Hz]
    T: float,              # 観測時間 [s]（1パスの可視時間など）
    base_loss_db_500km: float = 40.0,  # 500kmでの基準損失[dB]（口径/ジッタ等を含めた教育用まとめ値）
    eta_rx: float = 0.2,               # 受光/検出の総合効率
    p_noise: float = 0.01,             # 大気・トラッキング等でのQBER加算（衛星は少し大きめに）
    p_dark: float = 1e-6,
    sift_factor: float = 0.5
) -> dict:
    """
    教育用近似：
      500kmで Loss = base_loss_db_500km [dB] とし、距離に伴う 1/R^2 を 20log10(R/500km) で補正。
      η_ch = 10^(-(base + 20log10(R/500km))/10) * η_rx
      以降は fiber と同じ式でRを評価。
    """
    Rm = slant_range_km * 1e3
    loss_db = base_loss_db_500km + 20.0 * np.log10(max(Rm, 1.0) / 5.0e5)  # R=500kmで補正0
    eta_ch = (10 ** (-loss_db / 10.0)) * eta_rx

    rsift = L_pulse * sift_factor * eta_ch
    qber_dark = 0.5 * (p_dark / (eta_ch + p_dark))
    q = float(np.clip(p_noise + qber_dark, 0.0, 0.5 - 1e-9))

    r_bit = max(0.0, 1.0 - 2.0 * h2(q))
    R = rsift * r_bit

    return {
        "eta_ch": eta_ch,
        "QBER": q,
        "R": R,                 # [bit/s]
        "Rsift": rsift,         # [bit/s]
        "bits": R * T,          # T秒での積算bit
        "sift_bits": rsift * T,
    }

# ---- メイン：ハイブリッド（ローカルファイバ＋衛星） ----
def main():
    # --- パラメータ（必要に応じて変更可） ---
    L_pulse = 1e9          # 送信パルスレート [Hz]（教育用に高め）
    T_fiber = 24 * 3600    # ファイバは1日連続 [s]
    T_pass  = 600          # 衛星1パスの可視時間 [s]（約10分）
    passes_per_day = 4     # 1日の可視パス数（例）
    p_noise_fiber = 0.005  # ファイバ側の実効雑音
    p_noise_sat   = 0.02   # 衛星側の実効雑音（少し厳しめ）
    fiber_local   = 10.0   # ローカル拠点間のファイバ距離 [km]

    # --- ローカルファイバの評価 ---
    res_locals = simulate_fiber(
        fiber_len = fiber_local,
        L_pulse   = L_pulse,
        T         = T_fiber,
        p_noise   = p_noise_fiber,
    )

    # --- 衛星の距離掃引（図示用） ---
    sat_range = np.linspace(400, 1200, 17)  # 400〜1200km を等間隔
    R_sat = []
    for r in sat_range:
        out = simulate_satellite(
            slant_range_km = r,
            L_pulse        = L_pulse,
            T              = T_pass,
            p_noise        = p_noise_sat,
        )
        R_sat.append(out["R"])
    R_sat = np.array(R_sat)  # [bit/s]

    # --- 衛星パス当たりの鍵ビット & 日次合計 ---
    # 可視距離の中央値（=プロット範囲の中央値）を代表として積算を見積もる
    mid_r = float(np.median(sat_range))
    rep = simulate_satellite(
        slant_range_km = mid_r,
        L_pulse        = L_pulse,
        T              = T_pass,
        p_noise        = p_noise_sat,
    )
    T_sat_total = rep["bits"] * passes_per_day   # [bit/day]（代表パス×回数）

    R_day_fiber = res_locals["bits"]            # [bit/day]
    R_day_total = R_day_fiber + T_sat_total

    # --- 結果表示 ---
    print("== Hybrid QKD throughput (education) ==")
    print(f"Local fiber  {fiber_local:.1f} km : {R_day_fiber:.1e} bits/day")
    print(f"Satellite    ~{mid_r:.0f} km x{passes_per_day} passes : {T_sat_total:.1e} bits/day")
    print(f"Day total: {R_day_total:.1e} bits/day")

    # --- 図：衛星距離 vs 秘密鍵生成率（対数スケール） ---
    plt.figure()
    plt.semilogy(sat_range, R_sat, 'o-', label="Satellite downlink (R_sec)")
    plt.xlabel("Satellite slant range (km)")
    plt.ylabel("Secret key rate (per pair, log)")
    plt.title("E91 over Satellite Link (educational model)")
    plt.grid(True, which="both")
    plt.legend()

    plt.show()

# エントリポイント
if __name__ == "__main__":
    main()

