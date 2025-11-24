# quic_client.py
import asyncio, socket
from pathlib import Path
from typing import Optional
from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted
from sign_util import load_private_key, sign

HOST = "localhost"   # ← ここもホスト名に合わせる
PORT = 8443
ALPN = "qkd-demo"
CERT_FILE = "certs/server.crt"

def udp_port_reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout); s.sendto(b"\x00", (host, port))
        return True
    except Exception:
        return False

class EchoClientProtocol(QuicConnectionProtocol):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        loop = asyncio.get_event_loop()
        self.handshake_done = loop.create_future()
        self.reply: Optional[bytes] = None
    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted) and not self.handshake_done.done():
            self.handshake_done.set_result(True)
        elif isinstance(event, StreamDataReceived):
            self.reply = event.data
            print(f"[Client] RECV: {event.data!r}")

async def main() -> None:
    if not udp_port_reachable("127.0.0.1", PORT):
        print("[Client] server not reachable"); return

    cfg = QuicConfiguration(is_client=True, alpn_protocols=[ALPN])
    cfg.load_verify_locations(CERT_FILE)
    cfg.verify_mode = True
    cfg.server_name = "localhost"   # ← SNI/検証名を明示

    client_priv = load_private_key(Path("keys/client_sign_priv.pem"))

    async with connect(HOST, PORT, configuration=cfg, create_protocol=EchoClientProtocol) as proto:
        await proto.handshake_done
        msg = b"hello-stage76"
        frame = b"S" + sign(client_priv, msg) + msg
        q = proto._quic  # type: ignore
        sid = q.get_next_available_stream_id()  # type: ignore
        q.send_stream_data(sid, frame, end_stream=False)  # type: ignore
        proto.transmit()
        print(f"[Client] sent (signed) msg={msg!r}")
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

