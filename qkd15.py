import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
    print("[INFO] matplotlib なし：表のみ出力します。")

def expectation(a_bits, b_bits):
    if len(a_bits) == 0: return 0.0
    return 1.0 - 2.0 * float(np.mean(a_bits ^ b_bits))  # 一致:+1 / 不一致:-1

# ★ 角度セットの定義（ラジアン）
A_CHSH = [0.0, np.pi/4]             # A0=0°, A1=45°
B_CHSH = [ np.pi/8, -np.pi/8]       # B0=+22.5°, B1=−22.5°
A_KEY  = 0.0                        # 鍵用：0°
B_KEY  = 0.0                        # 鍵用：0°

def build_noise_model(p):
    nm = NoiseModel()
    p1 = max(0.0, min(p, 0.2))
    p2 = max(0.0, min(2*p, 0.3))
    nm.add_all_qubit_quantum_error(depolarizing_error(p1,1), ['h','ry'])
    nm.add_all_qubit_quantum_error(depolarizing_error(p2,2), ['cx'])
    nm.add_all_qubit_readout_error(ReadoutError([[1-p1,p1],[p1,1-p1]]))
    return nm

def e91_once(n_pairs, noise_p, seed=0, key_fraction=0.5):
    rng = np.random.default_rng(seed)
    sim = AerSimulator()
    nm  = build_noise_model(noise_p)

    circs = []
    meta  = []  # ('chsh', a_i, b_j) or ('key',)

    for _ in range(n_pairs):
        qc = QuantumCircuit(2,2)
        qc.h(0); qc.cx(0,1)  # EPR |Φ+>

        if rng.random() < key_fraction:
            # 鍵用（a=b=0°）
            qc.ry(-2*A_KEY, 0)
            qc.ry(-2*B_KEY, 1)
            meta.append(('key',))
        else:
            # CHSH 用（A0/A1 と B0/B1 をランダム）
            ai = rng.integers(0,2)
            bi = rng.integers(0,2)
            qc.ry(-2*A_CHSH[ai], 0)
            qc.ry(-2*B_CHSH[bi], 1)
            meta.append(('chsh', ai, bi))

        qc.measure([0,1],[0,1])
        circs.append(qc)

    res = sim.run(transpile(circs, sim), shots=1, noise_model=nm).result()

    # 収集
    Akey = []; Bkey = []
    E    = {(0,0):[], (0,1):[], (1,0):[], (1,1):[]}

    for i in range(n_pairs):
        bitstr = next(iter(res.get_counts(i)))
        a_bit, b_bit = int(bitstr[1]), int(bitstr[0])  # 右=Alice, 左=Bob
        tag = meta[i][0]
        if tag == 'key':
            Akey.append(a_bit); Bkey.append(b_bit)
        else:
            _, ai, bi = meta[i]
            E[(ai,bi)].append((a_bit, b_bit))

    # CHSH 計算
    def exp_from_list(pairs):
        if not pairs: return 0.0
        a = np.array([x[0] for x in pairs], dtype=np.uint8)
        b = np.array([x[1] for x in pairs], dtype=np.uint8)
        return expectation(a,b)

    CHSH = (exp_from_list(E[(0,0)]) + exp_from_list(E[(0,1)]) +
            exp_from_list(E[(1,0)]) - exp_from_list(E[(1,1)]))

    Akey = np.array(Akey, dtype=np.uint8)
    Bkey = np.array(Bkey, dtype=np.uint8)
    qber = float(np.mean(Akey ^ Bkey)) if len(Akey) else 0.0

    return CHSH, len(Akey), qber

def main():
    noises = [i/100 for i in range(0,9)]  # 0〜8%
    trials = 3
    n_pairs= 3000

    rows=[]
    print(" noise(p) |  CHSH  | QBER(%) | sifted_len")
    print("----------+--------+---------+-----------")
    for p in noises:
        ch,qb,kl = [],[],[]
        for t in range(trials):
            C,K,Q = e91_once(n_pairs, p, seed=100+t)
            ch.append(C); qb.append(Q*100.0); kl.append(K)
        CH = float(np.mean(ch))
        QB = float(np.mean(qb))
        KL = int(np.mean(kl))
        rows.append((p,CH,QB,KL))
        print(f"   {p:0.2f}   | {CH:5.2f} |  {QB:6.2f} | {KL:9d}")

    if HAS_MPL:
        xs   = [r[0]*100 for r in rows]
        ch_y = [r[1]      for r in rows]
        qb_y = [r[2]      for r in rows]
        kl_y = [r[3]      for r in rows]

        plt.figure(); plt.plot(xs,ch_y,marker='o'); plt.axhline(2,ls='--')
        plt.xlabel("Noise p (%)"); plt.ylabel("CHSH"); plt.title("E91: Noise vs CHSH"); plt.grid(True)

        plt.figure(); plt.plot(xs,qb_y,marker='o')
        plt.xlabel("Noise p (%)"); plt.ylabel("QBER (%)"); plt.title("E91: Noise vs QBER (key set)"); plt.grid(True)

        plt.figure(); plt.plot(xs,kl_y,marker='o')
        plt.xlabel("Noise p (%)"); plt.ylabel("Sifted key length"); plt.title("E91: Noise vs Sifted length"); plt.grid(True)

        plt.tight_layout(); plt.show()

if __name__ == "__main__":
    main()

