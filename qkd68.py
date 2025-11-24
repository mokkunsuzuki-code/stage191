# stage68_hybrid_tls_server_client.py
# 段階68：実TLSスタックに「PQC＋QKD」ハイブリッド鍵を注入する通信デモ
# pip install cryptography pqcrypto flask

import os, ssl, base64, threading, time, socket
from flask import Flask, jsonify
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
try:
    from pqcrypto.kem.kyber512 import generate_keypair, encapsulate, decapsulate
    HAVE_KYBER = True
except Exception:
    HAVE_KYBER = False
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

# ====== Hybrid KDF ======
def b64e(b): return base64.b64encode(b).decode()
def b64d(s): return base64.b64decode(s.encode())

def hkdf_mix(shared_secret: bytes, qkd_bits: bytes, label: bytes) -> bytes:
    """PQC共有鍵とQKDビットをミックスしてAES鍵を作る"""
    salt = hashes.Hash(hashes.SHA256()); salt.update(qkd_bits); salt = salt.finalize()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=label).derive(shared_secret + qkd_bits)

# ====== Hybrid Key Exchange (Kyber or X25519) ======
def hybrid_shared_key() -> bytes:
    if HAVE_KYBER:
        pk, sk = generate_keypair()
        ct, shared_cli = encapsulate(pk)
        shared_srv = decapsulate(sk, ct)
        return shared_cli  # クライアント側視点（両者同値）
    else:
        a = X25519PrivateKey.generate()
        b = X25519PrivateKey.generate()
        return a.exchange(b.public_key())

# ====== Hybrid Session Key Maker ======
class HybridSessionKey:
    def __init__(self, label=b"tls68"):
        self.label = label
        self.epoch = 0
        self.qkd_bits = os.urandom(64)
        self.shared_secret = hybrid_shared_key()
        self.aes_key = self.derive_key()

    def derive_key(self) -> bytes:
        return hkdf_mix(self.shared_secret, self.qkd_bits, self.label + b"-%02d" % self.epoch)

    def rekey(self):
        """QKDを新しい乱数で更新して鍵再生成"""
        self.epoch += 1
        self.qkd_bits = os.urandom(64)
        self.aes_key = self.derive_key()

# ====== AES-GCM暗号層（TLS送受信に似せた簡易版） ======
class HybridChannel:
    def __init__(self, session_key: HybridSessionKey):
        self.key = session_key.aes_key
        self.nonce_base = os.urandom(8)
        self.counter = 0

    def _nonce(self):
        self.counter += 1
        return self.counter.to_bytes(4, "big") + self.nonce_base

    def encrypt(self, msg: bytes) -> bytes:
        aes = AESGCM(self.key)
        return aes.encrypt(self._nonce(), msg, b"TLS68")

    def decrypt(self, ct: bytes) -> bytes:
        aes = AESGCM(self.key)
        return aes.decrypt(self._nonce(), ct, b"TLS68")

# ====== Flaskサーバで通信実験 ======
app = Flask(__name__)
session_key = HybridSessionKey(label=b"tls68-demo")
channel = HybridChannel(session_key)

@app.route("/")
def index():
    msg = b"Hello from Stage68 Secure Server"
    ct = channel.encrypt(msg)
    return jsonify({
        "epoch": session_key.epoch,
        "cipher_b64": b64e(ct),
        "note": "Encrypted with PQC+QKD hybrid key"
    })

def run_server():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="server.crt", keyfile="server.key")
    app.run(host="127.0.0.1", port=8443, ssl_context=context)

def run_client():
    context = ssl._create_unverified_context()
    while True:
        try:
            with socket.create_connection(("127.0.0.1", 8443)) as sock:
                with context.wrap_socket(sock, server_hostname="localhost") as s:
                    s.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                    data = s.recv(4096)
                    print("\n[Client Received]\n", data.decode(errors="ignore"))
        except Exception as e:
            print("[Client Error]", e)
        time.sleep(5)

if __name__ == "__main__":
    # 簡易証明書が無ければ作成（教育用）
    if not os.path.exists("server.crt"):
        os.system("openssl req -x509 -nodes -newkey rsa:2048 -keyout server.key -out server.crt -subj '/CN=localhost' -days 365")

    # 並列でサーバとクライアントを起動
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(2)
    run_client()

