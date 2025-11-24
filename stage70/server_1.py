# server.py  （MockSSLSocketに合わせて素のTCPでOK）
import socket

HOST = "127.0.0.1"
PORT = 8443           # client.py と同じ数字にする！

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(1)
        print(f"[Stage70] server listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            print(f"[Stage70] connection from {addr}")
            with conn:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    print("[Stage70] recv:", data[:80])
                    # 受け取ったら「OK」を返す（クライアント側の recv の確認用）
                    conn.sendall(b"OK")

if __name__ == "__main__":
    main()
