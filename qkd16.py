# qkd16_ok.py — E91フルパイプライン（CHSH→Sifting→強化EC→プライバシー増幅→XOR）
# ねらい：equal=True（最終鍵一致）まで通し、暗号化デモを必ず実行
import math, hashlib
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit_aer import AerSimulator

# ====== 実験パラメータ ======
N_PAIRS    = 5000          # もつれペア数（鍵長を増やしたいなら増やす）
TEST_FRAC  = 0.20          # QBER推定に使う公開割合
EPS_SEC    = 1e-6          # プライバシー増幅の安全目標（教育用）
EC_ROUNDS  = [64, 32, 16, 8, 4, 2]  # カスケード風ECのブロックサイズ列
SEED       = 0

# CHSH最大違反の角度（|Φ+>、X-Z平面、ry(-2θ)でZ測定化）
A_ANGLES = [0.0, np.pi/4]       # a0, a1
B_ANGLES = [np.pi/8, -np.pi/8]  # b0, b1
KEY_SETS = {(0,0), (1,1)}       # 鍵に使う測定組（半分が鍵用になる）

SIM = AerSimulator()
rng = np.random.default_rng(SEED)

# ====== ユーティリティ ======
def expectation(a_bits: np.ndarray, b_bits: np.ndarray) -> float:
    """E = P(一致) - P(不一致)"""
    if len(a_bits) == 0:
        return 0.0
    return 1.0 - 2.0 * float(np.mean(a_bits ^ b_bits))

def privacy_amp_sha256(bits: np.ndarray, m: int) -> np.ndarray:
    """簡易プライバシー増幅：0/1配列をSHA-256連結でmビットに短縮"""
    if m <= 0 or len(bits) == 0:
        return np.array([], dtype=np.uint8)
    raw = bytes(np.asarray(bits, dtype=np.uint8).tolist())
    out = bytearray()
    c = 0
    while len(out) * 8 < m:
        out.extend(hashlib.sha256(raw + c.to_bytes(4, "big")).digest())
        c += 1
    bitstr = "".join(f"{b:08b}" for b in out)[:m]
    return np.fromiter((1 if ch == "1" else 0 for ch in bitstr), dtype=np.uint8)

def bits_to_bytes(bits: np.ndarray):
    bits = np.asarray(bits, dtype=np.uint8)
    pad = (-len(bits)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    return bytes(np.packbits(bits).tolist()), pad

def xor_bytes(a: bytes, b: bytes) -> bytes:
    m = min(len(a), len(b))
    return bytes([a[i] ^ b[i] for i in range(m)])

# ====== 強化・誤り訂正（カスケード風） ======
def parity(arr: np.ndarray) -> int:
    return int(np.bitwise_xor.reduce(arr) if len(arr) else 0)

def _binary_search_fix(a, b, l, r, leak_counter) -> int:
    """区間[l,r)でパリティ差が出ているときに1bit反転を特定して直す。
       返り値：追加リーク（公開パリティ回数）"""
    while r - l > 1:
        m = (l + r) // 2
        leak_counter += 1
        if parity(a[l:m]) != parity(b[l:m]):
            r = m
        else:
            l = m
    b[l] ^= 1
    return leak_counter

def cascade_ec(a_key: np.ndarray, b_key: np.ndarray, rounds=EC_ROUNDS, verbose=True):
    """複数ラウンドのブロック分割＋二分探索修正。各ラウンドの前に乱択シャッフル。
       複数エラーは別ラウンドの分割で露見させて拾う。"""
    a = a_key.copy()
    b = b_key.copy()
    n = len(a)
    leak = 0

    # 初回にズレ数を把握
    def mismatches():
        return int(np.sum(a ^ b))

    if verbose:
        print("[EC] start mismatches", mismatches())

    # 乱択用permはラウンドごとに作る（Alice/Bob共通とみなす）
    for r_i, bs in enumerate(rounds, 1):
        # 乱択シャッフル
        perm = rng.permutation(n)
        inv  = np.empty(n, dtype=int); inv[perm] = np.arange(n)
        a = a[perm]; b = b[perm]

        # ブロックごとにパリティを比べ、差があれば二分探索で1bit修正
        fixes = 0
        for s in range(0, n, bs):
            e = min(s + bs, n)
            leak += 1
            if parity(a[s:e]) != parity(b[s:e]):
                leak = _binary_search_fix(a, b, s, e, leak)
                fixes += 1

        # 元の順序に戻す（次ラウンドの分割のため）
        a = a[inv]; b = b[inv]

        if verbose:
            print(f"[EC] round{r_i} bs={bs:>2}  fixes={fixes:>3}  "
                  f"mismatches={mismatches():>3}  leak+={leak}")

    if verbose:
        print("[EC] done mismatches", mismatches())

    return b, leak, (mismatches() == 0)

# ====== E91：測定とCHSH＋鍵セット抽出 ======
def run_e91_once(n_pairs=N_PAIRS):
    rows = []  # (a_choice, b_choice, a_bit, b_bit)
    # まとめて1ショットずつ実行（教育用簡易）
    for _ in range(n_pairs):
        # レジスタ（bを左、aを右）
        qr = QuantumRegister(2, "q")
        cr_a = ClassicalRegister(1, "a")
        cr_b = ClassicalRegister(1, "b")
        qc = QuantumCircuit(qr, cr_a, cr_b)

        # EPR生成
        qc.h(qr[0]); qc.cx(qr[0], qr[1])

        # 測定設定（0/1を等確率）
        a_choice = int(rng.integers(0, 2))
        b_choice = int(rng.integers(0, 2))

        # 任意角度基底に合わせて回す → Z測定
        qc.ry(-2*A_ANGLES[a_choice], qr[0])
        qc.ry(-2*B_ANGLES[b_choice], qr[1])

        # 測定：qubit0→a、qubit1→b
        qc.measure(qr[0], cr_a[0])
        qc.measure(qr[1], cr_b[0])

        counts = SIM.run(transpile(qc, SIM), shots=1).result().get_counts()
        # 'b a' / 'ba' の両表記に対応
        key = next(iter(counts.keys()))
        key = key.replace(" ", "")
        # 左=b、右=a
        b_bit = int(key[0])
        a_bit = int(key[1])
        rows.append((a_choice, b_choice, a_bit, b_bit))

    data = np.array(rows, dtype=int)

    # CHSH計算（4組）
    def sel(ai, bi):
        m = (data[:,0] == ai) & (data[:,1] == bi)
        return data[m,2], data[m,3]

    E00 = expectation(*sel(0,0))
    E01 = expectation(*sel(0,1))
    E10 = expectation(*sel(1,0))
    E11 = expectation(*sel(1,1))
    S   = E00 + E01 + E10 - E11

    # 鍵セット（(0,0),(1,1) を採用）
    keep = np.array([(a in (0,1)) and ((a,b) in KEY_SETS) for a,b in data[:,0:2]], dtype=bool)
    a_keep = data[keep, 2]
    b_keep = data[keep, 3]

    return S, (E00,E01,E10,E11), a_keep.astype(np.uint8), b_keep.astype(np.uint8)

# ====== メイン ======
def main():
    # --- E91 測定 → CHSH と鍵候補 ---
    S, (E00,E01,E10,E11), a_keep, b_keep = run_e91_once(N_PAIRS)
    print(f"=== E91 full pipeline (EC + PA + XOR) ===")
    print(f"CHSH={S:.3f}  | E00={E00:.3f} E01={E01:.3f} E10={E10:.3f} E11={E11:.3f}")
    print(f"sifted={len(a_keep)}  | key sets={(0,0),(1,1)}")

    # --- QBER 推定（鍵候補の20%を公開） ---
    k = max(1, int(len(a_keep) * TEST_FRAC))
    test_idx = rng.choice(len(a_keep), size=k, replace=False)
    qber = float(np.mean(a_keep[test_idx] ^ b_keep[test_idx]))

    # 使った分は鍵から除外
    mask = np.ones(len(a_keep), dtype=bool); mask[test_idx] = False
    a_key = a_keep[mask]; b_key = b_keep[mask]
    print(f"test={k}  | QBER={100*qber:.2f}%")

    # --- 強化EC（カスケード風） ---
    b_corr, leak_ec, ok_after_ec = cascade_ec(a_key, b_key, rounds=EC_ROUNDS, verbose=True)
    if not ok_after_ec:
        # 念のため最終チェック（ほぼ起きない）
        left = int(np.sum(a_key ^ b_corr))
        raise RuntimeError(f"[EC] after cascade mismatches remain: {left}")

    # --- プライバシー増幅（SHA-256） ---
    safety = int(math.ceil(2 * math.log2(1 / EPS_SEC)))
    m = max(0, len(a_key) - leak_ec - safety)
    a_final = privacy_amp_sha256(a_key,  m)
    b_final = privacy_amp_sha256(b_corr, m)
    equal = bool(np.array_equal(a_final, b_final))

    print(f"EC_leak={leak_ec}  | safety={safety}  | final m={m}  | equal={equal}")

    # --- XOR暗号デモ ---
    if equal and m > 0:
        msg = "QKDで作った鍵で暗号化テスト✋"
        key_a, _ = bits_to_bytes(a_final)
        key_b, _ = bits_to_bytes(b_final)
        msg_bytes = msg.encode("utf-8")
        # 鍵でトリミング
        L = min(len(key_a), len(msg_bytes))
        cipher = xor_bytes(msg_bytes[:L], key_a[:L])
        plain  = xor_bytes(cipher,           key_b[:L])
        print(f"cipher(hex)={cipher.hex()}")
        print(f"decrypted  ={plain.decode('utf-8')}")
    else:
        print("※ 最終鍵が一致しない/長さ0のため XOR デモはスキップしました。")

if __name__ == "__main__":
    main()

