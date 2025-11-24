# quic_client.py
import asyncio
import time

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

from metrics import (
    start_metrics_server,
    inc_bytes_sent,
    inc_bytes_recv,
    set_epoch,
    inc_rekeys,
    observe_rekey_latency,
)

HOST = "127.0.0.1"
PORT = 8443
ALPN = "qkd-demo"
METRICS_PORT = 8001  # サーバ(:8000)とぶつからないように

class QkdQuicClientProtocol(QuicConnectionProtocol):
    """
    - 接続後に自分で双方向ストリームを開く
    - サーバからの応答(“OK”)は quic_event_received で受け取る
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stream_id = None

    def quic_event_received(self, event) -> None:  # type: ignore[override]
        if isinstance(event, StreamDataReceived):
            inc_bytes_recv(len(event.data), "client")
            try:
                print(f"[Client] RECV: {event.data.decode()}")
            except Exception:
                print(f"[Client] RECV: {len(event.data)} bytes")

    async def open_stream(self) -> int:
        # NOTE: _quic は保護属性だが、aioquicの公式サンプルでも直接利用する
        self.stream_id = self._quic.get_next_available_stream_id()  # type: ignore[attr-defined]
        return self.stream_id

    def send(self, data: bytes) -> None:
        assert self.stream_id is not None, "stream not opened yet"
        self._quic.send_stream_data(self.stream_id, data, end_stream=False)  # type: ignore[attr-defined]
        inc_bytes_sent(len(data), "client")
        self.transmit()


async def main() -> None:
    # 1) Prometheusエクスポータ起動（埋まっていたら自動で次ポートへ逃がす）
    start_metrics_server(METRICS_PORT)

    # 2) QUIC/TLS 設定（デモなので検証は無効）
    cfg = QuicConfiguration(is_client=True, alpn_protocols=[ALPN])
    cfg.verify_mode = False

    # 3) 接続 → プロトコル取得
    async with connect(HOST, PORT, configuration=cfg,
                       create_protocol=QkdQuicClientProtocol) as proto:  # type: ignore[assignment]
        await asyncio.sleep(0.1)          # 接続直後の安定待ち
        await proto.open_stream()          # 双方向ストリームを確保

        # 初回エポック（デモ用に現在時刻）
        set_epoch(int(time.time()), "client")

        # 4) 送受信と“擬似リキー”計測を数回実施
        for i in range(1, 7):
            msg = f"hello-{i}".encode()
            t0 = time.perf_counter()

            proto.send(msg)
            print(f"[Client] SENT: {msg.decode()}")

            await asyncio.sleep(0.25)  # サーバの “OK” 応答待ち

            # 3回ごとに“擬似的に”リキー（Key Phase更新相当）
            if i % 3 == 0:
                set_epoch(int(time.time()), "client")
                inc_rekeys("client")
                observe_rekey_latency(time.perf_counter() - t0, "client")

        # 送信残があれば吐き切る
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

