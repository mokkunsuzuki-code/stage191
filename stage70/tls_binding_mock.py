# -*- coding: utf-8 -*-
# tls_binding_mock.py
"""学習用のモック TLS バインディング。
- exporter: (label|context) をプロセスシークレットでHMACして疑似導出
- key_update: ログ出力のみ
"""
from hashlib import sha256
import hmac
import os

_SECRET = os.urandom(32)

def _prf(*parts: bytes, outlen: int) -> bytes:
    data = b"|".join(parts)
    t = hmac.new(_SECRET, data, sha256).digest()
    if outlen <= 32:
        return t[:outlen]
    x = hmac.new(_SECRET, t + data + b"+", sha256).digest()
    return (t + x)[:outlen]

def tls_exporter(ssl_obj, label: bytes, context: bytes, outlen: int) -> bytes:
    return _prf(b"exporter", label, context, outlen=outlen)

def tls_key_update(ssl_obj, request_peer_update: bool = True):
    flag = "(peer also updates)" if request_peer_update else "(local only)"
    print(f"[MOCK] TLS KeyUpdate triggered {flag}")
