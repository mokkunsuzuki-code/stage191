#!/usr/bin/env bash
set -euo pipefail

PYTHONPATH=. python -u attack_scenarios/attack_05_rekey_reuse/runner.py
