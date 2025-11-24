# quic_client.py - Stage75 robust QUIC echo client (FINAL)
# pip install aioquic

import asyncio
import socket
from typing import Optional

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted

HOST = "127.0.0.1"
PORT = 8443
ALPN = "qkd-demo"

def udp_port_reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(b"\x00", (host, port))
        return True
    except Exception:
        return False

class EchoClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handshake_done = asyncio.get_event_loop().create_future()
        self.last_response: Optional[bytes] = None

    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            if not self.handshake_done.done():
                self.handshake_done.set_result(True)
        elif isinstance(event, StreamDataReceived):
            self.last_response = event.data
            print(f"[Client] RECV: {event.data!r}")

async def main() -> None:
    if not udp_port_reachable(HOST, PORT):
        print(f"[Client] UDP {HOST}:{PORT} not reachable (server down?)")
        return

    cfg = QuicConfiguration(is_client=True, alpn_protocols=[ALPN])
    cfg.verify_mode = False  # テスト用に証明書検証OFF

    retries = 5
    while retries > 0:
        try:
            async with connect(
                HOST,
                PORT,
                configuration=cfg,
                create_protocol=EchoClientProtocol,
            ) as proto:
                # 1) ハンドシェイク完了を待つ（ここが重要）
                await proto.handshake_done

                # 2) 送信 → エコーを受信
                quic = proto._quic  # type: ignore
                stream_id = quic.get_next_available_stream_id()  # type: ignore
                msg = b"hello-75"
                quic.send_stream_data(stream_id, msg, end_stream=False)  # type: ignore
                proto.transmit()
                print(f"[Client] sent: {msg!r}")

                # 3) 少し待って受信（イベントで表示される）
                await asyncio.sleep(0.5)
                print("[Client] done ✅")
                return

        except Exception as e:
            retries -= 1
            print(f"[Client] connect/send failed: {e}; retry left={retries}")
            await asyncio.sleep(0.6)

    print("[Client] give up 😢")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

