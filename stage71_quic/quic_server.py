# quic_server.py
import asyncio
from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted

HOST = "127.0.0.1"
PORT = 8443
ALPN = ["hq-29"]  # クライアントと合わせる

class EchoServerProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            print("[Server] handshake OK")
        if isinstance(event, StreamDataReceived):
            print(f"[Server] recv: {event.data!r}")
            # 受けたデータに "OK:" を付けて同じストリームに返す
            self._quic.send_stream_data(event.stream_id, b"OK:" + event.data, end_stream=False)
            self.transmit()

async def main() -> None:
    cfg = QuicConfiguration(is_client=False, alpn_protocols=ALPN)
    cfg.load_cert_chain("server.crt", "server.key")

    print(f"[Server] QUIC (UDP) listen on {HOST}:{PORT}")
    server = await serve(HOST, PORT, configuration=cfg, create_protocol=EchoServerProtocol)
    try:
        # サーバーを走らせ続ける
        await asyncio.Future()
    finally:
        server.close()

if __name__ == "__main__":
    asyncio.run(main())

