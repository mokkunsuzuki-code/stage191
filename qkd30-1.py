# qkd30_jp.py  — 段階30（日本語ラベル版）
from __future__ import annotations
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

# ====== 日本語フォントを指定 ======
rcParams['font.family'] = 'Hiragino Sans'  # Macの場合
# Windowsの人は → rcParams['font.family'] = 'Meiryo'

# ========= 配列対応の正規CDF =========
def norm_cdf(x):
    x = np.asarray(x, dtype=float)
    erf_vec = np.vectorize(math.erf)
    return 0.5 * (1.0 + erf_vec(x / np.sqrt(2.0)))

# ========= 天候モデル =========
def at_least_one_clear_once(p_list, rho: float, rng: np.random.Generator) -> bool:
    p = np.clip(np.asarray(p_list, dtype=float), 0.0, 1.0)
    M = p.size
    if M == 0:
        return False

    rho_min = -1.0 / (M - 1) + 1e-9 if M > 1 else -0.999999
    rho = float(np.clip(rho, rho_min, 0.999999))

    Sigma = np.full((M, M), rho, dtype=float)
    np.fill_diagonal(Sigma, 1.0)

    eps = 1e-12
    try:
        L = np.linalg.cholesky(Sigma)
    except np.linalg.LinAlgError:
        L = np.linalg.cholesky(Sigma + eps * np.eye(M))

    z0 = rng.standard_normal(M)
    Z  = L @ z0
    U  = norm_cdf(Z)

    clear_vec = (U < p)
    return bool(np.any(clear_vec))

# ========= CHSHゲート =========
def chsh_pass_once(qber: float, n_pairs: int, rng: np.random.Generator) -> bool:
    if n_pairs <= 0:
        return False
    S_thr = 2.0
    S_exp = 2.0 * np.sqrt(2.0) * max(0.0, (1.0 - 2.0 * qber))
    z = (S_exp - S_thr) * np.sqrt(float(n_pairs))
    p_pass = float(np.clip(norm_cdf(z), 0.0, 1.0))
    return bool(rng.random() < p_pass)

# ========= 定数 =========
DAYS               = 30
DT_SEC             = 60
STEPS_PER_DAY      = int(24*3600 // DT_SEC)

FIBER_BPS          = 5e6
SAT_BPS            = 50e6
SAT_QBER           = 0.03
CONS_BPS           = 10e6

N_SAT              = 3
PASSES_PER_DAY     = 4
PASS_TIME_SEC      = 600
PASS_DUTY          = (PASSES_PER_DAY * PASS_TIME_SEC) / (24*3600)
PASS_PROB_PER_STEP = PASS_DUTY

GROUND_P_LIST      = [0.5, 0.5, 0.5]
WEATHER_RHO        = 0.5

CHSH_TEST_FRACTION = 0.2
BUFFER_CAP_BITS    = int(2e11)
INIT_BUFFER_BITS   = 0

RNG_SEED           = 30

# ========= シミュレーション =========
def simulate():
    rng = np.random.default_rng(RNG_SEED)

    prod_fiber_day      = np.zeros(DAYS, dtype=np.int64)
    prod_sat_day        = np.zeros(DAYS, dtype=np.int64)
    cons_day            = np.zeros(DAYS, dtype=np.int64)
    outage_minutes_day  = np.zeros(DAYS, dtype=np.int32)
    min_buffer_day      = np.zeros(DAYS, dtype=np.int64)

    buffer_bits = INIT_BUFFER_BITS

    for d in range(DAYS):
        min_buf = BUFFER_CAP_BITS
        prod_fiber = 0
        prod_sat   = 0
        cons_total = 0
        outage_min = 0

        for _ in range(STEPS_PER_DAY):
            fiber_bits = int(FIBER_BPS * DT_SEC)

            active_any_sat = np.any(rng.random(N_SAT) < PASS_PROB_PER_STEP)
            clear_any = at_least_one_clear_once(GROUND_P_LIST, WEATHER_RHO, rng)

            if active_any_sat and clear_any:
                total_sat_bits = int(SAT_BPS * DT_SEC)
                test_bits      = int(total_sat_bits * CHSH_TEST_FRACTION)
                key_bits_base  = total_sat_bits - test_bits

                n_test_pairs = test_bits
                chsh_ok = chsh_pass_once(SAT_QBER, n_test_pairs, rng)

                sat_bits = key_bits_base if chsh_ok else 0
            else:
                sat_bits = 0

            cons_bits = int(CONS_BPS * DT_SEC)

            produced    = fiber_bits + sat_bits
            buffer_bits = min(BUFFER_CAP_BITS, max(0, buffer_bits + produced - cons_bits))

            prod_fiber += fiber_bits
            prod_sat   += sat_bits
            cons_total += cons_bits
            if buffer_bits == 0 and produced < cons_bits:
                outage_min += 1

            if buffer_bits < min_buf:
                min_buf = buffer_bits

        prod_fiber_day[d]     = prod_fiber
        prod_sat_day[d]       = prod_sat
        cons_day[d]           = cons_total
        outage_minutes_day[d] = outage_min
        min_buffer_day[d]     = min_buf

    return prod_fiber_day, prod_sat_day, cons_day, outage_minutes_day, min_buffer_day

# ========= 実行 & グラフ =========
def main():
    prod_fiber_day, prod_sat_day, cons_day, outage_minutes_day, min_buffer_day = simulate()

    total_prod_fiber = int(prod_fiber_day.sum())
    total_prod_sat   = int(prod_sat_day.sum())
    total_cons       = int(cons_day.sum())
    total_out_min    = int(outage_minutes_day.sum())

    days = np.arange(1, DAYS+1)
    fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    # 日本語ラベル
    ax[0].plot(days, prod_fiber_day/1e9, label="光ファイバー生産量 [Gbit/日]")
    ax[0].plot(days, prod_sat_day/1e9,   label="衛星（CHSHゲート通過） [Gbit/日]")
    ax[0].plot(days, cons_day/1e9,       label="消費量 [Gbit/日]")
    ax[0].set_ylabel("Gbit/日")
    ax[0].set_title("量子鍵配送シミュレーション（30日間）")
    ax[0].grid(True); ax[0].legend(loc="upper right")

    ax[1].step(days, outage_minutes_day, where='mid', label="停止時間 [分/日]")
    ax[1].set_xlabel("日数")
    ax[1].set_ylabel("分")
    ax[1].grid(True); ax[1].legend(loc="upper right")

    fig.suptitle("日次の鍵生成量と停止時間（CHSHゲート）")
    plt.tight_layout(); plt.show()

    # KPIを日本語で表示
    print(f"\n=== KPI（{DAYS}日間, CHSHゲートあり） ===")
    print(f"光ファイバー生産量合計: {total_prod_fiber/1e9:.3f} Gbit")
    print(f"衛星生産量合計        : {total_prod_sat/1e9:.3f} Gbit")
    print(f"消費合計              : {total_cons/1e9:.3f} Gbit")
    print(f"停止時間合計          : {total_out_min} 分")
    print(f"1日のバッファ最小値の中央値: {np.median(min_buffer_day)/1e6:.1f} Mbit")

if __name__ == "__main__":
    main()

