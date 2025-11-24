# -*- coding: utf-8 -*-
"""
qkd60.py
段階60：Owner公開鍵をPEMから読み込み、しきい値(2名)署名で運用操作を許可。
不足署名を分かりやすく案内する改良版。

依存: pip install cryptography
"""

from __future__ import annotations
import os, sys, json, time, base64
from typing import Dict, List, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ===== ポリシー（操作ごとの必要承認者数） =====
POLICY = {
    "ROTATE_DATA_DEK": {"min_approvers": 2, "role": "Owner"},
}

# ===== ファイル名 =====
REQUEST_JSON = "request.json"
DATA_DEK_BIN = "data_dek.bin"
AUDIT_LOG = "audit.log"

# 署名ファイルは sig_<owner>.json の形で複数置ける
def sig_file(owner: str) -> str:
    return f"sig_{owner}.json"

# ===== Owner公開鍵の読み込み =====
def load_pubkey_pem(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_public_key(f.read())

def load_owner_keys_from_files() -> Dict[str, ed25519.Ed25519PublicKey]:
    keys: Dict[str, ed25519.Ed25519PublicKey] = {}
    for name in ("ownerA", "ownerB", "ownerC"):
        pem = f"{name}_public.pem"
        if os.path.exists(pem):
            try:
                keys[name] = load_pubkey_pem(pem)
            except Exception as e:
                print(f"[WARN] 公開鍵ロード失敗 {pem}: {e}")
    return keys

# ===== デモ用：鍵ペア生成（学習用） =====
def make_owners():
    for name in ("ownerA", "ownerB"):
        sk = ed25519.Ed25519PrivateKey.generate()
        pk = sk.public_key()
        with open(f"{name}_private.pem", "wb") as f:
            f.write(sk.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ))
        os.chmod(f"{name}_private.pem", 0o600)
        with open(f"{name}_public.pem", "wb") as f:
            f.write(pk.public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ))
        print(f"[OK] {name}_private.pem / {name}_public.pem を作成")
    print("[HINT] 公開鍵は自動で読み込みます。")

# ===== リクエスト作成・署名 =====
def make_request(op="ROTATE_DATA_DEK", reason="routine-rotation"):
    req = {
        "op": op, "reason": reason,
        "ts": int(time.time()),
        "nonce": os.urandom(16).hex(),
    }
    with open(REQUEST_JSON, "w", encoding="utf-8") as f:
        json.dump(req, f, ensure_ascii=False, indent=2)
    print(f"[OK] {REQUEST_JSON} を作成")

def sign_request(owner_name: str):
    priv = f"{owner_name}_private.pem"
    if not os.path.exists(priv):
        print(f"[ERR] {priv} がありません。まず make-owners を実行してください。")
        sys.exit(1)
    if not os.path.exists(REQUEST_JSON):
        print(f"[ERR] {REQUEST_JSON} がありません。先に request を実行してください。")
        sys.exit(1)

    msg = open(REQUEST_JSON, "rb").read()
    sk = serialization.load_pem_private_key(open(priv, "rb").read(), password=None)
    sig = sk.sign(msg)
    out = {"owner": owner_name, "sig": base64.b64encode(sig).decode()}
    with open(sig_file(owner_name), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[OK] {sig_file(owner_name)} を作成")

# ===== 実処理（DEKローテーションの疑似） =====
def rotate_data_dek(reason: str):
    dek = os.urandom(32)
    open(DATA_DEK_BIN, "wb").write(dek)
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\tROTATE_DATA_DEK\t{reason}\tlen=32\n")
    print(f"[RUN] DEK を更新 -> {DATA_DEK_BIN} (32B)")
    print(f"[AUDIT] 監査ログに追記 -> {AUDIT_LOG}")

# ===== 検証ユーティリティ =====
def find_present_signatures(keys: Dict[str, ed25519.Ed25519PublicKey]) -> List[str]:
    """ディレクトリに存在する sig_*.json のうち、Owner名が keys にあるものを列挙"""
    present = []
    for owner in keys.keys():
        if os.path.exists(sig_file(owner)):
            present.append(owner)
    return sorted(present)

def verify_and_execute() -> bool:
    keys = load_owner_keys_from_files()
    if not keys:
        print("[ERR] Owner公開鍵( owner*_public.pem )が見つかりません。")
        return False
    if not os.path.exists(REQUEST_JSON):
        print(f"[ERR] {REQUEST_JSON} がありません。先に request を実行してください。")
        return False

    req_bytes = open(REQUEST_JSON, "rb").read()
    req = json.loads(req_bytes)
    op = req.get("op", "")
    need = POLICY.get(op, {}).get("min_approvers", 999)

    # 利用可能な署名を収集
    present = find_present_signatures(keys)
    if not present:
        print("[DENY] 署名ファイルがありません。sign ownerA / sign ownerB を実行してください。")
        return False

    ok = 0
    approvers = []
    for owner in present:
        try:
            item = json.load(open(sig_file(owner), "r", encoding="utf-8"))
            sig_b = base64.b64decode(item["sig"])
            keys[owner].verify(sig_b, req_bytes)
            ok += 1
            approvers.append(owner)
            print(f"[OK] 署名検証: {owner}")
        except Exception as e:
            print(f"[NG] 署名検証失敗: {owner} ({e})")

    missing = [o for o in keys.keys() if o not in approvers]
    if ok < need:
        print(f"[DENY] 承認者が足りません（必要={need}名, 実際={ok}名）")
        if missing:
            print("       不足している候補:", ", ".join(missing))
            print("       例) python qkd60.py sign ownerA")
        return False

    # しきい値を満たしたので実行
    if op == "ROTATE_DATA_DEK":
        rotate_data_dek(reason=req.get("reason", ""))
    else:
        print(f"[WARN] 未対応の操作 op={op}")
        return False

    print("[DONE] 操作完了")
    return True

# ===== 状態表示 =====
def list_owners():
    keys = load_owner_keys_from_files()
    if not keys:
        print("[INFO] 読み込めた Owner 公開鍵：0")
        return
    print("[INFO] 読み込めた Owner 公開鍵：", ", ".join(sorted(keys.keys())))

def status():
    keys = load_owner_keys_from_files()
    need = POLICY["ROTATE_DATA_DEK"]["min_approvers"]
    present = find_present_signatures(keys)
    print("== STATUS ==")
    print("必要承認数:", need)
    print("公開鍵ロード:", ", ".join(sorted(keys.keys())) if keys else "(なし)")
    print("署名ファイル:", ", ".join(present) if present else "(なし)")
    missing = [o for o in keys.keys() if o not in present]
    if missing:
        print("不足署名候補:", ", ".join(missing))

# ===== おまけ：現DEKで暗号化/復号 =====
def encrypt_demo(msg: str):
    if not os.path.exists(DATA_DEK_BIN):
        print("[ERR] DEKがありません。先に exec でローテーションしてください。")
        return
    dek = open(DATA_DEK_BIN, "rb").read()
    gcm = AESGCM(dek)
    nonce = os.urandom(12)
    ct = gcm.encrypt(nonce, msg.encode("utf-8"), None)
    open("out.bin", "wb").write(nonce + ct)
    print("[OK] out.bin を作成（現在DEKで暗号化）")

def decrypt_demo():
    if not os.path.exists(DATA_DEK_BIN) or not os.path.exists("out.bin"):
        print("[ERR] data_dek.bin か out.bin がありません。")
        return
    dek = open(DATA_DEK_BIN, "rb").read()
    blob = open("out.bin", "rb").read()
    nonce, ct = blob[:12], blob[12:]
    pt = AESGCM(dek).decrypt(nonce, ct, None)
    print("[OK] 復号:", pt.decode("utf-8", errors="replace"))

# ===== CLI =====
def usage():
    print("""
使い方:
  python qkd60.py make-owners       # 学習用: ownerA/Bの鍵ペアを作成
  python qkd60.py list-owners       # 読み込めた公開鍵の確認
  python qkd60.py request           # リクエスト(request.json)作成
  python qkd60.py sign ownerA|ownerB# 署名ファイル作成(sig_owner*.json)
  python qkd60.py status            # 必要人数/揃っている署名/不足の案内
  python qkd60.py exec              # 検証→DEKローテーション実行
  python qkd60.py enc 'text'        # 現DEKで暗号化 -> out.bin
  python qkd60.py dec               # out.bin を現DEKで復号
""".strip())

def main():
    if len(sys.argv) < 2:
        usage(); return
    cmd = sys.argv[1]
    if cmd == "make-owners": make_owners()
    elif cmd == "list-owners": list_owners()
    elif cmd == "request": make_request()
    elif cmd == "sign":
        if len(sys.argv) < 3: print("例: python qkd60.py sign ownerA"); return
        sign_request(sys.argv[2])
    elif cmd == "status": status()
    elif cmd == "exec": verify_and_execute()
    elif cmd == "enc":
        if len(sys.argv) < 3: print("例: python qkd60.py enc 'hello'"); return
        encrypt_demo(sys.argv[2])
    elif cmd == "dec": decrypt_demo()
    else: usage()

if __name__ == "__main__":
    main()


