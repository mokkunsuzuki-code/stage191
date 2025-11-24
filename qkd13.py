# qkd13_e91.py  — 段階13：E91プロトコル最小実装
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# --- CHSH計算用 ---
def expectation(a, b):
    """2つの測定結果ビット配列から相関期待値を計算"""
    return 1 - 2*np.mean(a ^ b)   # 一致→+1, 不一致→-1

# --- 実験条件 ---
N = 2000
rng = np.random.default_rng(0)

# 測定設定（アリス3種・ボブ3種）
# 教科書的なE91設定
alice_angles = [0, np.pi/4, np.pi/2]
bob_angles   = [np.pi/8, 3*np.pi/8, 5*np.pi/8]

# 記録用
data = []

for i in range(N):
    qc = QuantumCircuit(2, 2)
    # EPRペア作成
    qc.h(0); qc.cx(0,1)

    # アリス・ボブの測定基底をランダム選択
    a_choice = rng.integers(0, 3)
    b_choice = rng.integers(0, 3)

    # 回転してからZ測定 = 任意の角度基底測定
    qc.ry(-2*alice_angles[a_choice], 0)
    qc.ry(-2*bob_angles[b_choice],   1)

    qc.measure([0,1], [0,1])

    sim = AerSimulator()
    result = sim.run(transpile(qc, sim), shots=1).result()
    counts = result.get_counts(0)
    bitstr = list(counts.keys())[0]
    a_bit, b_bit = int(bitstr[1]), int(bitstr[0])  # [0]=LSB→Bob, [1]=Alice
    data.append((a_choice, b_choice, a_bit, b_bit))

data = np.array(data, dtype=int)

# --- CHSH値の計算 ---
# CHSH = E(a0,b0)+E(a0,b1)+E(a1,b0)-E(a1,b1)
def get_bits(a_set, b_set):
    sel = (data[:,0]==a_set) & (data[:,1]==b_set)
    return data[sel,2], data[sel,3]

E = {}
for (ai, bi) in [(0,0),(0,1),(1,0),(1,1)]:
    a_bits, b_bits = get_bits(ai, bi)
    if len(a_bits)>0:
        E[(ai,bi)] = expectation(a_bits, b_bits)
    else:
        E[(ai,bi)] = 0.0

CHSH = E[(0,0)] + E[(0,1)] + E[(1,0)] - E[(1,1)]

print("CHSH =", CHSH)
if CHSH > 2:
    print("→ 盗聴なし（量子相関あり、鍵配送OK）")
else:
    print("→ 相関が弱い（盗聴やノイズの可能性）")
