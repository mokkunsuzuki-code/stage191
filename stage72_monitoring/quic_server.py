# quic_server.py
import asyncio
import time
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

from metrics import (
    start_metrics_server, inc_bytes_recv, inc_bytes_sent,
    set_epoch,
)

HOST = "127.0.0.1"
PORT = 8443
ALPN = "qkd-demo"
METRICS_PORT = 8000

CERT_FILE = "server.crt"
KEY_FILE  = "server.key"


class EchoServerProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event) -> None:
        if isinstance(event, StreamDataReceived):
            data = event.data
            inc_bytes_recv(len(data), "server")
            print(f"[Server] RECV: {data.decode(errors='ignore')}")
            # エコーで "OK" を返す
            self._quic.send_stream_data(event.stream_id, b"OK", end_stream=False)
            inc_bytes_sent(2, "server")


async def main() -> None:
    # Prometheusメトリクス
    start_metrics_server(METRICS_PORT)

    # QUIC設定
    cfg = QuicConfiguration(is_client=False, alpn_protocols=[ALPN])
    cfg.load_cert_chain(CERT_FILE, KEY_FILE)

    # デモ用：起動時にエポック設定
    set_epoch(int(time.time()), "server")

    print(f"[Server] QUIC (UDP) listen on {HOST}:{PORT}")

    # ★ ここがポイント：async with ではなく await する
    await serve(
        HOST,
        PORT,
        configuration=cfg,
        create_protocol=EchoServerProtocol,
    )

    # サーバを動かし続ける（無限待機）
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Server] stopped manually")

