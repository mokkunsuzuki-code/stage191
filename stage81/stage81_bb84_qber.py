# -*- coding: utf-8 -*-
"""
Stage81: BB84(擬似) 盗聴検知 — QBER 推定としきい値判定
- Alice/Bob が BB84 を確率モデルで再現（Eve: intercept-resend / channel noise）
- シフティング → 犠牲ビットで QBER 推定 → しきい値判定（デフォルト 11%）
- 合格時、残りのビット列を鍵候補として alice_key.bin / bob_key.bin に保存
依存: numpy

使い方例:
  python3 stage81_bb84_qber.py --n 20000 --eve 0.5 --noise 0.01 --sample 0.2 --th 0.11 --seed 42
"""

from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
import numpy as np

def bits_to_bytes(bits: np.ndarray) -> bytes:
    """0/1 の numpy 配列をバイト列に変換（前詰め）"""
    if bits.size == 0:
        return b""
    # 8の倍数にパディング
    pad = (-bits.size) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    # 8ビットずつ畳み込み
    bits = bits.reshape(-1, 8)
    vals = (bits * (1 << np.arange(7, -1, -1, dtype=np.uint8))).sum(axis=1).astype(np.uint8)
    return vals.tobytes()

def simulate_bb84(n: int, eve_rate: float, noise: float, rng: np.random.Generator):
    """
    BB84(擬似)の送受信を確率的に再現して、シフティング用のデータを返す。
    - n: 送信ビット数
    - eve_rate: Eve が傍受する確率（各ビット独立）
    - noise: チャネルでのビット反転確率（Bob 受信直前に適用）
    戻り値:
      alice_bits, alice_bases, bob_bits, bob_bases  (各 np.uint8 の 0/1 配列)
    """
    # Alice のランダムビット・基底（0=Z, 1=X）
    alice_bits  = rng.integers(0, 2, size=n, dtype=np.uint8)
    alice_bases = rng.integers(0, 2, size=n, dtype=np.uint8)

    # Bob の測定基底（ランダム）
    bob_bases = rng.integers(0, 2, size=n, dtype=np.uint8)

    # Eve が傍受するか
    eve_hits = rng.random(n) < eve_rate  # True/False

    # Bob が観測するビットを埋めていく
    bob_bits = np.empty(n, dtype=np.uint8)

    # --- ケース分岐 ---
    # 1) Eve なし
    mask_no_eve = ~eve_hits
    if mask_no_eve.any():
        # (a) 基底一致: Bob_bit = Alice_bit（後でノイズで反転すること有）
        eq = mask_no_eve & (alice_bases == bob_bases)
        bob_bits[eq] = alice_bits[eq]
        # (b) 基底不一致: Bob_bit はランダム
        neq = mask_no_eve & (alice_bases != bob_bases)
        bob_bits[neq] = rng.integers(0, 2, size=neq.sum(), dtype=np.uint8)

    # 2) Eve あり（intercept-resend）
    # Eve の測定基底と測定結果
    mask_eve = eve_hits
    if mask_eve.any():
        eve_bases = rng.integers(0, 2, size=mask_eve.sum(), dtype=np.uint8)
        # Alice と Eve の基底一致？一致なら Eve は正確に読む、違えばランダム
        # まず Eve の測定結果を作る
        idx_eve = np.where(mask_eve)[0]
        eve_bits = np.empty(idx_eve.size, dtype=np.uint8)
        eq_ae = (alice_bases[idx_eve] == eve_bases)
        # 一致→ Eve_bit = Alice_bit
        eve_bits[eq_ae] = alice_bits[idx_eve][eq_ae]
        # 不一致→ ランダム
        if (~eq_ae).any():
            eve_bits[~eq_ae] = rng.integers(0, 2, size=(~eq_ae).sum(), dtype=np.uint8)

        # Eve は (eve_bases, eve_bits) の状態を Bob に送るとみなす
        # Bob が Eve と基底一致なら Eve_bit を得る。不一致ならランダム。
        eq_eb = (bob_bases[idx_eve] == eve_bases)
        # 一致
        bob_bits[idx_eve[eq_eb]] = eve_bits[eq_eb]
        # 不一致
        idx_neq = idx_eve[~eq_eb]
        if idx_neq.size:
            bob_bits[idx_neq] = rng.integers(0, 2, size=idx_neq.size, dtype=np.uint8)

    # チャネル雑音: 最後に一括でビット反転
    if noise > 0.0:
        flips = rng.random(n) < noise
        bob_bits[flips] ^= 1

    return alice_bits, alice_bases, bob_bits, bob_bases

def sift_and_estimate_qber(alice_bits, alice_bases, bob_bits, bob_bases,
                           sample_frac: float, rng: np.random.Generator):
    """
    シフティング（Alice/Bob 基底一致インデックスを抽出）
    → 犠牲ビット（割合 sample_frac）で QBER を推定
    → 残りを鍵候補として返す
    戻り値:
      qber_est, sample_size, alice_key, bob_key, residual_errors
    """
    # 基底一致のインデックス
    mask = (alice_bases == bob_bases)
    idx = np.where(mask)[0]
    if idx.size == 0:
        return 1.0, 0, np.array([], dtype=np.uint8), np.array([], dtype=np.uint8), 0

    a_sift = alice_bits[idx]
    b_sift = bob_bits[idx]

    # サンプルの個数（最低1ビット、最大は全体-1）
    s = max(1, int(round(a_sift.size * sample_frac)))
    s = min(s, max(1, a_sift.size - 1))  # 余りが0にならないように
    perm = rng.permutation(a_sift.size)
    sample_idx, remain_idx = perm[:s], perm[s:]

    a_sample = a_sift[sample_idx]
    b_sample = b_sift[sample_idx]
    # QBER 推定（サンプルの不一致率）
    qber_est = float((a_sample ^ b_sample).sum()) / float(a_sample.size)

    # 残り＝鍵候補
    alice_key = a_sift[remain_idx]
    bob_key   = b_sift[remain_idx]
    residual_errors = int((alice_key ^ bob_key).sum())  # 次段階のエラー訂正で除去すべき数

    return qber_est, int(s), alice_key, bob_key, residual_errors

def save_key(path: Path, bits: np.ndarray):
    data = bits_to_bytes(bits.astype(np.uint8))
    path.write_bytes(data)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser(description="Stage81 BB84(擬似) 盗聴検知/QBER推定")
    ap.add_argument("--n", type=int, default=10000, help="送信ビット数")
    ap.add_argument("--eve", type=float, default=0.0, help="Eve傍受率(0〜1)")
    ap.add_argument("--noise", type=float, default=0.0, help="チャネル雑音（ビット反転確率）")
    ap.add_argument("--sample", type=float, default=0.2, help="犠牲ビット比率(0〜1)")
    ap.add_argument("--th", type=float, default=0.11, help="QBERしきい値（合格は <= しきい値）")
    ap.add_argument("--seed", type=int, default=None, help="乱数シード（再現用）")
    ap.add_argument("--outdir", type=Path, default=Path("."), help="出力先ディレクトリ")
    args = ap.parse_args()

    if not (0.0 <= args.eve <= 1.0 and 0.0 <= args.sample <= 1.0 and 0.0 <= args.noise <= 1.0):
        print("✗ 引数エラー: --eve/--sample/--noise は 0〜1 の範囲で指定してください。")
        sys.exit(2)

    rng = np.random.default_rng(args.seed)

    # 1) 送受信の擬似シミュレーション
    alice_bits, alice_bases, bob_bits, bob_bases = simulate_bb84(
        n=args.n, eve_rate=args.eve, noise=args.noise, rng=rng
    )

    # 2) シフティング & QBER 推定
    qber_est, s_size, a_key, b_key, residual = sift_and_estimate_qber(
        alice_bits, alice_bases, bob_bits, bob_bases, sample_frac=args.sample, rng=rng
    )

    sifted_len = int((alice_bases == bob_bases).sum())
    key_len = a_key.size

    # 3) レポート
    report = {
        "n_sent": int(args.n),
        "eve_rate": float(args.eve),
        "channel_noise": float(args.noise),
        "sample_frac": float(args.sample),
        "sifted_len": sifted_len,
        "sample_size": int(s_size),
        "qber_estimate": float(qber_est),
        "threshold": float(args.th),
        "accepted": bool(qber_est <= args.th and key_len > 0),
        "key_len_bits": int(key_len),
        "residual_bit_errors": int(residual)  # 次段階のエラー訂正で除去
    }

    # 4) 判定と保存
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "stage81_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== Stage81 BB84 QBER Report ===")
    for k, v in report.items():
        print(f"{k:>20}: {v}")

    if not report["accepted"]:
        print("✗ QBER がしきい値を超過、または鍵長が0のため鍵生成を中止しました。")
        sys.exit(1)

    # 合格時、鍵候補を保存（次段階で誤り訂正＆プライバシー増幅）
    save_key(args.outdir / "alice_key.bin", a_key)
    save_key(args.outdir / "bob_key.bin", b_key)
    print(f"✅ 鍵候補を書き出しました: {args.outdir}/alice_key.bin, {args.outdir}/bob_key.bin")
    if residual > 0:
        print(f"ℹ️ 残差誤り: {residual} bit（次段階で訂正します）")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ エラー: {e}")
        sys.exit(2)
