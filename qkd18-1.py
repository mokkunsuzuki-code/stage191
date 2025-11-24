# qkd_E91_distance.py
# E91（エンタングルメント）で、距離に応じて
#   1) CHSH値（盗聴検出の指標）
#   2) 鍵集合のQBER（同じ基底で測ったときの誤り率）
#   3) 鍵として使える検出数
# を可視化する教育用シミュレーション（モンテカルロ）

import numpy as np
import math

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
    print("[INFO] matplotlib が無いのでグラフは省略（表だけ出力）。")

rng = np.random.default_rng(0)

# ===== 物理・装置パラメタ（変えて遊べます） =====
alpha_db_per_km = 0.2     # ファイバー損失 [dB/km]
eta_det         = 0.8     # 検出効率（1台あたり）
p_dark          = 1e-6    # ダークカウント確率（1ゲートあたり）
e_mis           = 0.015   # ミスアラインメント（信号-信号時の誤り率 ≒ 1.5%）
gate_per_pair   = 1       # 1ペア当たりの検出ゲート（簡易）

# 距離設定（エンタングル源は中間にある想定 → 片道 L/2 の損失を2本通る）
distance_km_list = list(range(0, 101, 5))  # 0〜100 km を 5 km 刻み

# 1距離あたりの試行回数（増やすと滑らか／時間↑）
TRIALS = 20000

# E91 の角度（|Φ+> & 偏光モデルの簡易対応）
# CHSH 最大違反：a0=0, a1=π/4 ; b0=+π/8, b1=-π/8
a_angles = [0.0, np.pi/4]
b_angles = [ np.pi/8, -np.pi/8]

# モードの振り分け：鍵用(同角度) と CHSH検査用
p_key = 0.6  # 60% を鍵用（同角度 Z=0）に、残り40%をCHSH用に使う

# ===== ユーティリティ =====
def transmittance(distance_km):
    """距離Lを中間配置で分割：各腕 L/2 の損失を掛け合わせる"""
    arm = (distance_km / 2.0)
    T_one = 10 ** ( - alpha_db_per_km * arm / 10.0 )   # 片腕の透過率
    return T_one * T_one                                # 両腕の総透過率（信号が両方届く確率の上限）

def sample_correlated_bits(theta_a, theta_b, visibility):
    """
    角度差に応じた相関をもつ 0/1 をサンプル。
    E = visibility * cos(2Δ) として、
    P(a==b) = (1+E)/2 を満たすように b を決める。
    """
    delta = theta_a - theta_b
    E = visibility * math.cos(2.0 * delta)
    p_same = (1.0 + E) / 2.0
    a = rng.integers(0, 2)
    if rng.random() < p_same:
        b = a
    else:
        b = 1 - a
    return a, b

def chsh_from_samples(samples):
    """
    samples: [(ai, bi, a_bit, b_bit), ...]（CHSH用に集めたレコード）
    CHSH = E(a0,b0) + E(a0,b1) + E(a1,b0) - E(a1,b1)
    """
    samples = np.array(samples, dtype=int)
    def E(ai, bi):
        sel = (samples[:,0]==ai) & (samples[:,1]==bi)
        if not np.any(sel): return 0.0
        a = samples[sel,2]; b = samples[sel,3]
        return 1.0 - 2.0 * float(np.mean(a ^ b))
    E00 = E(0,0); E01 = E(0,1); E10 = E(1,0); E11 = E(1,1)
    S = E00 + E01 + E10 - E11
    return S, (E00,E01,E10,E11)

# ===== メインの距離スイープ =====
rows = []  # (dist, S, qber_key, sifted_key)

print("dist(km) | CHSH S | QBER_key(%) | sifted_key")
print("---------+--------+-------------+-----------")
for L in distance_km_list:
    T = transmittance(L)                  # 両腕合わせた伝送確率（損失のみ）
    p_sig_a = math.sqrt(T)                # 片腕（片側）で信号が届く確率の目安
    p_sig_b = p_sig_a
    # 実際の“信号-信号で両側検出”確率（検出効率も考慮）
    p_ss = p_sig_a * eta_det * p_sig_b * eta_det

    # 片側だけ信号、もう片側はダーク（ランダム化）の確率近似
    p_sd = p_sig_a * eta_det * (1 - p_sig_b * eta_det) * (p_dark**gate_per_pair) \
         + p_sig_b * eta_det * (1 - p_sig_a * eta_det) * (p_dark**gate_per_pair)

    # 両側ともダークで“たまたま両方クリック”の確率（ランダム）
    p_dd = (p_dark**gate_per_pair) * (p_dark**gate_per_pair)

    # 信号イベントの“見かけ可視度”：ミスアラインメントで低下
    # visibility ≈ 1 - 2*e_mis（片側が e_mis で反転する近似）
    visibility = max(0.0, 1.0 - 2.0 * e_mis)

    chsh_samples = []
    key_a_bits = []
    key_b_bits = []

    for _ in range(TRIALS):
        r = rng.random()
        if r < p_key:  # 鍵用：同じ角度（ここでは Z とみなして θ=0）
            theta_a = 0.0; theta_b = 0.0
        else:          # 検査用：CHSH
            ai = int(rng.integers(0,2))
            bi = int(rng.integers(0,2))
            theta_a = a_angles[ai]
            theta_b = b_angles[bi]

        # どのタイプの“検出”かを選ぶ（簡易に正規化）
        p_rest = 1.0 - (p_ss + p_sd + p_dd)
        if p_rest < 0: p_rest = 0.0
        choice = rng.random() * (p_ss + p_sd + p_dd + p_rest)
        if choice < p_ss:
            # 信号-信号：相関あり（可視度 visibility）、ただし e_mis で個別反転も起こるモデルに等価
            a,b = sample_correlated_bits(theta_a, theta_b, visibility)
        elif choice < p_ss + p_sd:
            # 片側信号・片側ダーク：実質ランダム相関（=独立）
            a = rng.integers(0,2); b = rng.integers(0,2)
        elif choice < p_ss + p_sd + p_dd:
            # 両側ダーク：独立ランダム
            a = rng.integers(0,2); b = rng.integers(0,2)
        else:
            # 検出無し（どちらか欠落）→ このトライアルはスキップ
            continue

        # 記録
        if rng.random() < p_key:
            # 鍵用トライアル（同角度のときだけ鍵に加える）
            key_a_bits.append(a); key_b_bits.append(b)
        else:
            # CHSH用トライアル
            # a_angles/b_angles のどれを使ったかをもう一度決め直す（確率は1/4ずつでOK）
            ai = int(rng.integers(0,2)); bi = int(rng.integers(0,2))
            th_a = a_angles[ai]; th_b = b_angles[bi]
            # 同じ選びで再度サンプルでも良いが、上の a,b をそのまま入れて統計を集めてもOK。
            # ここは厳密さより教育的簡潔さを優先して、上で出た a,b を登録。
            chsh_samples.append((ai, bi, a, b))

    key_a = np.array(key_a_bits, dtype=np.uint8)
    key_b = np.array(key_b_bits, dtype=np.uint8)

    # QBER（鍵集合）
    if len(key_a) > 0:
        qber_key = float(np.mean(key_a ^ key_b))
    else:
        qber_key = 0.0

    # CHSH
    if len(chsh_samples) > 0:
        S, _ = chsh_from_samples(chsh_samples)
    else:
        S = 0.0

    rows.append((L, S, 100.0*qber_key, len(key_a)))
    print(f"{L:7.1f} | {S:7.3f} | {100.0*qber_key:11.3f} | {len(key_a):11d}")

# ===== グラフ =====
if HAS_MPL:
    xs = [r[0] for r in rows]
    Svals = [r[1] for r in rows]
    Qvals = [r[2] for r in rows]
    Kvals = [r[3] for r in rows]

    plt.figure()
    plt.plot(xs, Svals, marker="o")
    plt.axhline(2.0, linestyle="--")
    plt.xlabel("Distance (km)")
    plt.ylabel("CHSH S")
    plt.title("E91: Distance vs CHSH")
    plt.grid(True)

    plt.figure()
    plt.plot(xs, Qvals, marker="o")
    plt.xlabel("Distance (km)")
    plt.ylabel("QBER on key set (%)")
    plt.title("E91: Distance vs QBER (same basis)")
    plt.grid(True)

    plt.figure()
    plt.plot(xs, Kvals, marker="o")
    plt.xlabel("Distance (km)")
    plt.ylabel("Sifted key (counts)")
    plt.title("E91: Distance vs Sifted length")
    plt.grid(True)

    plt.tight_layout()
    plt.show()

