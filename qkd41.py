# qkd40_final.py  — 段階40 完全版（日本語表示 & OTP自動フィット付き）
# 依存: numpy, hashlib（標準）

from __future__ import annotations
import math
import hashlib
import numpy as np

# ===== ユーティリティ =====
def h2(x: float) -> float:
    if x <= 0.0 or x >= 1.0:
        return 0.0
    return -(x * math.log2(x) + (1 - x) * math.log2(1 - x))

# 正規分布の逆関数（Acklam 近似）
def normal_ppf(p: float) -> float:
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((( (d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                 ((( (d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q / \
           (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)

def wilson_CI(k: int, n: int, alpha: float) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    z = normal_ppf(1 - alpha / 2)
    den = 1 + z*z/n
    ctr = (p + z*z/(2*n)) / den
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return max(0.0, ctr - half), min(1.0, ctr + half)

def bits_to_bytes(bits: np.ndarray) -> bytes:
    if len(bits) == 0:
        return b""
    pad = (8 - (len(bits) % 8)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for b in bits[i:i+8]:
            v = (v << 1) | int(b)
        out.append(v)
    return bytes(out)

def sha256_amp(bits: np.ndarray, m: int) -> np.ndarray:
    if m <= 0:
        return np.zeros(0, dtype=np.uint8)
    raw = bits_to_bytes(bits)
    buf = bytearray()
    ctr = 0
    while len(buf) * 8 < m:
        buf.extend(hashlib.sha256(raw + ctr.to_bytes(4, "big")).digest())
        ctr += 1
    bitstr = "".join(f"{b:08b}" for b in buf)[:m]
    return np.fromiter((1 if c == "1" else 0 for c in bitstr), dtype=np.uint8)

# ===== E91（教育） =====
A = [0.0, math.pi/4]
B = [math.pi/8, -math.pi/8]

def E_theory(vis: float, ai: int, bi: int) -> float:
    return -vis * math.cos(2*(A[ai] - B[bi]))

def sample_from_E(E: float, rng) -> tuple[int, int]:
    a_bit = 1 if rng.random() < 0.5 else 0
    same  = rng.random() < (1 + E) / 2
    b_bit = a_bit if same else a_bit ^ 1
    return a_bit, b_bit

def run_e91(N_pairs=400_000, key_fraction=0.85, p_flip=0.004, alpha_CI=0.02, seed=2025):
    rng = np.random.default_rng(seed)
    vis = max(0.0, 1 - 2*p_flip)

    a_key, b_key = [], []
    ch = {(0,0): [0,0], (0,1): [0,0], (1,0): [0,0], (1,1): [0,0]}

    for _ in range(N_pairs):
        if rng.random() < key_fraction:
            a = 1 if rng.random() < 0.5 else 0
            b = a ^ (1 if rng.random() < p_flip else 0)
            a_key.append(a); b_key.append(b)
        else:
            ai = rng.integers(0, 2); bi = rng.integers(0, 2)
            E = E_theory(vis, ai, bi)
            a, b = sample_from_E(E, rng)
            eq = 1 if a == b else 0
            rec = ch[(ai, bi)]; rec[0] += eq; rec[1] += 1

    a_key = np.array(a_key, dtype=np.uint8)
    b_key = np.array(b_key, dtype=np.uint8)
    n_key = len(a_key)
    qber  = float(np.mean(a_key ^ b_key)) if n_key > 0 else 0.0

    E_pt, E_lb = {}, {}
    for ai, bi in [(0,0), (0,1), (1,0), (1,1)]:
        eq, tot = ch[(ai, bi)]
        if tot == 0:
            E_pt[(ai,bi)] = 0.0; E_lb[(ai,bi)] = -1.0
        else:
            p_eq = eq / tot
            E_pt[(ai,bi)] = 2*p_eq - 1
            lo, _ = wilson_CI(eq, tot, alpha_CI)
            E_lb[(ai,bi)] = 2*lo - 1

    S_pt = E_pt[(0,0)] + E_pt[(0,1)] + E_pt[(1,0)] - E_pt[(1,1)]
    S_LB = E_lb[(0,0)] + E_lb[(0,1)] + E_lb[(1,0)] - E_lb[(1,1)]
    return {"a_key": a_key, "b_key": b_key, "n_key": n_key,
            "qber": qber, "S_pt": S_pt, "S_LB": S_LB}

# ===== CASCADE風EC（インターリーブ+追加ラウンド） =====
def parity(arr: np.ndarray) -> int:
    return int(np.bitwise_xor.reduce(arr) if len(arr) else 0)

def bs_fix(a: np.ndarray, b: np.ndarray, l: int, r: int) -> int:
    leak = 0
    while r - l > 1:
        m = (l + r) // 2
        leak += 1
        if parity(a[l:m]) != parity(b[l:m]):
            r = m
        else:
            l = m
    b[l] ^= 1
    return leak

def cascade(a_key: np.ndarray, b_key: np.ndarray,
            passes=(256,128,64,32,16,8,4,2,1), extra=2, seed=2025):
    rng = np.random.default_rng(seed)
    a = a_key.copy(); b = b_key.copy(); n = len(a); leak = 0

    def one_pass(bs: int):
        nonlocal leak, a, b
        for s in range(0, n, bs):
            e = min(s + bs, n)
            if parity(a[s:e]) != parity(b[s:e]):
                leak += 1
                leak += bs_fix(a, b, s, e)

    for bs in passes:
        perm = rng.permutation(n)
        a = a[perm]; b = b[perm]
        one_pass(bs)
        inv = np.empty_like(perm); inv[perm] = np.arange(n)
        a = a[inv]; b = b[inv]
    for _ in range(extra):
        one_pass(1)

    mism = int(np.sum(a ^ b))
    return b, leak, mism

# ===== 認証（タグ消費モデル） =====
def consume_tag(bits: np.ndarray, tag_bits=128) -> tuple[np.ndarray, int, bool]:
    if len(bits) < tag_bits:
        return bits.copy(), 0, False
    return bits[:-tag_bits].copy(), tag_bits, True

# ===== パイプライン =====
def pipeline(N_pairs=400_000, key_fraction=0.85, p_flip=0.004, alpha_CI=0.02,
             passes=(256,128,64,32,16,8,4,2,1), tag_bits=128, safety_bits=80, seed=2025):
    sim = run_e91(N_pairs, key_fraction, p_flip, alpha_CI, seed)
    a_key, b_key = sim["a_key"], sim["b_key"]

    b_corr, leak_ec, mism = cascade(a_key, b_key, passes, extra=2, seed=seed)

    # 認証タグを消費（等長に揃える）
    a_tag, leak_tag_a, ok_a = consume_tag(a_key, tag_bits)
    b_tag, leak_tag_b, ok_b = consume_tag(b_corr, tag_bits)
    leak_tag = max(leak_tag_a, leak_tag_b)
    auth_ok  = (mism == 0 and ok_a and ok_b)  # 参考（今は未使用）

    # PA
    n_after = len(a_tag)
    leak_total = leak_ec + leak_tag + safety_bits
    m = max(0, n_after - leak_total)
    a_final = sha256_amp(a_tag, m)
    b_final = sha256_amp(b_tag, m)
    equal = bool(np.array_equal(a_final, b_final))

    return {
        "n_key": sim["n_key"], "qber": sim["qber"], "S_pt": sim["S_pt"], "S_LB": sim["S_LB"],
        "leak_ec": leak_ec, "mism": mism, "leak_tag": leak_tag, "safety": safety_bits,
        "m": m, "equal": equal, "a_final": a_final, "b_final": b_final
    }

# ===== OTP デモ（鍵が短ければメッセージを自動フィット） =====
def otp_encrypt_decrypt(message: str, key_bits: np.ndarray) -> tuple[str, str, str]:
    key_bytes = bits_to_bytes(key_bits)
    mb = message.encode("utf-8")
    L = min(len(mb), len(key_bytes))
    if L == 0:
        return "", "", "（鍵長が0のためOTPデモはスキップしました）"
    mb_fit = mb[:L]
    cipher = bytes(mb_fit[i] ^ key_bytes[i] for i in range(L))
    plain  = bytes(cipher[i] ^ key_bytes[i] for i in range(L)).decode("utf-8", "ignore")
    note = "" if len(mb) == L else "※メッセージを鍵の長さに合わせて切り詰めました"
    return cipher.hex(), plain, note

# ===== メイン =====
if __name__ == "__main__":
    res = pipeline(
        N_pairs=400_000,      # 統計を厚めに
        key_fraction=0.85,    # 鍵85% / CHSH15%
        p_flip=0.004,         # ≈0.4%誤り
        alpha_CI=0.02,        # ≈98%CI
        passes=(256,128,64,32,16,8,4,2,1),
        tag_bits=128,
        safety_bits=80,
        seed=2025
    )

    print("\n=== 段階40: 最終鍵までフル実行 ===")
    print(f"鍵候補 n_key = {res['n_key']:,}，QBER = {100*res['qber']:.2f}%")
    print(f"CHSH 推定 S_point = {res['S_pt']:.4f}，下限 S_LB = {res['S_LB']:.4f}（>2 で量子相関OK）")
    print(f"[EC] 公開パリティ漏えい = {res['leak_ec']:,} ビット，EC後の不一致 = {res['mism']}")
    print(f"[AUTH] タグ消費 = {res['leak_tag']} ビット")
    print(f"[PA] セーフティ = {res['safety']} ビット")
    print(f"→ 最終鍵 m = {res['m']:,}，equal={res['equal']}")

    # OTPデモ（鍵が空でなければ）
    cipher, decrypted, note = otp_encrypt_decrypt("E91で作った鍵で暗号化テスト🔐", res['a_final'])
    print("\n=== OTP暗号デモ ===")
    if cipher:
        print("暗号文 (hex):", cipher)
        print("復号メッセージ:", decrypted)
        if note:
            print(note)
    else:
        print("鍵が0ビットのためデモは実行しませんでした。")

    # 失敗時のヒント
    if not res['equal'] or res['m'] == 0:
        print("\n[ヒント]")
        print("・N_pairs を増やす / key_fraction を上げる（S_LBの安定 & 鍵候補増）")
        print("・passes を増やす（ECをより強力に）")
        print("・p_flip を小さく（良い回線想定）")

