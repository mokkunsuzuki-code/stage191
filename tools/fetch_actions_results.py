#!/usr/bin/env python3
# MIT License © 2025 Motohiro Suzuki

"""
Fetch GitHub Actions run + jobs evidence and write:

- out/ci/actions_runs.json
- out/ci/actions_jobs.json

Modes:
1) --run-id <id>                (A-plan: pin THIS run as evidence)
2) --branch <name> --pick ...   (fallback mode if you want)
   pick: latest_completed | latest_success
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


API = "https://api.github.com"


def _die(msg: str) -> None:
    raise SystemExit(f"[FAIL] {msg}")


def _token() -> str:
    t = os.environ.get("GITHUB_TOKEN")
    if not t:
        _die("GITHUB_TOKEN is not set")
    return t


def _headers() -> Dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {_token()}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    if r.status_code >= 400:
        _die(f"GET {url} failed: {r.status_code} {r.text[:200]}")
    return r.json()


def _ensure_outdir() -> Path:
    out_dir = Path("out/ci")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


@dataclass
class Config:
    repo: str
    run_id: Optional[int]
    branch: Optional[str]
    pick: Optional[str]


def _parse_args() -> Config:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--run-id", type=int, default=None, help="pin a specific run id (A-plan)")
    p.add_argument("--branch", default=None, help="branch name for list mode")
    p.add_argument("--pick", default=None, choices=["latest_completed", "latest_success"])

    a = p.parse_args()

    if a.run_id is None:
        # list mode requires branch+pick
        if not a.branch or not a.pick:
            _die("Either --run-id OR (--branch AND --pick) must be provided")

    return Config(repo=a.repo, run_id=a.run_id, branch=a.branch, pick=a.pick)


def _fetch_run(repo: str, run_id: int) -> Dict[str, Any]:
    return _get(f"{API}/repos/{repo}/actions/runs/{run_id}")


def _fetch_jobs(repo: str, run_id: int) -> Dict[str, Any]:
    # paginate jobs (per_page max 100)
    all_jobs: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = _get(
            f"{API}/repos/{repo}/actions/runs/{run_id}/jobs",
            params={"per_page": 100, "page": page},
        )
        jobs = data.get("jobs", [])
        all_jobs.extend(jobs)
        # GitHub returns total_count; if we got less than 100, it's done
        if len(jobs) < 100:
            return {"total_count": len(all_jobs), "jobs": all_jobs}
        page += 1


def _list_runs(repo: str, branch: str) -> List[Dict[str, Any]]:
    # list workflow runs for the repo/branch (not limited to a workflow file)
    data = _get(
        f"{API}/repos/{repo}/actions/runs",
        params={"branch": branch, "per_page": 50},
    )
    return data.get("workflow_runs", [])


def _choose_run(runs: List[Dict[str, Any]], pick: str) -> Tuple[int, Dict[str, Any]]:
    if not runs:
        _die("no workflow runs found")

    if pick == "latest_completed":
        for r in runs:
            if r.get("status") == "completed":
                return int(r["id"]), r
        _die("no completed run found")

    if pick == "latest_success":
        for r in runs:
            if r.get("status") == "completed" and r.get("conclusion") == "success":
                return int(r["id"]), r
        _die("no completed success run found")

    _die(f"unknown pick: {pick}")
    raise AssertionError  # unreachable


def _normalize_jobs(jobs_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for j in jobs_data.get("jobs", []):
        out.append(
            {
                "id": j.get("id"),
                "name": j.get("name"),
                "status": j.get("status"),
                "conclusion": j.get("conclusion"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
                "html_url": j.get("html_url"),
            }
        )
    return out


def main() -> None:
    cfg = _parse_args()
    out_dir = _ensure_outdir()

    if cfg.run_id is not None:
        run_id = int(cfg.run_id)
        chosen = _fetch_run(cfg.repo, run_id)
        runs_list = [chosen]
    else:
        runs_list = _list_runs(cfg.repo, cfg.branch or "")
        run_id, chosen = _choose_run(runs_list, cfg.pick or "")

    jobs_data = _fetch_jobs(cfg.repo, run_id)
    jobs_norm = _normalize_jobs(jobs_data)

    runs_out = out_dir / "actions_runs.json"
    runs_out.write_text(
        json.dumps(
            {
                "repo": cfg.repo,
                "mode": {
                    "run_id": cfg.run_id,
                    "branch": cfg.branch,
                    "pick": cfg.pick,
                    "chosen_run_id": run_id,
                },
                "chosen_run": chosen,
                "workflow_runs": runs_list,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    jobs_out = out_dir / "actions_jobs.json"
    jobs_out.write_text(
        json.dumps(
            {
                "repo": cfg.repo,
                "run_id": run_id,
                "jobs": jobs_norm,
                "raw": jobs_data,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"[OK] wrote: {runs_out}")
    print(f"[OK] wrote: {jobs_out}")
    print(f"[OK] chosen run: id={run_id} status={chosen.get('status')} conclusion={chosen.get('conclusion')}")


if __name__ == "__main__":
    main()
