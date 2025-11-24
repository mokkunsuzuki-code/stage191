# -*- coding: utf-8 -*-
from sign_util import ensure_keypair

if __name__ == "__main__":
    ensure_keypair("server_sign.key", "server_sign.pub")
    ensure_keypair("client_sign.key", "client_sign.pub")
    print("✅ Ed25519鍵を用意しました：server_sign.*, client_sign.*")
