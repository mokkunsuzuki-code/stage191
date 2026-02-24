# MIT License © 2025 Motohiro Suzuki
"""
Fetch GitHub Actions run + jobs JSON and write to out/ci/.

Auth priority:
1) If GITHUB_TOKEN exists → REST API (Bearer)
2) Else → use `gh api` (GitHub CLI)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import requests


API = "https://api.github.com"
OUTDIR = Path("out/ci")


def die(msg: str) -> None:
    raise SystemExit(msg if msg.endswith("\n") else msg + "\n")


# --------------------------
# AUTH
# --------------------------

def gh_headers() -> Dict[str, str]:
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok:
        return {}
    return {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def gh_get(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    headers = gh_headers()

    # ---- Mode 1: REST API ----
    if headers:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code >= 400:
            die(f"[FAIL] GET {url} failed: {r.status_code} {r.text}")
        return r.json()

    # ---- Mode 2: gh CLI fallback ----
    path = url.replace(API, "")
    cmd = ["gh", "api", path]
    if params:
        for k, v in params.items():
            cmd.extend(["-f", f"{k}={v}"])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        die(f"[FAIL] gh api failed: {result.stderr}")

    return json.loads(result.stdout)


# --------------------------
# CORE
# --------------------------

def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def pick_run(repo: str, branch: str) -> Dict[str, Any]:
    url = f"{API}/repos/{repo}/actions/runs"
    data = gh_get(url, {"branch": branch, "per_page": 20})
    runs = data.get("workflow_runs", [])
    if not runs:
        die("[FAIL] no runs found")
    for run in runs:
        if run.get("status") == "completed":
            return run
    return runs[0]


def fetch_jobs(repo: str, run_id: int) -> Dict[str, Any]:
    url = f"{API}/repos/{repo}/actions/runs/{run_id}/jobs"
    return gh_get(url, {"per_page": 100})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    run = pick_run(args.repo, args.branch)
    run_id = run["id"]

    runs_out = OUTDIR / "actions_runs.json"
    write_json(runs_out, {"repo": args.repo, "chosen": run})

    jobs_data = fetch_jobs(args.repo, run_id)
    jobs_out = OUTDIR / "actions_jobs.json"
    write_json(jobs_out, {"repo": args.repo, "run_id": run_id, **jobs_data})

    print(f"[OK] wrote: {runs_out}")
    print(f"[OK] wrote: {jobs_out}")
    print(f"[OK] chosen run: {run_id}")


if __name__ == "__main__":
    main()