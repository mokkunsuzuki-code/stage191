# -*- coding: utf-8 -*-
# aead.py
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class AEAD:
    """
    AES-GCM の薄いラッパ。
    key: 16/24/32 バイト (AES-128/192/256)
    nonce: 12 バイト（各メッセージで一意）
    aad: 追加認証データ（改ざん検知に含めるメタ情報）
    """
    def __init__(self, key: bytes):
        if len(key) not in (16, 24, 32):
            raise ValueError("AES-GCM key must be 16/24/32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, nonce12: bytes, plaintext: bytes, aad: bytes) -> bytes:
        if len(nonce12) != 12:
            raise ValueError("AES-GCM nonce must be 12 bytes")
        return self._aead.encrypt(nonce12, plaintext, aad)

    def decrypt(self, nonce12: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        if len(nonce12) != 12:
            raise ValueError("AES-GCM nonce must be 12 bytes")
        return self._aead.decrypt(nonce12, ciphertext, aad)
