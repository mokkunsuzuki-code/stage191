import numpy as np
import hashlib, math
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator


# ===== ユーティリティ =====
def privacy_amp_sha256(bits: np.ndarray, m: int) -> np.ndarray:
    """
    教育用の簡易プライバシー増幅：
    入力bits(np.uint8; 0/1)をSHA-256連結でmビットに短縮。
    """
    if m <= 0 or len(bits) == 0:
        return np.array([], dtype=np.uint8)
    # 0/1配列をバイト列へ（各要素を1バイト化）
    raw = bytes(bits.tolist())
    out = bytearray()
    counter = 0
    while len(out) * 8 < m:
        h = hashlib.sha256(raw + counter.to_bytes(4, "big")).digest()
        out.extend(h)
        counter += 1
    bitstr = "".join(f"{b:08b}" for b in out)[:m]
    return np.fromiter((1 if c == "1" else 0 for c in bitstr), dtype=np.uint8)


def parity(arr: np.ndarray) -> int:
    return int(np.bitwise_xor.reduce(arr) if len(arr) else 0)


def block_parity_ec(a_key: np.ndarray, b_key: np.ndarray, block_size: int = 8):
    """
    教育用・簡易誤り訂正：
    各ブロックでパリティが違えば二分探索で“1bitだけ”修正。
    漏洩量は公開したパリティ回数（ざっくり1bit/回）でカウント。
    """
    a = a_key.copy()
    b = b_key.copy()
    leakage = 0
    n = len(a)
    for s in range(0, n, block_size):
        e = min(s + block_size, n)
        if parity(a[s:e]) != parity(b[s:e]):
            l, r = s, e
            leakage += 1  # ブロック全体のパリティ公開
            # 二分探索
            while r - l > 1:
                m = (l + r) // 2
                leakage += 1  # 中間パリティ公開
                if parity(a[l:m]) != parity(b[l:m]):
                    r = m
                else:
                    l = m
            b[l] ^= 1  # 1bit反転
    return b, leakage


# ===== ここから実験（段階6） =====
N = 800
rng = np.random.default_rng(0)

# 送信ビット & 基底（0=Z, 1=X）
alice_bits  = rng.integers(0, 2, size=N, dtype=np.uint8)
alice_basis = rng.integers(0, 2, size=N, dtype=np.uint8)
bob_basis   = rng.integers(0, 2, size=N, dtype=np.uint8)

# --- 送受信 ---
circs = []
for b, ba, bb in zip(alice_bits, alice_basis, bob_basis):
    qc = QuantumCircuit(1, 1)
    if b == 1:  qc.x(0)   # まずビット
    if ba == 1: qc.h(0)   # 次にアリス基底
    if bb == 1: qc.h(0)   # 測定基底
    qc.measure(0, 0)
    circs.append(qc)

sim = AerSimulator()
res = sim.run(transpile(circs, sim), shots=1).result()
bob_bits = np.array([1 if res.get_counts(i).get("1", 0) else 0 for i in range(N)], dtype=np.uint8)

# --- 任意ノイズ（現実の揺らぎを模擬）---
flip_noise = 0.08          # ← ノイズなしにしたい時は 0.0
flips = rng.random(len(bob_bits)) < flip_noise
bob_bits ^= flips.astype(np.uint8)

# --- シフティング（基底一致のみ抽出） ---
match = (alice_basis == bob_basis)
idx = np.where(match)[0]
a_sift = alice_bits[idx].copy()
b_sift = bob_bits[idx].copy()

# --- QBER推定（検査20%を公開） ---
rng2 = np.random.default_rng(1)
k = max(1, int(len(a_sift) * 0.20))              # 検査で公開する本数
test_idx = rng2.choice(len(a_sift), size=k, replace=False)
qber = float(np.mean(a_sift[test_idx] ^ b_sift[test_idx]))

# 検査に使ったビットは鍵から除外
mask = np.ones(len(a_sift), dtype=bool)
mask[test_idx] = False
a_key = a_sift[mask]
b_key = b_sift[mask]

# --- 教育用・誤り訂正（1ブロック1bit修正） ---
# 8ビットブロックだと 7〜8% の誤りでも直りやすい
b_corr, leak_ec = block_parity_ec(a_key, b_key, block_size=8)

# --- プライバシー増幅（SHA-256） ---
# 安全余裕（教育用目安）：eps=1e-6 に対し 2*log2(1/eps) を引く
eps_sec = 1e-6
safety = int(math.ceil(2 * math.log2(1/eps_sec)))

# 【重要】いま m を計算する n は「検査後の鍵長」
n_after_tests = len(a_key)
m = max(0, n_after_tests - leak_ec - safety)

a_final = privacy_amp_sha256(a_key,  m)
b_final = privacy_amp_sha256(b_corr, m)

print(f"QBER={qber:.2%} | sifted={len(a_sift)} | test={k} "
      f"| EC_leak={leak_ec} | safety={safety} | m={m} | equal={np.array_equal(a_final, b_final)}")

# 参考表示：最初の64ビット（短いときはあるだけ）
show = min(64, len(a_final))
if show > 0:
    print("A_final[:64] =", "".join(map(str, a_final[:show].tolist())))
    print("B_final[:64] =", "".join(map(str, b_final[:show].tolist())))

