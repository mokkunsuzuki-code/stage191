# qkd14_noise_sweep.py — ノイズONで CHSH が 2 に近づく様子を可視化
# 使い方: python qkd14_noise_sweep.py
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit_aer import AerSimulator

# ---- CHSH 最大違反の角度セット（|Φ+>）----
A_ANGLES = [0.0, np.pi/4]       # a0, a1
B_ANGLES = [np.pi/8, -np.pi/8]  # b0, b1
SHOTS    = 4096                  # 統計安定用（環境に合わせて増減OK）

# ---- ノイズ設定（ここを変えて遊ぶ）----
# 掃引（スイープ）する 1量子ゲート脱分極ノイズの候補
DEPOL_LEVELS = [0.0, 0.005, 0.01, 0.015, 0.02]   # 0% → 2%
READOUT_ERR  = (0.0, 0.0)  # 読み出しエラー (p(0→1), p(1→0)) 例: (0.01,0.02)

# ---- ノイズ付きシミュレータの作成 ----
def make_simulator(p_depol_1q: float, readout=(0.0, 0.0)) -> AerSimulator:
    from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError
    nm = NoiseModel()
    if p_depol_1q > 0:
        # RY, H, X に 1量子ゲート脱分極ノイズを適用（CXは使うが今回は1Qだけで十分）
        nm.add_all_qubit_quantum_error(depolarizing_error(p_depol_1q, 1), ['ry','h','x'])
        # 参考：2量子ゲートにも入れたい場合は nm.add_all_qubit_quantum_error(depolarizing_error(p2, 2), ['cx'])
    p01, p10 = readout
    if (p01 > 0) or (p10 > 0):
        nm.add_all_qubit_readout_error(ReadoutError([[1-p01, p01],[p10, 1-p10]]))
    return AerSimulator(noise_model=nm)

# ---- 相関 E の計算（bが左、aが右）----
def corr_expectation(sim: AerSimulator, a_angle: float, b_angle: float, shots: int = SHOTS) -> float:
    qr   = QuantumRegister(2, "q")
    cr_a = ClassicalRegister(1, "a")  # 右：Alice
    cr_b = ClassicalRegister(1, "b")  # 左：Bob
    qc   = QuantumCircuit(qr, cr_a, cr_b)

    # EPR |Φ+> 生成
    qc.h(qr[0]); qc.cx(qr[0], qr[1])

    # 任意角度基底（Zに合わせて回す）
    qc.ry(-2*a_angle, qr[0])
    qc.ry(-2*b_angle, qr[1])

    # 測定（qubit0→a[0], qubit1→b[0]）
    qc.measure(qr[0], cr_a[0])
    qc.measure(qr[1], cr_b[0])

    counts = sim.run(transpile(qc, sim), shots=shots).result().get_counts()

    # 'ba' 形式と 'b a' 形式の両対応で確率を取得
    def prob(k_no_space: str, k_with_space: str) -> float:
        return (counts.get(k_no_space, 0) + counts.get(k_with_space, 0)) / shots

    p00 = prob("00", "0 0")
    p01 = prob("01", "0 1")
    p10 = prob("10", "1 0")
    p11 = prob("11", "1 1")
    return (p00 + p11) - (p01 + p10)

def chsh(sim: AerSimulator) -> float:
    a0, a1 = A_ANGLES
    b0, b1 = B_ANGLES
    E00 = corr_expectation(sim, a0, b0)
    E01 = corr_expectation(sim, a0, b1)
    E10 = corr_expectation(sim, a1, b0)
    E11 = corr_expectation(sim, a1, b1)
    return E00 + E01 + E10 - E11, (E00, E01, E10, E11)

def main():
    print("dep1q(%) |   CHSH S  |   E00    E01    E10    E11 ")
    print("---------+-----------+---------------------------")
    rows = []
    for p in DEPOL_LEVELS:
        sim = make_simulator(p, READOUT_ERR)
        S, (E00,E01,E10,E11) = chsh(sim)
        print(f"{100*p:7.3f} | {S:9.4f} | {E00:6.3f} {E01:6.3f} {E10:6.3f} {E11:6.3f}")
        rows.append((p, S))

    # もし matplotlib があればグラフ化（無ければスキップ）
    try:
        import matplotlib.pyplot as plt
        xs = [100*r[0] for r in rows]
        ys = [r[1] for r in rows]
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.axhline(2.0, linestyle="--")  # しきい値
        plt.xlabel("1Q depolarizing noise p (%)")
        plt.ylabel("CHSH S")
        plt.title("Noise ↑ → CHSH → 2 に近づく")
        plt.grid(True)
        plt.show()
    except Exception:
        pass

if __name__ == "__main__":
    main()

