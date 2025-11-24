# quic_server.py
import asyncio
import time

from aioquic.asyncio import serve           # ← この serve は「await する」タイプ
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

from metrics import (
    start_metrics_server,
    inc_bytes_recv,
    inc_bytes_sent,
    set_epoch,
)

HOST = "127.0.0.1"
PORT = 8443
ALPN = "qkd-demo"
CERT_FILE = "server.crt"
KEY_FILE  = "server.key"
METRICS_PORT = 8000

class EchoServerProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event) -> None:  # type: ignore[override]
        if isinstance(event, StreamDataReceived):
            data = event.data
            inc_bytes_recv(len(data), "server")
            preview = data.decode(errors="ignore")[:60]
            print(f"[Server] RECV: {preview}")
            self._quic.send_stream_data(event.stream_id, b"OK", end_stream=False)
            inc_bytes_sent(2, "server")
            self.transmit()

async def main() -> None:
    # 1) Prometheus エクスポータ起動（埋まってたら自動で次のポートへ）
    start_metrics_server(METRICS_PORT)

    # 2) TLS 設定
    cfg = QuicConfiguration(is_client=False, alpn_protocols=[ALPN])
    cfg.load_cert_chain(CERT_FILE, KEY_FILE)

    # 3) 起動時にエポックセット（デモ用）
    set_epoch(int(time.time()), "server")

    print(f"[Server] QUIC (UDP) listen on {HOST}:{PORT}")

    # ★ ここがポイント：async with ではなく「await serve(...)」
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

