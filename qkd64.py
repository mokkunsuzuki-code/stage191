# qkd64.py — 段階64 検証API（PQC署名+QKD-HMAC、ポリシーで合否決定）
# 依存: pip install flask cryptography pqcrypto

import os, json, time, base64, hmac, hashlib
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify, abort

# Dilithium は入っていれば使う（無ければ Ed だけで動作）
try:
    from pqcrypto.sign import dilithium2
    HAVE_DILITHIUM = True
except Exception:
    dilithium2 = None
    HAVE_DILITHIUM = False

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

API_TOKEN  = os.environ.get("VERIFY_API_TOKEN", "")  # 未設定ならオープン
QKD_B64    = os.environ.get("VERIFY_QKD_B64", "")    # サーバ保有QKD（Base64）
QKD_BYTES  = base64.b64decode(QKD_B64) if QKD_B64 else None

app = Flask(__name__)

# ===== utils =====
def b64e(b: bytes) -> str: return base64.b64encode(b).decode()
def b64d(s: str) -> bytes: return base64.b64decode(s.encode())

def hkdf(ikm: bytes, length: int, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(ikm)

def canonical_body(body: Dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def require_token() -> bool:
    if not API_TOKEN:
        return True
    return request.headers.get("Authorization","") == f"Bearer {API_TOKEN}"

# ===== 検証ロジック =====
def verify_envelope(env: Dict[str, Any],
                    policy: Dict[str, Any],
                    qkd_bytes: Optional[bytes]) -> Dict[str, Any]:
    # 既定
    require_pqc  = bool(policy.get("require_pqc", True))
    require_mac  = bool(policy.get("require_qkd_mac", True))
    allow_ed255  = bool(policy.get("allow_ed25519", True))
    min_sigs     = int(policy.get("min_valid_signatures", 1))

    res = {
        "pqc_ok": False,
        "ed_ok": False,
        "qkd_mac_ok": (not require_mac),  # 要求しないなら合格扱い
        "valid_signatures": 0,
        "policy_ok": True
    }

    body = env.get("body", {})
    msg  = canonical_body(body)

    # 署名検証
    for rec in env.get("sigs", []):
        scheme = (rec.get("scheme") or "").strip()
        try:
            pk  = b64d(rec["pub"])
            sig = b64d(rec["sig"])
        except Exception:
            continue

        if scheme == "Ed25519" and allow_ed255:
            try:
                Ed25519PublicKey.from_public_bytes(pk).verify(sig, msg)
                res["ed_ok"] = True
                res["valid_signatures"] += 1
            except Exception:
                pass

        if scheme == "Dilithium" and HAVE_DILITHIUM:
            try:
                dilithium2.verify(msg, sig, pk)
                res["pqc_ok"] = True
                res["valid_signatures"] += 1
            except Exception:
                pass

    # QKD-HMAC 検証
    if require_mac:
        mac_rec = env.get("qkd_mac")
        ok = False
        if qkd_bytes and mac_rec:
            try:
                nonce = b64d(mac_rec["nonce"])
                tag   = b64d(mac_rec["tag"])
                mac_key = hkdf(qkd_bytes, 32, b"stage63-qkd-macstage63")
                calc = hmac.new(mac_key, msg + nonce, hashlib.sha256).digest()
                ok = hmac.compare_digest(tag, calc)
            except Exception:
                ok = False
        res["qkd_mac_ok"] = ok

    # 最終判定
    ok = True
    if require_pqc and not res["pqc_ok"]:
        ok = False
    if res["valid_signatures"] < min_sigs:
        ok = False
    if not res["qkd_mac_ok"]:
        ok = False

    res["ok"] = ok
    return res

# ===== API =====
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status":"ok", "have_dilithium": HAVE_DILITHIUM})

@app.route("/verify", methods=["POST"])
def verify_api():
    if not require_token():
        abort(401)
    data   = request.get_json(force=True)
    env    = data.get("envelope", {})
    policy = data.get("policy", {})
    # クライアントがQKDを持ってくるならそれを優先
    qkd_b64 = data.get("qkd_b64")
    qkd     = base64.b64decode(qkd_b64) if qkd_b64 else QKD_BYTES

    result = verify_envelope(env, policy, qkd)
    return jsonify({"result": result})

if __name__ == "__main__":
    # ポートが競合する時は環境変数 PORT=5081 などに
    port = int(os.environ.get("PORT", "5080"))
    app.run(host="127.0.0.1", port=port, debug=False)

