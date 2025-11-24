# qkd_E91_maxkey.py
# 目的: E91 を 100 km 条件で "最終鍵 m" を最大化
# 方針: CHSHは最小限で合格→鍵集めに集中 / QBER検査5% / 簡易CascadeでEC漏洩を低減

import numpy as np, math, hashlib
rng = np.random.default_rng(0)

# ===== 固定条件（長距離・低ノイズ） =====
DIST_KM          = 100          # 総距離（中間にもつれ源想定→片腕50 km）
ALPHA_DB_PER_KM  = 0.20         # ファイバ損失 [dB/km]
ETA_DET          = 0.90         # 検出効率
P_DARK           = 1e-8         # ダーク確率/ゲート（SNSPD+狭窓想定）
E_MIS            = 0.010        # ミスアラインメント ≈1%
TRIALS_TOTAL     = 300_000      # 総試行回数（増やすほど m↑）
EPS_SEC          = 1e-6         # プライバシー増幅の安全余裕（教育用）

# ===== 最適化ノブ =====
# CHSHを「必要最小限」で合格させる設定
CHSH_MIN_PER     = 200          # 各( a∈{0,1}, b∈{0,1} )で最低この件数の同時計数
CHSH_MARGIN      = 0.05         # 合格判定: S > 2 + 余裕
CHSH_MAX_TRIALS  = TRIALS_TOTAL // 3   # CHSHに使う上限（超えたら残りは鍵）

# QBERの検査割合（捨てる割合）
TEST_FRAC        = 0.05         # 5%（多すぎると m↓、少なすぎると推定が荒れる）

# 誤り訂正（簡易Cascade）ブロックサイズ列（誤り率~1%向け）
EC_ROUNDS        = (256, 128, 64, 32, 16, 8, 4, 2, 2)

# 測定角（CHSH最大違反）
A_ANGLES = [0.0, np.pi/4]
B_ANGLES = [ np.pi/8, -np.pi/8]

# ----------------- ユーティリティ -----------------
def transmittance_total(distance_km: float) -> float:
    arm = distance_km / 2.0
    T_one = 10 ** ( - ALPHA_DB_PER_KM * arm / 10.0 )
    return T_one * T_one

def sample_correlated_bits(theta_a, theta_b, visibility):
    d = theta_a - theta_b
    E = visibility * math.cos(2.0 * d)
    p_same = (1.0 + E) / 2.0
    a = rng.integers(0, 2)
    b = a if rng.random() < p_same else 1 - a
    return a, b

def parity(arr: np.ndarray) -> int:
    return int(np.bitwise_xor.reduce(arr) if len(arr) else 0)

def block_parity_once(a: np.ndarray, b: np.ndarray, block_size: int):
    a = a.copy(); b = b.copy()
    n = len(a); leakage = 0
    for s in range(0, n, block_size):
        e = min(s + block_size, n)
        # 教育用: 不一致ブロックのみ公開としてカウント
        if parity(a[s:e]) != parity(b[s:e]):
            l, r = s, e
            leakage += 1
            while r - l > 1:
                m = (l + r) // 2
                leakage += 1
                if parity(a[l:m]) != parity(b[l:m]): r = m
                else:                              l = m
            b[l] ^= 1
    return b, leakage

def cascade_like_ec(a_key: np.ndarray, b_key: np.ndarray, rounds=EC_ROUNDS, seed=1234):
    rng_local = np.random.default_rng(seed)
    b = b_key.copy()
    total_leak = 0
    for i, bs in enumerate(rounds, 1):
        perm = np.arange(len(a_key)); rng_local.shuffle(perm)
        inv = np.argsort(perm)
        a_p, b_p = a_key[perm], b[perm]
        b_corr, leak = block_parity_once(a_p, b_p, bs)
        b = b_corr[inv]; total_leak += leak
        mism = int(np.sum(a_key ^ b))
        print(f"[EC] round{i} bs={bs:>3}  mismatches={mism}  leak+={leak}  total_leak={total_leak}")
        if mism == 0: break
    return b, total_leak

def privacy_amp_sha256(bits: np.ndarray, m: int) -> np.ndarray:
    if m <= 0 or len(bits) == 0: return np.array([], dtype=np.uint8)
    raw = bytes(bits.tolist())
    out = bytearray(); c = 0
    while len(out) * 8 < m:
        out.extend(hashlib.sha256(raw + c.to_bytes(4, "big")).digest()); c += 1
    bitstr = "".join(f"{b:08b}" for b in out)[:m]
    return np.fromiter((1 if ch == "1" else 0 for ch in bitstr), dtype=np.uint8)

def bits_to_bytes(bits: np.ndarray):
    bits = np.asarray(bits, dtype=np.uint8)
    pad = (-len(bits)) % 8
    if pad: bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    return bytes(np.packbits(bits).tolist()), pad

def xor_bytes(a: bytes, b: bytes) -> bytes:
    m = min(len(a), len(b))
    return bytes([a[i] ^ b[i] for i in range(m)])

def utf8_truncate(s: str, max_bytes: int):
    b = s.encode("utf-8")
    if len(b) <= max_bytes: return s, b
    b = b[:max_bytes]
    while True:
        try:    return b.decode("utf-8"), b
        except UnicodeDecodeError: b = b[:-1]

def expectation_from_bits(a_bits: np.ndarray, b_bits: np.ndarray) -> float:
    if len(a_bits) == 0: return 0.0
    return 1.0 - 2.0 * float(np.mean(a_bits ^ b_bits))

def chsh_value(acc):
    # acc は各設定の (alist, blist) の辞書
    def E(k):
        a = np.array(acc[k][0], dtype=np.uint8)
        b = np.array(acc[k][1], dtype=np.uint8)
        return expectation_from_bits(a, b)
    E00 = E((0,0)); E01 = E((0,1)); E10 = E((1,0)); E11 = E((1,1))
    return E00 + E01 + E10 - E11, (E00, E01, E10, E11)

# ----------------- メイン処理 -----------------
def run_and_maximize():
    # 透過率・可視度
    Ttot = transmittance_total(DIST_KM)
    p_sig_one = math.sqrt(Ttot)
    visibility = max(0.0, 1.0 - 2.0 * E_MIS)

    # 1) CHSH フェーズ（必要最小限）
    acc = { (0,0): ([],[]), (0,1): ([],[]), (1,0): ([],[]), (1,1): ([],[]) }
    used = 0
    while used < CHSH_MAX_TRIALS:
        used += 1
        ai = int(rng.integers(0,2)); bi = int(rng.integers(0,2))
        ta, tb = A_ANGLES[ai], B_ANGLES[bi]

        # 検出の「由来」を一意に決定
        # Alice
        sig_a = (rng.random() < p_sig_one)
        det_a = False; origin_a = None
        if sig_a and rng.random() < ETA_DET: det_a, origin_a = True, "signal"
        elif rng.random() < P_DARK:          det_a, origin_a = True, "dark"
        # Bob
        sig_b = (rng.random() < p_sig_one)
        det_b = False; origin_b = None
        if sig_b and rng.random() < ETA_DET: det_b, origin_b = True, "signal"
        elif rng.random() < P_DARK:          det_b, origin_b = True, "dark"

        if not(det_a and det_b): continue

        # ビット生成
        if origin_a=="signal" and origin_b=="signal":
            a_bit, b_bit = sample_correlated_bits(ta, tb, visibility)
        else:
            a_bit, b_bit = rng.integers(0,2), rng.integers(0,2)

        acc[(ai,bi)][0].append(a_bit)
        acc[(ai,bi)][1].append(b_bit)

        # すべての設定で最低件数がたまっていて、S>2+margin なら打ち切り
        if all(len(acc[k][0]) >= CHSH_MIN_PER for k in acc):
            S, Es = chsh_value(acc)
            if S > 2.0 + CHSH_MARGIN: break

    # CHSH 最終値
    S, (E00,E01,E10,E11) = chsh_value(acc)

    # 2) 鍵フェーズ（残りの試行を鍵に全振り）
    key_a, key_b = [], []
    for _ in range(TRIALS_TOTAL - used):
        ta = tb = 0.0   # 同角度（鍵用）
        # 由来判定
        sig_a = (rng.random() < p_sig_one)
        det_a = False; origin_a = None
        if sig_a and rng.random() < ETA_DET: det_a, origin_a = True, "signal"
        elif rng.random() < P_DARK:          det_a, origin_a = True, "dark"
        sig_b = (rng.random() < p_sig_one)
        det_b = False; origin_b = None
        if sig_b and rng.random() < ETA_DET: det_b, origin_b = True, "signal"
        elif rng.random() < P_DARK:          det_b, origin_b = True, "dark"
        if not(det_a and det_b): continue
        if origin_a=="signal" and origin_b=="signal":
            a_bit, b_bit = sample_correlated_bits(ta, tb, visibility)
        else:
            a_bit, b_bit = rng.integers(0,2), rng.integers(0,2)
        key_a.append(a_bit); key_b.append(b_bit)

    a_sift = np.array(key_a, dtype=np.uint8)
    b_sift = np.array(key_b, dtype=np.uint8)

    # 3) QBER推定（5%公開）
    if len(a_sift)==0:
        raise RuntimeError("同時計数がゼロ。TRIALS_TOTAL を増やすか条件を緩めてください。")
    k = max(1, int(len(a_sift) * TEST_FRAC))
    idx = np.random.default_rng(1).choice(len(a_sift), size=k, replace=False)
    qber = float(np.mean(a_sift[idx] ^ b_sift[idx]))
    mask = np.ones(len(a_sift), dtype=bool); mask[idx] = False
    a_key, b_key = a_sift[mask], b_sift[mask]

    # 4) 誤り訂正（簡易Cascade）
    b_corr, leak_ec = cascade_like_ec(a_key, b_key, rounds=EC_ROUNDS)
    mism = int(np.sum(a_key ^ b_corr))

    # 5) プライバシー増幅
    safety = int(math.ceil(2 * math.log2(1 / EPS_SEC)))
    n_after = len(a_key)
    m = max(0, n_after - leak_ec - safety)
    a_final = privacy_amp_sha256(a_key,  m)
    b_final = privacy_amp_sha256(b_corr, m)
    equal = bool(np.array_equal(a_final, b_final))

    # 結果まとめ
    out = {
        "S": S, "E": (E00,E01,E10,E11), "used_for_CHSH": used,
        "sifted": len(a_sift), "test": k, "qber": qber,
        "kept_for_EC": n_after, "EC_leak": leak_ec, "mism_after_EC": mism,
        "safety": safety, "m": m, "equal": equal,
        "a_final": a_final, "b_final": b_final
    }
    return out

# ----------------- 実行 -----------------
if __name__ == "__main__":
    out = run_and_maximize()
    E00,E01,E10,E11 = out["E"]
    print(f"=== E91 max-key @ {DIST_KM} km ===")
    print(f"CHSH S = {out['S']:.4f}  (E00={E00:.4f}, E01={E01:.4f}, E10={E10:.4f}, E11={E11:.4f})")
    print(f"used_for_CHSH={out['used_for_CHSH']} / {TRIALS_TOTAL}")
    print(f"sifted={out['sifted']} | test={out['test']} ({100*TEST_FRAC:.1f}%) | QBER={100*out['qber']:.2f}%")
    print(f"kept_for_EC={out['kept_for_EC']} | EC_leak={out['EC_leak']} | mism_after_EC={out['mism_after_EC']}")
    print(f"safety={out['safety']} | m={out['m']} | equal={out['equal']}")
    if out["m"] > 0 and out["equal"]:
        # 確認: XORデモ
        msg = "E91で作った鍵で暗号化テスト🗝️"
        key_bytes, _ = bits_to_bytes(out["a_final"])
        msg_fit, msg_bytes = utf8_truncate(msg, len(key_bytes))
        cipher = xor_bytes(msg_bytes, key_bytes[:len(msg_bytes)])
        plain  = xor_bytes(cipher,    key_bytes[:len(msg_bytes)])
        print(f"cipher(hex)={cipher.hex()}")
        print(f"decrypted ={plain.decode('utf-8')}")
    else:
        print("※ equal=False または m=0 のため XOR デモはスキップ")

