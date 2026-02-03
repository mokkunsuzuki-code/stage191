#!/usr/bin/env bash
set -euo pipefail

PYTHONPATH=. python -u attack_scenarios/attack_04_appdata_before_handshake/runner.py
