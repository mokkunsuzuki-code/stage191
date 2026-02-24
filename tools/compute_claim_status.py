# MIT License © 2025 Motohiro Suzuki
"""
Compute claim_status from GitHub Actions job results.

Inputs:
  - claims/claims.yaml (or claims/claims.yml)
  - out/ci/actions_jobs.json  (produced by tools/fetch_actions_results.py)

Outputs:
  - out/ci/claim_status.json
  - out/ci/claim_status.md  (human-readable summary)

Fail-closed policy:
  - Missing job result => FAIL
  - Non-success conclusion => FAIL
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
OUT_CI_DIR = ROOT / "out" / "ci"
CLAIMS_DIR = ROOT / "claims"


@dataclass
class Claim:
    key: str
    title: str
    required_jobs: List[str]


def die(msg: str, code: int = 1) -> None:
    print(f"[ERR] {msg}", file=sys.stderr)
    sys.exit(code)


def load_claims_yaml() -> Dict[str, Any]:
    if yaml is None:
        die("PyYAML is not installed. Please run: pip install pyyaml")

    candidates = [
        CLAIMS_DIR / "claims.yaml",
        CLAIMS_DIR / "claims.yml",
        ROOT / "claims.yaml",
        ROOT / "claims.yml",
    ]
    for p in candidates:
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                die(f"claims file must be a YAML mapping: {p}")
            return data

    die("claims file not found. Expected claims/claims.yaml (or .yml).")


def normalize_job_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


def index_jobs(actions_jobs_json: Path) -> Dict[str, Dict[str, Any]]:
    if not actions_jobs_json.exists():
        die(f"missing input: {actions_jobs_json}")

    payload = json.loads(actions_jobs_json.read_text(encoding="utf-8"))
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        die("actions_jobs.json must contain a top-level key 'jobs' as a list")

    idx: Dict[str, Dict[str, Any]] = {}
    for j in jobs:
        if not isinstance(j, dict):
            continue
        name = j.get("name") or j.get("job_name") or j.get("id")
        if not isinstance(name, str) or not name.strip():
            continue
        idx[normalize_job_name(name)] = j
    return idx


def parse_claims(data: Dict[str, Any]) -> List[Claim]:
    claims_block = data.get("claims")
    if isinstance(claims_block, dict):
        data = claims_block

    claims: List[Claim] = []
    for key, v in data.items():
        if not isinstance(key, str):
            continue
        if not isinstance(v, dict):
            continue

        title = v.get("title") if isinstance(v.get("title"), str) else ""
        req = v.get("required_jobs")

        if req is None:
            req_list: List[str] = []
        elif isinstance(req, list):
            req_list = [str(x) for x in req if str(x).strip()]
        else:
            req_list = [str(req)] if str(req).strip() else []

        claims.append(Claim(key=key.strip(), title=title.strip(), required_jobs=req_list))

    if not claims:
        die("no claims found in claims.yaml")
    return claims


def job_conclusion(job: Dict[str, Any]) -> str:
    conc = job.get("conclusion")
    if isinstance(conc, str) and conc.strip():
        return conc.strip().lower()
    status = job.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip().lower()
    return "unknown"


def compute_status(claims: List[Claim], jobs_idx: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"claims": {}, "summary": {}}
    pass_count = 0
    fail_count = 0

    for c in claims:
        details: Dict[str, Any] = {
            "title": c.title,
            "required_jobs": c.required_jobs,
            "jobs": [],
            "status": "FAIL",
            "reason": "",
        }

        if not c.required_jobs:
            details["reason"] = "missing required_jobs (fail-closed)"
            fail_count += 1
            result["claims"][c.key] = details
            continue

        all_ok = True
        missing: List[str] = []
        non_success: List[Dict[str, str]] = []

        for req in c.required_jobs:
            key = normalize_job_name(req)
            job = jobs_idx.get(key)
            if job is None:
                all_ok = False
                missing.append(req)
                details["jobs"].append({"required": req, "found": False, "conclusion": "missing"})
                continue

            conc = job_conclusion(job)
            ok = conc in ("success", "passed")
            if not ok:
                all_ok = False
                non_success.append({"job": req, "conclusion": conc})
            details["jobs"].append({"required": req, "found": True, "conclusion": conc})

        if all_ok:
            details["status"] = "PASS"
            details["reason"] = "all required jobs success"
            pass_count += 1
        else:
            details["status"] = "FAIL"
            reasons = []
            if missing:
                reasons.append(f"missing_jobs={missing}")
            if non_success:
                reasons.append(f"non_success={non_success}")
            if not reasons:
                reasons.append("unknown failure")
            details["reason"] = "; ".join(reasons)
            fail_count += 1

        result["claims"][c.key] = details

    total = pass_count + fail_count
    result["summary"] = {
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "overall": "PASS" if fail_count == 0 else "FAIL",
    }
    return result


def write_outputs(payload: Dict[str, Any]) -> None:
    OUT_CI_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_CI_DIR / "claim_status.json"
    out_md = OUT_CI_DIR / "claim_status.md"

    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    s = payload.get("summary", {})
    lines: List[str] = []
    lines.append("# Claim Status (Stage191)\n")
    lines.append(f"- overall: **{s.get('overall', 'UNKNOWN')}**")
    lines.append(f"- pass: **{s.get('pass', 0)}** / total: **{s.get('total', 0)}**\n")

    lines.append("## Claims\n")
    claims = payload.get("claims", {})
    for k in sorted(claims.keys()):
        c = claims[k]
        status = c.get("status", "UNKNOWN")
        title = c.get("title", "")
        reason = c.get("reason", "")
        lines.append(f"### {k} {title}".rstrip())
        lines.append(f"- status: **{status}**")
        if reason:
            lines.append(f"- reason: `{reason}`")
        jobs = c.get("jobs", [])
        if isinstance(jobs, list) and jobs:
            lines.append("- jobs:")
            for j in jobs:
                if not isinstance(j, dict):
                    continue
                req = j.get("required", "")
                found = j.get("found", False)
                conc = j.get("conclusion", "")
                lines.append(f"  - {req}: found={found}, conclusion={conc}")
        lines.append("")

    out_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    print(f"[OK] wrote: {out_json}")
    print(f"[OK] wrote: {out_md}")
    print(f"[OK] overall: {s.get('overall', 'UNKNOWN')}")


def main() -> None:
    claims_yaml = load_claims_yaml()
    claims = parse_claims(claims_yaml)

    jobs_json = OUT_CI_DIR / "actions_jobs.json"
    jobs_idx = index_jobs(jobs_json)

    payload = compute_status(claims, jobs_idx)
    write_outputs(payload)


if __name__ == "__main__":
    main()
