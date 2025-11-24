# qkd13_e91_ok.py — E91 / CHSH を確実に > 2 で出す最小実装（バージョン差に強い）
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit_aer import AerSimulator

SIM = AerSimulator()

# CHSH最大違反（Tsirelson境界）を与える角度セット
A_ANGLES = [0.0, np.pi/4]      # a0, a1
B_ANGLES = [np.pi/8, -np.pi/8] # b0, b1

def corr_expectation(a_angle: float, b_angle: float, shots: int = 4096) -> float:
    """角度(a_angle, b_angle)での相関 E = P00 + P11 - P01 - P10 を計算"""
    # レジスタを明示的に作る（整数と混在させない）
    qr   = QuantumRegister(2, "q")
    cr_a = ClassicalRegister(1, "a")  # 右側（Alice）
    cr_b = ClassicalRegister(1, "b")  # 左側（Bob）
    qc   = QuantumCircuit(qr, cr_a, cr_b)

    # EPR |Φ+> = (|00> + |11>)/√2
    qc.h(qr[0]); qc.cx(qr[0], qr[1])

    # 任意角度基底で測定できるよう Z に合わせて回す（ry(-2θ)）
    qc.ry(-2*a_angle, qr[0])
    qc.ry(-2*b_angle, qr[1])

    # 測定：qubit0→a[0]（右桁），qubit1→b[0]（左桁）
    qc.measure(qr[0], cr_a[0])
    qc.measure(qr[1], cr_b[0])

    counts = SIM.run(transpile(qc, SIM), shots=shots).result().get_counts()

    # 複数レジスタの表示は 'b a' になることが多いが、環境で '00' 形式のときもあるので両対応
    def p(key_no_space: str, key_with_space: str) -> float:
        return (counts.get(key_no_space, 0) + counts.get(key_with_space, 0)) / shots

    # b が左, a が右 になる想定で集計
    p00 = p("00", "0 0")  # b=0, a=0
    p01 = p("01", "0 1")  # b=0, a=1
    p10 = p("10", "1 0")  # b=1, a=0
    p11 = p("11", "1 1")  # b=1, a=1

    return (p00 + p11) - (p01 + p10)

def main():
    a0, a1 = A_ANGLES
    b0, b1 = B_ANGLES

    E00 = corr_expectation(a0, b0)
    E01 = corr_expectation(a0, b1)
    E10 = corr_expectation(a1, b0)
    E11 = corr_expectation(a1, b1)

    S = E00 + E01 + E10 - E11
    print(f"E(a0,b0)={E00:.4f}, E(a0,b1)={E01:.4f}, E(a1,b0)={E10:.4f}, E(a1,b1)={E11:.4f}")
    print(f"CHSH S = {S:.4f}")
    if S > 2:
        print("→ 盗聴なし（量子相関あり、鍵配送OK）")
    else:
        print("→ 相関が弱い（盗聴やノイズの可能性）")

if __name__ == "__main__":
    main()
