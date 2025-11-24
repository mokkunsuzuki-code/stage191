# -*- coding: utf-8 -*-
"""
Stage84: 量子鍵で復号（引数なしでも分かりやすいエラー表示）
- key未指定なら final_key.bin を自動探索（./, ../stage83）
- outfile未指定なら <infile>.dec
"""
import argparse
from pathlib import Path
from utils import load_key_auto, xor_bytes

def main():
    ap = argparse.ArgumentParser(description="QKD鍵でファイル復号")
    ap.add_argument("--infile", required=True, help="暗号ファイル（.qenc）")
    ap.add_argument("--key", help="量子鍵ファイル。未指定なら自動探索（./, ../stage83）")
    ap.add_argument("--outfile", help="出力ファイル（復号文）。未指定なら <infile>.dec")
    args = ap.parse_args()

    encfile = Path(args.infile)
    if not encfile.exists():
        raise FileNotFoundError(f"暗号ファイルが見つかりません: {encfile}")

    key_bytes = load_key_auto(args.key)

    dec = xor_bytes(encfile.read_bytes(), key_bytes)
    outfile = Path(args.outfile) if args.outfile else encfile.with_suffix(".dec")
    outfile.write_bytes(dec)

    print(f"✅ 復号完了: {encfile} → {outfile}")
    print(f"🔑 使用鍵: {'指定なし(自動探索)' if not args.key else args.key}")

if __name__ == "__main__":
    main()
