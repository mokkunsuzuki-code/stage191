# qkd13_chsh_ok.py — CHSH が安定して 2 を超える最小・堅牢実装
# 使い方: python qkd13_chsh_ok.py
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit_aer import AerSimulator

# （任意）ノイズを入れて試したい場合は True にし、パラメータを調整
USE_NOISE = False
NOISE_DEPOL_1Q = 0.0   # 1量子ゲート用 脱分極ノイズ p（例: 0.01）
NOISE_READOUT  = (0.0, 0.0)  # 読み出し誤り (p(0→1), p(1→0)) 例:(0.01,0.02)

# CHSH 最大違反の角度セット（|Φ+>、X-Z平面）
A_ANGLES = [0.0, np.pi/4]      # a0, a1
B_ANGLES = [np.pi/8, -np.pi/8] # b0, b1
SHOTS = 8192                   # 統計を安定させる（4096以上推奨）

# ---- オプション：ノイズモデル ----
def make_simulator():
    if not USE_NOISE:
        return AerSimulator()
    # ここから先はノイズを入れる場合のみ
    from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError
    nm = NoiseModel()
    if NOISE_DEPOL_1Q > 0:
        nm.add_all_qubit_quantum_error(depolarizing_error(NOISE_DEPOL_1Q, 1), ['ry','cx','h','x'])
    p01, p10 = NOISE_READOUT
    if (p01 > 0) or (p10 > 0):
        nm.add_all_qubit_readout_error(ReadoutError([[1-p01, p01],[p10, 1-p10]]))
    return AerSimulator(noise_model=nm)

SIM = make_simulator()

def corr_expectation(a_angle: float, b_angle: float, shots: int = SHOTS) -> float:
    """角度(a_angle, b_angle)での相関 E = P00 + P11 - P01 - P10 を確率から計算"""
    # レジスタを明示的に作り、左右（bが左/aが右）を固定
    qr   = QuantumRegister(2, "q")
    cr_a = ClassicalRegister(1, "a")  # 右：Alice
    cr_b = ClassicalRegister(1, "b")  # 左：Bob
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

    # Qiskit の表示差（'ba' と 'b a'）に両対応
    def prob(key_no_space: str, key_with_space: str) -> float:
        return (counts.get(key_no_space, 0) + counts.get(key_with_space, 0)) / shots

    # b が左, a が右
    p00 = prob("00", "0 0")
    p01 = prob("01", "0 1")
    p10 = prob("10", "1 0")
    p11 = prob("11", "1 1")

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
    print(f"noise={'ON' if USE_NOISE else 'OFF'}")

    if S > 2:
        print("→ 盗聴なし（量子相関あり、鍵配送OK）")
    else:
        print("→ 相関が弱い（盗聴やノイズの可能性）")

if __name__ == "__main__":
    main()

