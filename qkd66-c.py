# qkd66_c.py  --- Stage66 TLS client (test)
import socket, ssl

HOST = "127.0.0.1"
PORT = 8443

def main():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # 自己署名を許可（検証しない）

    with socket.create_connection((HOST, PORT)) as sock:
        with ctx.wrap_socket(sock, server_hostname=HOST) as ssock:
            ssock.sendall(b"hello from client")
            resp = ssock.recv(4096)
            print("[Resp]", resp.decode(errors="ignore"))

if __name__ == "__main__":
    main()

