# quic_server.py - Stage74 Echo QUIC server (fixed)
# pip install aioquic

import asyncio
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted

HOST = "127.0.0.1"
PORT = 8443
ALPN = "qkd-demo"
CERT_FILE = "server.crt"
KEY_FILE = "server.key"

class EchoServerProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            print("[Server] handshake completed")
        elif isinstance(event, StreamDataReceived):
            print(f"[Server] RECV stream={event.stream_id} data={event.data!r}")
            self._quic.send_stream_data(event.stream_id, b"OK:" + event.data, end_stream=False)
            self.transmit()

async def main() -> None:
    cfg = QuicConfiguration(is_client=False, alpn_protocols=[ALPN])
    cfg.load_cert_chain(CERT_FILE, KEY_FILE)

    print(f"[Server] QUIC (UDP) listen on {HOST}:{PORT}")

    # ❗ここが修正点：async with ではなく await で受け取る
    server = await serve(
        HOST,
        PORT,
        configuration=cfg,
        create_protocol=EchoServerProtocol,
    )
    try:
        # サーバーを走らせ続ける
        await asyncio.Future()
    finally:
        server.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Server] stopped manually")

