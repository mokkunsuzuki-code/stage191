# -*- coding: utf-8 -*-
# stage82_cascade.py
# BB84 で得た Alice/Bob のキーに対して、簡易 CASCADE 誤り訂正を行うデモ実装
# 目的: 2者のキー不一致(ビット誤り)を公開パリティ交換＋二分探索で修正する
#
# 使い方例:
#   cd ~/Desktop/test/stage82
#   python3 stage82_cascade.py \
#       --alice ../stage81/out81/alice_key.bin \
#       --bob   ../stage81/out81/bob_key.bin \
#       --qber  0.03 \
#       --passes 4 \
#       --seed 42 \
#       --outdir out82

from __future__ import annotations
import argparse
import os
import sys
import random
from pathlib import Path
from typing import List, Tuple, Dict

# -------------------------
# ユーティリティ
# -------------------------
def load_key_bits(path: Path) -> List[int]:
    raw = path.read_bytes()
    bits: List[int] = []
    for b in raw:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    return bits

def save_key_bits(path: Path, bits: List[int]) -> None:
    n = len(bits)
    out = bytearray((n + 7) // 8)
    for i, bit in enumerate(bits):
        if bit:
            out[i // 8] |= (1 << (7 - (i % 8)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))

def hamming(a: List[int], b: List[int]) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)

def parity(bits: List[int], s: int, e: int) -> int:
    # 区間 [s, e) のパリティ
    p = 0
    for i in range(s, e):
        p ^= bits[i]
    return p

def binary_search_and_fix(alice: List[int], bob: List[int], s: int, e: int) -> None:
    # 区間内の誤り位置を二分探索で特定して Bob を修正（Alice を正とみなす）
    while e - s > 1:
        m = (s + e) // 2
        if parity(alice, s, m) != parity(bob, s, m):
            e = m
        else:
            s = m
    # s が誤り箇所
    bob[s] ^= 1

def shuffle_indices(n: int, seed: int) -> List[int]:
    idx = list(range(n))
    rnd = random.Random(seed)
    rnd.shuffle(idx)
    return idx

# -------------------------
# 簡易 CASCADE 本体
# -------------------------
def cascade(alice: List[int], bob: List[int], qber: float, passes: int, seed: int) -> Dict:
    n = len(alice)
    assert n == len(bob)

    # ブロック長の初期値（経験的設定）
    # 目安: L ≈ max(1, int(0.73 / qber)) ただし極端に長くしすぎない
    if qber <= 0:
        L0 = max(4, min(1024, n // 32))
    else:
        L0 = max(4, min(1024, int(0.73 / qber)))

    history: List[Tuple[int, int, int]] = []  # (pass_id, blocks, fixes)
    work_a = alice[:]  # 破壊的変更を避ける
    work_b = bob[:]
    total_fixes = 0

    for p in range(passes):
        # パスごとにキーを既知の乱数でシャッフル（公開可）
        idx = shuffle_indices(n, seed + p)
        a = [work_a[i] for i in idx]
        b = [work_b[i] for i in idx]

        # パスごとにブロック長を調整（少しずつ細かくしていく）
        L = max(2, L0 // (2 ** p))
        blocks = (n + L - 1) // L
        fixes = 0

        # 各ブロックでパリティ比較 → 不一致なら二分探索で 1bit 修正
        for bi in range(blocks):
            s = bi * L
            e = min(n, s + L)
            if parity(a, s, e) != parity(b, s, e):
                binary_search_and_fix(a, b, s, e)
                fixes += 1

        # 元の並びに戻す
        inv = [0] * n
        for new_i, old_i in enumerate(idx):
            inv[old_i] = new_i
        work_a = [a[inv[i]] for i in range(n)]
        work_b = [b[inv[i]] for i in range(n)]

        total_fixes += fixes
        history.append((p + 1, blocks, fixes))

        # もう一致したら早期終了
        if hamming(work_a, work_b) == 0:
            break

    report = {
        "n_bits": n,
        "passes": len(history),
        "history": [{"pass": p, "blocks": b, "fixed": f} for (p, b, f) in history],
        "final_hamming": hamming(work_a, work_b),
        "total_fixes": total_fixes,
    }
    return {"alice": work_a, "bob": work_b, "report": report}

# -------------------------
# メイン: 引数処理と入出力
# -------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Stage82: CASCADE error correction (demo)")
    ap.add_argument("--alice", required=True, help="Alice key file (bin)")
    ap.add_argument("--bob",   required=True, help="Bob key file (bin)")
    ap.add_argument("--qber",  type=float, default=0.03, help="estimated QBER (0.01=1%)")
    ap.add_argument("--passes", type=int, default=4, help="number of passes (>=1)")
    ap.add_argument("--seed", type=int, default=42, help="public shuffle seed")
    ap.add_argument("--outdir", default="out82", help="output dir")
    args = ap.parse_args()

    a_path = Path(args.alice)
    b_path = Path(args.bob)
    if not a_path.exists() or not b_path.exists():
        print("✗ 入力キーが見つかりません。パスを確認してください。")
        print(f"  alice: {a_path.resolve()}")
        print(f"  bob  : {b_path.resolve()}")
        sys.exit(1)

    a_bits = load_key_bits(a_path)
    b_bits = load_key_bits(b_path)
    if len(a_bits) != len(b_bits):
        print("✗ キー長が一致しません。段階81の出力をそのまま渡してください。")
        sys.exit(1)

    result = cascade(a_bits, b_bits, qber=args.qber, passes=args.passes, seed=args.seed)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # 訂正後キーを書き出し（同じ内容のはず）
    alice_out = outdir / "alice_key_corr.bin"
    bob_out   = outdir / "bob_key_corr.bin"
    save_key_bits(alice_out, result["alice"])
    save_key_bits(bob_out,   result["bob"])

    r = result["report"]
    print("=== Stage82 CASCADE Report ===")
    print(f"n_bits         : {r['n_bits']}")
    print(f"passes_run     : {r['passes']}")
    for h in r["history"]:
        print(f"  - pass#{h['pass']:>2} blocks={h['blocks']:>5} fixed={h['fixed']:>5}")
    print(f"final_hamming  : {r['final_hamming']}")
    print(f"total_fixes    : {r['total_fixes']}")

    if r["final_hamming"] == 0:
        print(f"✅ 誤り訂正に成功: Alice & Bob のキーが一致しました")
        print(f"   書き出し: {alice_out} / {bob_out}")
        sys.exit(0)
    else:
        print("⚠️ まだ不一致が残っています。--passes や --qber を再調整してください。")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ 実行エラー: {e}")
        sys.exit(2)
