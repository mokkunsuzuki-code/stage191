# metrics.py
from __future__ import annotations
import os
import time
from typing import Optional

from prometheus_client import Counter, Histogram, start_http_server

# ---- メトリクス定義（role ラベルで Client/Server を区別） ----
BYTES_SENT = Counter("bytes_sent_total", "Total bytes sent", ["role"])
BYTES_RECV = Counter("bytes_recv_total", "Total bytes received", ["role"])
REKEYS     = Counter("rekeys_total", "Total number of rekeys", ["role"])
QKD_MISS   = Counter("qkd_missing_total", "Times QKD slice was missing", ["role"])
REKEY_LAT  = Histogram("rekey_latency_seconds", "Rekey latency", ["role"])

def inc_bytes_sent(n: int, role: str) -> None:
    BYTES_SENT.labels(role=role).inc(n)

def inc_bytes_recv(n: int, role: str) -> None:
    BYTES_RECV.labels(role=role).inc(n)

def inc_rekeys(role: str) -> None:
    REKEYS.labels(role=role).inc()

def inc_qkd_missing(role: str) -> None:
    QKD_MISS.labels(role=role).inc()

def observe_rekey_latency(dt: float, role: str) -> None:
    REKEY_LAT.labels(role=role).observe(dt)

# （デモ用）現在のエポックを覚えておく
_CURRENT_EPOCH: Optional[int] = None
def set_epoch(epoch: int, role: str) -> None:
    global _CURRENT_EPOCH
    _CURRENT_EPOCH = epoch
    # 参考までにカウンタも1回だけ進める（可視化の目印）
    REKEYS.labels(role=role).inc()

def start_metrics_server(preferred_port: int) -> int:
    """
    Prometheus の HTTP エクスポーターを起動。
    既に使用中なら、次のポートへ自動フォールバック（最大 +20 まで）。
    戻り値: 実際にバインドできたポート番号
    """
    # 環境変数があればそれを最優先（例: METRICS_PORT=9000）
    env = os.getenv("METRICS_PORT")
    if env and env.isdigit():
        preferred_port = int(env)

    port = preferred_port
    last_error: Optional[Exception] = None
    for _ in range(21):  # preferred_port ～ preferred_port+20 を試す
        try:
            start_http_server(port)
            print(f"[metrics] Prometheus exporter started at :{port}")
            return port
        except OSError as e:
            last_error = e
            port += 1
    # ここまで来たらすべて失敗
    raise RuntimeError(f"Failed to start metrics exporter (from :{preferred_port})") from last_error

