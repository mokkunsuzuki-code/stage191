# qkd29.py  —  段階29：ファイバ + 衛星 + 天候相関(ガウス・コピュラ) + バッファ + 消費
from __future__ import annotations
import math
import numpy as np
import matplotlib.pyplot as plt

# ========= 配列対応の正規CDF（erfの配列化が肝） =========
def norm_cdf(x):
    """標準正規Φ(x)。math.erfはスカラー専用なのでベクトル化して配列OKにする。"""
    x = np.asarray(x, dtype=float)
    erf_vec = np.vectorize(math.erf)
    return 0.5 * (1.0 + erf_vec(x / np.sqrt(2.0)))

# ========= 天候：相関付き 1 ステップの「少なくとも1局晴れ」 =========
def at_least_one_clear_once(p_list, rho: float, rng: np.random.Generator) -> bool:
    p = np.clip(np.asarray(p_list, dtype=float), 0.0, 1.0)
    M = p.size
    if M == 0:
        return False

    # 一様相関行列が半正定値になる範囲にクリップ（下限は -1/(M-1)）
    rho_min = -1.0 / (M - 1) + 1e-9 if M > 1 else -0.999999
    rho = float(np.clip(rho, rho_min, 0.999999))

    # 相関行列 Σ（対角=1, オフ対角=rho）
    Sigma = np.full((M, M), rho, dtype=float)
    np.fill_diagonal(Sigma, 1.0)

    # コレスキー分解（微小εで安定化）
    eps = 1e-12
    try:
        L = np.linalg.cholesky(Sigma)
    except np.linalg.LinAlgError:
        L = np.linalg.cholesky(Sigma + eps * np.eye(M))

    # 相関付き標準正規ベクトル Z ~ N(0, Σ)
    z0 = rng.standard_normal(M)
    Z  = L @ z0
    U  = norm_cdf(Z)           # 相関あり一様乱数（0..1）

    clear_vec = (U < p)        # 各局：U_i < p_i で晴れ
    return bool(np.any(clear_vec))

# ========= シナリオ定数 =========
DAYS               = 30
DT_SEC             = 60                    # 1分ステップ
STEPS_PER_DAY      = int(24*3600 // DT_SEC)

FIBER_BPS          = 5e6                   # ファイバ鍵生成レート [bit/s]
SAT_BPS            = 50e6                  # 衛星鍵生成レート [bit/s]（可視＋晴天）

CONS_BPS           = 10e6                  # 消費レート [bit/s]

N_SAT              = 3
PASSES_PER_DAY     = 4
PASS_TIME_SEC      = 600
PASS_DUTY          = (PASSES_PER_DAY * PASS_TIME_SEC) / (24*3600)
PASS_PROB_PER_STEP = PASS_DUTY             # ベルヌーイ近似：各分で稼働している確率

GROUND_P_LIST      = [0.5, 0.5, 0.5]       # 各地上局の晴れ確率
WEATHER_RHO        = 0.5                   # 天候相関係数（一様相関）

BUFFER_CAP_BITS    = int(2e11)             # バッファ上限
INIT_BUFFER_BITS   = 0

RNG_SEED           = 29

# ========= メイン・シミュレーション =========
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
            # 生産（ファイバは常時）
            fiber_bits = int(FIBER_BPS * DT_SEC)

            # 衛星：N機のうち少なくとも1機が稼働
            active_any_sat = np.any(rng.random(N_SAT) < PASS_PROB_PER_STEP)
            # 天候：少なくとも1局晴れ
            clear_any = at_least_one_clear_once(GROUND_P_LIST, WEATHER_RHO, rng)

            sat_bits = int(SAT_BPS * DT_SEC) if (active_any_sat and clear_any) else 0

            # 消費
            cons_bits = int(CONS_BPS * DT_SEC)

            # バッファ更新（上限/下限のクリップ）
            produced   = fiber_bits + sat_bits
            buffer_bits = min(BUFFER_CAP_BITS, max(0, buffer_bits + produced - cons_bits))

            # 統計
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

# ========= 実行 & KPI =========
def main():
    prod_fiber_day, prod_sat_day, cons_day, outage_minutes_day, min_buffer_day = simulate()

    total_prod_fiber = int(prod_fiber_day.sum())
    total_prod_sat   = int(prod_sat_day.sum())
    total_cons       = int(cons_day.sum())
    total_out_min    = int(outage_minutes_day.sum())

    print("\n=== KPI (30日まとめ) ===")
    print(f"Produced (fiber): {total_prod_fiber/1e9:.3f} Gbit")
    print(f"Produced (sat)  : {total_prod_sat/1e9:.3f} Gbit")
    print(f"Consumed total  : {total_cons/1e9:.3f} Gbit")
    print(f"Outage minutes  : {total_out_min} min")
    print(f"Days with ANY outage: {(outage_minutes_day>0).sum()} / {DAYS}")
    print(f"Mean of daily min buffer: {np.mean(min_buffer_day)/1e6:.1f} Mbit")

    print("\n--- Parameters ---")
    print(f"N_sat={N_SAT}, passes/day/sat={PASSES_PER_DAY}, pass_time={PASS_TIME_SEC}s")
    print(f"Ground p list={GROUND_P_LIST}, rho={WEATHER_RHO}")
    print(f"Fiber_bps={FIBER_BPS:.0f}, Sat_bps={SAT_BPS:.0f}, Cons_bps={CONS_BPS:.0f}")
    print(f"Buffer cap={BUFFER_CAP_BITS/1e9:.2f} Gbit")

    # 日ごとの簡易グラフ（任意）
    days = np.arange(1, DAYS+1)
    plt.figure(figsize=(10,5))
    plt.plot(days, prod_fiber_day/1e9, label="Fiber produced [Gbit/day]")
    plt.plot(days, prod_sat_day/1e9,   label="Sat produced [Gbit/day]")
    plt.plot(days, cons_day/1e9,       label="Consumed [Gbit/day]")
    plt.step(days, outage_minutes_day, where='mid', label="Outage minutes [min/day]")
    plt.xlabel("Day"); plt.grid(True); plt.legend(); plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()

