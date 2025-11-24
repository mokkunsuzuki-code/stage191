# qkd10_b92.py  — 段階10：B92プロトコルの最小実装

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

N = 1000
rng = np.random.default_rng(0)

# アリスのビット列（0 -> |0>, 1 -> |+>）
alice_bits = rng.integers(0, 2, size=N, dtype=np.uint8)

# ボブの測定基底（0=Z, 1=X）
bob_choice = rng.integers(0, 2, size=N, dtype=np.uint8)

# --- 回路を作って実行 ---
circs = []
for a, bc in zip(alice_bits, bob_choice):
    qc = QuantumCircuit(1, 1)
    if a == 1:   # 1なら |+> を準備
        qc.h(0)
    if bc == 1:  # X基底で測定
        qc.h(0)
    qc.measure(0, 0)
    circs.append(qc)

sim = AerSimulator()
res = sim.run(transpile(circs, sim), shots=1).result()
meas = np.array([1 if res.get_counts(i).get("1", 0) else 0 for i in range(N)], dtype=np.uint8)

# --- 判定ルール ---
# Z基底で 1 が出たら「アリス=1」確定
# X基底で 1 が出たら「アリス=0」確定
conclusive = ((bob_choice == 0) & (meas == 1)) | ((bob_choice == 1) & (meas == 1))
bob_bits = np.where(bob_choice == 0, 1, 0)[conclusive]
alice_keep = alice_bits[conclusive]

# --- QBER計算（確定した分だけで）---
if len(alice_keep):
    qber = float(np.mean(alice_keep ^ bob_bits))
else:
    qber = 0.0

print(f"B92結果: conclusive={len(alice_keep)} / {N} ({len(alice_keep)/N:.2%}), QBER={qber:.2%}")

