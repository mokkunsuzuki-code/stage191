# -*- coding: utf-8 -*-
"""
Stage85: 量子鍵を使った安全送信（Alice側）
"""
import socket
from utils import load_key_auto, xor_bytes

HOST = "127.0.0.1"
PORT = 5555

def main():
    key = load_key_auto()
    message = "This is a quantum-safe message from Alice!"
    encrypted = xor_bytes(message.encode(), key)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        s.sendall(encrypted)
        print(f"✅ 暗号化送信完了！: {message}")
        print(f"🔑 使用鍵: final_key.bin")

if __name__ == "__main__":
    main()

