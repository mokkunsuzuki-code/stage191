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

FINAL_RC=0

run_step "demo" bash scripts/01_run_demo.sh || FINAL_RC=1
run_step "attack-01" bash attack_scenarios/attack_01_tamper_sig/run.sh || FINAL_RC=1
run_step "attack-02" bash attack_scenarios/attack_02_replay_ack/run.sh || FINAL_RC=1
run_step "attack-03" bash attack_scenarios/attack_03_epoch_rollback/run.sh || FINAL_RC=1
run_step "attack-04" bash attack_scenarios/attack_04_wrong_session_id/run.sh || FINAL_RC=1

# Stage176: Attack-05 (key schedule confusion)
run_step "attack-05" bash attack_scenarios/attack_05_key_schedule_confusion/run.sh || FINAL_RC=1

run_step "pytest" bash scripts/02_run_pytest.sh || FINAL_RC=1
run_step "summarize" bash scripts/05_summarize.sh || FINAL_RC=1

echo "[matrix] DONE"
if [[ "${FINAL_RC}" -eq 0 ]]; then
  echo "[matrix] FINAL = PASS"
else
  echo "[matrix] FINAL = FAIL (one or more steps failed)"
fi

exit "${FINAL_RC}"
