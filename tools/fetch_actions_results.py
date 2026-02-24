# MIT License © 2025 Motohiro Suzuki
"""
Fetch GitHub Actions run + jobs JSON and write to out/ci/.

Supports:
  --repo owner/repo
  --run-id <id>        (CIから渡される)
  --branch main        (run-id未指定時に使用)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

API_PREFIX = "repos"
OUTDIR = Path("out/ci")


def die(msg: str) -> None:
    raise SystemExit(msg if msg.endswith("\n") else msg + "\n")


def gh_api(path: str) -> Any:
    """Use gh CLI (assumes gh auth login済み)"""
    cmd = ["gh", "api", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"[FAIL] gh api failed: {r.stderr}")
    return json.loads(r.stdout)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--run-id")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    repo = args.repo

    # -----------------------------
    # run_id 決定
    # -----------------------------
    if args.run_id:
        run_id = args.run_id
        run_data = gh_api(f"{API_PREFIX}/{repo}/actions/runs/{run_id}")
    else:
        data = gh_api(f"{API_PREFIX}/{repo}/actions/runs?per_page=1")
        runs = data.get("workflow_runs", [])
        if not runs:
            die("[FAIL] no runs found")
        run_data = runs[0]
        run_id = run_data["id"]

    # 保存（run情報）
    write_json(OUTDIR / "actions_runs.json", {
        "repo": repo,
        "chosen": run_data
    })

    # -----------------------------
    # jobs 取得
    # -----------------------------
    jobs_data = gh_api(f"{API_PREFIX}/{repo}/actions/runs/{run_id}/jobs?per_page=100")

    write_json(OUTDIR / "actions_jobs.json", {
        "repo": repo,
        "run_id": run_id,
        **jobs_data
    })

    print(f"[OK] wrote: out/ci/actions_runs.json")
    print(f"[OK] wrote: out/ci/actions_jobs.json")
    print(f"[OK] chosen run: {run_id}")


if __name__ == "__main__":
    main()