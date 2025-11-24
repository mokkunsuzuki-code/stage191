# qkd_perfect.py
# 量子鍵生成 → 誤り訂正（おもちゃCascade強化）→ プライバシー増幅 → XOR暗号/復号
# 目標: equal=True かつ メッセージ全文が復号されるまで自動でN（試行数）を増やす

import math, hashlib
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# ================== ユーティリティ ==================
def privacy_amp_sha256(bits: np.ndarray, m: int) -> np.ndarray:
    """教育用: 0/1配列をSHA-256連結でmビットまで短縮"""
    if m <= 0 or len(bits) == 0:
        return np.array([], dtype=np.uint8)
    raw = bytes(bits.tolist())
    out = bytearray()
    counter = 0
    while len(out) * 8 < m:
        h = hashlib.sha256(raw + counter.to_bytes(4, "big")).digest()
        out.extend(h); counter += 1
    bitstr = "".join(f"{b:08b}" for b in out)[:m]
    return np.fromiter((1 if c == "1" else 0 for c in bitstr), dtype=np.uint8)

def parity(arr: np.ndarray) -> int:
    return int(np.bitwise_xor.reduce(arr) if len(arr) else 0)

def block_parity_ec(a_key: np.ndarray, b_key: np.ndarray, block_size: int = 8):
    """
    教育用・簡易誤り訂正: ブロックのパリティ不一致なら二分探索で1bit修正
    漏洩量は公開パリティを 1bit/回 とカウント（教育用近似）
    """
    a = a_key.copy().astype(np.uint8)
    b = b_key.copy().astype(np.uint8)
    leakage = 0
    n = len(a)
    for s in range(0, n, block_size):
        e = min(s + block_size, n)
        if parity(a[s:e]) != parity(b[s:e]):
            l, r = s, e
            leakage += 1  # ブロック全体のパリティ公開
            while r - l > 1:
                m = (l + r) // 2
                leakage += 1  # 中間パリティ公開
                if parity(a[l:m]) != parity(b[l:m]):
                    r = m
                else:
                    l = m
            b[l] ^= 1
    return b, leakage

def cascade_ec(a_key, b_key, block_sizes=(64, 32, 16, 8, 4, 2), rng_seed=42):
    """
    おもちゃCascade: ラウンド毎に同一permで並べ替え→block_parity_ec→元順に戻す
    小さいブロックまで攻めて複数誤りも拾う。漏洩は各ラウンド合計。
    """
    rng = np.random.default_rng(rng_seed)
    a = a_key.copy().astype(np.uint8)
    b = b_key.copy().astype(np.uint8)
    n = len(a)
    total_leak = 0
    for r, bs in enumerate(block_sizes, start=1):
        perm = rng.permutation(n); inv = np.empty_like(perm); inv[perm] = np.arange(n)
        a_p, b_p = a[perm], b[perm]
        b_corr_p, leak = block_parity_ec(a_p, b_p, block_size=bs)
        total_leak += leak
        a, b = a_p[inv], b_corr_p[inv]
        mismatches = int(np.sum(a != b))
        print(f"[EC] round{r} bs={bs}  mismatches={mismatches}  leak+={leak}  total_leak={total_leak}")
    return b, total_leak

def bits_to_bytes(bits: np.ndarray):
    """0/1配列→bytes（8の倍数に0詰めしてからpack）。戻り値(bytes, pad)"""
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
    return bytes([a[i] ^ b[i] for i in range(m)])

def utf8_truncate(s: str, max_bytes: int):
    """
    UTF-8の途中切れを避けつつmax_bytes以内に丸めた (文字列, バイト列) を返す
    """
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s, b
    b = b[:max_bytes]
    while True:
        try:
            return b.decode("utf-8"), b
        except UnicodeDecodeError:
            b = b[:-1]

# ================== 1回分のQKD→鍵生成関数 ==================
def run_qkd_once(
    N: int,
    flip_noise: float = 0.05,    # 5%ノイズ（現実の揺らぎを模擬）
    test_ratio: float = 0.10,    # QBER検査に使う割合（少なめで鍵を温存）
    block_sizes=(64, 32, 16, 8, 4, 2),
    seed_main: int = 0,
    seed_qber: int = 1,
    eps_sec: float = 1e-6,
):
    rng = np.random.default_rng(seed_main)

    # --- 送信ビット & 基底（0=Z, 1=X）
    alice_bits  = rng.integers(0, 2, size=N, dtype=np.uint8)
    alice_basis = rng.integers(0, 2, size=N, dtype=np.uint8)
    bob_basis   = rng.integers(0, 2, size=N, dtype=np.uint8)

    # --- 送受信（Qiskitで1ショット測定の配列） ---
    circs = []
    for b, ba, bb in zip(alice_bits, alice_basis, bob_basis):
        qc = QuantumCircuit(1, 1)
        if b == 1:  qc.x(0)
        if ba == 1: qc.h(0)
        if bb == 1: qc.h(0)
        qc.measure(0, 0)
        circs.append(qc)

    sim = AerSimulator()
    res = sim.run(transpile(circs, sim), shots=1).result()
    bob_bits = np.array([1 if res.get_counts(i).get("1", 0) else 0 for i in range(N)], dtype=np.uint8)

    # --- 任意ノイズ ---
    flips = rng.random(len(bob_bits)) < flip_noise
    bob_bits ^= flips.astype(np.uint8)

    # --- シフティング（基底一致のみ抽出） ---
    match = (alice_basis == bob_basis)
    idx = np.where(match)[0]
    a_sift = alice_bits[idx].copy()
    b_sift = bob_bits[idx].copy()

    # --- QBER推定（検査を公開） ---
    rng2 = np.random.default_rng(seed_qber)
    k = max(1, int(len(a_sift) * test_ratio))
    test_idx = rng2.choice(len(a_sift), size=k, replace=False)
    qber = float(np.mean(a_sift[test_idx] ^ b_sift[test_idx]))

    # 検査に使ったビットは鍵から除外
    mask = np.ones(len(a_sift), dtype=bool); mask[test_idx] = False
    a_key = a_sift[mask]; b_key = b_sift[mask]

    # --- 誤り訂正（おもちゃCascadeで強化） ---
    b_corr, leak_ec = cascade_ec(a_key, b_key, block_sizes=block_sizes, rng_seed=42)
    # 仕上げ（まだ残っていたら2bit誤り対策の保険）
    if not np.array_equal(a_key, b_corr):
        b_corr, add_leak = block_parity_ec(a_key, b_corr, block_size=2)
        leak_ec += add_leak
        print(f"[EC] final pass bs=2  mismatches={int(np.sum(a_key!=b_corr))}  total_leak={leak_ec}")

    # --- プライバシー増幅 ---
    safety = int(math.ceil(2 * math.log2(1 / eps_sec)))
    n_after_tests = len(a_key)
    m = max(0, n_after_tests - leak_ec - safety)
    a_final = privacy_amp_sha256(a_key,  m)
    b_final = privacy_amp_sha256(b_corr, m)
    equal_final = np.array_equal(a_final, b_final)

    print(f"QBER={qber:.2%} | sifted={len(a_sift)} | test={k} | EC_leak={leak_ec} | safety={safety} | m={m} | equal={equal_final}")

    return {
        "a_final": a_final, "b_final": b_final, "equal_final": equal_final,
        "m_bits": m, "qber": qber, "sifted": len(a_sift), "test": k, "leak": leak_ec,
    }

# ================== メイン：パーフェクトになるまで再試行 ==================
if __name__ == "__main__":
    msg = "藤井風さん最高ー"
    msg_bytes = msg.encode("utf-8")
    need_bits = len(msg_bytes) * 8  # メッセージ全文に必要な鍵ビット

    N = 1200                # 初期フォトン数
    MAX_TRY = 6             # 上限試行（足りなければNを増やす）
    ok = False
    for attempt in range(1, MAX_TRY + 1):
        print(f"\n===== TRY {attempt}  N={N} =====")
        result = run_qkd_once(
            N=N,
            flip_noise=0.05,          # ノイズは5%に設定（安定）
            test_ratio=0.10,          # 検査10%で鍵を温存
            block_sizes=(64, 32, 16, 8, 4, 2),   # 強めのCascade
        )
        a_final, b_final = result["a_final"], result["b_final"]
        equal_final, m_bits = result["equal_final"], result["m_bits"]

        if equal_final and m_bits >= need_bits:
            ok = True
            print(f"[OK] equal=True かつ 必要ビット {need_bits} ≥ 確保 {m_bits}")
            break

        # 条件未達ならNを増やして再試行
        N += 800

    if not ok:
        raise RuntimeError("鍵が足りない or equal=False。もう一度実行してください（Nは自動で増えます）。")

    # ===== ここから暗号化/復号（パーフェクト条件を満たした状態） =====
    # 送信側（Alice）は a_final、受信側（Bob）は b_final を使う
    key_a, _ = bits_to_bytes(a_final)
    key_b, _ = bits_to_bytes(b_final)

    # 念のためジャスト長に切り詰め
    key_a = key_a[:len(msg_bytes)]
    key_b = key_b[:len(msg_bytes)]

    cipher = xor_bytes(msg_bytes, key_a)   # 暗号化
    plain  = xor_bytes(cipher,   key_b)    # 復号

    print("cipher(hex) =", cipher.hex())
    print("decrypted   =", plain.decode("utf-8"))
