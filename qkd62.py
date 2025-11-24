# qkd62.py - 段階62：QR承認データの検証デモ（Ed25519/RSA 両対応）
# 依存: pip install "cryptography qrcode[pil]"

import os, json, base64
from typing import Any, Dict, Tuple

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, padding as asy_padding
from cryptography.exceptions import InvalidSignature
import qrcode

IN_JSON  = "approval_payload.json"
OUT_KEY  = "rotated_key.bin"
OUT_QR   = "verification_qr.png"

SIG_KEYS = ("sig_b64", "signature", "sig")
PUB_KEYS = ("pub_pem_b64", "pub_b64", "pub", "public_key")
DATA_KEYS = ("data", "payload", "message")
ALG_KEYS = ("alg", "algorithm")

def b64d(s: str) -> bytes: return base64.b64decode(s)

def canonical(obj: Dict[str,Any]) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",",":"), sort_keys=True).encode("utf-8")

def load_pub(b64: str):
    raw = b64d(b64)
    if raw.startswith(b"-----BEGIN"):
        k = serialization.load_pem_public_key(raw)
        if isinstance(k, (ed25519.Ed25519PublicKey, rsa.RSAPublicKey)):
            return k
        raise ValueError("PEM公開鍵は Ed25519 / RSA のみ対応")
    if len(raw) == 32:
        return ed25519.Ed25519PublicKey.from_public_bytes(raw)
    raise ValueError("公開鍵形式が不明（PEM または Raw32B を想定）")

def pull(obj: Dict[str,Any], keys) -> Any:
    for k in keys:
        if k in obj: return obj[k]
    return None

def load_payload(path: str) -> Tuple[bytes, bytes, Any, str]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    sig_b64 = pull(payload, SIG_KEYS)
    pub_b64 = pull(payload, PUB_KEYS)
    alg     = (pull(payload, ALG_KEYS) or "").lower()
    if not sig_b64 or not pub_b64:
        raise KeyError("sig_b64 / 公開鍵 が不足しています")

    data = pull(payload, DATA_KEYS)
    if data is None:
        # sig/鍵/alg 以外を message と見なすフォールバック
        data = {k:v for k,v in payload.items() if k not in SIG_KEYS + PUB_KEYS + ALG_KEYS}
        if not data:
            raise KeyError("検証対象データが見つかりません（data/payload/message 等）")

    msg = canonical(data)
    sig = b64d(sig_b64)
    pk  = load_pub(pub_b64)

    return msg, sig, pk, alg

def verify(pk, alg: str, msg: bytes, sig: bytes):
    if isinstance(pk, ed25519.Ed25519PublicKey) or alg == "ed25519":
        pk.verify(sig, msg); return
    if isinstance(pk, rsa.RSAPublicKey) or alg in ("rsa","rs256","pss"):
        if alg == "pss":
            pad = asy_padding.PSS(mgf=asy_padding.MGF1(hashes.SHA256()),
                                  salt_length=asy_padding.PSS.MAX_LENGTH)
        else:
            pad = asy_padding.PKCS1v15()
        pk.verify(sig, msg, pad, hashes.SHA256()); return
    raise ValueError("未対応の鍵/アルゴリズム")

def main():
    print("＝＝ 段階62：QR承認データの検証デモ（Ed25519/RSA対応）＝＝")

    if not os.path.exists(IN_JSON):
        print("❌ approval_payload.json が見つかりません。先に qkd61.py を実行してください。")
        return

    try:
        msg, sig, pk, alg = load_payload(IN_JSON)
        verify(pk, alg, msg, sig)
        print(f"✅ 署名検証 OK — alg={alg or type(pk).__name__}")
    except InvalidSignature:
        print("❌ 検証失敗: 署名が一致しません（payload を作り直してください）")
        return
    except Exception as e:
        print("❌ 検証失敗:", e); return

    # 鍵更新（デモ）
    new_key = os.urandom(32)
    with open(OUT_KEY, "wb") as f: f.write(new_key)
    print(f"🔑 鍵を更新しました: {OUT_KEY}（32 bytes）")

    # 検証完了QR
    confirm = {
        "status":"verified",
        "note":"stage62 ok",
        "next_key_hint_b64": base64.b64encode(new_key[:8]).decode()
    }
    img = qrcode.make(json.dumps(confirm, ensure_ascii=False, separators=(",",":"), sort_keys=True))
    img.save(OUT_QR)
    print(f"📱 検証完了QRを保存: {OUT_QR}")

if __name__ == "__main__":
    main()

