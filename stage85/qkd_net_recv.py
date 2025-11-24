# -*- coding: utf-8 -*-
"""
Stage85: 量子鍵を使った安全受信（Bob側）
"""
import socket
from pathlib import Path          # ★ ここを追加！
from utils import load_key_auto, xor_bytes

HOST = "127.0.0.1"
PORT = 5555

def main():
    key = load_key_auto()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(1)
        print(f"[Bob] Listening on {HOST}:{PORT} ...")
        conn, addr = s.accept()
        with conn:
            print(f"[Bob] Connected by {addr}")
            data = conn.recv(4096)
            if not data:
                print("[Bob] No data received.")
                return

            decrypted = xor_bytes(data, key)

            # 受信メッセージをファイルに保存
            Path("received_message.txt").write_bytes(decrypted)

            print("✅ 復号完了 → received_message.txt に保存")
            print(f"🔑 使用鍵: final_key.bin")
            try:
                print(f"📩 内容: {decrypted.decode('utf-8')}")
            except UnicodeDecodeError:
                print("📩 内容: （バイナリデータのため表示不可）")

if __name__ == "__main__":
    main()
