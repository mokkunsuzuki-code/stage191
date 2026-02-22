# MIT License © 2025 Motohiro Suzuki
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

def _die(msg: str, code: int = 2) -> None:
    print(f"[GATE FAIL] {msg}", file=sys.stderr)
    raise SystemExit(code)

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        _die(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def _job_map(jobs: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for j in jobs.get("jobs", []):
        name = j.get("name", "")
        concl = j.get("conclusion", "") or ""
        out[name] = concl
    return out

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs-json", default="out/ci/actions_runs.json")
    p.add_argument("--jobs-json", default="out/ci/actions_jobs.json")
    p.add_argument("--require-run-success", action="store_true")
    p.add_argument("--require-job", action="append", default=[])
    p.add_argument("--allow-skipped", action="store_true")
    args = p.parse_args()

    runs = _load_json(Path(args.runs_json))
    jobs = _load_json(Path(args.jobs_json))

    chosen = runs.get("chosen_run", {}) or {}
    run_concl = chosen.get("conclusion")
    if args.require_run_success:
        if run_concl != "success":
            _die(f"Run conclusion not success: {run_concl}")
        job_map = _job_map(jobs)
        bad = []
        for name, st in job_map.items():
            if st == "success":
                continue
            if args.allow_skipped and st == "skipped":
                continue
            bad.append(f"{name}={st}")
        if bad:
            _die("Some jobs are not success: " + ", ".join(bad))
        print("[GATE OK] all jobs success")
        return

    job_map = _job_map(jobs)
    for req in args.require_job:
        if req not in job_map:
            _die(f"Required job not found: {req}")
        st = job_map[req]
        if st == "success":
            continue
        if args.allow_skipped and st == "skipped":
            continue
        _die(f"Required job not success: {req}={st}")

    print("[GATE OK] required jobs satisfied")

if __name__ == "__main__":
    main()
