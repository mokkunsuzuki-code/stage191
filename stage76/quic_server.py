# quic_server.py
import asyncio
from pathlib import Path
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted
from sign_util import load_public_key, verify

HOST = "localhost"        # ← ここをIPではなくホスト名に
PORT = 8443
ALPN = "qkd-demo"

CERT_FILE = "certs/server.crt"
KEY_FILE = "certs/server.key"
CLIENT_PUB = load_public_key(Path("keys/client_sign_pub.pem"))

class EchoServerProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            print("[Server] handshake completed")
        elif isinstance(event, StreamDataReceived):
            data = event.data
            if not (len(data) >= 65 and data[:1] == b"S"):
                print("[Server] invalid frame"); return
            sig = data[1:65]; msg = data[65:]
            if verify(CLIENT_PUB, msg, sig):
                print(f"[Server] ✓ verified msg={msg!r}")
                reply = b"OK:" + msg
            else:
                print("[Server] ✗ signature NG"); reply = b"NG"
            self._quic.send_stream_data(event.stream_id, reply, end_stream=False)  # type: ignore
            self.transmit()

async def main() -> None:
    cfg = QuicConfiguration(is_client=False, alpn_protocols=[ALPN])
    cfg.load_cert_chain(CERT_FILE, KEY_FILE)
    print(f"[Server] QUIC (UDP) listen on {HOST}:{PORT}")
    server = await serve(HOST, PORT, configuration=cfg, create_protocol=EchoServerProtocol)
    try:
        await asyncio.Future()
    finally:
        server.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Server] stopped")
