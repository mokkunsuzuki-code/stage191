# MIT License © 2025 Motohiro Suzuki
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.request
import urllib.error

API_BASE = "https://api.github.com"

@dataclass
class FetchConfig:
    repo: str
    branch: str
    workflow: Optional[str]
    event: Optional[str]
    per_page: int
    pick: str
    run_id: Optional[int]
    out_dir: Path
    token_env: str

def _die(msg: str, code: int = 2) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    raise SystemExit(code)

def _get_token(token_env: str) -> str:
    token = os.environ.get(token_env) or os.environ.get("GITHUB_TOKEN")
    if not token:
        _die(f"Missing token env. Set {token_env} or GITHUB_TOKEN.")
    return token.strip()

def _http_get_json(url: str, token: str) -> Dict[str, Any]:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        _die(f"HTTPError {e.code} for {url}\n{body}", 3)
    except urllib.error.URLError as e:
        _die(f"URLError for {url}: {e}", 3)

def _build_runs_url(cfg: FetchConfig) -> str:
    if cfg.workflow:
        return (
            f"{API_BASE}/repos/{cfg.repo}/actions/workflows/{cfg.workflow}/runs"
            f"?branch={cfg.branch}&per_page={cfg.per_page}"
            + (f"&event={cfg.event}" if cfg.event else "")
        )
    return (
        f"{API_BASE}/repos/{cfg.repo}/actions/runs"
        f"?branch={cfg.branch}&per_page={cfg.per_page}"
        + (f"&event={cfg.event}" if cfg.event else "")
    )

def _pick_run(runs: list[Dict[str, Any]], pick: str) -> Dict[str, Any]:
    if not runs:
        _die("No workflow runs found (empty list).", 4)

    def is_completed(r: Dict[str, Any]) -> bool:
        return (r.get("status") == "completed") and (r.get("conclusion") is not None)

    if pick == "latest":
        return runs[0]
    if pick == "latest_completed":
        for r in runs:
            if is_completed(r):
                return r
        _die("No completed runs found.", 4)
    if pick == "latest_success":
        for r in runs:
            if is_completed(r) and (r.get("conclusion") == "success"):
                return r
        _die("No successful completed runs found.", 4)

    _die(f"Unknown --pick value: {pick}", 2)

def _get_jobs(repo: str, run_id: int, token: str) -> Dict[str, Any]:
    all_jobs: list[Dict[str, Any]] = []
    page = 1
    while True:
        url = f"{API_BASE}/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100&page={page}"
        data = _http_get_json(url, token)
        jobs = data.get("jobs", [])
        all_jobs.extend(jobs)
        total_count = int(data.get("total_count", len(all_jobs)))
        if len(all_jobs) >= total_count or not jobs:
            break
        page += 1
        time.sleep(0.2)
    return {"total_count": len(all_jobs), "jobs": all_jobs, "run_id": run_id}

def _get_run(repo: str, run_id: int, token: str) -> Dict[str, Any]:
    url = f"{API_BASE}/repos/{repo}/actions/runs/{run_id}"
    return _http_get_json(url, token)

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--branch", default="main")
    p.add_argument("--workflow", default=None, help="workflow file name (e.g. ci.yml) or workflow id. Optional.")
    p.add_argument("--event", default=None, help="Optional event filter, e.g. push, workflow_dispatch")
    p.add_argument("--per-page", type=int, default=20)
    p.add_argument("--pick", default="latest_completed", choices=["latest", "latest_completed", "latest_success"])
    p.add_argument("--run-id", type=int, default=None, help="If set, fetch this specific run id (overrides --pick).")
    p.add_argument("--out-dir", default="out/ci")
    p.add_argument("--token-env", default="GITHUB_TOKEN")
    args = p.parse_args()

    cfg = FetchConfig(
        repo=args.repo,
        branch=args.branch,
        workflow=args.workflow,
        event=args.event,
        per_page=args.per_page,
        pick=args.pick,
        run_id=args.run_id,
        out_dir=Path(args.out_dir),
        token_env=args.token_env,
    )

    token = _get_token(cfg.token_env)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)

    if cfg.run_id is not None:
        chosen = _get_run(cfg.repo, cfg.run_id, token)
        run_id = int(chosen["id"])
        runs_list = [chosen]
        jobs_data = _get_jobs(cfg.repo, run_id, token)
        runs_out = cfg.out_dir / "actions_runs.json"
        jobs_out = cfg.out_dir / "actions_jobs.json"
        runs_out.write_text(json.dumps({
            "repo": cfg.repo,
            "branch": cfg.branch,
            "workflow": cfg.workflow,
            "event": cfg.event,
            "pick": f"run_id:{run_id}",
            "chosen_run_id": run_id,
            "chosen_run": chosen,
            "workflow_runs": runs_list,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        jobs_out.write_text(json.dumps(jobs_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] wrote: {runs_out}")
        print(f"[OK] wrote: {jobs_out}")
        print(f"[OK] chosen run: id={run_id} status={chosen.get('status')} conclusion={chosen.get('conclusion')}")
        return

    runs_url = _build_runs_url(cfg)
    runs_data = _http_get_json(runs_url, token)
    runs_list = runs_data.get("workflow_runs", [])
    chosen = _pick_run(runs_list, cfg.pick)

    run_id = int(chosen["id"])
    jobs_data = _get_jobs(cfg.repo, run_id, token)

    runs_out = cfg.out_dir / "actions_runs.json"
    jobs_out = cfg.out_dir / "actions_jobs.json"

    runs_out.write_text(json.dumps({
        "repo": cfg.repo,
        "branch": cfg.branch,
        "workflow": cfg.workflow,
        "event": cfg.event,
        "pick": cfg.pick,
        "chosen_run_id": run_id,
        "chosen_run": chosen,
        "workflow_runs": runs_list,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    jobs_out.write_text(json.dumps(jobs_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[OK] wrote: {runs_out}")
    print(f"[OK] wrote: {jobs_out}")
    print(f"[OK] chosen run: id={run_id} status={chosen.get('status')} conclusion={chosen.get('conclusion')}")

if __name__ == "__main__":
    main()
