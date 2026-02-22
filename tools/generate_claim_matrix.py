# MIT License © 2025 Motohiro Suzuki
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _job_rows(jobs: Dict[str, Any]) -> list[dict]:
    return list(jobs.get("jobs", []))

def _iso(s: str | None) -> str:
    return s or ""

def build_markdown(runs: Dict[str, Any], jobs: Dict[str, Any]) -> str:
    chosen = runs.get("chosen_run", {}) or {}
    repo = runs.get("repo", "")
    run_id = runs.get("chosen_run_id", "")
    run_name = chosen.get("name") or chosen.get("workflow_id") or "workflow"
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}"

    lines = [
        "# claim_matrix (dynamic)",
        "",
        "> Generated from GitHub Actions API results (Stage191).",
        "",
        "## Target run",
        "",
        f"- Repo: `{repo}`",
        f"- Run: [{run_name}]({run_url})",
        f"- Run ID: `{run_id}`",
        f"- Status: `{chosen.get('status')}`  Conclusion: `{chosen.get('conclusion')}`",
        f"- Created: `{chosen.get('created_at')}`  Updated: `{chosen.get('updated_at')}`",
        "",
        "## Evidence table (jobs)",
        "",
        "| Job | Conclusion | Started | Completed | Evidence |",
        "|---|---|---:|---:|---|",
    ]

    for j in _job_rows(jobs):
        name = j.get("name", "")
        conclusion = j.get("conclusion", "")
        started = _iso(j.get("started_at"))
        completed = _iso(j.get("completed_at"))
        job_id = j.get("id", "")
        job_url = f"https://github.com/{repo}/actions/runs/{run_id}/job/{job_id}"
        lines.append(f"| {name} | `{conclusion}` | `{started}` | `{completed}` | [job log]({job_url}) |")

    lines += [
        "",
        "## Reproducibility note",
        "",
        "- Evidence is fetched via REST API with `GITHUB_TOKEN`.",
        "- The matrix is regenerated on each Stage191 run.",
        "",
    ]
    return "\n".join(lines)

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs-json", default="out/ci/actions_runs.json")
    p.add_argument("--jobs-json", default="out/ci/actions_jobs.json")
    p.add_argument("--out", default="out/ci/claim_matrix.md")
    args = p.parse_args()

    runs = _load_json(Path(args.runs_json))
    jobs = _load_json(Path(args.jobs_json))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_markdown(runs, jobs), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")

if __name__ == "__main__":
    main()
