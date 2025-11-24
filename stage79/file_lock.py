# -*- coding: utf-8 -*-
"""
Stage79: QKD鍵(32B)でローカルファイルをAES-GCM暗号化/復号するワンファイルツール
- 依存: 標準ライブラリ + cryptography
    pip install cryptography
- 使い方:
    # 暗号化
    python3 file_lock.py encrypt /path/to/plain.bin --key group_key_ac.bin
    # 復号
    python3 file_lock.py decrypt /path/to/plain.bin.qkenc --key group_key_ac.bin

鍵ファイルがない場合:
    --key を省略すると自動で 32B を生成し stage79_demo_key.bin に保存して使います。

フォーマット:
  Header:  magic(8='QKDFILE1') | salt(16) | chunk_size(4LE) | orig_size(8LE)
  Body  :  [ AES-GCM(ciphertext_chunk_i | tag_i) ] x N   (nonce = base(12) XOR i)
  Footer:  'SHA256'(6) | digest(32)
"""
from __future__ import annotations
import argparse, os, sys, struct, tempfile, hashlib, secrets
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import hmac
from hashlib import sha256

MAGIC = b"QKDFILE1"
FOOTER_TAG = b"SHA256"
CHUNK_SIZE_DEFAULT = 1024 * 1024  # 1 MiB
NONCE_SIZE = 12  # AES-GCM nonce
KEY_SIZE = 32    # 256-bit

def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if salt is None:
        salt = b"\x00" * 32
    return hmac.new(salt, ikm, sha256).digest()

def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    out = b""
    t = b""
    counter = 1
    while len(out) < length:
        t = hmac.new(prk, t + info + bytes([counter]), sha256).digest()
        out += t
        counter += 1
    return out[:length]

def _xor(b1: bytes, b2: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(b1, b2))

def load_or_create_key(path: Path) -> bytes:
    """
    32Bの鍵を読み込む。存在しなければ安全に新規生成して保存する。
    """
    if path.exists():
        data = path.read_bytes()
        if len(data) != KEY_SIZE:
            raise ValueError(f"鍵ファイル {path} は {KEY_SIZE} バイトである必要があります（実際: {len(data)}）")
        return data
    key = secrets.token_bytes(KEY_SIZE)
    path.write_bytes(key)
    try: os.chmod(path, 0o600)
    except Exception: pass
    print(f"🔑 鍵を新規生成しました: {path}（32B）")
    return key

def derive_file_keys(master_key: bytes, salt16: bytes) -> tuple[bytes, bytes]:
    """
    マスター鍵(QKD鍵32B) + salt16 から HKDF で
      - file_key(32B) と nonce_base(12B) を導出
    """
    prk = hkdf_extract(salt16, master_key)
    file_key = hkdf_expand(prk, b"file-key-v1", 32)
    nonce_base = hkdf_expand(prk, b"nonce-base-v1", NONCE_SIZE)
    return file_key, nonce_base

def encrypt_file(src: Path, dst: Path, master_key: bytes, chunk_size: int = CHUNK_SIZE_DEFAULT) -> Path:
    if not src.exists():
        raise FileNotFoundError(src)
    if dst.exists():
        raise FileExistsError(f"出力先が既に存在します: {dst}")

    salt16 = secrets.token_bytes(16)
    file_key, nonce_base = derive_file_keys(master_key, salt16)
    aead = AESGCM(file_key)

    total_size = src.stat().st_size
    header = MAGIC + salt16 + struct.pack("<IQ", chunk_size, total_size)

    sha = hashlib.sha256()
    tmp = Path(str(dst) + ".part")

    with open(src, "rb") as fin, open(tmp, "wb") as fout:
        fout.write(header)
        idx = 0
        while True:
            chunk = fin.read(chunk_size)
            if not chunk:
                break
            sha.update(chunk)
            # per-chunk nonce = base XOR counter(12B big-endian)
            nonce = _xor(nonce_base, idx.to_bytes(NONCE_SIZE, "big"))
            ct = aead.encrypt(nonce, chunk, header)  # headerをAADにする
            fout.write(ct)
            idx += 1
        footer = FOOTER_TAG + sha.digest()
        fout.write(footer)

    tmp.replace(dst)
    try:
        os.chmod(dst, 0o600)
    except Exception:
        pass
    return dst

def decrypt_file(src: Path, dst: Path, master_key: bytes) -> Path:
    if not src.exists():
        raise FileNotFoundError(src)
    if dst.exists():
        raise FileExistsError(f"出力先が既に存在します: {dst}")

    with open(src, "rb") as fin:
        header = fin.read(len(MAGIC) + 16 + 4 + 8)
        if len(header) != (len(MAGIC) + 16 + 4 + 8):
            raise ValueError("ファイルが壊れています（ヘッダ不足）")
        magic = header[:8]
        if magic != MAGIC:
            raise ValueError("不明なファイル形式（MAGIC不一致）")
        salt16 = header[8:24]
        chunk_size, orig_size = struct.unpack("<IQ", header[24:24+12])

        # フッタ位置を計算（最後の38B: 'SHA256'(6) + digest(32)）
        fin.seek(0, os.SEEK_END)
        file_size = fin.tell()
        footer_size = len(FOOTER_TAG) + 32
        if file_size < len(header) + footer_size:
            raise ValueError("ファイルが壊れています（長さ不足）")

        # 本文の終端位置
        body_end = file_size - footer_size
        fin.seek(body_end)
        footer = fin.read(footer_size)
        if not footer.startswith(FOOTER_TAG):
            raise ValueError("フッタが壊れています（タグ不一致）")
        expect_digest = footer[len(FOOTER_TAG):]

        # 復号準備
        file_key, nonce_base = derive_file_keys(master_key, salt16)
        aead = AESGCM(file_key)
        sha = hashlib.sha256()

        # 本文復号
        fin.seek(len(header))
        remaining = body_end - len(header)
        idx = 0
        tmp = Path(str(dst) + ".part")
        with open(tmp, "wb") as fout:
            while remaining > 0:
                # 暗号文チャンク長は平文長 + 16(tag) になるが、
                # 平文側は固定1MB(最後だけ小さい)。暗号文長は読取り単位を決めにくい。
                # そこで、最後以外は必ず chunk_size 分の平文が入っている前提で、
                # 暗号文側は (chunk_size + 16) を読む。最後だけ(残り全部)を読む。
                read_len = remaining if remaining <= (chunk_size + 16) else (chunk_size + 16)
                ct = fin.read(read_len)
                if not ct:
                    break
                nonce = _xor(nonce_base, idx.to_bytes(NONCE_SIZE, "big"))
                pt = aead.decrypt(nonce, ct, header)
                fout.write(pt)
                sha.update(pt)
                remaining -= len(ct)
                idx += 1

        # 整合性確認（全体SHA256）
        if sha.digest() != expect_digest:
            tmp.unlink(missing_ok=True)
            raise ValueError("復号は完了しましたが、整合性チェックに失敗しました（ハッシュ不一致）")

        tmp.replace(dst)
        # 復元サイズを念のため確認（切詰め不要なはずだが検査）
        if dst.stat().st_size != orig_size:
            raise ValueError("復号後サイズがヘッダの期待値と一致しません")

    try:
        os.chmod(dst, 0o600)
    except Exception:
        pass
    return dst

def main():
    p = argparse.ArgumentParser(description="Stage79 QKD File Locker (AES-GCM)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("encrypt", help="ファイルを暗号化 (*.qkenc を出力)")
    pe.add_argument("src", type=Path)
    pe.add_argument("--out", type=Path, default=None)
    pe.add_argument("--key", type=Path, default=Path("group_key_ac.bin"))
    pe.add_argument("--chunk", type=int, default=CHUNK_SIZE_DEFAULT)

    pd = sub.add_parser("decrypt", help="暗号ファイルを復号")
    pd.add_argument("src", type=Path)
    pd.add_argument("--out", type=Path, default=None)
    pd.add_argument("--key", type=Path, default=Path("group_key_ac.bin"))

    args = p.parse_args()

    # 鍵準備（group_key_ac.bin が無ければ stage79_demo_key.bin を生成して使用）
    key_path = args.key
    if not key_path.exists():
        print(f"⚠️ 指定の鍵が見つかりません: {key_path}")
        key_path = Path("stage79_demo_key.bin")
        print(f"代わりにデモ鍵を生成して使います -> {key_path}")
    key = load_or_create_key(key_path)

    if args.cmd == "encrypt":
        src: Path = args.src
        dst: Path = args.out or src.with_suffix(src.suffix + ".qkenc")
        out = encrypt_file(src, dst, key, chunk_size=args.chunk)
        print(f"✅ 暗号化完了: {src.name} -> {out.name}")
        print(f"   鍵: {key_path} / チャンク: {args.chunk} bytes")
    else:
        src: Path = args.src
        # 既定の復号出力名: 末尾の .qkenc を取り除く
        if args.out:
            dst = args.out
        else:
            dst = src
            if dst.suffix == ".qkenc":
                dst = dst.with_suffix("")  # remove one suffix
            else:
                dst = dst.with_name(dst.name + ".dec")
        out = decrypt_file(src, dst, key)
        print(f"🔓 復号完了: {src.name} -> {out.name}")
        print(f"   鍵: {key_path}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ エラー: {e}")
        sys.exit(1)
