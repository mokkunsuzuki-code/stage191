# MIT License © 2025 Motohiro Suzuki
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"[NG] missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_actions_jobs(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Accepts either:
      - { "repo": "...", "run_id": "...", "jobs": [...], "raw": {...} }
      - or a plain list of job dicts
    Returns (jobs_list, meta)
    """
    data = _load_json(path)
    meta: Dict[str, Any] = {}

    if isinstance(data, dict):
        meta["repo"] = data.get("repo")
        meta["run_id"] = data.get("run_id")
        jobs = data.get("jobs", [])
        if isinstance(jobs, list):
            return jobs, meta
        raw = data.get("raw")
        if isinstance(raw, dict) and isinstance(raw.get("jobs"), list):
            return raw["jobs"], meta
        return [], meta

    if isinstance(data, list):
        return data, meta

    return [], meta


@dataclass
class ClaimSpec:
    cid: str
    title: str
    required_jobs: List[str]
    evidence_paths: List[str]


def load_claims_yaml(path: Path) -> List[ClaimSpec]:
    if not path.exists():
        raise FileNotFoundError(f"[NG] missing: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    claims = data.get("claims", {})
    if not isinstance(claims, dict):
        raise ValueError("[NG] claims.yaml: 'claims' must be a mapping")

    specs: List[ClaimSpec] = []
    for cid, obj in claims.items():
        if not isinstance(obj, dict):
            continue
        title = str(obj.get("title", "")).strip()
        req = obj.get("required_jobs", []) or []
        ev = obj.get("evidence_paths", []) or []
        if not isinstance(req, list):
            req = []
        if not isinstance(ev, list):
            ev = []
        specs.append(
            ClaimSpec(
                cid=str(cid),
                title=title,
                required_jobs=[str(x) for x in req],
                evidence_paths=[str(x) for x in ev],
            )
        )

    specs.sort(key=lambda s: s.cid)
    return specs


def job_by_name(jobs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    m: Dict[str, Dict[str, Any]] = {}
    for j in jobs:
        if not isinstance(j, dict):
            continue
        name = j.get("name")
        if isinstance(name, str) and name:
            m[name] = j
    return m


def fmt_job_state(j: Optional[Dict[str, Any]]) -> str:
    if j is None:
        return "missing"
    status = j.get("status")
    concl = j.get("conclusion")
    return f"{status}/{concl}"


def write_claim_matrix(
    out_path: Path,
    specs: Optional[List[ClaimSpec]],
    jobs: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    jm = job_by_name(jobs)
    repo = meta.get("repo")
    run_id = meta.get("run_id")

    lines: List[str] = []
    lines.append("# Claim Matrix (CI Evidence)")
    if repo or run_id:
        lines.append("")
        lines.append(f"- repo: `{repo}`" if repo else "- repo: (unknown)")
        lines.append(f"- run_id: `{run_id}`" if run_id else "- run_id: (unknown)")

    lines.append("")
    lines.append("## Jobs snapshot")
    lines.append("")
    lines.append("| job | status/conclusion |")
    lines.append("|---|---|")
    for name in sorted(jm.keys()):
        lines.append(f"| `{name}` | `{fmt_job_state(jm.get(name))}` |")

    if specs:
        lines.append("")
        lines.append("## Claims")
        lines.append("")
        for s in specs:
            lines.append(f"### {s.cid} — {s.title}")
            lines.append("")
            lines.append("| required_job | status/conclusion |")
            lines.append("|---|---|")
            for r in s.required_jobs:
                lines.append(f"| `{r}` | `{fmt_job_state(jm.get(r))}` |")
            if s.evidence_paths:
                lines.append("")
                lines.append("Evidence paths:")
                for p in s.evidence_paths:
                    lines.append(f"- `{p}`")
            lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    # legacy flags (keep)
    ap.add_argument("--runs-json", default="out/ci/actions_runs.json", help="Path to actions_runs.json")
    ap.add_argument("--jobs-json", default="out/ci/actions_jobs.json", help="Path to actions_jobs.json")
    ap.add_argument("--out", default="out/ci/claim_matrix.md", help="Output markdown path")

    # new flags (your workflow uses these)
    ap.add_argument("--claims", default=None, help="Path to claims.yaml (optional)")
    ap.add_argument("--jobs", default=None, help="Alias of --jobs-json (optional)")
    args = ap.parse_args()

    jobs_path = Path(args.jobs if args.jobs else args.jobs_json)
    out_path = Path(args.out)

    jobs, meta = load_actions_jobs(jobs_path)

    specs: Optional[List[ClaimSpec]] = None
    if args.claims:
        specs = load_claims_yaml(Path(args.claims))

    write_claim_matrix(out_path=out_path, specs=specs, jobs=jobs, meta=meta)


if __name__ == "__main__":
    main()
