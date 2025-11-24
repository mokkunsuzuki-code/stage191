# -*- coding: utf-8 -*-
"""
段階29 改良版：
- 衛星のアウト時間（緑）を日ごとにゆらぐ（天気のゆらぎを導入）
- 鍵バッファ残量（青点線）を同じグラフに追加
- 左Y軸: Gbit/day（Fiber/Sat/Consume/Buffer）
- 右Y軸: Outage minutes（min/day）
"""

import numpy as np
import matplotlib.pyplot as plt

# ===== パラメータ（必要なら調整OK） =====
DAYS = 30
SEED = 42
rng = np.random.default_rng(SEED)

# 光ファイバー（日次の生産量, Gbit/day）
FIBER_MEAN = 450.0         # 平均
FIBER_JITTER = 40.0        # ±ゆらぎ幅（均一乱数）

# 衛星（日次の最大クリア時生産量, Gbit/day）
SAT_CLEAR_PROD = 250.0     # 1日フルに晴れていたときの目安生産
MEAN_P_CLEAR = 0.50        # 平均晴天率（50%）
SIGMA_P_CLEAR = 0.15       # 日ごとの晴天率のゆらぎ（正規分布, 0〜1にクリップ）
MAX_SAT_MIN = 300.0        # 1日に衛星が鍵配送可能な“最大”分数（教育用仮定）

# 需要（消費, Gbit/day）
CONS_MEAN = 550.0
CONS_JITTER = 120.0

# バッファ初期値（Gbit）
BUF0 = 0.0
BUF_MAX = 10_000.0         # 教育用上限（無限でもOK。見やすさ用）

# ===== データ生成 =====
days = np.arange(1, DAYS + 1)

# Fiber 生産（ゆらぐが大きくは変わらない）
fiber_prod = FIBER_MEAN + rng.uniform(-FIBER_JITTER, +FIBER_JITTER, size=DAYS)
fiber_prod = np.clip(fiber_prod, 0.0, None)

# その日の晴天率を正規分布からサンプル → [0,1] にクリップ
p_clear_daily = np.clip(rng.normal(MEAN_P_CLEAR, SIGMA_P_CLEAR, size=DAYS), 0.0, 1.0)

# Outage（分/日）＝（曇り・雨の割合）× 最大稼働分数
outage_min = (1.0 - p_clear_daily) * MAX_SAT_MIN

# Sat 生産（晴天率に比例）
sat_prod = SAT_CLEAR_PROD * p_clear_daily

# 需要（消費）
consume = CONS_MEAN + rng.uniform(-CONS_JITTER, +CONS_JITTER, size=DAYS)
consume = np.clip(consume, 0.0, None)

# ===== 鍵バッファ残量（“貯金”）の推移 =====
buffer = np.zeros(DAYS, dtype=float)
buf = BUF0
for i in range(DAYS):
    buf = buf + fiber_prod[i] + sat_prod[i] - consume[i]
    # マイナスは 0 に（使い切ったらゼロ）
    buf = max(0.0, buf)
    # 上限も設定（教育用）
    buf = min(buf, BUF_MAX)
    buffer[i] = buf

# ===== 集計を少し表示 =====
print("=== 日次サマリ（先頭5日） ===")
for i in range(min(5, DAYS)):
    print(f"Day {i+1:2d} | Fiber={fiber_prod[i]:6.1f} | Sat={sat_prod[i]:6.1f} "
          f"| Cons={consume[i]:6.1f} | Buffer={buffer[i]:7.1f} | Outage={outage_min[i]:6.1f} min")

print("\n合計 生産: (Fiber) {:.1f} Gbit, (Sat) {:.1f} Gbit / 合計 消費 {:.1f} Gbit".format(
    fiber_prod.sum(), sat_prod.sum(), consume.sum()))
print("最終バッファ残量: {:.1f} Gbit".format(buffer[-1]))

# ===== 可視化 =====
fig, ax_left = plt.subplots(figsize=(9, 5))

# 左Y軸（Gbit/day）
ax_left.plot(days, fiber_prod, label="Fiber produced [Gbit/day]", color="#1f77b4", linewidth=2)
ax_left.plot(days, sat_prod,   label="Sat produced [Gbit/day]",   color="#ff7f0e", linewidth=2)
ax_left.plot(days, consume,    label="Consumed [Gbit/day]",       color="#d62728", linewidth=2)
# バッファは折れ線（同じ左軸にGbitで載せる）
ax_left.plot(days, buffer,     label="Key buffer [Gbit] (stock)", color="#2ca02c", linestyle="--", linewidth=2)

ax_left.set_xlabel("Day")
ax_left.set_ylabel("Gbit / day (Production / Consumption) & Gbit (Buffer)")
ax_left.set_xticks(days[::2])
ax_left.grid(True, alpha=0.3)

# 右Y軸（分/日）でアウト時間を折れ線で
ax_right = ax_left.twinx()
ax_right.plot(days, outage_min, label="Outage minutes [min/day]", color="#2ca02c", linewidth=2)
ax_right.set_ylabel("Outage minutes [min/day]")

# 凡例（左右軸をまとめる）
lines_left,  labels_left  = ax_left.get_legend_handles_labels()
lines_right, labels_right = ax_right.get_legend_handles_labels()
ax_left.legend(lines_left + lines_right, labels_left + labels_right, loc="upper left")

plt.title("Fiber/Sat production, Consumption, Buffer, and Outage (daily)")
plt.tight_layout()
plt.show()

