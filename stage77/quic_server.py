# quic_server.py
# -*- coding: utf-8 -*-

import asyncio
from pathlib import Path
from typing import Optional

from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted

from decrypt_cert import decrypt_to_file

HOST = "127.0.0.1"
PORT = 8443
ALPN = ["qkd-demo"]
CERT_FILE = "certs/server.crt"

class EchoServerProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            print("[Server] handshake completed")
        elif isinstance(event, StreamDataReceived):
            data = event.data
            print(f"[Server] RECV stream={event.stream_id}: {data[:80]!r}")
            # エコー返信
            self._quic.send_stream_data(event.stream_id, b"OK:" + data, end_stream=False)

async def main() -> None:
    # 1) 暗号化された鍵を一時復号
    tmp_key_path = decrypt_to_file()

    # 2) サーバ設定
    cfg = QuicConfiguration(is_client=False, alpn_protocols=ALPN)
    cfg.load_cert_chain(CERT_FILE, tmp_key_path)

    print(f"[Server] QUIC (UDP) listen on {HOST}:{PORT}")

    # 3) 起動
    server = await serve(
        HOST,
        PORT,
        configuration=cfg,
        create_protocol=EchoServerProtocol,
    )

    # 4) 読み込み後は一時鍵を削除（load_cert_chain 済みなのでOK）
    try:
        Path(tmp_key_path).unlink(missing_ok=True)
        print("[Server] 一時鍵を削除しました")
    except Exception:
        pass

    try:
        # 動かし続ける
        await asyncio.Future()
    finally:
        server.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Server] stopped manually")
