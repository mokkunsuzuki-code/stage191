#!/usr/bin/env python3
# MIT License © 2025 Motohiro Suzuki

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _die(msg: str) -> None:
    print(f"[GATE FAIL] {msg}", file=sys.stderr)
    raise SystemExit(1)


def _load_json(path: Path) -> Any:
    if not path.exists():
        _die(f"missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _job_map(jobs_json: Any) -> Dict[str, Dict[str, Optional[str]]]:
    if isinstance(jobs_json, dict) and "jobs" in jobs_json:
        jobs = jobs_json["jobs"]
    else:
        jobs = jobs_json

    out = {}
    for j in jobs:
        name = j.get("name")
        out[name] = {
            "status": j.get("status"),
            "conclusion": j.get("conclusion"),
        }
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs-json", default="out/ci/actions_runs.json")
    p.add_argument("--jobs-json", default="out/ci/actions_jobs.json")

    p.add_argument("--require-jobs-all", action="store_true")
    p.add_argument("--allow-in-progress-job", action="append", default=[])

    args = p.parse_args()

    jobs = _load_json(Path(args.jobs_json))
    job_map = _job_map(jobs)

    for name, info in job_map.items():
        status = info.get("status")
        conclusion = info.get("conclusion")

        # allow current running job
        if name in args.allow_in_progress_job and status == "in_progress":
            continue

        if conclusion != "success":
            _die(f"{name} not success: status={status} conclusion={conclusion}")

    print("[GATE OK] all jobs acceptable")


if __name__ == "__main__":
    main()
