import asyncio, ssl
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted

HOST = "127.0.0.1"
PORT = 8443
ALPN = ["hq-29"]

class EchoClientProtocol(QuicConnectionProtocol):
    async def start(self):
        sid = self._quic.get_next_available_stream_id()
        for i in range(1, 4):
            self._quic.send_stream_data(sid, f"hello-{i}".encode(), end_stream=False)
            self.transmit()
            await asyncio.sleep(0.2)

    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            print("[Client] handshake OK")
        if isinstance(event, StreamDataReceived):
            print(f"[Client] resp: {event.data!r}")

async def main():
    cfg = QuicConfiguration(is_client=True, alpn_protocols=ALPN)
    cfg.verify_mode = ssl.CERT_NONE  # デモなので検証OFF（本番は検証ON）
    async with connect(HOST, PORT, configuration=cfg, create_protocol=EchoClientProtocol) as proto:
        await proto.start()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())

