# client.py  — Stage70 demo (IPv4固定 & リトライ付き, send実装)

import socket
import time

from qkd_buffer import QKDKeyBuffer
from key_update_manager import KeyUpdateManager, RekeyPolicy

HOST = "127.0.0.1"
PORT = 8443


class MockSSLSocket:
    """
    TLSの代わりに素のTCPを“SSL風”に扱う軽いラッパ。
    app_wire.py が .send()/.recv() を使うので両方用意する。
    """
    def __init__(self, sock: socket.socket):
        self.sock = sock

    # app_wire.py が使う
    def send(self, data: bytes) -> int:
        # 1回で送る。必要なら sendall に切り替え可
        return self.sock.send(data)

    def sendall(self, data: bytes) -> None:
        self.sock.sendall(data)

    def recv(self, bufsize: int) -> bytes:
        return self.sock.recv(bufsize)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


def connect_with_retry(host: str, port: int, tries: int = 25, interval: float = 0.2) -> socket.socket:
    last_err = None
    for _ in range(tries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # IPv4固定
            s.settimeout(1.0)
            s.connect((host, port))
            return s
        except OSError as e:
            last_err = e
            time.sleep(interval)
    raise RuntimeError(f"server {host}:{port} not reachable: {last_err}")


def main():
    # 1) サーバーへ接続
    s = connect_with_retry(HOST, PORT)
    print(f"[Client] connected to {HOST}:{PORT}")

    # 2) “SSLもどき”ラッパ
    ssl_obj = MockSSLSocket(s)

    # 3) QKDスライスをバッファに投入（学習用ダミー32B）
    qkd = QKDKeyBuffer()
    for e in range(1, 101):
        slice32 = (f"QKD_SLICE_{e:04d}".encode() + b"\x00" * 32)[:32]
        qkd.feed(e, slice32)

    # 4) 鍵更新マネージャ（1MB or 60秒で自動更新の例）
    mgr = KeyUpdateManager(ssl_obj, qkd, RekeyPolicy(max_bytes=1024 * 1024, max_seconds=60))

    # 初回同期 → 鍵更新（制御メッセージは .send()/.recv() を使用）
    mgr.epoch = 0
    mgr.rekey()

    # 5) 送受信テスト（server_1.py は受信後 b"OK" を返す）
    try:
        for i in range(1, 9):
            payload = f"hello-{i}".encode()
            ssl_obj.sendall(payload)
            resp = ssl_obj.recv(4096)
            print(f"[Client] sent={payload!r}  resp={resp!r}")
            time.sleep(0.1)
    finally:
        ssl_obj.close()
        print("[Client] closed")


if __name__ == "__main__":
    main()

