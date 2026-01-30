#!/usr/bin/env bash
# MIT License © 2025 Motohiro Suzuki
set -euo pipefail

mkdir -p out/logs out/reports out/evidence

run_step() {
  local name="$1"; shift
  echo "[matrix] ${name}"
  if "$@"; then
    echo "[matrix] [OK] ${name}"
    return 0
  else
    local rc=$?
    echo "[matrix] [NG] ${name} rc=${rc}"
    return "${rc}"
  fi
}

run_pytest_soft() {
  set +e
  pytest -q
  local rc=$?
  set -e
  if [[ "${rc}" -eq 0 ]]; then
    echo "[pytest] ok"
    return 0
  fi
  if [[ "${rc}" -eq 5 ]]; then
    echo "[pytest] no tests collected -> treat as OK"
    return 0
  fi
  echo "[pytest] failed rc=${rc}"
  return "${rc}"
}

FINAL_RC=0

# demo: 既存の Stage167 demo runner をそのまま呼ぶ（これが以前のログ形式）
run_step "demo" python -u protocol/stage167_demo_runner.py || FINAL_RC=1

run_step "attack-01" bash attack_scenarios/attack_01_tamper_sig/run.sh || FINAL_RC=1
run_step "attack-02" bash attack_scenarios/attack_02_replay_ack/run.sh || FINAL_RC=1
run_step "attack-03" bash attack_scenarios/attack_03_epoch_rollback/run.sh || FINAL_RC=1
run_step "attack-04" bash attack_scenarios/attack_04_wrong_session_id/run.sh || FINAL_RC=1
run_step "attack-05" bash attack_scenarios/attack_05_key_schedule_confusion/run.sh || FINAL_RC=1
run_step "attack-06" bash attack_scenarios/attack_06_phase_confusion/run.sh || FINAL_RC=1

run_step "pytest" run_pytest_soft || FINAL_RC=1
run_step "summarize" bash scripts/05_summarize.sh || FINAL_RC=1

echo "[matrix] DONE"
if [[ "${FINAL_RC}" -eq 0 ]]; then
  echo "[matrix] FINAL = PASS"
else
  echo "[matrix] FINAL = FAIL (one or more steps failed)"
fi

exit "${FINAL_RC}"
