# -*- coding: utf-8 -*-
import os
from typing import Tuple
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)
from cryptography.hazmat.primitives import serialization

def ensure_keypair(priv_path: str, pub_path: str) -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    if os.path.exists(priv_path) and os.path.exists(pub_path):
        with open(priv_path, "rb") as f:
            priv = serialization.load_pem_private_key(f.read(), password=None)
        with open(pub_path, "rb") as f:
            pub = serialization.load_pem_public_key(f.read())
        return priv, pub  # type: ignore[return-value]

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    with open(priv_path, "wb") as f:
        f.write(priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    with open(pub_path, "wb") as f:
        f.write(pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
    return priv, pub

def load_public_key(pub_path: str) -> Ed25519PublicKey:
    with open(pub_path, "rb") as f:
        return serialization.load_pem_public_key(f.read())  # type: ignore[return-value]
