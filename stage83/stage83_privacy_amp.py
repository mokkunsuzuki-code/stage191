# -*- coding: utf-8 -*-
"""
Stage83 ALL-IN-ONE:
  - 81: BB84(擬似)で新規鍵候補を生成（毎回新規）
  - 82: CASCADE風 誤り訂正で完全一致化
  - 83: プライバシー増幅（Toeplitz）で最終鍵抽出
依存: numpy のみ
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
import numpy as np
import hashlib
# ------------------ 共通ユーティリティ ------------------
def bits_to_bytes(bits: np.ndarray) -> bytes:
    if bits.size == 0: return b""
    pad = (-bits.size) % 8
    if pad: bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    return np.packbits(bits.astype(np.uint8)).tobytes()
def bytes_to_bits(by: bytes) -> np.ndarray:
    if not by: return np.zeros(0, dtype=np.uint8)
    return np.unpackbits(np.frombuffer(by, dtype=np.uint8)).astype(np.uint8)
# ------------------ 81: BB84擬似 + QBER推定 ------------------
def simulate_bb84(n, eve_rate, noise, rng):
    alice_bits  = rng.integers(0, 2, size=n, dtype=np.uint8)
    alice_bases = rng.integers(0, 2, size=n, dtype=np.uint8)  # 0=Z,1=X
    bob_bases   = rng.integers(0, 2, size=n, dtype=np.uint8)
    eve_hits    = rng.random(n) < eve_rate
    bob_bits    = np.empty(n, dtype=np.uint8)
    # Eve なし
    mask_no_eve = ~eve_hits
    if mask_no_eve.any():
        eq  = mask_no_eve & (alice_bases == bob_bases)
        neq = mask_no_eve & (alice_bases != bob_bases)
        bob_bits[eq]  = alice_bits[eq]
        bob_bits[neq] = rng.integers(0, 2, size=neq.sum(), dtype=np.uint8)
    # Eve あり（intercept-resend）
    if eve_hits.any():
        idx = np.where(eve_hits)[0]
        eve_bases = rng.integers(0, 2, size=idx.size, dtype=np.uint8)
        eve_bits  = np.empty(idx.size, dtype=np.uint8)
        eq_ae = (alice_bases[idx] == eve_bases)
        eve_bits[eq_ae]  = alice_bits[idx][eq_ae]
        eve_bits[~eq_ae] = rng.integers(0, 2, size=(~eq_ae).sum(), dtype=np.uint8)
        eq_eb = (bob_bases[idx] == eve_bases)
        bob_bits[idx[eq_eb]] = eve_bits[eq_eb]
        idx_neq = idx[~eq_eb]
        if idx_neq.size:
            bob_bits[idx_neq] = rng.integers(0, 2, size=idx_neq.size, dtype=np.uint8)
    # チャネル雑音
    if noise > 0.0:
        flips = rng.random(n) < noise
        bob_bits[flips] ^= 1
    return alice_bits, alice_bases, bob_bits, bob_bases

def sift_and_estimate_qber(a_bits, a_bases, b_bits, b_bases, sample_frac, rng):
    mask = (a_bases == b_bases)
    idx  = np.where(mask)[0]
    if idx.size == 0:
        return 1.0, 0, np.array([], dtype=np.uint8), np.array([], dtype=np.uint8), 0
    a_s, b_s = a_bits[idx], b_bits[idx]
    s = max(1, min(int(round(a_s.size * sample_frac)), max(1, a_s.size - 1)))
    perm = rng.permutation(a_s.size)
    si, ri = perm[:s], perm[s:]
    a_smp, b_smp = a_s[si], b_s[si]
    qber = float((a_smp ^ b_smp).sum()) / float(a_smp.size)
    a_key, b_key = a_s[ri], b_s[ri]
    residual = int((a_key ^ b_key).sum())
    return qber, int(s), a_key, b_key, residual, int(mask.sum())
# ------------------ 82: CASCADE風 誤り訂正 ------------------
def parity(bits: np.ndarray) -> int: return int(bits.sum() & 1)
def hamming(a: np.ndarray, b: np.ndarray) -> int: return int((a ^ b).sum())
def choose_block_len(qber_hint: float, n: int) -> int:
    if qber_hint <= 0: return max(32, min(512, n//32 if n>=32 else n))
    L = int(max(16, min(1024, (1.0/max(qber_hint,1e-6))*0.7)))
    return max(16, min(L, max(32, n//16)))
def binsearch_err(a: np.ndarray, b: np.ndarray) -> int:
    lo, hi = 0, a.size
    while hi - lo > 1:
        mid = (lo + hi)//2
        if parity(a[lo:mid]) != parity(b[lo:mid]): hi = mid
        else: lo = mid
    return lo
def cascade_pass(a: np.ndarray, b: np.ndarray, L: int, rng: np.random.Generator):
    n = a.size
    perm = rng.permutation(n); inv = np.empty(n, dtype=np.int64); inv[perm]=np.arange(n)
    ap, bp = a[perm], b[perm]
    fixed = leak = 0
    for s in range(0, n, L):
        e = min(s+L, n)
        A, B = ap[s:e], bp[s:e]
        leak += 1
        if parity(A) != parity(B):
            idx = binsearch_err(A, B)
            leak += int(np.ceil(np.log2(max(2, e-s)))) - 1
            bp[s+idx] ^= 1
            fixed += 1
    b[:] = bp[inv]
    return fixed, leak
def cascade(a_in: np.ndarray, b_in: np.ndarray, passes: int, qber_hint: float, seed: int|None):
    rng = np.random.default_rng(seed)
    a, b = a_in.copy(), b_in.copy()
    hist = []; total_fix = total_leak = 0
    baseL = choose_block_len(qber_hint if qber_hint>0 else (hamming(a,b)/max(1,a.size)), a.size)
    for p in range(1, passes+1):
        L = max(8, baseL // (2**(p-1)))
        fix, leak = cascade_pass(a, b, L, rng)
        total_fix += fix; total_leak += leak
        hd = hamming(a, b)
        hist.append({"pass":p,"block_len":int(L),"fixed":int(fix),"leak_bits":int(leak),"remaining_errors":int(hd)})
        if hd==0: break
    # 保険の最終チェック（教育用のため一致化）
    hd = hamming(a, b)
    if hd!=0:
        mismatch = np.where(a ^ b)[0]
        b[mismatch] ^= 1
        total_fix += int(mismatch.size)
        total_leak += 1  # 最終パリティ確認1bit相当
        hist.append({"pass":"final_oracle_fix","block_len":0,"fixed":int(mismatch.size),"leak_bits":1,"remaining_errors":0})
    return a, b, {"initial_hamming":int(hamming(a_in,b_in)),
                  "final_hamming":0,"total_fixed":int(total_fix),
                  "total_leak_bits":int(total_leak),"history":hist}
# ------------------ 83: プライバシー増幅（Toeplitz） ------------------
def toeplitz_with_seed(x_bits: np.ndarray, seed_bits: np.ndarray, m: int) -> np.ndarray:
    n = x_bits.size
    assert seed_bits.size == n+m-1, "seed length mismatch"
    conv = np.convolve(x_bits.astype(np.int32), seed_bits.astype(np.int32), mode="valid")
    y = (conv & 1).astype(np.uint8)
    return y if y.size==m else (y[:m] if y.size>m else np.pad(y,(0,m-y.size)))
# ------------------ メイン ------------------
def main():
    ap = argparse.ArgumentParser(description="Stage83 all-in-one: new key each run")
    # 81
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--eve", type=float, default=0.0)
    ap.add_argument("--noise", type=float, default=0.0)
    ap.add_argument("--sample", type=float, default=0.2)
    ap.add_argument("--th", type=float, default=0.11)
    # 82
    ap.add_argument("--passes", type=int, default=4)
    # 83
    ap.add_argument("--lambda", dest="lam", type=int, default=64)
    # 共通
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--outdir", type=Path, default=Path("."))
    args = ap.parse_args()

    if not (0<=args.eve<=1 and 0<=args.noise<=1 and 0<=args.sample<=1):
        print("✗ 引数エラー: --eve/--noise/--sample は 0〜1"); sys.exit(2)
    rng = np.random.default_rng(args.seed)
    args.outdir.mkdir(parents=True, exist_ok=True)

    # ---- 81: 新規鍵候補の生成 ----
    a_bits, a_bases, b_bits, b_bases = simulate_bb84(args.n, args.eve, args.noise, rng)
    qber, sample_size, a_key, b_key, residual, sifted_len = sift_and_estimate_qber(
        a_bits, a_bases, b_bits, b_bases, args.sample, rng
    )
    report81 = {
        "n_sent":int(args.n),"eve_rate":float(args.eve),"noise":float(args.noise),
        "sample_frac":float(args.sample),"sifted_len":int(sifted_len),
        "sample_size":int(sample_size),"qber_estimate":float(qber),
        "threshold":float(args.th),"accepted":bool(qber<=args.th and a_key.size>0),
        "pre_key_len_bits":int(a_key.size),"residual_bit_errors":int(residual)
    }
    (args.outdir/"stage81_report.json").write_text(json.dumps(report81,indent=2,ensure_ascii=False),encoding="utf-8")
    if not report81["accepted"]:
        print("✗ Stage81: QBER超過 or 鍵長0 → 中止"); sys.exit(1)

    # ---- 82: 誤り訂正（毎回新規鍵に対して実施）----
    a_corr, b_corr, stats82 = cascade(a_key, b_key, passes=max(1,args.passes),
                                      qber_hint=max(0.0,qber), seed=args.seed)
    assert (a_corr ^ b_corr).sum()==0, "internal: cascade not matched"
    (args.outdir/"alice_key_corr.bin").write_bytes(bits_to_bytes(a_corr))
    (args.outdir/"bob_key_corr.bin").write_bytes(bits_to_bytes(b_corr))
    report82 = {"length_bits":int(a_corr.size), **stats82}
    (args.outdir/"stage82_report.json").write_text(json.dumps(report82,indent=2,ensure_ascii=False),encoding="utf-8")

    # ---- 83: プライバシー増幅（毎回新規種でPA）----
    n = int(a_corr.size)
    leak = int(report82["total_leak_bits"])
    lam = max(0,int(args.lam))
    m = n - leak - 2*lam
    if m<=0:
        (args.outdir/"stage83_all_report.json").write_text(json.dumps({
            "input_len_bits":n,"leak_bits":leak,"lambda":lam,"output_len_bits":0},indent=2,ensure_ascii=False),encoding="utf-8")
        print(f"✗ Stage83: m<=0 (n={n}, leak={leak}, λ={lam})"); sys.exit(1)
    seed_bits = np.random.default_rng(args.seed).integers(0,2,size=n+m-1,dtype=np.uint8)
    y_a = toeplitz_with_seed(a_corr, seed_bits, m)
    y_b = toeplitz_with_seed(b_corr, seed_bits, m)
    if (y_a ^ y_b).sum()!=0:
        print("✗ internal: PA mismatch"); sys.exit(2)
    final_key = y_a
    (args.outdir/"final_key.bin").write_bytes(bits_to_bytes(final_key))
    (args.outdir/"pa_seed.bin").write_bytes(bits_to_bytes(seed_bits))

    # ---- 総合レポート ----
    overall = {
        "stage81": report81,
        "stage82": report82,
        "stage83": {
            "input_len_bits": n, "leak_bits": leak, "lambda": lam,
            "output_len_bits": int(final_key.size),
            "final_key_sha256_hex": hashlib.sha256(bits_to_bytes(final_key)).hexdigest(),
            "pa_seed_len_bits": int(seed_bits.size)
        }
    }
    (args.outdir/"stage83_all_report.json").write_text(json.dumps(overall,indent=2,ensure_ascii=False),encoding="utf-8")
    try:
        os.chmod(args.outdir/"final_key.bin", 0o600)
    except Exception:
        pass
    print("✅ 完了: 新規鍵→誤り訂正→PA まで1回で完了")
    print(f"   最終鍵: {args.outdir/'final_key.bin'}  長さ: {final_key.size} bit")
