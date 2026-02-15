#!/usr/bin/env bash
set -euo pipefail

PYTHONPATH=. python -u attack_scenarios/attack_02_rekey_race/runner.py
