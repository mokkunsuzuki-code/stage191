# quic_recv.py — Stage80 QUIC file receiver (version-agnostic)
# pip install aioquic

import asyncio
from pathlib import Path

from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted, StreamDataReceived
from aioquic.asyncio import serve  # バージョン差吸収は下の main で処理

HOST = "127.0.0.1"
PORT = 9555
ALPN = "qkd-demo"

CERT_FILE = "certs/server.crt"
KEY_FILE  = "certs/server.key"
OUT_FILE  = "received.bin"

class FileRecvProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._buf = bytearray()

    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            print("[Server] handshake completed")
        elif isinstance(event, StreamDataReceived):
            self._buf += event.data
            print(f"[Server] RECV {len(event.data)} bytes (total={len(self._buf)})")
            if event.end_stream:
                Path(OUT_FILE).write_bytes(self._buf)
                print(f"[Server] saved -> {OUT_FILE}")
                # 簡単な応答
                sid = self._quic.get_next_available_stream_id()
                self._quic.send_stream_data(sid, b"OK", end_stream=True)
                self.transmit()

async def _run_forever():
    # Ctrl+Cまで待つ
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass

async def main() -> None:
    cfg = QuicConfiguration(is_client=False, alpn_protocols=[ALPN])
    cfg.load_cert_chain(CERT_FILE, KEY_FILE)

    print(f"[Server] QUIC (UDP) listen on {HOST}:{PORT}")

    # 互換対応：serve が async-context-manager の場合と、await で server を返す場合に対応
    svc = serve(HOST, PORT, configuration=cfg, create_protocol=FileRecvProtocol)

    # 1) async-context-manager 方式？
    if hasattr(svc, "__aenter__"):
        async with svc:
            await _run_forever()
    else:
        # 2) await で QuicServer を返す方式
        server = await svc
        try:
            await _run_forever()
        finally:
            server.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Server] stopped")
