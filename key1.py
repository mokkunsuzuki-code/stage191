# e91_stage1_2.py
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# =========================
# パラメータ
# =========================
N_pairs    = 4000           # 生成するEPRペア総数
test_ratio = 0.5            # CHSHテストに回す割合（残りはキー生成）
rng        = np.random.default_rng(42)

# 角度設定（偏光モデル想定；測定は Bloch球のY軸周り回転→Z測定）
# |Φ+> を使うと、θa = θb のとき強い正の相関が出る（キー生成に向く）
# CHSH最大化：a0=0, a1=π/4, b0=π/8, b1=−π/8 で S=2√2 を達成（理想）
a0 = 0.0
a1 = np.pi/4
b0 = np.pi/8
b1 = -np.pi/8

# キー生成用の角度（両者同じ）
theta_key_a = 0.0
theta_key_b = 0.0

sim = AerSimulator()

def measure_epr_once(theta_a: float, theta_b: float) -> tuple[int, int]:
    """
    もつれ状態 |Φ+> を作り、アリス/ボブがそれぞれ角度 theta_a, theta_b の基底で測定。
    実装：RY(-2θ) をかけて Z測定（偏光の 2θ が効く形）
    戻り値： (bit_a, bit_b) 各 {0,1}
    """
    qc = QuantumCircuit(2, 2)

    # |Φ+> = (|00> + |11>)/sqrt(2) を作る
    qc.h(0)
    qc.cx(0, 1)

    # 測定基底の回転（Y軸周り）
    if theta_a != 0.0:
        qc.ry(-2*theta_a, 0)
    if theta_b != 0.0:
        qc.ry(-2*theta_b, 1)

    # 測定
    qc.measure(0, 0)
    qc.measure(1, 1)

    tqc = transpile(qc, sim, optimization_level=0)
    result = sim.run(tqc, shots=1, memory=True).result()
    mem = result.get_memory()[0]  # 例: '10' （c0,c1 の順）
    # get_memory の並びは回路で measure(cbit_index) の順序に依存
    # 上で c0 <- q0, c1 <- q1 なので 'ab' の a=bit0, b=bit1
    bit_a = int(mem[0])
    bit_b = int(mem[1])
    return bit_a, bit_b

# =========================
# 収集用バケット
# =========================
# CHSH 用に E(a0,b0), E(a0,b1), E(a1,b0), E(a1,b1) の相関を集計
# E = (N00 + N11 - N01 - N10) / N_total
def corr_bucket():
    return {"n00":0, "n01":0, "n10":0, "n11":0, "N":0}

bucket_a0b0 = corr_bucket()
bucket_a0b1 = corr_bucket()
bucket_a1b0 = corr_bucket()
bucket_a1b1 = corr_bucket()

# キー用
key_alice = []
key_bob   = []

# =========================
# 実験ループ
# =========================
for _ in range(N_pairs):
    is_test = rng.random() < test_ratio

    if is_test:
        # テスト用：CHSH の4組からランダムに選ぶ
        choice = rng.integers(0, 4)
        if choice == 0:
            th_a, th_b = a0, b0
            ba = bucket_a0b0
        elif choice == 1:
            th_a, th_b = a0, b1
            ba = bucket_a0b1
        elif choice == 2:
            th_a, th_b = a1, b0
            ba = bucket_a1b0
        else:
            th_a, th_b = a1, b1
            ba = bucket_a1b1

        a_bit, b_bit = measure_epr_once(th_a, th_b)
        # バケット集計
        if   a_bit == 0 and b_bit == 0: ba["n00"] += 1
        elif a_bit == 0 and b_bit == 1: ba["n01"] += 1
        elif a_bit == 1 and b_bit == 0: ba["n10"] += 1
        else:                           ba["n11"] += 1
        ba["N"] += 1

    else:
        # キー用：両者同じ角度（θ=0）で測定 → 高相関
        a_bit, b_bit = measure_epr_once(theta_key_a, theta_key_b)
        key_alice.append(a_bit)
        key_bob.append(b_bit)

# =========================
# CHSH の計算
# =========================
def E_from_bucket(b):
    if b["N"] == 0:
        return np.nan
    return (b["n00"] + b["n11"] - b["n01"] - b["n10"]) / b["N"]

E_a0b0 = E_from_bucket(bucket_a0b0)
E_a0b1 = E_from_bucket(bucket_a0b1)
E_a1b0 = E_from_bucket(bucket_a1b0)
E_a1b1 = E_from_bucket(bucket_a1b1)
S = E_a0b0 + E_a0b1 + E_a1b0 - E_a1b1

# =========================
# キー一致率
# =========================
key_alice = np.array(key_alice, dtype=int)
key_bob   = np.array(key_bob, dtype=int)
key_len   = len(key_alice)
agreement = float('nan') if key_len==0 else np.mean(key_alice == key_bob)

# =========================
# 出力
# =========================
print("=== E91 段階1&2：キー生成＋CHSHテスト（理想：ノイズなし） ===")
print(f"総EPRペア数                     : {N_pairs}")
print(f"テスト用（CHSH）に回した割合    : {test_ratio:.2f}")
print(f"キー用に残ったビット数          : {key_len}")
print(f"キー一致率（理想は ≈1.0）      : {agreement:.4f}")

print("\n[CHSH 相関（E値）]")
print(f"E(a0,b0) = {E_a0b0:.4f}   サンプル数: {bucket_a0b0['N']}")
print(f"E(a0,b1) = {E_a0b1:.4f}   サンプル数: {bucket_a0b1['N']}")
print(f"E(a1,b0) = {E_a1b0:.4f}   サンプル数: {bucket_a1b0['N']}")
print(f"E(a1,b1) = {E_a1b1:.4f}   サンプル数: {bucket_a1b1['N']}")
print(f"S = {S:.4f}   （盗聴なし理想：S ≈ 2.828 > 2 でベル不等式違反）")

# 共有鍵の例（先頭64ビット）
if key_len > 0:
    print("\n[共有鍵の例（先頭64ビット, アリス視点）]")
    print(''.join(map(str, key_alice[:64])))

