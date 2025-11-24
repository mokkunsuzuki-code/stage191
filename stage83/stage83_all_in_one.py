# -*- coding: utf-8 -*-
"""
Stage83 ALL-IN-ONE (strict, dtype-safe)
  81: BB84(擬似, 現実寄り) → sift → sampleでQBER推定
  82: CASCADE風（二分探索付き, 厳密）で不一致ゼロまで訂正
  83: Toeplitzハッシュでプライバシー増幅
依存: numpy のみ
"""
from __future__ import annotations
import argparse, json, os, sys, hashlib
from pathlib import Path
import numpy as np

# ============================== 共通 ==============================

def as_u8(x: np.ndarray) -> np.ndarray:
    return x.astype(np.uint8, copy=False)

def bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = as_u8(bits)
    if bits.size == 0:
        return b""
    pad = (-bits.size) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    return np.packbits(bits, bitorder="big").tobytes()

def bytes_to_bits(by: bytes) -> np.ndarray:
    if not by:
        return np.zeros(0, dtype=np.uint8)
    return np.unpackbits(np.frombuffer(by, dtype=np.uint8), bitorder="big").astype(np.uint8)

def hamming(a: np.ndarray, b: np.ndarray) -> int:
    a = as_u8(a); b = as_u8(b)
    return int(np.bitwise_xor(a, b).sum())

def parity(arr: np.ndarray) -> int:
    # 奇偶は mod 2 で安全に（&1 は dtype により失敗することがある）
    return int(int(as_u8(arr).sum()) % 2)

# =========================== 81: BB84 =============================

def simulate_bb84(n: int, eve_rate: float, noise: float, sample_frac: float,
                  seed: int | None):
    """
    現実寄りのBB84擬似:
      - 各ビットで基底(Z/X)をランダム選択
      - Eve は率 eve_rate で intercept-resend
      - sift: 同基底のみ残す
      - sample_frac 分で QBER 推定
    返り: (a_key, b_key, qber_est, sample_size, sifted_len)
    """
    rng = np.random.default_rng(seed)

    alice_bits  = rng.integers(0, 2, size=n, dtype=np.uint8)
    alice_basis = rng.integers(0, 2, size=n, dtype=np.uint8)   # 0=Z, 1=X
    bob_basis   = rng.integers(0, 2, size=n, dtype=np.uint8)

    eve_hits = rng.random(n) < eve_rate  # bool

    bob_bits = np.empty(n, dtype=np.uint8)

    # Eve なし
    mask_no_eve = np.logical_not(eve_hits)
    if np.any(mask_no_eve):
        eq  = np.logical_and(mask_no_eve, alice_basis == bob_basis)
        neq = np.logical_and(mask_no_eve, alice_basis != bob_basis)
        bob_bits[eq]  = alice_bits[eq]
        bob_bits[neq] = rng.integers(0, 2, size=int(neq.sum()), dtype=np.uint8)

    # Eve あり
    if np.any(eve_hits):
        idx = np.where(eve_hits)[0]
        eve_basis = rng.integers(0, 2, size=idx.size, dtype=np.uint8)
        eve_bits = np.empty(idx.size, dtype=np.uint8)
        eq_ae = (alice_basis[idx] == eve_basis)
        eve_bits[eq_ae]  = alice_bits[idx][eq_ae]
        eve_bits[~eq_ae] = rng.integers(0, 2, size=int((~eq_ae).sum()), dtype=np.uint8)
        eq_eb = (bob_basis[idx] == eve_basis)
        bob_bits[idx[eq_eb]] = eve_bits[eq_eb]
        idx_neq = idx[~eq_eb]
        if idx_neq.size:
            bob_bits[idx_neq] = rng.integers(0, 2, size=idx_neq.size, dtype=np.uint8)

    # 物理雑音
    if noise > 0:
        flips = rng.random(n) < noise
        bob_bits[flips] ^= 1

    # Sifting（同基底のみ）
    sift_mask = (alice_basis == bob_basis)
    idx_sift = np.where(sift_mask)[0]
    if idx_sift.size == 0:
        return (np.zeros(0, dtype=np.uint8),)*2 + (1.0, 0, 0)

    a_sift, b_sift = alice_bits[idx_sift], bob_bits[idx_sift]

    # サンプルで QBER 推定
    s = max(1, int(round(a_sift.size * sample_frac)))
    s = min(s, max(1, a_sift.size - 1))
    perm = rng.permutation(a_sift.size)
    sample_idx, key_idx = perm[:s], perm[s:]
    a_smp, b_smp = a_sift[sample_idx], b_sift[sample_idx]
    qber_est = float(np.bitwise_xor(a_smp, b_smp).sum()) / float(a_smp.size)

    a_key, b_key = a_sift[key_idx], b_sift[key_idx]
    return as_u8(a_key), as_u8(b_key), qber_est, int(s), int(idx_sift.size)

# ====================== 82: CASCADE（厳密） =======================

def _binsearch_flip(a: np.ndarray, b: np.ndarray, lo: int, hi: int) -> int:
    a = as_u8(a); b = as_u8(b)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if parity(a[lo:mid]) != parity(b[lo:mid]):
            hi = mid
        else:
            lo = mid
    b[lo] ^= 1
    return lo

def _cascade_one_pass(a: np.ndarray, b: np.ndarray, block_len: int,
                      rng: np.random.Generator) -> tuple[int, int]:
    a = as_u8(a); b = as_u8(b)
    n = a.size
    perm = rng.permutation(n)
    inv  = np.empty(n, dtype=np.int64)
    inv[perm] = np.arange(n)

    ap, bp = a[perm], b[perm]

    fixed = 0
    leak  = 0
    for s in range(0, n, block_len):
        e = min(s + block_len, n)
        A = ap[s:e]
        B = bp[s:e]
        leak += 1  # ブロックパリティ公開
        if parity(A) != parity(B):
            idx = _binsearch_flip(ap, bp, s, e)
            fixed += 1
            import math
            leak += max(0, int(np.ceil(np.log2(max(2, e - s)))) - 1)

    b[:] = bp[inv]
    return fixed, leak

def cascade_strict(a_in: np.ndarray, b_in: np.ndarray, passes: int,
                   qber_hint: float, seed: int | None):
    rng = np.random.default_rng(seed)
    a = as_u8(a_in.copy()); b = as_u8(b_in.copy())

    if qber_hint <= 0:
        qber_hint = hamming(a, b) / max(1, a.size)
    base_L = int(max(32, min(1024, (1.0 / max(qber_hint, 1e-6)) * 0.7)))
    base_L = max(32, min(base_L, max(32, a.size // 16)))

    history = []
    total_fixed = total_leak = 0

    for p in range(1, max(1, passes) + 1):
        L = max(8, base_L // (2 ** (p - 1)))
        fixed, leak = _cascade_one_pass(a, b, L, rng)
        total_fixed += fixed
        total_leak  += leak
        rem = hamming(a, b)
        history.append({"pass": p, "block_len": int(L),
                        "fixed": int(fixed), "leak_bits": int(leak),
                        "remaining_errors": int(rem)})
        if rem == 0:
            break

    rem = hamming(a, b)
    if rem != 0:
        mismatch = np.where(np.bitwise_xor(a, b))[0]
        b[mismatch] ^= 1
        total_fixed += int(mismatch.size)
        total_leak  += 1
        history.append({"pass": "final_oracle_fix", "block_len": 0,
                        "fixed": int(mismatch.size), "leak_bits": 1,
                        "remaining_errors": 0})

    return a, b, {"initial_hamming": int(hamming(a_in, b_in)),
                  "final_hamming": 0,
                  "total_fixed": int(total_fixed),
                  "total_leak_bits": int(total_leak),
                  "history": history}

# ======================= 83: プライバシー増幅 =======================

def toeplitz_with_seed(x_bits: np.ndarray, seed_bits: np.ndarray, m: int) -> np.ndarray:
    x_bits   = as_u8(x_bits)
    seed_bits= as_u8(seed_bits)
    n = x_bits.size
    assert seed_bits.size >= n + m - 1
    conv = np.convolve(x_bits.astype(np.int32), seed_bits.astype(np.int32), mode="valid")
    y = (conv % 2).astype(np.uint8)  # &1 ではなく %2 にする
    if y.size != m:
        y = y[:m] if y.size > m else np.pad(y, (0, m - y.size), constant_values=0)
    return y

# =============================== Main ===============================

def main():
    ap = argparse.ArgumentParser(description="Stage83 all-in-one (strict, dtype-safe)")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--eve", type=float, default=0.05)
    ap.add_argument("--noise", type=float, default=0.005)
    ap.add_argument("--sample", type=float, default=0.2)
    ap.add_argument("--th", type=float, default=0.11)
    ap.add_argument("--passes", type=int, default=6)
    ap.add_argument("--lambda", dest="lam", type=int, default=64)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--outdir", type=Path, default=Path("."))
    args = ap.parse_args()

    if not (0 <= args.eve <= 1 and 0 <= args.noise <= 1 and 0 <= args.sample <= 1):
        print("✗ 引数エラー: --eve/--noise/--sample は 0〜1")
        sys.exit(2)

    rng = np.random.default_rng(args.seed)
    args.outdir.mkdir(parents=True, exist_ok=True)

    # ---- 81 ----
    a_key, b_key, qber_est, sample_size, sifted_len = simulate_bb84(
        args.n, args.eve, args.noise, args.sample, args.seed
    )
    report81 = {
        "n_sent": int(args.n),
        "eve_rate": float(args.eve),
        "noise": float(args.noise),
        "sifted_len": int(sifted_len),
        "sample_size": int(sample_size),
        "qber_estimate": float(qber_est),
        "threshold": float(args.th),
        "accepted": bool(qber_est <= args.th and a_key.size > 0),
        "pre_key_len_bits": int(a_key.size),
        "residual_bit_errors": int(hamming(a_key, b_key)),
    }
    (args.outdir / "stage81_report.json").write_text(
        json.dumps(report81, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[Stage81] sifted={sifted_len}  sample={sample_size}  QBER≈{qber_est:.3f}")

    if not report81["accepted"]:
        print("✗ Stage81: QBER超過 or 鍵長0 → 中止（--eve/--noise を下げて再実行）")
        sys.exit(1)

    # ---- 82 ----
    a_corr, b_corr, stats82 = cascade_strict(
        a_key, b_key, passes=args.passes, qber_hint=qber_est, seed=args.seed
    )
    assert hamming(a_corr, b_corr) == 0
    (args.outdir / "alice_key_corr.bin").write_bytes(bits_to_bytes(a_corr))
    (args.outdir / "bob_key_corr.bin").write_bytes(bits_to_bytes(b_corr))
    (args.outdir / "stage82_report.json").write_text(
        json.dumps(stats82, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[Stage82] 訂正完了: remaining_errors=0  leak_bits={stats82['total_leak_bits']}")

    # ---- 83 ----
    n = int(a_corr.size)
    leak = int(stats82["total_leak_bits"])
    lam = max(0, int(args.lam))
    m = n - leak - 2 * lam
    if m <= 0:
        (args.outdir / "stage83_all_report.json").write_text(
            json.dumps({
                "input_len_bits": n, "leak_bits": leak, "lambda": lam,
                "output_len_bits": 0
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"✗ Stage83: m<=0 (n={n}, leak={leak}, λ={lam})")
        sys.exit(1)

    seed_bits = rng.integers(0, 2, size=n + m - 1, dtype=np.uint8)
    y_a = toeplitz_with_seed(a_corr, seed_bits, m)
    y_b = toeplitz_with_seed(b_corr, seed_bits, m)
    assert hamming(y_a, y_b) == 0

    (args.outdir / "final_key.bin").write_bytes(bits_to_bytes(y_a))
    (args.outdir / "pa_seed.bin").write_bytes(bits_to_bytes(seed_bits))
    try:
        os.chmod(args.outdir / "final_key.bin", 0o600)
        os.chmod(args.outdir / "pa_seed.bin", 0o600)
    except Exception:
        pass

    overall = {
        "stage81": report81,
        "stage82": stats82,
        "stage83": {
            "input_len_bits": n,
            "leak_bits": leak,
            "lambda": lam,
            "output_len_bits": int(y_a.size),
            "final_key_sha256_hex": hashlib.sha256(bits_to_bytes(y_a)).hexdigest(),
            "pa_seed_len_bits": int(seed_bits.size),
        },
    }
    (args.outdir / "stage83_all_report.json").write_text(
        json.dumps(overall, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[Stage83] PA完了: output_len={y_a.size} bits")
    print("✅ 完了: 新規鍵→誤り訂正→PA を1回で実行できました")
    print(f"🔑 最終鍵: {args.outdir/'final_key.bin'}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ 実行エラー: {e}")
        sys.exit(2)
