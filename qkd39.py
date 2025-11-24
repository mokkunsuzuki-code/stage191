# qkd39_final.py  -- 実用寄りE91(教育) 一発完走版
# 依存: numpy, hashlib（ともに標準/準標準）
# 目的: CHSH>2 を満たしつつ、EC→認証→PA を経て equal=True で最終鍵 m>0 を得る

from __future__ import annotations
import math, hashlib, secrets
import numpy as np

# =========================
#  小さなユーティリティ
# =========================
def h2(x: float) -> float:
    """2進エントロピー H2(x)"""
    if x <= 0.0 or x >= 1.0:
        return 0.0
    return -(x*math.log2(x) + (1-x)*math.log2(1-x))

def normal_ppf_acklam(p: float) -> float:
    """正規分布の百分位点関数 Φ^{-1}(p) （Acklam 近似）"""
    # 出典: Peter John Acklam, http://home.online.no/~pjacklam/notes/invnorm/
    # p∈(0,1)
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p in (0,1)")
    a = [ -3.969683028665376e+01,  2.209460984245205e+02,
          -2.759285104469687e+02,  1.383577518672690e+02,
          -3.066479806614716e+01,  2.506628277459239e+00 ]
    b = [ -5.447609879822406e+01,  1.615858368580409e+02,
          -1.556989798598866e+02,  6.680131188771972e+01,
          -1.328068155288572e+01 ]
    c = [ -7.784894002430293e-03, -3.223964580411365e-01,
          -2.400758277161838e+00, -2.549732539343734e+00,
           4.374664141464968e+00,  2.938163982698783e+00 ]
    d = [  7.784695709041462e-03,  3.224671290700398e-01,
           2.445134137142996e+00,  3.754408661907416e+00 ]
    plow  = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2*math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    if phigh < p:
        q = math.sqrt(-2*math.log(1-p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                 ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    q = p - 0.5
    r = q*q
    return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q / \
           (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)

def wilson_two_sided_CI(k: int, n: int, alpha: float) -> tuple[float,float]:
    """二項比率のWilson区間（安全側）。k成功, n試行"""
    if n == 0:
        return (0.0, 1.0)
    p = k/n
    z = normal_ppf_acklam(1 - alpha/2)
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return lo, hi

def bits_to_bytes(bits: np.ndarray) -> bytes:
    """0/1のnp.uint8配列→バイト列（先頭から詰める）"""
    if len(bits) == 0:
        return b""
    pad = (8 - (len(bits) % 8)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    by = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for b in bits[i:i+8]:
            v = (v<<1) | int(b)
        by.append(v)
    return bytes(by)

def sha256_privacy_amp(bits: np.ndarray, m: int) -> np.ndarray:
    """SHA-256連結でmビットへ圧縮"""
    if m <= 0:
        return np.zeros(0, dtype=np.uint8)
    raw = bits_to_bytes(bits)
    out = bytearray()
    ctr = 0
    while len(out)*8 < m:
        out.extend(hashlib.sha256(raw + ctr.to_bytes(4,'big')).digest())
        ctr += 1
    bitstr = ''.join(f'{b:08b}' for b in out)[:m]
    return np.fromiter((1 if c=='1' else 0 for c in bitstr), dtype=np.uint8)

# =========================
#  E91 もつれ測定の教育的シミュレーション
# =========================
# 角度は Tsirelson 最適化の定番: a0=0, a1=π/4, b0=π/8, b1=-π/8
A_ANGLES = [0.0, math.pi/4]
B_ANGLES = [ math.pi/8, -math.pi/8 ]

def chsh_expectation(visibility: float, ai: int, bi: int) -> float:
    """理想 singlet の相関 E = -vis*cos(2*(a-b))"""
    a = A_ANGLES[ai]; b = B_ANGLES[bi]
    return -visibility * math.cos(2*(a - b))

def sample_ab_from_E(E: float, rng: np.random.Generator) -> tuple[int,int]:
    """
    E = <A*B> を満たす ±1の相関サンプリング（周辺一様）
    P(A=B)= (1+E)/2,  P(A≠B)=(1-E)/2
    返り値は 0/1 ビット（±1→0/1 に写像）
    """
    A = 1 if rng.random() < 0.5 else -1
    same = rng.random() < (1+E)/2
    B = A if same else -A
    # ±1 → 0/1 に変換（-1→1, +1→0 でもどちらでも可）
    a_bit = 0 if A==1 else 1
    b_bit = 0 if B==1 else 1
    return a_bit, b_bit

def run_e91_once(N_pairs=300_000, key_fraction=0.80, p_flip=0.005, alpha_CI=0.02, seed=2025):
    """
    E91(教育)シミュレーション：
      - key_fraction の割合→鍵セット（Z相当、Bobにビット反転ノイズ p_flip）
      - 残り→CHSHセット（可変角、visibility=1-2*p_flip）
      - Wilson区間から各E_ijの下限を作り、S_LB=E00+E01+E10-E11 を計算
    """
    rng = np.random.default_rng(seed)
    vis = max(0.0, 1 - 2*p_flip)    # 可視度（単純モデル）

    # 記録
    a_key = []
    b_key = []

    # CHSH: 各組み合わせの一致回数
    ch_cnt = {(0,0):[0,0], (0,1):[0,0], (1,0):[0,0], (1,1):[0,0]}  # [equal, total]

    for _ in range(N_pairs):
        if rng.random() < key_fraction:
            # 鍵セット: 完全相関にBob側ビット反転ノイズ
            a = 1 if rng.random()<0.5 else 0
            b = a
            if rng.random() < p_flip:
                b ^= 1
            a_key.append(a); b_key.append(b)
        else:
            # CHSHセット
            ai = rng.integers(0,2); bi = rng.integers(0,2)
            E = chsh_expectation(vis, ai, bi)
            a,b = sample_ab_from_E(E, rng)
            eq = 1 if (a==b) else 0
            rec = ch_cnt[(ai,bi)]
            rec[0] += eq; rec[1] += 1

    a_key = np.array(a_key, dtype=np.uint8)
    b_key = np.array(b_key, dtype=np.uint8)
    n_key = int(len(a_key))
    qber = float(np.mean(a_key ^ b_key)) if n_key>0 else 0.0

    # CHSH 推定と“下限”の作成
    E_point = {}
    E_LB = {}
    for k,(ai,bi) in enumerate([(0,0),(0,1),(1,0),(1,1)]):
        eq, tot = ch_cnt[(ai,bi)]
        if tot==0:
            E_point[(ai,bi)] = 0.0
            E_LB[(ai,bi)] = -1.0  # 最悪
        else:
            p_eq = eq/tot
            # 一致率→相関 E = 2p_eq-1
            E_point[(ai,bi)] = 2*p_eq - 1
            # p_eq の下限→ E の下限
            lo, _ = wilson_two_sided_CI(eq, tot, alpha_CI)
            E_LB[(ai,bi)] = 2*lo - 1

    S_point =  E_point[(0,0)] + E_point[(0,1)] + E_point[(1,0)] - E_point[(1,1)]
    S_LB    =  E_LB[(0,0)]   + E_LB[(0,1)]   + E_LB[(1,0)]   - E_LB[(1,1)]

    return {
        "n_key": n_key,
        "a_key": a_key, "b_key": b_key,
        "qber": qber,
        "S_point": S_point, "S_LB": S_LB
    }

# =========================
#  CASCADE風 EC + インターリーブ + 追加パス
# =========================
def parity(arr: np.ndarray) -> int:
    return int(np.bitwise_xor.reduce(arr) if len(arr) else 0)

def binary_search_fix(a: np.ndarray, b: np.ndarray, l: int, r: int) -> int:
    """区間[l,r) 内で1ビット誤りを二分探索で修正。漏洩カウント（比較回数）を返す。"""
    leak = 0
    while r - l > 1:
        m = (l + r)//2
        leak += 1
        if parity(a[l:m]) != parity(b[l:m]):
            r = m
        else:
            l = m
    b[l] ^= 1
    return leak

def cascade_ec(a_key: np.ndarray, b_key: np.ndarray,
               passes=(256,128,64,32,16,8,4,2,1),
               interleave=True, seed=2025, extra_rounds=2):
    """
    CASCADE風EC（教育版）:
      - 各パスでブロック化→パリティ比較→不一致ブロックに二分探索
      - パス間でインターリーブ（同じseedのランダム並べ替え）
      - 必要なら小さいブロックで追加ラウンド
    返り値: b_corr, leak_ec(bit), mism_after
    """
    rng = np.random.default_rng(seed)
    a = a_key.copy()
    b = b_key.copy()
    n = len(a)
    leak = 0

    def one_pass(block_size: int) -> int:
        nonlocal leak, a, b
        mismatches = 0
        for s in range(0, n, block_size):
            e = min(s+block_size, n)
            if parity(a[s:e]) != parity(b[s:e]):
                leak += 1
                leak += binary_search_fix(a, b, s, e)
                mismatches += 1
        return mismatches

    # メインパス
    for bs in passes:
        if interleave:
            perm = rng.permutation(n)
            a = a[perm]; b = b[perm]
        mism = one_pass(bs)
        # インターリーブを戻す（次のパスのため）
        if interleave:
            inv = np.empty_like(perm)
            inv[perm] = np.arange(n)
            a = a[inv]; b = b[inv]

    # 必要なら追加で微細パス
    bs = 1
    for _ in range(extra_rounds):
        mism = one_pass(bs)

    mism_after = int(np.sum(a ^ b))
    return b, leak, mism_after

# =========================
#  認証タグ (Wegman–Carter 風)
# =========================
def consume_auth_tag(bits: np.ndarray, tag_bits=128) -> tuple[np.ndarray, int, bool]:
    """
    ハッシュタグ分のビットを消費して検証するとみなす（モデル化）。
    実装簡略化: bitsが空でなければ「検証成功」とする。
    """
    if len(bits) < tag_bits:
        return bits.copy(), 0, False
    # 消費（末尾を使う）
    return bits[:-tag_bits].copy(), tag_bits, True

# =========================
#  パイプライン: E91→EC→認証→PA
# =========================
def run_pipeline(N_pairs=300_000,
                 key_fraction=0.80,
                 p_flip=0.005,
                 alpha_CI=0.02,
                 cascade_passes=(256,128,64,32,16,8,4,2,1),
                 tag_bits=128,
                 safety_bits=80,
                 seed=2025):

    sim = run_e91_once(N_pairs=N_pairs, key_fraction=key_fraction,
                       p_flip=p_flip, alpha_CI=alpha_CI, seed=seed)
    a_key = sim["a_key"]; b_key = sim["b_key"]
    n_key = sim["n_key"]; qber = sim["qber"]
    S_point = sim["S_point"]; S_LB = sim["S_LB"]

    # --- 誤り訂正（CASCADE風） ---
    b_corr, leak_ec, mism_after = cascade_ec(a_key, b_key,
                        passes=cascade_passes, interleave=True,
                        seed=seed, extra_rounds=2)

    # 検証タグ（鍵一致の最終確認）
    a_after_ec = a_key.copy()
    # a側は既に正しいのでそのまま
    a_for_auth = a_after_ec
    b_for_auth = b_corr
    # 認証タグ分を消費（両者同じだけ消費）
    a_after_tag, leak_tag_a, auth_ok_a = consume_auth_tag(a_for_auth, tag_bits=tag_bits)
    b_after_tag, leak_tag_b, auth_ok_b = consume_auth_tag(b_for_auth, tag_bits=tag_bits)
    leak_tag = max(leak_tag_a, leak_tag_b)
    auth_ok = auth_ok_a and auth_ok_b and (mism_after==0)

    # --- プライバシー増幅 ---
    # 漏えい総量 = ECの公開パリティ数 + 認証タグ消費 + 安全マージン
    # 残り長さ = 現在の鍵長
    n_after = int(len(a_after_tag))
    leak_total = leak_ec + leak_tag + safety_bits
    m = max(0, n_after - leak_total)

    a_final = sha256_privacy_amp(a_after_tag, m)
    b_final = sha256_privacy_amp(b_after_tag, m)
    equal = bool(np.array_equal(a_final, b_final))

    return {
        "N_pairs": N_pairs,
        "key_fraction": key_fraction,
        "p_flip": p_flip,
        "alpha_CI": alpha_CI,
        "n_key": n_key,
        "qber": qber,
        "S_point": S_point,
        "S_LB": S_LB,
        "leak_ec": leak_ec,
        "mism_after_ec": mism_after,
        "leak_tag": leak_tag,
        "safety_bits": safety_bits,
        "m": m,
        "equal": equal,
        "auth_ok": auth_ok,
        "a_final": a_final,
        "b_final": b_final,
    }

# =========================
#  OTPテスト（一致＆長さ>0なら）
# =========================
def otp_demo(final_bits: np.ndarray, msg="E91で作った鍵で暗号化テスト🗝"):
    key_bytes = bits_to_bytes(final_bits)
    # UTF-8に丸め込み
    mb = msg.encode("utf-8")
    L = min(len(mb), len(key_bytes))
    if L == 0:
        return {"ok": False}
    cipher = bytes([mb[i] ^ key_bytes[i] for i in range(L)])
    plain  = bytes([cipher[i] ^ key_bytes[i] for i in range(L)]).decode("utf-8","ignore")
    return {"ok": True, "key_len_bits": len(final_bits), "cipher_hex": cipher.hex(), "recovered": plain}

# =========================
#  メイン（日本語表示）
# =========================
if __name__ == "__main__":
    out = run_pipeline(
        N_pairs=300_000,        # 統計を増やして S_LB>2 を安定化
        key_fraction=0.80,      # 鍵80% / CHSH20%
        p_flip=0.005,           # ≈0.5%の誤り率（良回線）
        alpha_CI=0.02,          # ≈98%信頼区間
        cascade_passes=(256,128,64,32,16,8,4,2,1),  # しっかり直す
        tag_bits=128,           # 認証タグ消費
        safety_bits=80,         # セーフティ
        seed=2025
    )

    print("\n=== 実用寄り E91（教育版・完全版）===")
    print(f"総ペア数 N = {out['N_pairs']:,}, 鍵に回した割合 = {out['key_fraction']:.2f}, ノイズ p = {100*out['p_flip']:.3f}%")
    print(f"鍵候補 n_key = {out['n_key']:,}, QBER = {100*out['qber']:.2f}%")
    print(f"CHSH 推定 S_point = {out['S_point']:.4f}, 下限 S_LB = {out['S_LB']:.4f}  （>2 なら量子相関OK）")
    print("\n[EC] CASCADE風")
    print(f"  公開パリティ総数 = {out['leak_ec']:,} ビット（情報漏えい）")
    print(f"  EC後の残り不一致 = {out['mism_after_ec']}  （0が理想）")
    print("\n[認証] Wegman–Carter 風（タグ消費）")
    print(f"  認証タグ消費 = {out['leak_tag']} ビット,  認証OK? = {out['auth_ok']}")
    print("\n[PA] SHA-256 で圧縮（プライバシー増幅）")
    print(f"  安全マージン safety = {out['safety_bits']} bits")
    print(f"=== 要約 ===")
    print(f"最終鍵 m = {out['m']:,},  equal={out['equal']}")

    if out["equal"] and out["m"]>0:
        demo = otp_demo(out["a_final"])
        print("\n[OTPデモ]")
        print(f"鍵長  = {demo['key_len_bits']} ビット")
        print(f"暗号文(hex) = {demo['cipher_hex']}")
        print(f"復号結果     = {demo['recovered']}")
    else:
        print("\n⚠️ 最終鍵が一致していないか長さ0です。")
        print("   ・CASCADEのパスを増やす / extra_rounds を増やす")
        print("   ・key_fraction を上げて統計を増やす（S_LB と ECの安定化）")
        print("   ・p_flip を少し下げる（回線が良い前提）")

