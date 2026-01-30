#!/usr/bin/env bash
# MIT License © 2025 Motohiro Suzuki
set -euo pipefail

cd /app
export PYTHONPATH="/app"
export PYTHONUNBUFFERED=1

mkdir -p out/logs out/evidence out/reports

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OUT="out/logs/attack_01_tamper_sig.json"
SERVER_LOG="out/logs/server167_attack01.log"
CLIENT_LOG="out/logs/client167_attack01.log"

rm -f "$OUT" "$SERVER_LOG" "$CLIENT_LOG"

{
  echo "[attack-01][debug] pwd=$(pwd)"
  echo "[attack-01][debug] python=$(python -V 2>&1 || true)"
  echo "[attack-01][debug] PYTHONPATH=${PYTHONPATH}"
  echo "[attack-01][debug] ls protocol?"; ls -la protocol 2>&1 | head -n 30 || true
  echo "[attack-01][debug] ls runners?";  ls -la runners  2>&1 | head -n 30 || true
} >"$SERVER_LOG"

echo "[attack-01] start server in background..."
( python -u runners/run_server167.py >>"$SERVER_LOG" 2>&1 ) &
SERVER_PID=$!

cleanup() {
  echo "[attack-01] cleanup: stopping server pid=$SERVER_PID" >>"$SERVER_LOG" 2>&1 || true
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 1

echo "[attack-01] run client with tampered ACK confirm (QSP_STAGE167A_FAIL=1)..."
set +e
QSP_STAGE167A_FAIL=1 python -u runners/run_client167.py client >"$CLIENT_LOG" 2>&1
CLIENT_RC=$?
set -e

OBSERVED="UNKNOWN"
OK_JSON="false"

if grep -q "ack confirm mismatch" "$SERVER_LOG"; then
  OBSERVED="FAIL_CLOSED_REKEY_REJECTED"
  OK_JSON="true"
elif grep -q "rekey FAILED" "$SERVER_LOG"; then
  OBSERVED="FAIL_CLOSED_REKEY_FAILED"
  OK_JSON="true"
elif grep -q "timeout" "$CLIENT_LOG"; then
  OBSERVED="FAIL_CLOSED_TIMEOUT"
  OK_JSON="true"
else
  OBSERVED="CLIENT_DID_NOT_TAMPER"
  OK_JSON="false"
fi

cat > "$OUT" <<JSON
{"stage":176,"attack":"attack_01_tamper_sig","ts_utc":"$TS","expected":"FAIL_CLOSED","observed":"$OBSERVED","ok":$OK_JSON,"client_rc":$CLIENT_RC,"artifacts":{"server_log":"$SERVER_LOG","client_log":"$CLIENT_LOG"}}
JSON

echo "[attack-01] wrote $OUT"

bash scripts/05_summarize.sh
bash scripts/04_collect_logs.sh

echo "[OK] attack-01 complete"
