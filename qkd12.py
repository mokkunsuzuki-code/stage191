# qkd12_keyrate.py  — 段階12：理論式との比較
import numpy as np, math, hashlib
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# --- エントロピー関数 h2 ---
def h2(x):
    if x <= 0 or x >= 1:
        return 0.0
    return -x*math.log2(x) - (1-x)*math.log2(1-x)

# --- BB84 の1回分シミュレーション（簡易） ---
def run_once(n=800, flip_noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    alice_bits  = rng.integers(0,2,size=n,dtype=np.uint8)
    alice_basis = rng.integers(0,2,size=n,dtype=np.uint8)
    bob_basis   = rng.integers(0,2,size=n,dtype=np.uint8)

    # 回路生成
    circs=[]
    for b,ba,bb in zip(alice_bits,alice_basis,bob_basis):
        qc=QuantumCircuit(1,1)
        if b==1: qc.x(0)
        if ba==1: qc.h(0)
        if bb==1: qc.h(0)
        qc.measure(0,0)
        circs.append(qc)

    sim=AerSimulator()
    res=sim.run(transpile(circs,sim),shots=1).result()
    bob_bits=np.array([1 if res.get_counts(i).get("1",0) else 0 for i in range(n)],dtype=np.uint8)

    # 擬似ノイズ
    if flip_noise>0:
        flips = rng.random(len(bob_bits)) < flip_noise
        bob_bits ^= flips.astype(np.uint8)

    # Sifting
    match=(alice_basis==bob_basis)
    idx=np.where(match)[0]
    a_sift=alice_bits[idx]; b_sift=bob_bits[idx]

    # QBER推定
    if len(a_sift)==0: return 0.0,0
    k=max(1,int(len(a_sift)*0.2))
    rng2=np.random.default_rng(1)
    test_idx=rng2.choice(len(a_sift), size=k, replace=False)
    qber=float(np.mean(a_sift[test_idx]^b_sift[test_idx]))
    return qber,len(a_sift)

# --- 実験スイープ ---
noises=[i/100 for i in range(0,16)]
q_exp=[]; m_theory=[]
for p in noises:
    q_list=[]
    for t in range(5):
        q,sifted=run_once(flip_noise=p,seed=100+t)
        q_list.append(q)
    q=np.mean(q_list)
    q_exp.append(q)
    R_theory=0.5*(1-2*h2(q))
    if R_theory<0: R_theory=0
    m_theory.append(R_theory*sifted)  # 期待される最終鍵長

# --- グラフ化 ---
plt.figure()
plt.plot([x*100 for x in noises],[x*100 for x in q_exp],marker="o")
plt.xlabel("Flip noise (%)"); plt.ylabel("QBER (%)"); plt.title("Noise vs QBER"); plt.grid(True)

plt.figure()
plt.plot([x*100 for x in noises],m_theory,marker="o",label="Theory key length")
plt.xlabel("Flip noise (%)"); plt.ylabel("Key length (theory)")
plt.title("Noise vs Theoretical key length")
plt.grid(True); plt.legend()

plt.show()
