# quic_send.py — Stage80 QUIC sender (robust, version-agnostic)
# pip install aioquic cryptography
#
# 使い方(例):
#   python3 quic_send.py --host localhost --port 9555 --cert certs/server.crt --file secret.txt
#   # 省略可の既定値: host=localhost, port=9555, cert=certs/server.crt, file=secret.txt

import argparse
import asyncio
import socket
import time
from pathlib import Path
from typing import Optional

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted, StreamDataReceived

ALPN = "qkd-demo"

# --- UDP到達性チェック（落ちるなら即リトライへ） -------------------------
def udp_port_reachable(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(b"\x00", (host, port))
        return True
    except Exception:
        return False

# --- 送信用プロトコル ------------------------------------------------------
class Sender(QuicConnectionProtocol):
    def __init__(self, *args, payload: bytes, **kwargs):
        super().__init__(*args, **kwargs)
        self._payload = payload
        self._done = asyncio.Event()
        self._resp: Optional[bytes] = None

    def quic_event_received(self, event) -> None:
        if isinstance(event, HandshakeCompleted):
            print("[Client] handshake completed; sending file...")
            sid = self._quic.get_next_available_stream_id()
            self._quic.send_stream_data(sid, self._payload, end_stream=True)
            self.transmit()

        elif isinstance(event, StreamDataReceived):
            self._resp = event.data
            print(f"[Client] RECV resp={self._resp!r}")
            self._done.set()

# --- 1回分の送信処理 ------------------------------------------------------
async def run_once(host: str, port: int, cert: Path, file: Path, timeout: float = 5.0) -> bool:
    data = file.read_bytes()

    cfg = QuicConfiguration(is_client=True, alpn_protocols=[ALPN])
    # サーバ証明書を信頼ストアに追加（自己署名の想定）
    cfg.load_verify_locations(str(cert))
    # SNI（IP直指定でもホスト名SANで検証できるように）
    cfg.server_name = "localhost" if host in ("127.0.0.1", "::1") else host

    # 接続 & 送信（async context manager）
    async with connect(host, port, configuration=cfg,
                       create_protocol=lambda *a, **k: Sender(*a, payload=data, **k)) as proto:  # type: ignore
        try:
            await asyncio.wait_for(proto._done.wait(), timeout=timeout)  # type: ignore[attr-defined]
        except asyncio.TimeoutError:
            print("[Client] timeout waiting server reply")
            return False

        # サーバからOK応答が来ていれば成功判定
        return getattr(proto, "_resp", None) == b"OK"  # type: ignore[attr-defined]

# --- メイン（リトライ付き） ------------------------------------------------
async def main() -> None:
    p = argparse.ArgumentParser(description="QUIC file sender")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=9555)
    p.add_argument("--cert", default="certs/server.crt")
    p.add_argument("--file", default="secret.txt")
    p.add_argument("--retries", type=int, default=6)
    args = p.parse_args()

    host = args.host
    port = args.port
    cert = Path(args.cert)
    file = Path(args.file)

    if not cert.exists():
        raise FileNotFoundError(f"certificate not found: {cert}")
    if not file.exists():
        raise FileNotFoundError(f"file to send not found: {file}")

    if not udp_port_reachable(host, port):
        print(f"[Client] UDP {host}:{port} unreachable (quick check)")

    last_err: Optional[BaseException] = None
    for attempt in range(1, args.retries + 1):
        try:
            ok = await run_once(host, port, cert, file)
            if ok:
                print("[Client] SUCCESS")
                return
            else:
                print("[Client] unexpected response; retry left=%d" % (args.retries - attempt))
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            last_err = e
            left = args.retries - attempt
            print(f"[Client] connect/send failed: {e!s}; retry left={left}")
            time.sleep(0.5)
        except Exception as e:
            last_err = e
            print(f"[Client] unexpected: {e!r}")
            break

    print("[Client] give up")
    if last_err:
        raise last_err

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
