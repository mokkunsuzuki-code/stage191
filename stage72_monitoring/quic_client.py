# quic_client.py
import asyncio, time
from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

from metrics import (
    start_metrics_server, inc_bytes_sent, inc_bytes_recv,
    set_epoch, inc_rekeys, observe_rekey_latency,
)

HOST = "127.0.0.1"
PORT = 8443
ALPN = "qkd-demo"
METRICS_PORT = 8001

class QkdQuicClientProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event) -> None:
        if isinstance(event, StreamDataReceived):
            inc_bytes_recv(len(event.data), "client")
            print(f"[Client] RECV: {event.data.decode(errors='ignore')}")

    async def advance_epoch(self):
        t0 = time.perf_counter()
        new_epoch = int(time.time())
        set_epoch(new_epoch, "client")
        inc_rekeys("client")
        observe_rekey_latency(time.perf_counter() - t0, "client")
        print(f"[Client] 🔑 epoch → {new_epoch}")

async def main():
    start_metrics_server(METRICS_PORT)

    cfg = QuicConfiguration(is_client=True, alpn_protocols=[ALPN])
    cfg.verify_mode = False  # デモなので検証OFF（実運用では証明書検証を有効に）

    print(f"[Client] connect to {HOST}:{PORT}")
    async with connect(HOST, PORT, configuration=cfg, create_protocol=QkdQuicClientProtocol) as client:
        proto: QkdQuicClientProtocol = client
        await asyncio.sleep(0.2)

        for i in range(1, 6):
            msg = f"hello_{i}".encode()
            proto._quic.send_stream_data(0, msg, end_stream=False)
            inc_bytes_sent(len(msg), "client")
            print(f"[Client] SENT: {msg.decode()}")
            await asyncio.sleep(0.2)

        await proto.advance_epoch()
        print("[Client] done.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Client] stopped manually")

