# quic_client.py - Stage74 Echo QUIC client (FINAL FINAL ✅)
# pip install aioquic

import asyncio
import socket
from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

HOST = "127.0.0.1"
PORT = 8443
ALPN = "qkd-demo"

# --- UDPチェック ---
def udp_port_reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(b"\x00", (host, port))
        return True
    except Exception:
        return False


# --- クライアント側プロトコル ---
class EchoClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.response = None

    def quic_event_received(self, event) -> None:
        if isinstance(event, StreamDataReceived):
            print(f"[Client] RECV: {event.data!r}")
            self.response = event.data


# --- メイン処理 ---
async def main():
    if not udp_port_reachable(HOST, PORT):
        print(f"[Client] UDP {HOST}:{PORT} not reachable (server down?)")
        return

    cfg = QuicConfiguration(is_client=True, alpn_protocols=[ALPN])
    cfg.verify_mode = False  # 証明書チェック無効（テスト用）

    retry = 5
    while retry > 0:
        try:
            async with connect(
                HOST,
                PORT,
                configuration=cfg,
                create_protocol=EchoClientProtocol,
            ) as client:
                # ✅ ここがポイント
                proto = client
                quic = client._quic  # QUICセッションを直接取得

                # メッセージ送信
                msg = b"hello"
                stream_id = quic.get_next_available_stream_id()  # type: ignore
                quic.send_stream_data(stream_id, msg, end_stream=False)  # type: ignore
                proto.transmit()
                print(f"[Client] sent: {msg!r}")

                # 応答待ち
                await asyncio.sleep(0.5)
                print("[Client] done ✅")
                return

        except Exception as e:
            retry -= 1
            print(f"[Client] connect/send failed: {e}; retry left={retry}")
            await asyncio.sleep(0.5)

    print("[Client] give up 😢")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

