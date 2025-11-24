# qkd_full.py
# BB84(教育用) → Noise(Aer) → Sifting → QBER → Block-EC → SHA-256 PA → OTP暗号化/復号
# 重要: 「鍵 >= メッセージ長」を満たさないとUTF-8文字列は完全復号できません。

import math, hashlib
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

# -------------------------
# パラメータ
# -------------------------
N = 2000                 # 送信ビット数（鍵を十分に得るため 2000 以上推奨）
TEST_FRAC = 0.10         # QBER検査で公開する割合（0.10〜0.20 目安）
DEPOL_P_1Q = 0.01        # 1量子ビットゲートのデポラ化誤り率
READOUT = [[0.995, 0.005],   # 読み出し誤り（各行の合計は1.0必須）
           [0.010, 0.990]]
EPS_SEC = 1e-6           # セキュリティ失敗確率（PAの安全余裕）
SHOW_BITS = 64           # デバッグ表示するビット数

# -------------------------
# ユーティリティ
# -------------------------
def parity(arr: np.ndarray) -> int:
    """配列の総パリティ（0/1）"""
    return int(np.bitwise_xor.reduce(arr)) if len(arr) else 0

def block_parity_ec(a_key: np.ndarray, b_key: np.ndarray, block_size: int = 8):
    """
    教育用・簡易誤り訂正：各ブロックでパリティ不一致なら2分探索で1bitだけ修正。
    漏えい情報は「公開したパリティ回数（ざっくり1ビット/回）」でカウント。
    """
    a = a_key.copy()
    b = b_key.copy()
    n = len(a)
    leakage = 0

    for s in range(0, n, block_size):
        e = min(s + block_size, n)

        if parity(a[s:e]) != parity(b[s:e]):
            leakage += 1
            l, r = s, e
            while r - l > 1:
                m = (l + r) // 2
                leakage += 1
                if parity(a[l:m]) != parity(b[l:m]):
                    r = m
                else:
                    l = m
            b[l] ^= 1  # 1bit反転で修正

    return b, leakage

def privacy_amp_sha256(bits: np.ndarray, m: int) -> np.ndarray:
    """
    教育用プライバシー増幅：bits(0/1)をバイト化→SHA-256を連結してmビット得る。
    """
    if m <= 0 or len(bits) == 0:
        return np.array([], dtype=np.uint8)
    raw = bytes(bits.tolist())
    out = bytearray()
    counter = 0
    while len(out) * 8 < m:
        h = hashlib.sha256(raw + counter.to_bytes(4, "big")).digest()
        out.extend(h)
        counter += 1
    bitstr = "".join(f"{b:08b}" for b in out)[:m]
    return np.fromiter((1 if c == "1" else 0 for c in bitstr), dtype=np.uint8)

def bits_to_bytes(bits: np.ndarray):
    """0/1配列→bytes。8の倍数に0パディングしてpackbits。padは付け足した0の個数。"""
    bits = np.asarray(bits, dtype=np.uint8)
    pad = (-len(bits)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    by = np.packbits(bits)
    return bytes(by.tolist()), pad

def bytes_to_bits(by: bytes, drop_pad: int = 0) -> np.ndarray:
    arr = np.frombuffer(by, dtype=np.uint8)
    bits = np.unpackbits(arr)
    if drop_pad:
        bits = bits[:-drop_pad]
    return bits.astype(np.uint8)

def xor_bytes(a: bytes, b: bytes) -> bytes:
    m = min(len(a), len(b))
    return bytes(a[i] ^ b[i] for i in range(m))

# -------------------------
# 送信ビット・基底の生成
# -------------------------
rng = np.random.default_rng(1)
alice_bits  = rng.integers(0, 2, size=N, dtype=np.uint8)
alice_basis = rng.integers(0, 2, size=N, dtype=np.uint8)  # 0=Z, 1=X
bob_basis   = rng.integers(0, 2, size=N, dtype=np.uint8)

# -------------------------
# 回路生成（1ビット1回路）
# -------------------------
circs = []
for b, ba, bb in zip(alice_bits, alice_basis, bob_basis):
    qc = QuantumCircuit(1, 1)
    if b == 1: qc.x(0)               # まずビット
    if ba == 1: qc.h(0)              # 次に送信基底
    if bb == 1: qc.h(0)              # 測定基底
    qc.measure(0, 0)
    circs.append(qc)

# -------------------------
# ノイズモデル
# -------------------------
nm = NoiseModel()
err1q = depolarizing_error(DEPOL_P_1Q, 1)      # (p, num_qubits)
nm.add_all_qubit_quantum_error(err1q, ['x', 'h'])
ro = ReadoutError(READOUT)                     # 各行の合計が1.0であること
nm.add_all_qubit_readout_error(ro)

# -------------------------
# シミュレーション
# -------------------------
sim = AerSimulator()
res = sim.run(transpile(circs, sim), shots=1, noise_model=nm).result()
# 各回路のcountsから '1' の有無でビット化
bob_bits = np.array([1 if res.get_counts(i).get("1", 0) else 0 for i in range(N)], dtype=np.uint8)

# -------------------------
# Sifting（基底一致のみ抽出） & QBER検査
# -------------------------
match = (alice_basis == bob_basis)
idx = np.where(match)[0]
a_sift = alice_bits[idx].copy()
b_sift = bob_bits[idx].copy()

rng2 = np.random.default_rng(1)
k = max(1, int(len(a_sift) * TEST_FRAC))       # 検査で公開する本数
test_idx = rng2.choice(len(a_sift), size=k, replace=False)
qber = float(np.mean(a_sift[test_idx] ^ b_sift[test_idx]))

# 検査に使ったビットは除去して鍵へ
mask = np.ones(len(a_sift), dtype=bool)
mask[test_idx] = False
a_key = a_sift[mask]
b_key = b_sift[mask]

# -------------------------
# 誤り訂正（教育用・1ブロック1bit修正）
# -------------------------
b_corr, leak_ec = block_parity_ec(a_key, b_key, block_size=8)

# -------------------------
# プライバシー増幅（SHA-256）
# 安全余裕：safety ≈ ceil(2 + log2(1/eps))
#   ※ここでは単純化して EC漏えいのみ差し引き（検査分は既に除去済）
# -------------------------
safety = int(math.ceil(2 + math.log2(1 / EPS_SEC)))
n_after_tests = len(a_key)
m = max(0, n_after_tests - leak_ec - safety)

a_final = privacy_amp_sha256(a_key,  m)
b_final = privacy_amp_sha256(b_corr, m)

# 結果サマリ
print(f"QBER with NoiseModel = {qber:.2%}, sifted = {len(a_sift)}")
print(f"EC_leak={leak_ec} | safety={safety} | m={m} | equal={np.array_equal(a_final, b_final)}")
if len(a_final) >= SHOW_BITS and len(b_final) >= SHOW_BITS:
    print("A_final[:64] =", "".join(map(str, a_final[:SHOW_BITS].tolist())))
    print("B_final[:64] =", "".join(map(str, b_final[:SHOW_BITS].tolist())))

# -------------------------
# ワンタイムパッド（OTP）暗号化/復号
# -------------------------
msg = "QKDで作った鍵で暗号化テスト✋"
msg_bytes = msg.encode("utf-8")

key_bytes, pad = bits_to_bytes(a_final)
need, have = len(msg_bytes), len(key_bytes)

# 鍵不足なら即エラー（ここを通れば必ず全文が復号できる）
if have < need:
    raise ValueError(f"鍵が不足: key={have}B < msg={need}B。"
                     f" N を増やすか TEST_FRAC を下げて再実行してください。")

cipher = xor_bytes(msg_bytes, key_bytes[:need])
plain  = xor_bytes(cipher,    key_bytes[:need])

print("cipher(hex) =", cipher.hex())
print("decrypted   =", plain.decode("utf-8"))

