# qkd63.py  — 段階63：PQC + QKD-HMAC 署名デモ（oqs不要・自動フォールバック付き）
import os, json, base64, hashlib, hmac
from cryptography.hazmat.primitives.asymmetric import ed25519

# ---- pqcrypto（Dilithium2）を試し、ダメならEd25519に自動フォールバック ----
try:
    from pqcrypto.sign import dilithium2
    HAVE_PQC = True
except Exception:
    print("⚠️ pqcrypto.sign.dilithium2 を読み込めません。Ed25519代用にフォールバックします。")
    HAVE_PQC = False

def generate_pqc_keypair():
    if HAVE_PQC:
        # pqcrypto は (public_key, secret_key) のタプル等を返す実装が複数あります。
        # ここでは sign()/open() が受け取れる「キーペアオブジェクト」をそのまま保持します。
        return dilithium2.generate_keypair()
    else:
        priv = ed25519.Ed25519PrivateKey.generate()
        pub  = priv.public_key()
        return {"private": priv, "public": pub}

def pqc_sign(message: bytes, keypair):
    if HAVE_PQC:
        return dilithium2.sign(message, keypair)
    else:
        return keypair["private"].sign(message)

def pqc_verify(message: bytes, signature: bytes, keypair):
    if HAVE_PQC:
        try:
            # open() は検証に成功するとメッセージを返す実装
            _ = dilithium2.open(signature, keypair)
            return True
        except Exception:
            return False
    else:
        try:
            keypair["public"].verify(signature, message)
            return True
        except Exception:
            return False

def qkd_hmac(data: bytes, qkd_key: bytes) -> bytes:
    return hmac.new(qkd_key, data, hashlib.sha256).digest()

def make_envelope(body: dict, alice_pqc, qkd_bytes: bytes) -> dict:
    msg = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    sig_pqc  = pqc_sign(msg, alice_pqc)
    sig_hmac = qkd_hmac(msg, qkd_bytes)
    return {
        "body": body,
        "sig_pqc":  base64.b64encode(sig_pqc).decode(),
        "sig_hmac": base64.b64encode(sig_hmac).decode(),
    }

def verify_envelope(env: dict, policy: dict, qkd_bytes: bytes) -> dict:
    msg      = json.dumps(env["body"], sort_keys=True, separators=(",", ":")).encode()
    sig_pqc  = base64.b64decode(env["sig_pqc"])
    sig_hmac = base64.b64decode(env["sig_hmac"])

    res = {"pqc_ok": True, "hmac_ok": True}

    if policy.get("require_pqc", True):
        res["pqc_ok"] = pqc_verify(msg, sig_pqc, policy["alice_pqc"])
    if policy.get("require_qkd_mac", True):
        res["hmac_ok"] = hmac.compare_digest(qkd_hmac(msg, qkd_bytes), sig_hmac)

    res["all_ok"] = res["pqc_ok"] and res["hmac_ok"]
    return res

def demo():
    print("=== 段階63: PQC + QKD-HMAC 署名デモ（oqs不要）===")

    # 共有（QKD）鍵を想定
    qkd_bytes = os.urandom(32)

    # 署名鍵（PQC優先 / ダメならEd25519）
    alice_pqc = generate_pqc_keypair()

    # 本文
    body = {"action": "ROTATE_DATA_DEK", "params": {"reason": "routine"}}

    # エンベロープ生成
    env = make_envelope(body, alice_pqc, qkd_bytes)

    # 検証
    policy = {"require_pqc": True, "require_qkd_mac": True, "alice_pqc": alice_pqc}
    res = verify_envelope(env, policy, qkd_bytes)
    print("✅ 正常検証結果")
    print(json.dumps(res, ensure_ascii=False, indent=2))

    # 改ざんテスト
    env_bad = json.loads(json.dumps(env))
    env_bad["body"]["params"]["reason"] = "tampered"
    res_bad = verify_envelope(env_bad, policy, qkd_bytes)
    print("🚫 改ざん検出結果")
    print(json.dumps(res_bad, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    demo()

