#!/usr/bin/env bash
# MIT License © 2025 Motohiro Suzuki
set -euo pipefail

OUT_MD="out/reports/summary.md"
mkdir -p "out/reports"

now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

git_commit_short() {
  if [[ -n "${GIT_COMMIT:-}" ]]; then
    echo "${GIT_COMMIT}"
    return
  fi
  if command -v git >/dev/null 2>&1; then
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      git rev-parse --short HEAD 2>/dev/null || echo "N/A"
      return
    fi
  fi
  echo "N/A"
}

json_ok() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo ""
    return
  fi
  python - "$f" <<'PY'
import json, sys
p = sys.argv[1]
try:
  with open(p, "r", encoding="utf-8") as fh:
    obj = json.load(fh)
  v = obj.get("ok", None)
  if v is True: print("true")
  elif v is False: print("false")
  else: print("")
except Exception:
  print("")
PY
}

status_from_json_ok() {
  local ok="$1"
  if [[ "$ok" == "true" ]]; then
    echo "PASS"
  elif [[ "$ok" == "false" ]]; then
    echo "FAIL"
  else
    echo "N/A"
  fi
}

preview_json() {
  local f="$1"
  if [[ -f "$f" ]]; then
    head -c 600 "$f"
    echo
  else
    echo "_(report not found)_"
  fi
}

evidence_grep_first() {
  local file="$1"
  local pattern="$2"
  if [[ ! -f "$file" ]]; then
    echo "N/A"
    return
  fi
  local hit
  hit="$(grep -n "$pattern" "$file" | head -n 1 || true)"
  if [[ -n "$hit" ]]; then
    echo "${file}:${hit}"
  else
    echo "N/A"
  fi
}

# ---- locate artifacts ----
DEMO_JSON="out/evidence/logs/demo.json"
if [[ ! -f "$DEMO_JSON" ]]; then
  DEMO_JSON="out/logs/demo.json"
fi

ATTACK01_JSON="out/logs/attack_01_tamper_sig.json"
ATTACK02_JSON="out/logs/attack_02_replay.json"
ATTACK03_JSON="out/logs/attack_03_epoch_rollback.json"
ATTACK04_JSON="out/logs/attack_04_wrong_session_id.json"
ATTACK05_JSON="out/logs/attack_05_key_schedule_confusion.json"
ATTACK06_JSON="out/logs/attack_06_phase_confusion.json"

DEMO_SERVER_LOG="out/logs/server167.log"
ATTACK01_SERVER_LOG="out/logs/server167_attack01.log"
ATTACK02_SERVER_LOG="out/logs/server167_attack02.log"
ATTACK03_SERVER_LOG="out/logs/server167_attack03.log"
ATTACK04_SERVER_LOG="out/logs/server167_attack04.log"
ATTACK05_SERVER_LOG="out/logs/server167_attack05.log"
ATTACK06_SERVER_LOG="out/logs/server167_attack06.log"

demo_ok="$(json_ok "$DEMO_JSON")"
attack01_ok="$(json_ok "$ATTACK01_JSON")"
attack02_ok="$(json_ok "$ATTACK02_JSON")"
attack03_ok="$(json_ok "$ATTACK03_JSON")"
attack04_ok="$(json_ok "$ATTACK04_JSON")"
attack05_ok="$(json_ok "$ATTACK05_JSON")"
attack06_ok="$(json_ok "$ATTACK06_JSON")"

demo_status="$(status_from_json_ok "$demo_ok")"
attack01_status="$(status_from_json_ok "$attack01_ok")"
attack02_status="$(status_from_json_ok "$attack02_ok")"
attack03_status="$(status_from_json_ok "$attack03_ok")"
attack04_status="$(status_from_json_ok "$attack04_ok")"
attack05_status="$(status_from_json_ok "$attack05_ok")"
attack06_status="$(status_from_json_ok "$attack06_ok")"

demo_evidence="$(evidence_grep_first "$DEMO_SERVER_LOG" "handshake OK")"
attack01_evidence="$(evidence_grep_first "$ATTACK01_SERVER_LOG" "ack confirm mismatch")"
attack02_evidence="$(evidence_grep_first "$ATTACK02_SERVER_LOG" "REPLAY DETECTED")"
attack03_evidence="$(evidence_grep_first "$ATTACK03_SERVER_LOG" "EPOCH ROLLBACK DETECTED")"
attack04_evidence="$(evidence_grep_first "$ATTACK04_SERVER_LOG" "WRONG SESSION_ID")"
attack05_evidence="$(evidence_grep_first "$ATTACK05_SERVER_LOG" "BAD REKEY ACK HEADER")"
attack06_evidence="$(evidence_grep_first "$ATTACK06_SERVER_LOG" "PHASE CONFUSION DETECTED")"

{
  echo "# QSP Report Summary"
  echo
  echo "- Generated: \`$(now_utc)\`"
  echo "- Git commit: \`$(git_commit_short)\`"
  echo
  echo "This page provides a **single-glance PASS/FAIL overview** for both **Demo** and **Attack scenarios**."
  echo
  echo "## Overview"
  echo
  echo "| Item | Status | Report | Evidence |"
  echo "|---|---:|---|---|"
  echo "| Demo | **${demo_status}** | \`${DEMO_JSON:-N/A}\` | \`${demo_evidence}\` |"
  echo "| Attack-01 | **${attack01_status}** | \`${ATTACK01_JSON}\` | \`${attack01_evidence}\` |"
  echo "| Attack-02 | **${attack02_status}** | \`${ATTACK02_JSON}\` | \`${attack02_evidence}\` |"
  echo "| Attack-03 | **${attack03_status}** | \`${ATTACK03_JSON}\` | \`${attack03_evidence}\` |"
  echo "| Attack-04 | **${attack04_status}** | \`${ATTACK04_JSON}\` | \`${attack04_evidence}\` |"
  echo "| Attack-05 | **${attack05_status}** | \`${ATTACK05_JSON}\` | \`${attack05_evidence}\` |"
  echo "| Attack-06 | **${attack06_status}** | \`${ATTACK06_JSON}\` | \`${attack06_evidence}\` |"
  echo
  echo "## Demo"
  echo
  echo "- Status: **${demo_status}**"
  echo "- Report: \`${DEMO_JSON:-N/A}\`"
  echo "- Evidence: \`${demo_evidence}\`"
  echo
  echo "### Preview"
  echo '```'
  preview_json "${DEMO_JSON:-}"
  echo '```'
  echo
  echo "## Attack-01"
  echo
  echo "- Status: **${attack01_status}**"
  echo "- Report: \`${ATTACK01_JSON}\`"
  echo "- Evidence: \`${attack01_evidence}\`"
  echo
  echo "### Preview"
  echo '```'
  preview_json "${ATTACK01_JSON}"
  echo '```'
  echo
  echo "## Attack-02"
  echo
  echo "- Status: **${attack02_status}**"
  echo "- Report: \`${ATTACK02_JSON}\`"
  echo "- Evidence: \`${attack02_evidence}\`"
  echo
  echo "### Preview"
  echo '```'
  preview_json "${ATTACK02_JSON}"
  echo '```'
  echo
  echo "## Attack-03"
  echo
  echo "- Status: **${attack03_status}**"
  echo "- Report: \`${ATTACK03_JSON}\`"
  echo "- Evidence: \`${attack03_evidence}\`"
  echo
  echo "### Preview"
  echo '```'
  preview_json "${ATTACK03_JSON}"
  echo '```'
  echo
  echo "## Attack-04"
  echo
  echo "- Status: **${attack04_status}**"
  echo "- Report: \`${ATTACK04_JSON}\`"
  echo "- Evidence: \`${attack04_evidence}\`"
  echo
  echo "### Preview"
  echo '```'
  preview_json "${ATTACK04_JSON}"
  echo '```'
  echo
  echo "## Attack-05"
  echo
  echo "- Status: **${attack05_status}**"
  echo "- Report: \`${ATTACK05_JSON}\`"
  echo "- Evidence: \`${attack05_evidence}\`"
  echo
  echo "### Preview"
  echo '```'
  preview_json "${ATTACK05_JSON}"
  echo '```'
  echo
  echo "## Attack-06"
  echo
  echo "- Status: **${attack06_status}**"
  echo "- Report: \`${ATTACK06_JSON}\`"
  echo "- Evidence: \`${attack06_evidence}\`"
  echo
  echo "### Preview"
  echo '```'
  preview_json "${ATTACK06_JSON}"
  echo '```'
  echo
  echo "---"
  echo
  echo "## Next"
  echo
  echo "- Add more scenarios: **attack-07 (phase confusion: INIT instead of ACK / duplicate COMMIT / out-of-order frames)** etc."
} > "${OUT_MD}"

echo "[OK] wrote ${OUT_MD}"
