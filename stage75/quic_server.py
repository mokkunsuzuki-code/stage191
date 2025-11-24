# quic_server.py - Stage75 robust QUIC echo server (FINAL)
# pip install aioquic

import asyncio
from typing import Optional
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
            data = event.data
            print(f"[Server] RECV stream={event.stream_id} data={data!r}")
            # そのままエコー
            msg = b"OK:" + data
            self._quic.send_stream_data(event.stream_id, msg, end_stream=False)  # type: ignore
            self.transmit()

async def main() -> None:
    cfg = QuicConfiguration(is_client=False, alpn_protocols=[ALPN])
    cfg.load_cert_chain(CERT_FILE, KEY_FILE)

    print(f"[Server] QUIC (UDP) listen on {HOST}:{PORT}")
    server = await serve(
        HOST,
        PORT,
        configuration=cfg,
        create_protocol=EchoServerProtocol,
    )
    try:
        await asyncio.Future()  # Ctrl+Cまで維持
    finally:
        server.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Server] stopped manually")

