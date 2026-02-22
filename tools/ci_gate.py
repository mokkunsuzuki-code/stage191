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
    """
    Accepts:
      - {"jobs": [ ... ]}  (our normalized format)
      - {"raw": {...}}    (we ignore raw here)
      - [ ... ]           (direct list)
    """
    if isinstance(jobs_json, dict) and "jobs" in jobs_json:
        jobs = jobs_json["jobs"]
    elif isinstance(jobs_json, dict) and "raw" in jobs_json and isinstance(jobs_json["raw"], dict) and "jobs" in jobs_json["raw"]:
        jobs = jobs_json["raw"]["jobs"]
    else:
        jobs = jobs_json

    out: Dict[str, Dict[str, Optional[str]]] = {}
    if not isinstance(jobs, list):
        _die("jobs-json has no jobs list")

    for j in jobs:
        if not isinstance(j, dict):
            continue
        name = j.get("name") or j.get("job_id") or j.get("id") or "UNKNOWN"
        out[str(name)] = {
            "status": j.get("status"),
            "conclusion": j.get("conclusion"),
        }
    return out


def _is_ok(status: Optional[str], conclusion: Optional[str], allow_in_progress: bool) -> bool:
    if conclusion == "success":
        return True
    if allow_in_progress and status == "in_progress" and conclusion in (None, "neutral"):
        return True
    return False


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--jobs-json", default="out/ci/actions_jobs.json")

    # A-plan: gate by jobs only
    p.add_argument("--require-jobs-all", action="store_true")

    # If set, ANY in_progress job is acceptable (recommended for A-plan)
    p.add_argument("--allow-any-in-progress", action="store_true")

    # If not using allow-any, allow these job names to be in_progress
    p.add_argument("--allow-in-progress-job", action="append", default=[])

    args = p.parse_args()

    jobs = _load_json(Path(args.jobs_json))
    job_map = _job_map(jobs)

    if not job_map:
        _die("no jobs found in jobs-json")

    if args.require_jobs_all:
        bad = []
        for name, info in job_map.items():
            st = info.get("status")
            concl = info.get("conclusion")

            allow_ip = args.allow_any_in_progress or (name in set(args.allow_in_progress_job))

            if _is_ok(st, concl, allow_ip):
                continue
            bad.append(f"{name}=status:{st} conclusion:{concl}")

        if bad:
            _die("Some jobs are not acceptable: " + ", ".join(bad))
        print("[GATE OK] all jobs acceptable")
        return

    # If someone calls without --require-jobs-all, fail clearly (avoid silent pass)
    _die("missing required flag: --require-jobs-all")


if __name__ == "__main__":
    main()
