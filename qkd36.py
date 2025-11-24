# qkd36_fixed.py  —  E91（教育用）: 有限サイズ・下限つき最終鍵を“確実に”出す完全版
# 依存: Python 3.9+ / numpy
from __future__ import annotations

import math
import numpy as np


# ========= ユーティリティ =========
def h2(x: float) -> float:
    """2進エントロピー h2(x) = -x log2 x - (1-x) log2 (1-x)"""
    if x <= 0.0 or x >= 1.0:
        return 0.0
    return -(x * math.log2(x) + (1 - x) * math.log2(1 - x))


def wilson_interval(k: int, n: int, alpha: float = 1e-3) -> tuple[float, float]:
    """
    Wilson近似で二項比率の信頼区間 [lo, hi] を返す（教育用）。
    alpha=1e-3 → 99.9%信頼区間
    """
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    # 正規近似のz（両側）
    from math import sqrt
    # だいたいの近似：alpha=1e-3 → z≈3.29（99.9%）
    # alphaを変えてもOKなように逆誤差関数近似（ここでは固定でも十分）
    z = 3.29 if abs(alpha - 1e-3) < 1e-12 else 2.58  # 1e-3か、それ以外は99%相当
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return (lo, hi)


def chsh_min_entropy_term(S_LB: float) -> float:
    """
    Acín系の下限（教育用簡略版）: 量子相関の項 h2( (1+sqrt((S/2)^2-1))/2 )
    S_LB<=2 のときは相関優位が言えず、項は1に近づく→鍵率は0方向
    """
    if S_LB <= 2.0:
        return 1.0
    t = 0.5 * (1.0 + math.sqrt(max(0.0, (S_LB / 2.0) ** 2 - 1.0)))
    t = min(max(t, 0.5), 1.0)
    return h2(t)


def bits_to_bytes(bits: np.ndarray) -> tuple[bytes, int]:
    bits = np.asarray(bits, dtype=np.uint8)
    pad = (-len(bits)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    by = np.packbits(bits)
    return bytes(by.tolist()), pad


def utf8_truncate(s: str, max_bytes: int) -> tuple[str, bytes]:
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s, b
    b = b[:max_bytes]
    while True:
        try:
            return b.decode("utf-8"), b
        except UnicodeDecodeError:
            b = b[:-1]


def xor_bytes(a: bytes, b: bytes) -> bytes:
    m = min(len(a), len(b))
    return bytes([a[i] ^ b[i] for i in range(m)])


# ========= 物理モデル（高速・教育用） =========
def simulate_e91_samples(
    N_total: int,
    key_fraction: float,
    visibility: float,
    qber_true: float,
    rng: np.random.Generator,
):
    """
    教育用の高速サンプル生成：
    - テスト用: CHSHの4設定 (a0b0,a0b1,a1b0,a1b1) を均等割り当て
      理想の相関 E00=E01=E10=+1/√2、E11=-1/√2 を visibility でスケール
      → 不一致確率 p_ij=(1-Eij)/2 からビット一致/不一致を生成
    - 鍵用: 同一基底の対で、誤り率 qber_true のビット不一致を生成
    """
    n_key = int(N_total * key_fraction)
    n_test = N_total - n_key
    # ---- テスト（CHSH）----
    per = n_test // 4
    rem = n_test - 4 * per
    counts = [per, per, per, per]
    for i in range(rem):
        counts[i] += 1
    # 相関係数（教育用）
    c = visibility / math.sqrt(2.0)
    E00 = E01 = E10 = c
    E11 = -c
    # 不一致確率
    p00 = (1 - E00) / 2
    p01 = (1 - E01) / 2
    p10 = (1 - E10) / 2
    p11 = (1 - E11) / 2  # E11<0 → p11>0.5

    mism = []
    for p, n in zip([p00, p01, p10, p11], counts):
        # 不一致: 1、一致: 0 として数える
        mism.append(rng.binomial(n=n, p=p))

    # ---- 鍵用（同一基底セット）----
    key_mism = rng.binomial(n=n_key, p=qber_true)

    return {
        "n_key": n_key,
        "n_test": n_test,
        "test_counts": counts,        # 各設定の試行数
        "test_mismatches": mism,      # 各設定の不一致数
        "key_mismatches": key_mism,   # 鍵セットの不一致数
    }


# ========= 最終鍵の計算 =========
def compute_final_key(
    N_total: int = 200_000,       # 総ペア数（増やすと統計が安定）
    key_fraction: float = 0.80,   # 鍵に回す割合（残りがテスト）
    visibility: float = 0.98,     # 0～1：1で理想S=2√2、0.98でS≈2.77
    qber_true: float = 0.004,     # 実際の誤り率（0.4%）
    alpha: float = 1e-3,          # 信頼水準（99.9%）
    leak_per_bit: float = 0.02,   # 誤り訂正漏えい(bits/bit)の目安
    safety_bits: int = 40,        # 追加安全マージン（固定ビット）
    seed: int = 2025,
):
    rng = np.random.default_rng(seed)

    # 1) サンプル生成
    samp = simulate_e91_samples(
        N_total=N_total,
        key_fraction=key_fraction,
        visibility=visibility,
        qber_true=qber_true,
        rng=rng,
    )

    n_key = samp["n_key"]
    n_test = samp["n_test"]
    cts = samp["test_counts"]
    mis = samp["test_mismatches"]
    key_mis = samp["key_mismatches"]

    # 2) CHSHの下限（設定ごとの二項区間からE_ij下限→合成）
    E_lo = []
    E_point = []
    for n, m in zip(cts, mis):
        # 一致率 = 1 - (m/n) → 相関E = 2*一致率 - 1 = 1 - 2*(m/n)
        if n == 0:
            E_point.append(0.0)
            E_lo.append(0.0)
            continue
        p_hat = 1.0 - (m / n)
        lo, hi = wilson_interval(k=int(round(p_hat * n)), n=n, alpha=alpha)
        E_point.append(1.0 - 2.0 * (m / n))
        E_lo.append(1.0 - 2.0 * (1.0 - lo))

    E00, E01, E10, E11 = E_point
    E00_lo, E01_lo, E10_lo, E11_lo = E_lo

    S_point = E00 + E01 + E10 - E11
    S_LB = E00_lo + E01_lo + E10_lo - E11_lo  # 下限

    # 3) QBERの上限（鍵セットの二項区間）
    if n_key > 0:
        qhat = key_mis / n_key
        _, q_hi = wilson_interval(k=key_mis, n=n_key, alpha=alpha)
        Q_upper = q_hi
    else:
        qhat = 0.5
        Q_upper = 0.5

    # 4) Devetak–Winter の“下限鍵率” r_low
    chsh_term = chsh_min_entropy_term(S_LB)
    r_low = max(0.0, 1.0 - h2(Q_upper) - chsh_term)

    # 5) 最終鍵長 m = floor(n_key*r_low) - EC漏えい - 安全ビット - 有限サイズ補正Δ
    #    有限サイズ補正（教育用）：Δ = ceil(6 * sqrt(n_key))
    ell_raw = max(0, int(math.floor(n_key * r_low)))
    leak_EC = int(math.ceil(leak_per_bit * n_key))
    Delta = int(math.ceil(6.0 * math.sqrt(n_key)))
    m = max(0, ell_raw - leak_EC - safety_bits - Delta)

    out = {
        "N_total": N_total,
        "n_key": n_key,
        "n_test": n_test,
        "S_point": S_point,
        "S_LB": S_LB,
        "Q_hat": qhat,
        "Q_upper": Q_upper,
        "r_low": r_low,
        "ell_raw": ell_raw,
        "leak_EC": leak_EC,
        "Delta": Delta,
        "safety_bits": safety_bits,
        "m": m,
    }
    return out


# ========= OTPデモ（鍵が出たら実施） =========
def otp_demo(final_bits: int, seed: int = 7):
    rng = np.random.default_rng(seed)
    # ランダム鍵を生成（デモ用）
    key_bits = rng.integers(0, 2, size=final_bits, dtype=np.uint8)
    key_bytes, _ = bits_to_bytes(key_bits)

    # 適当な日本語メッセージを暗号化（鍵長以内に切る）
    msg = "E91で作った鍵で暗号化テスト🔒"
    msg_fit, msg_bytes = utf8_truncate(msg, len(key_bytes))

    cipher = xor_bytes(msg_bytes, key_bytes[: len(msg_bytes)])
    plain = xor_bytes(cipher, key_bytes[: len(msg_bytes)])

    return {
        "key_len_bits": final_bits,
        "cipher_hex": cipher.hex(),
        "recovered": plain.decode("utf-8"),
    }


# ========= メイン =========
def main():
    # ★ここが“成功させるため”の推奨値（そのままでもOK）
    RES = compute_final_key(
        N_total=200_000,       # 20万ペア
        key_fraction=0.80,     # 8割を鍵、2割をテスト
        visibility=0.98,       # S_point ≈ 2.77 付近を狙う
        qber_true=0.004,       # 0.4%（実験室レベルなら十分ありえる）
        alpha=1e-3,            # 99.9%信頼
        leak_per_bit=0.02,     # 誤り訂正の公開ヒント 0.02 bits/bit
        safety_bits=40,        # 固定の安全マージン
        seed=2025,
    )

    print("＝＝ 段階36 修正版（日本語表示）＝＝")
    print(f"N（総ペア数）= {RES['N_total']:,}")
    print(f"鍵候補 n_key = {RES['n_key']:,}、テスト n_test = {RES['n_test']:,}")
    print(f"CHSH推定点 S_point = {RES['S_point']:.4f}")
    print(f"CHSH下限   S_LB    = {RES['S_LB']:.4f}（2より十分大なら量子相関OK）")
    print(f"QBER点推定 Q_hat   = {100*RES['Q_hat']:.3f}%")
    print(f"QBER上限   Q_upper = {100*RES['Q_upper']:.3f}%（信頼区間の上側）")
    print(f"下限鍵率    r_low  = {RES['r_low']:.5f} bits/ペア")
    print(f"生鍵長      ell_raw= {RES['ell_raw']:,} bits（= floor(n_key*r_low)）")
    print(f"EC漏えい    leak_EC= {RES['leak_EC']:,} bits")
    print(f"有限サイズ  Δ      = {RES['Delta']:,} bits")
    print(f"安全ビット  safety = {RES['safety_bits']:,} bits")
    print(f"――――――――――――――――――――――――")
    print(f"最終鍵長    m      = {RES['m']:,} bits")

    if RES["m"] > 0:
        demo = otp_demo(RES["m"])
        print("\n[OTPデモ]")
        print(f"＊鍵長      = {demo['key_len_bits']:,} ビット")
        print(f"＊暗号文(hex)= {demo['cipher_hex']}")
        print(f"＊復号結果   = {demo['recovered']}")
    else:
        print("\n※ m=0 のため OTPデモはスキップしました。")
        print("  → N を増やす / visibility↑ / QBER↓ / alpha を少し緩める / leak_EC↓ / Δの扱い見直し 等で m>0 にできます。")


if __name__ == "__main__":
    main()

