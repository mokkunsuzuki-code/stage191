# qkd65.py  フォールバック Keystore（ファイル保存 + AES-GCM ラップ）
# 依存: cryptography
#   pip install cryptography

from __future__ import annotations
import os, json, base64, pathlib, secrets
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ===== util =====
def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")

def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))

def read_bytes(p: pathlib.Path) -> Optional[bytes]:
    try:
        return p.read_bytes()
    except FileNotFoundError:
        return None

def write_bytes(p: pathlib.Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)

def read_json(p: pathlib.Path) -> dict:
    try:
        return json.loads(p.read_text("utf-8"))
    except FileNotFoundError:
        return {}

def write_json(p: pathlib.Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ===== config =====
@dataclass
class KeystoreConfig:
    dir: pathlib.Path = pathlib.Path(".")
    master_key_file: str = "storage_master.key"   # 32B AES-256-GCM key
    wrap_file: str      = "ed25519_wrapped.bin"   # nonce|ciphertext
    meta_file: str      = "ed25519_meta.json"     # public key etc.
    aad: bytes          = b"stage65-os-wrap"


# ===== file keystore =====
class FileKeystore:
    def __init__(self, cfg: KeystoreConfig) -> None:
        self.cfg = cfg
        self.path_master = cfg.dir / cfg.master_key_file
        self.path_wrap   = cfg.dir / cfg.wrap_file
        self.path_meta   = cfg.dir / cfg.meta_file

    def _get_or_create_master_key(self) -> bytes:
        mk = read_bytes(self.path_master)
        if mk is None:
            mk = secrets.token_bytes(32)
            write_bytes(self.path_master, mk)
        return mk

    def _init_keypair(self) -> None:
        mk = self._get_or_create_master_key()

        # 1) generate Ed25519 sk/pk
        sk = Ed25519PrivateKey.generate()
        sk_bytes = sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pk_bytes = sk.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        # 2) wrap secret key with AES-256-GCM: store as nonce(12B) | ct
        aes = AESGCM(mk)
        nonce = secrets.token_bytes(12)
        ct = aes.encrypt(nonce, sk_bytes, self.cfg.aad)
        write_bytes(self.path_wrap, nonce + ct)

        # 3) meta (only public key)
        write_json(self.path_meta, {"alg": "Ed25519", "public_key_b64": b64e(pk_bytes)})

    def ensure(self) -> None:
        if not self.path_wrap.exists() or not self.path_meta.exists():
            self._init_keypair()

    def _load_private_key(self) -> Ed25519PrivateKey:
        self.ensure()
        mk = self._get_or_create_master_key()
        wrapped = read_bytes(self.path_wrap)
        if not wrapped or len(wrapped) < 13:
            raise RuntimeError("wrapped secret broken")
        nonce, ct = wrapped[:12], wrapped[12:]
        sk_bytes = AESGCM(mk).decrypt(nonce, ct, self.cfg.aad)
        return Ed25519PrivateKey.from_private_bytes(sk_bytes)

    def public_key_b64(self) -> str:
        meta = read_json(self.path_meta)
        pk_b64 = meta.get("public_key_b64")
        if pk_b64:
            return pk_b64
        pk_b = self._load_private_key().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        pk_b64 = b64e(pk_b)
        meta["public_key_b64"] = pk_b64
        write_json(self.path_meta, meta)
        return pk_b64

    def sign_b64(self, msg: bytes) -> str:
        sk = self._load_private_key()
        sig = sk.sign(msg)  # 64 bytes
        return b64e(sig)


# ===== facade =====
class Keystore:
    def __init__(self, cfg: KeystoreConfig) -> None:
        self.impl = FileKeystore(cfg)

    def ensure(self) -> None:
        self.impl.ensure()

    def public_key_b64(self) -> str:
        return self.impl.public_key_b64()

    def sign_b64(self, msg: bytes) -> str:
        return self.impl.sign_b64(msg)


# ===== demo =====
def demo():
    cfg = KeystoreConfig(dir=pathlib.Path("."))  # save in current dir
    ks = Keystore(cfg)

    ks.ensure()
    print(f"[Keystore] public_key(b64) = {ks.public_key_b64()[:60]}...")

    msg = b"hello-stage65"
    sig_b64 = ks.sign_b64(msg)
    print(f"[Sign] sig(b64) = {sig_b64[:60]}... (len={len(base64.b64decode(sig_b64))}B)")

    pk_b = base64.b64decode(ks.public_key_b64())
    pk = Ed25519PublicKey.from_public_bytes(pk_b)
    try:
        pk.verify(base64.b64decode(sig_b64), msg)
        print("[Verify] OK")
    except Exception as e:
        print("[Verify] NG:", e)

if __name__ == "__main__":
    demo()

