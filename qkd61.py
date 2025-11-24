# qkd61.py - 段階61：オフライン承認QRデモ（Ed25519 / RSA / RSA-PSS 署名生成）
# 依存: pip install "cryptography qrcode[pil]"

import os, json, base64, time, argparse
from typing import Dict, Any
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, padding as asy_padding
from cryptography.hazmat.primitives import serialization as ser
import qrcode

OUT_JSON = "approval_payload.json"
OUT_QR   = "approval_qr.png"

def b64(b: bytes) -> str: return base64.b64encode(b).decode()

def canonical_json(obj: Dict[str,Any]) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",",":"), sort_keys=True).encode("utf-8")

def gen_keys(alg: str):
    if alg == "ed25519":
        sk = ed25519.Ed25519PrivateKey.generate()
        pk = sk.public_key()
        pem = pk.public_bytes(ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)
        return sk, ("ed25519", pem)
    # RSA 2048
    sk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pk = sk.public_key()
    pem = pk.public_bytes(ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)
    return sk, ("rsa", pem)

def sign(sk, alg: str, msg: bytes) -> bytes:
    if alg == "ed25519":
        return sk.sign(msg)
    if alg == "pss":
        return sk.sign(msg, asy_padding.PSS(mgf=asy_padding.MGF1(hashes.SHA256()),
                                            salt_length=asy_padding.PSS.MAX_LENGTH),
                       hashes.SHA256())
    # 既定: RSA PKCS#1 v1.5 + SHA-256
    return sk.sign(msg, asy_padding.PKCS1v15(), hashes.SHA256())

def main():
    p = argparse.ArgumentParser()
    p.add_argument("alg", nargs="?", default="ed25519",
                   choices=["ed25519","rsa","pss"], help="署名アルゴリズム")
    args = p.parse_args()
    alg = args.alg

    sk, (kind, pub_pem) = gen_keys("ed25519" if alg=="ed25519" else "rsa")

    # 署名対象データ（自由に拡張可）
    data = {
        "type":"ROTATE_DATA_DEK",
        "reason":"periodic",
        "ts": int(time.time()),
        "req_id":"demo-req-001"
    }
    msg = canonical_json(data)

    sig = sign(sk, alg, msg)

    payload = {
        # 検証側が取り出すデータ部（qkd62 はまずここを探します）
        "data": data,
        # 検証用メタ（アルゴリズムヒント＆公開鍵）
        "alg": alg,                            # "ed25519" / "rsa" / "pss"
        "pub_pem_b64": b64(pub_pem),
        "sig_b64": b64(sig)
    }

    # 保存
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    img = qrcode.make(json.dumps(payload, ensure_ascii=False, separators=(",",":"), sort_keys=True))
    img.save(OUT_QR)

    print("✅ 署名生成: OK")
    print("   JSON を保存 :", os.path.abspath(OUT_JSON))
    print("   QR を保存   :", os.path.abspath(OUT_QR))

if __name__ == "__main__":
    main()

