# metrics.py
from prometheus_client import Counter, Gauge, Histogram, start_http_server

BYTES_SENT = Counter("qkd_bytes_sent_total", "Bytes sent", ["role"])
BYTES_RECV = Counter("qkd_bytes_recv_total", "Bytes received", ["role"])
REKEYS     = Counter("qkd_rekeys_total", "Number of rekeys", ["role"])
REKEY_LAT  = Histogram("qkd_rekey_latency_seconds", "Rekey latency (s)", ["role"])
EPOCH      = Gauge("qkd_epoch", "Current QKD epoch", ["role"])

_DEF_PORT = 8000

def start_metrics_server(port: int | None = None) -> None:
    start_http_server(port or _DEF_PORT)
    print(f"[metrics] Prometheus exporter started at :{port or _DEF_PORT}")

def inc_bytes_sent(n: int, role="server"): BYTES_SENT.labels(role=role).inc(n)
def inc_bytes_recv(n: int, role="server"): BYTES_RECV.labels(role=role).inc(n)
def inc_rekeys(role="server"):             REKEYS.labels(role=role).inc()
def observe_rekey_latency(sec: float, role="server"): REKEY_LAT.labels(role=role).observe(sec)
def set_epoch(epoch: int, role="server"):  EPOCH.labels(role=role).set(epoch)
