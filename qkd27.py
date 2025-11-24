# qkd27_realistic.py  — 実運用スケールの数値で衛星E91と光ファイバーを比較（教育用モデル）
# 必要: numpy, matplotlib
import numpy as np

try:
    import matplotlib.pyplot as plt
except Exception as e:
    raise SystemExit("matplotlib が必要です: pip install matplotlib") from e

# ==========================
# 現実運用に近い“目安”パラメータ
# ==========================
# --- 衛星（LEO, ダウンリンク E91想定） ---
N_SAT_MAX         = 24         # 比較する最大衛星数
P_CLEAR           = 0.50       # 晴天率（50%） ← 地域で変えてOK（0.2〜0.8あたり）
PASSES_PER_DAY    = 4.0        # 1衛星・1局あたり平均パス回数/日（中緯度で3〜6のことが多い）
PASS_DURATION_SEC = 350        # 1パス平均の有効通信秒（300〜600s 程度）
SECRET_RATE_AVAIL = 2_000      # “リンクが成立中”の最終鍵生成レート [bits/s]（1〜5 kbpsクラス）

# --- 地上ファイバー（都市圏・デコイBB84など） ---
# 例: 50km クラスのメトロ区間で最終鍵 1 Mbps オーダーが実用域で出るケース
FIBER_SECRET_RATE = 1_000_000  # [bits/s] 最終鍵レート（例: 1 Mbps）
FIBER_HOURS_PER_DAY = 24       # 連続運用（メンテ時間を引きたいならここを減らす）

# --- 可視化・算出条件 ---
N_SAT_LIST = list(range(1, N_SAT_MAX + 1))
RANDOM_SEED = 0

# ==========================
# 計算関数
# ==========================
def satellite_bits_per_day(n_sat: int,
                           p_clear=P_CLEAR,
                           passes_per_day=PASSES_PER_DAY,
                           pass_dur=PASS_DURATION_SEC,
                           secret_rate=SECRET_RATE_AVAIL) -> float:
    """
    衛星数 n_sat のとき、1地上局あたりの 1日合計“最終鍵ビット数”を計算。
    educationモデル：重なりや運用制約は平均化して、期待値で単純加算。
    """
    # 1衛星あたりの“良好な”パス本数（晴天・夜間・可視などをまとめて p_clear で近似）
    good_passes = passes_per_day * p_clear
    # 1衛星あたり 1日最終鍵ビット
    bits_per_sat = good_passes * pass_dur * secret_rate
    return n_sat * bits_per_sat

def fiber_bits_per_day(secret_rate=FIBER_SECRET_RATE, hours=FIBER_HOURS_PER_DAY) -> float:
    """
    メトロ級ファイバーリンクの 1日最終鍵ビット数（連続運用想定）
    """
    return secret_rate * hours * 3600.0

# ==========================
# メイン：計算 & 可視化
# ==========================
def main():
    # 1) 衛星コンステレーションのスケーリング（図1）
    sat_daily = [satellite_bits_per_day(n) for n in N_SAT_LIST]

    # 2) 代表ケースの棒グラフ（図2）
    N_SAT_PICK = 12    # ここを変えると任意台数の比較が見れる
    sat_day_pick = satellite_bits_per_day(N_SAT_PICK)
    fib_day = fiber_bits_per_day()
    total_day = sat_day_pick + fib_day

    # ---- 表示（図1：衛星数スイープ） ----
    plt.figure(figsize=(7,5))
    plt.plot(N_SAT_LIST, sat_daily, marker="o", label=f"Satellite downlink E91 (p_clear={P_CLEAR:.0%})")
    plt.yscale("log")
    plt.xlabel("Number of satellites")
    plt.ylabel("Daily secret key [bits/day] (log scale)")
    plt.title("Constellation effect on QKD throughput (realistic order, edu.)")
    plt.grid(True, which="both", linestyle=":")
    plt.legend()

    # ---- 表示（図2：棒グラフ） ----
    labels = [f"Fiber/day\n(50 km)", f"Satellite/day\n(N_sat={N_SAT_PICK})", "Total/day"]
    values = [fib_day, sat_day_pick, total_day]

    plt.figure(figsize=(7,5))
    bars = plt.bar(labels, values)
    plt.yscale("log")
    plt.ylabel("Secret key bits per day (log scale)")
    plt.title("Hybrid QKD Throughput (Fiber + Satellite, realistic order)")
    # 値を吹き出し表示（見やすさ用）
    for b, v in zip(bars, values):
        plt.text(b.get_x() + b.get_width()/2, v, f"{v:.2e}", ha="center", va="bottom", fontsize=9)
    plt.grid(True, axis="y", which="both", linestyle=":")

    # ---- コンソール出力（数値） ----
    print("\n=== Parameters (realistic-order, editable) ===")
    print(f"P_CLEAR={P_CLEAR:.0%}, PASSES_PER_DAY≈{PASSES_PER_DAY}, PASS_DURATION_SEC≈{PASS_DURATION_SEC}s, "
          f"SECRET_RATE_AVAIL≈{SECRET_RATE_AVAIL} bits/s")
    print(f"Fiber SECRET_RATE≈{FIBER_SECRET_RATE} bits/s over {FIBER_HOURS_PER_DAY} h/day")
    print("\n=== Results ===")
    print("Satellites | bits/day (sat constellation)")
    for n, v in zip(N_SAT_LIST, sat_daily):
        print(f"{n:>3d}        | {v: .3e} bits/day")
    print(f"\nFiber/day      = {fib_day: .3e} bits/day")
    print(f"Satellite/day  = {sat_day_pick: .3e} bits/day  (N_sat={N_SAT_PICK})")
    print(f"Total/day      = {total_day: .3e} bits/day\n")

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()

