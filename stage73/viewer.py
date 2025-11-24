# -*- coding: utf-8 -*-
# viewer.py
#
# 目的:
# - Prometheus/Grafana なしで、QUIC×QKDメトリクスを簡易ダッシュボード表示
# - サーバ(:8000)とクライアント(:8001)の /metrics を1秒ごとに取りに行き、
#   bytes_sent_total / bytes_recv_total / rekeys_total / qkd_missing_total /
#   rekey_latency_seconds（ヒストグラムの合計・回数）を集計・可視化
#
# 使い方（手順は文末にも再掲）:
#   1) サーバを起動:  python quic_server.py   （metrics→:8000）
#   2) クライアント:  python quic_client.py   （metrics→:8001）
#   3) 本ビュー:      python viewer.py         （ダッシュボード→:8050）
#   4) ブラウザで http://127.0.0.1:8050

import time
import threading
import urllib.request
from typing import Dict, Tuple, Optional

from flask import Flask, jsonify, Response

# ===== 設定 =====
SERVER_METRICS_URL = "http://127.0.0.1:8000/metrics"
CLIENT_METRICS_URL = "http://127.0.0.1:8001/metrics"
REFRESH_INTERVAL_SEC = 1.0  # ポーリング間隔
DASHBOARD_PORT = 8050

app = Flask(__name__)

# 最新スナップショットを保持（ビュー側は /api/snapshot を叩くだけ）
_latest: Dict[str, Dict[str, float]] = {}
_latest_ts: float = 0.0
_lock = threading.Lock()


# ---- Prometheusテキストをシンプルにパースする ----
def _fetch(url: str) -> Optional[str]:
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def _parse_prom(text: str) -> Dict[Tuple[str, str], float]:
    """
    返り値: { (metric_name, role): value }
    例: ('bytes_sent_total', 'client') -> 1234.0
    """
    out: Dict[Tuple[str, str], float] = {}
    if not text:
        return out

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # 例:
        # BYTES_SENT{role="client"} 42
        # rekey_latency_seconds_sum{role="server"} 0.183
        # → metrics.py の Counter/Histo 名と合わせる
        # metrics.py 側で:
        #   BYTES_SENT  -> "bytes_sent_total"
        #   BYTES_RECV  -> "bytes_recv_total"
        #   REKEYS      -> "rekeys_total"
        #   QKD_MISS    -> "qkd_missing_total"
        #   REKEY_LAT(histogram) -> "rekey_latency_seconds_*"
        name_part, val_part = line.split(" ", 1)
        value = float(val_part.strip())

        # name_part から metric名と role を取り出す
        role = ""
        if "role=" in name_part:
            # name{role="client"} の role を抜く
            try:
                role = name_part.split('role="', 1)[1].split('"', 1)[0]
            except Exception:
                role = ""

        # {…} を除いた素のmetric名
        metric_name = name_part.split("{", 1)[0]

        # 大文字→小文字の統一（metrics.pyは Counter名→小文字に直して出る想定）
        metric_name = metric_name.strip()

        # 主要メトリクスだけ取り込む
        interesting = (
            "bytes_sent_total",
            "bytes_recv_total",
            "rekeys_total",
            "qkd_missing_total",
            "rekey_latency_seconds_sum",
            "rekey_latency_seconds_count",
        )
        if any(metric_name.endswith(x) for x in interesting):
            out[(metric_name, role)] = value

    return out


def _collect() -> Dict[str, Dict[str, float]]:
    """
    サーバ・クライアントの /metrics を集めて 役割別に整理して返す
    戻り値: { role: {metric: value, ...}, ... }
    """
    server = _parse_prom(_fetch(SERVER_METRICS_URL) or "")
    client = _parse_prom(_fetch(CLIENT_METRICS_URL) or "")

    def fold(src: Dict[Tuple[str, str], float]) -> Dict[str, Dict[str, float]]:
        folded: Dict[str, Dict[str, float]] = {}
        for (name, role), val in src.items():
            role = role or "unknown"
            folded.setdefault(role, {})[name] = val
        return folded

    data: Dict[str, Dict[str, float]] = {}

    # サーバ分
    for role, d in fold(server).items():
        data.setdefault(role, {}).update(d)
    # クライアント分（同じrole="client"のキーがあれば上書き）
    for role, d in fold(client).items():
        data.setdefault(role, {}).update(d)

    # rekey_latency の平均（sum/count）を計算（あれば）
    for role, dv in data.items():
        s = dv.get("rekey_latency_seconds_sum", 0.0)
        c = dv.get("rekey_latency_seconds_count", 0.0)
        if c > 0:
            dv["rekey_latency_seconds_avg"] = s / c
        else:
            dv["rekey_latency_seconds_avg"] = 0.0

    return data


def _collector_loop():
    global _latest, _latest_ts
    while True:
        snap = _collect()
        with _lock:
            _latest = snap
            _latest_ts = time.time()
        time.sleep(REFRESH_INTERVAL_SEC)


# ===== Flask ルート =====
@app.route("/")
def index() -> Response:
    # 依存ライブラリなしの素朴な折れ線描画
    html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>QKD×QUIC Monitoring (no Docker)</title>
<style>
body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans JP", sans-serif; margin: 20px; }}
h1 {{ margin: 0 0 12px; }}
.card {{ border: 1px solid #ddd; border-radius: 10px; padding: 12px; margin: 10px 0; }}
.row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
canvas {{ width: 100%; height: 220px; border: 1px solid #eee; border-radius: 8px; }}
.badge {{ display:inline-block; background:#f2f2f2; padding:2px 8px; border-radius: 999px; font-size: 12px; margin-left:6px; }}
</style>
</head>
<body>
  <h1>QKD×QUIC Monitoring <span class="badge">server:8000 / client:8001</span></h1>

  <div class="row">
    <div class="card">
      <h3>Total Bytes (client)</h3>
      <div class="mono" id="clientVals">sent=0 recv=0 rekeys=0 miss=0 avg_rekey_lat=0</div>
      <canvas id="clientChart"></canvas>
    </div>
    <div class="card">
      <h3>Total Bytes (server)</h3>
      <div class="mono" id="serverVals">sent=0 recv=0 rekeys=0 miss=0 avg_rekey_lat=0</div>
      <canvas id="serverChart"></canvas>
    </div>
  </div>

<script>
const CMAX = 120; // 120点（約2分）を保持
let clientSeries = {{sent:[], recv:[], rekeys:[], miss:[], avg:[]}};
let serverSeries = {{sent:[], recv:[], rekeys:[], miss:[], avg:[]}};

function draw(canvas, series, color="#0b84f3", color2="#34a853") {{
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0,0,w,h);
  // 軸
  ctx.strokeStyle = "#eaeaea";
  ctx.beginPath(); ctx.moveTo(40,10); ctx.lineTo(40,h-20); ctx.lineTo(w-10,h-20); ctx.stroke();

  function plot(arr, col, yScale) {{
    if (arr.length < 2) return;
    const maxV = Math.max(1, ...arr);
    const scale = (h-40) / (yScale? yScale : maxV);
    ctx.strokeStyle = col;
    ctx.beginPath();
    for (let i=0;i<arr.length;i++) {{
      const x = 40 + (w-60) * (i/(CMAX-1));
      const y = (h-20) - arr[i]*scale;
      if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }}
    ctx.stroke();
  }}

  plot(series.sent, color);
  plot(series.recv, color2);
}}

function pushSeries(series, data) {{
  series.sent.push(data.sent || 0);
  series.recv.push(data.recv || 0);
  series.rekeys.push(data.rekeys || 0);
  series.miss.push(data.miss || 0);
  series.avg.push(data.avg || 0);
  for (const k of Object.keys(series)) {{
    if (series[k].length > CMAX) series[k].shift();
  }}
}}

async function tick() {{
  try {{
    const res = await fetch('/api/snapshot');
    const js = await res.json();
    const cli = js.client || {{}};
    const svr = js.server || {{}};  // role="server" 側

    document.getElementById('clientVals').textContent =
      `sent=${{cli.bytes_sent_total||0}} recv=${{cli.bytes_recv_total||0}} rekeys=${{cli.rekeys_total||0}} miss=${{cli.qkd_missing_total||0}} avg_rekey_lat=${{(cli.rekey_latency_seconds_avg||0).toFixed(4)}}`;
    document.getElementById('serverVals').textContent =
      `sent=${{svr.bytes_sent_total||0}} recv=${{svr.bytes_recv_total||0}} rekeys=${{svr.rekeys_total||0}} miss=${{svr.qkd_missing_total||0}} avg_rekey_lat=${{(svr.rekey_latency_seconds_avg||0).toFixed(4)}}`;

    pushSeries(clientSeries, {{
      sent: cli.bytes_sent_total, recv: cli.bytes_recv_total,
      rekeys: cli.rekeys_total, miss: cli.qkd_missing_total, avg: cli.rekey_latency_seconds_avg
    }});
    pushSeries(serverSeries, {{
      sent: svr.bytes_sent_total, recv: svr.bytes_recv_total,
      rekeys: svr.rekeys_total, miss: svr.qkd_missing_total, avg: svr.rekey_latency_seconds_avg
    }});

    draw(document.getElementById('clientChart'), clientSeries);
    draw(document.getElementById('serverChart'), serverSeries, "#ff6d00", "#9c27b0");
  }} catch (e) {{
    // 失敗しても黙って次へ
  }}
}}

setInterval(tick, {int(REFRESH_INTERVAL_SEC*1000)});
tick(); // 初回
</script>
</body>
</html>
    """
    return Response(html, mimetype="text/html")


@app.route("/api/snapshot")
def api_snapshot():
    with _lock:
        return jsonify({"ts": _latest_ts, **_latest})


def main():
    # バックグラウンドで収集ループを回す
    th = threading.Thread(target=_collector_loop, daemon=True)
    th.start()
    app.run(host="127.0.0.1", port=DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    main()

