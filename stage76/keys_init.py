# keys_init.py
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple
import ipaddress

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from sign_util import (
    generate_ed25519_keypair, save_private_key, save_public_key, KEYS_DIR
)

CERTS_DIR = Path("certs")
CERTS_DIR.mkdir(exist_ok=True)

def create_self_signed_cert(hostname: str, cert_path: Path, key_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    san = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow() - timedelta(minutes=1))
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

def main():
    # Ed25519(送信者署名)は前のままでOK。既存の鍵があるならスキップでも可
    client_priv, client_pub = generate_ed25519_keypair()
    save_private_key(client_priv, KEYS_DIR / "client_sign_priv.pem")
    save_public_key(client_pub, KEYS_DIR / "client_sign_pub.pem")
    print("[keys] generated client_sign_{priv,pub}.pem")

    cert_path = CERTS_DIR / "server.crt"
    key_path = CERTS_DIR / "server.key"
    create_self_signed_cert("localhost", cert_path, key_path)
    print(f"[certs] created {cert_path} & {key_path} (SAN: localhost, 127.0.0.1)")

if __name__ == "__main__":
    main()
