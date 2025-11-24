# qkd66_s.py  --- Stage66 TLS server (minimal)
import socket
import ssl

HOST = "127.0.0.1"
PORT = 8443
CERT_FILE = "server.crt"
KEY_FILE  = "server.key"

def main():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    ctx.verify_mode = ssl.CERT_NONE  # クライアント証明書要求なし

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        sock.bind((HOST, PORT))
        sock.listen(5)
        print(f"[Stage66] Server running on https://{HOST}:{PORT}")

        while True:
            conn, addr = sock.accept()
            with ctx.wrap_socket(conn, server_side=True) as ssock:
                print(f"[Stage66] Connection from {addr}")
                data = ssock.recv(4096)
                if not data:
                    continue
                print("[Recv]", data.decode(errors="ignore"))
                ssock.sendall(b"OK from Stage66 secure server")

if __name__ == "__main__":
    main()

