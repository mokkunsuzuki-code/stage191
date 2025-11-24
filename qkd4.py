import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

N = 800
rng = np.random.default_rng(0)

alice_bits  = rng.integers(0,2,size=N,dtype=np.uint8)
alice_basis = rng.integers(0,2,size=N,dtype=np.uint8)  # 0=Z, 1=X
bob_basis   = rng.integers(0,2,size=N,dtype=np.uint8)

# --- 送受信 ---
circs = []
for b, ba, bb in zip(alice_bits, alice_basis, bob_basis):
    qc = QuantumCircuit(1,1)
    if b==1:  qc.x(0)      # 1を準備
    if ba==1: qc.h(0)      # アリスの基底
    if bb==1: qc.h(0)      # ボブの測定基底
    qc.measure(0,0)
    circs.append(qc)

sim = AerSimulator()
res = sim.run(transpile(circs, sim), shots=1).result()
bob_bits = np.array([1 if res.get_counts(i).get('1',0) else 0 for i in range(N)], dtype=np.uint8)

# --- ★ここにノイズを差し込む（Bobの測定結果を擬似的に乱す） ---
flip_noise =0.08  # 8%の反転ノイズ
flips = rng.random(len(bob_bits)) < flip_noise
bob_bits ^= flips.astype(np.uint8)

# --- シフティング ---
match = (alice_basis == bob_basis)
idx = np.where(match)[0]
a_sift = alice_bits[idx].copy()
b_sift = bob_bits[idx].copy()

# --- QBER推定（検査20%）---
rng2 = np.random.default_rng(1)
k = max(1, int(len(a_sift)*0.2))
test_idx = rng2.choice(len(a_sift), size=k, replace=False)
qber = float(np.mean(a_sift[test_idx] ^ b_sift[test_idx]))

print(f"QBER={qber:.2%}, sifted={len(a_sift)}")
