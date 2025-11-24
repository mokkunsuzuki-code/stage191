# qkd11_eve.py  — 段階11：Eve盗聴シミュレーション
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

N = 800
rng = np.random.default_rng(0)

# アリスの乱数
alice_bits  = rng.integers(0, 2, size=N, dtype=np.uint8)
alice_basis = rng.integers(0, 2, size=N, dtype=np.uint8)  # 0=Z, 1=X
bob_basis   = rng.integers(0, 2, size=N, dtype=np.uint8)

# --- Eveの盗聴確率 ---
eve_prob = 1   # 30% のフォトンをEveが盗聴する（0.0にすれば盗聴なし）

circs = []
for b, ba, bb in zip(alice_bits, alice_basis, bob_basis):
    qc = QuantumCircuit(1, 1)

    # アリスの送信
    if b == 1: qc.x(0)
    if ba == 1: qc.h(0)

    # Eveが盗聴するか？
    if rng.random() < eve_prob:
        eve_basis = rng.integers(0, 2)   # Eveの測定基底（ランダム）
        if eve_basis == 1: qc.h(0)
        qc.measure(0, 0)   # Eveが測定
        # 測定結果を初期状態に戻して送り直す
        qc.reset(0)
        eve_bit = 0  # デフォルト
        # ここでは測定結果を0/1の確率で再現
        # Eveが得たビットを保存してボブへ再送
        # （簡易：ランダム測定結果を使う）
        # 実際は結果をres.get_countsで取得して分岐するが、
        # 教育用に「0か1が半分ずつ出る」と仮定
        eve_bit = rng.integers(0, 2)
        if eve_bit == 1: qc.x(0)
        if ba == 1: qc.h(0)   # Eveも送信基底を合わせる（アリスの基底で再準備）

    # ボブの測定基底
    if bb == 1: qc.h(0)
    qc.measure(0, 0)
    circs.append(qc)

# 実行
sim = AerSimulator()
res = sim.run(transpile(circs, sim), shots=1).result()
bob_bits = np.array([1 if res.get_counts(i).get("1", 0) else 0 for i in range(N)], dtype=np.uint8)

# --- Sifting ---
match = (alice_basis == bob_basis)
idx = np.where(match)[0]
a_sift = alice_bits[idx]
b_sift = bob_bits[idx]

# --- QBER ---
if len(a_sift) > 0:
    qber = float(np.mean(a_sift ^ b_sift))
else:
    qber = 0.0

print(f"Eve盗聴あり: 盗聴率={eve_prob*100:.0f}% | sifted={len(a_sift)} | QBER={qber:.2%}")
