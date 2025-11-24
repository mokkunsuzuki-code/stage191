# -*- coding: utf-8 -*-
# quic_client.py — Stage77 Echo QUIC client (robust, with retries)
# 事前に: pip install aioquic

import asyncio
import socket
import time
from typing import Optional

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted

HOST = "127.0.0.1"
PORT = 8443
ALPN = "qkd-demo"

# ====== UDP 到達性チェック（サーバーがいない時は即わかる） ======
def udp_port_reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(b"\x00", (host, port))
        return True
    except Exception:
        return False


# ====== クライアント用 Protocol ======
class EchoClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._handshake_ok: asyncio.Event = asyncio.Event()
        self._resp_fut: asyncio.Future[bytes] = asyncio.get_event_loop().create_future()

    # QUICイベント受信
    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            print("[Client] handshake completed")
            self._handshake_ok.set()
        elif isinstance(event, StreamDataReceived):
            # サーバーからのエコー
            data = event.data
            print(f"[Client] RECV stream={event.stream_id}: {data!r}")
            if not self._resp_fut.done():
                self._resp_fut.set_result(data)

    async def wait_handshake(self, timeout: float = 3.0) -> None:
        await asyncio.wait_for(self._handshake_ok.wait(), timeout=timeout)

    async def run(self, message: bytes = b"hello-stage77") -> bytes:
        """
        1) ストリームを開く
        2) メッセージ送信
        3) エコー受信を待つ
        4) ストリームを閉じる
        """
        quic = self._quic

        # ストリームIDを確保
        stream_id = quic.get_next_available_stream_id()
        # 送信（end_stream=False で半閉）
        quic.send_stream_data(stream_id, message, end_stream=False)
        self.transmit()
        print(f"[Client] SENT stream={stream_id}: {message!r}")

        # 受信待ち（サーバーは "b'OK' またはエコー" を返す設計）
        data = await asyncio.wait_for(self._resp_fut, timeout=3.0)

        # クリーンにクローズ
        quic.send_stream_data(stream_id, b"", end_stream=True)
        self.transmit()
        return data


# ====== エントリポイント ======
async def main() -> None:
    # 1) サーバーが待ち受け中か軽くチェック（任意）
    if not udp_port_reachable(HOST, PORT):
        print(f"[Client] UDP {HOST}:{PORT} not reachable (server down?)")
        return

    # 2) QUIC設定
    cfg = QuicConfiguration(is_client=True, alpn_protocols=[ALPN])

    # 自己署名のため検証をオフ（手っ取り早いデモ向け）
    cfg.verify_mode = False

    # ← 実運用寄りにするなら検証オンにして、server.crt を信頼させる
    # cfg.verify_mode = True
    # cfg.load_verify_locations("certs/server.crt")

    # 3) 接続〜送受信（リトライつき）
    retries = 3
    for attempt in range(1, retries + 1):
        try:
            async with connect(
                HOST, PORT, configuration=cfg, create_protocol=EchoClientProtocol
            ) as client:
                proto: EchoClientProtocol = client  # 型ヒント用

                # ハンドシェイク完了待ち
                await proto.wait_handshake()
                await asyncio.sleep(0.05)

                # メッセージ送受信
                resp = await proto.run(b"hello-stage77")
                print(f"[Client] OK: resp={resp!r}")
                break

        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            left = retries - attempt
            print(f"[Client] connect/send failed: {e.__class__.__name__}: {e}; retry left={left}")
            if left == 0:
                print("[Client] give up")
                raise
            time.sleep(0.4)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

