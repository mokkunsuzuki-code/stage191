# qkd14_e91_key.py  — 段階14：E91でsifted key生成
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# --- 相関期待値 ---
def expectation(a, b):
    return 1 - 2*np.mean(a ^ b)

# --- 実験条件 ---
N = 2000
rng = np.random.default_rng(0)

# E91の典型的な測定角度（アリス3種・ボブ3種）
alice_angles = [0, np.pi/4, np.pi/2]
bob_angles   = [np.pi/8, 3*np.pi/8, 5*np.pi/8]

# 記録
records = []

sim = AerSimulator()
for i in range(N):
    qc = QuantumCircuit(2, 2)
    # EPRペア作成
    qc.h(0); qc.cx(0,1)

    # アリス・ボブの基底をランダム選択
    a_choice = rng.integers(0, 3)
    b_choice = rng.integers(0, 3)

    # 基底に応じて回転
    qc.ry(-2*alice_angles[a_choice], 0)
    qc.ry(-2*bob_angles[b_choice],   1)

    qc.measure([0,1],[0,1])

    res = sim.run(transpile(qc, sim), shots=1).result()
    counts = res.get_counts()
    bitstr = list(counts.keys())[0]
    a_bit, b_bit = int(bitstr[1]), int(bitstr[0])
    records.append((a_choice, b_choice, a_bit, b_bit))

records = np.array(records, dtype=int)

# --- CHSH値の計算（盗聴検出用）---
def get_bits(a_set, b_set):
    sel = (records[:,0]==a_set) & (records[:,1]==b_set)
    return records[sel,2], records[sel,3]

E = {}
for (ai, bi) in [(0,0),(0,1),(1,0),(1,1)]:
    a_bits, b_bits = get_bits(ai, bi)
    E[(ai,bi)] = expectation(a_bits, b_bits) if len(a_bits)>0 else 0.0

CHSH = E[(0,0)] + E[(0,1)] + E[(1,0)] - E[(1,1)]
print(f"CHSH = {CHSH:.3f}")
if CHSH > 2:
    print("→ 盗聴なし（鍵配送可能）")
else:
    print("→ 相関弱い（盗聴やノイズ疑い）")

# --- sifted key の生成 ---
# ルール: アリス=角度0, ボブ=角度0 のとき → 鍵に使う
sel = (records[:,0]==0) & (records[:,1]==0)
a_key = records[sel,2]
b_key = records[sel,3]

print(f"Sifted key length = {len(a_key)}")
print("Alice key sample:", "".join(map(str, a_key[:32])))
print("Bob   key sample:", "".join(map(str, b_key[:32])))

# --- QBER計算 ---
if len(a_key)>0:
    qber = float(np.mean(a_key ^ b_key))
    print(f"QBER (sifted key) = {qber:.2%}")

