# -*- coding: utf-8 -*-
"""
Stage84: 量子鍵で暗号化（引数なしでも動く親切版）
- infile未指定なら message.txt を自動生成して暗号化
- key未指定なら final_key.bin を自動探索（./ または ../stage83）
"""
import argparse
from pathlib import Path
from utils import load_key_auto, xor_bytes

def main():
    ap = argparse.ArgumentParser(description="QKD鍵でファイル暗号化")
    ap.add_argument("--infile", help="入力ファイル（平文）。未指定なら message.txt を自動生成して使用")
    ap.add_argument("--key", help="量子鍵ファイル。未指定なら自動探索（./, ../stage83）")
    ap.add_argument("--outfile", help="出力ファイル（暗号文）。未指定なら <infile>.qenc")
    args = ap.parse_args()

    # 1) 入力ファイルの用意
    if args.infile:
        infile = Path(args.infile)
        if not infile.exists():
            raise FileNotFoundError(f"入力ファイルが見つかりません: {infile}")
    else:
        # サンプル平文を自動生成
        infile = Path("message.txt")
        if not infile.exists():
            infile.write_text("Quantum Key Distribution is awesome!\n", encoding="utf-8")

    # 2) 鍵のロード（自動探索）
    key_bytes = load_key_auto(args.key)

    # 3) 暗号化
    data = infile.read_bytes()
    enc = xor_bytes(data, key_bytes)

    # 4) 出力
    outfile = Path(args.outfile) if args.outfile else infile.with_suffix(".qenc")
    outfile.write_bytes(enc)

    print(f"✅ 暗号化完了: {infile} → {outfile}")
    print(f"🔑 使用鍵: {'指定なし(自動探索)' if not args.key else args.key}")

if __name__ == "__main__":
    main()
