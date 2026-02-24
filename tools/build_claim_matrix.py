# MIT License © 2025 Motohiro Suzuki
"""
Stage192: Claim Coverage Matrix (Claim ↔ Job ↔ Evidence)
- Reads: claims/claims.yaml
- Reads: out/ci/actions_jobs.json  (Stage191 output)
- Writes: docs/claim_coverage_matrix.md
- Writes: out/ci/claim_matrix.json
- Optionally updates README.md block (between markers)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml  # type: ignore
except Exception as e:
    raise SystemExit("[ERROR] PyYAML is required. Install: pip install pyyaml") from e


ROOT = Path(__file__).resolve().parents[1]
CLAIMS_YAML = ROOT / "claims" / "claims.yaml"
ACTIONS_JOBS = ROOT / "out" / "ci" / "actions_jobs.json"
OUT_JSON = ROOT / "out" / "ci" / "claim_matrix.json"
OUT_MD = ROOT / "docs" / "claim_coverage_matrix.md"
README = ROOT / "README.md"

BEGIN = "<!-- BEGIN CLAIM COVERAGE MATRIX -->"
END = "<!-- END CLAIM COVERAGE MATRIX -->"


@dataclass
class JobResult:
    name: str
    conclusion: str


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _read_yaml(p: Path) -> Dict[str, Any]:
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _normalize_conclusion(x: Any) -> str:
    if not x:
        return "unknown"
    return str(x).strip().lower()


def _extract_jobs(actions_jobs_json: Dict[str, Any]) -> List[JobResult]:
    jobs: List[JobResult] = []

    if isinstance(actions_jobs_json, dict) and isinstance(actions_jobs_json.get("jobs"), list):
        for j in actions_jobs_json["jobs"]:
            name = str(j.get("name") or j.get("job_name") or j.get("id") or "unknown")
            concl = _normalize_conclusion(j.get("conclusion") or j.get("result") or j.get("status"))
            jobs.append(JobResult(name=name, conclusion=concl))
        return jobs

    raw = actions_jobs_json.get("raw") if isinstance(actions_jobs_json, dict) else None
    if isinstance(raw, dict) and isinstance(raw.get("jobs"), list):
        for j in raw["jobs"]:
            name = str(j.get("name") or j.get("id") or "unknown")
            concl = _normalize_conclusion(j.get("conclusion") or j.get("status"))
            jobs.append(JobResult(name=name, conclusion=concl))
        return jobs

    return jobs


def _job_matches(required_pattern: str, job_name: str) -> bool:
    rp = required_pattern.strip()
    if len(rp) >= 2 and rp.startswith("/") and rp.endswith("/"):
        pat = rp[1:-1]
        return re.search(pat, job_name, flags=re.IGNORECASE) is not None
    return rp.lower() in job_name.lower()


def _job_passed(conclusion: str) -> bool:
    return conclusion in {"success", "passed", "pass", "ok"}


def _file_exists(rel_path: str) -> bool:
    p = (ROOT / rel_path).resolve() if not rel_path.startswith("/") else Path(rel_path)
    return p.exists()


def _render_summary_block(summary_lines: List[str]) -> str:
    return "\n".join([BEGIN, *summary_lines, END])


def _update_readme_block(new_block: str) -> Tuple[bool, str]:
    if not README.exists():
        return False, "[WARN] README.md not found; skipped README update."

    text = README.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        return False, f"[WARN] README.md has no markers. Add:\n{BEGIN}\n...\n{END}\n"

    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), flags=re.DOTALL)
    replaced, n = pattern.subn(new_block, text, count=1)
    if n == 0:
        return False, "[WARN] README marker replacement failed."
    if replaced == text:
        return False, "[OK] README block already up-to-date."
    README.write_text(replaced, encoding="utf-8")
    return True, "[OK] README block updated."


def main() -> None:
    if not CLAIMS_YAML.exists():
        raise SystemExit(f"[ERROR] missing: {CLAIMS_YAML}")
    if not ACTIONS_JOBS.exists():
        raise SystemExit(f"[ERROR] missing: {ACTIONS_JOBS}  (Run Stage191 fetch first)")

    claims_data = _read_yaml(CLAIMS_YAML)
    actions_jobs = _read_json(ACTIONS_JOBS)

    jobs = _extract_jobs(actions_jobs)
    jobs_index = [{"name": j.name, "conclusion": j.conclusion} for j in jobs]

    claims: Dict[str, Any] = claims_data.get("claims", {})
    if not isinstance(claims, dict) or not claims:
        raise SystemExit("[ERROR] claims/claims.yaml has no 'claims' mapping.")

    matrix_rows: List[Dict[str, Any]] = []
    covered_count = 0

    for claim_id, c in claims.items():
        title = str(c.get("title", "")).strip()
        required_jobs: List[str] = list(c.get("required_jobs") or [])
        evidence_paths: List[str] = list(c.get("evidence_paths") or [])

        job_checks: List[Dict[str, Any]] = []
        job_ok = True

        for req in required_jobs:
            matches = [j for j in jobs if _job_matches(str(req), j.name)]
            if not matches:
                job_checks.append({"required": req, "matched": [], "ok": False, "reason": "no matching job"})
                job_ok = False
                continue

            passed = [m for m in matches if _job_passed(m.conclusion)]
            ok = len(passed) > 0
            job_checks.append(
                {
                    "required": req,
                    "matched": [{"name": m.name, "conclusion": m.conclusion} for m in matches],
                    "ok": ok,
                    "reason": "passed" if ok else "matched but not success",
                }
            )
            if not ok:
                job_ok = False

        evidence_checks: List[Dict[str, Any]] = []
        ev_ok = True
        for ev in evidence_paths:
            exists = _file_exists(str(ev))
            evidence_checks.append({"path": ev, "exists": exists})
            if not exists:
                ev_ok = False

        covered = job_ok and ev_ok
        if covered:
            covered_count += 1

        total_checks = len(required_jobs) + len(evidence_paths)
        passed_checks = sum(1 for jc in job_checks if jc["ok"]) + sum(1 for ec in evidence_checks if ec["exists"])
        claim_pct = 100 if total_checks == 0 else int(round(100 * passed_checks / total_checks))

        matrix_rows.append(
            {
                "claim": claim_id,
                "title": title,
                "required_jobs": required_jobs,
                "job_checks": job_checks,
                "evidence_paths": evidence_paths,
                "evidence_checks": evidence_checks,
                "covered": covered,
                "coverage_pct": claim_pct,
            }
        )

    total_claims = len(matrix_rows)
    overall_pct = 0 if total_claims == 0 else int(round(100 * covered_count / total_claims))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    out_obj = {
        "stage": 192,
        "inputs": {
            "claims_yaml": str(CLAIMS_YAML.relative_to(ROOT)),
            "actions_jobs": str(ACTIONS_JOBS.relative_to(ROOT)),
        },
        "jobs": jobs_index,
        "claims_total": total_claims,
        "claims_covered": covered_count,
        "coverage_pct": overall_pct,
        "matrix": matrix_rows,
    }
    OUT_JSON.write_text(json.dumps(out_obj, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage192: Claim Coverage Matrix")
    lines.append("")
    lines.append(f"- Claims covered: **{covered_count} / {total_claims}**")
    lines.append(f"- Coverage: **{overall_pct}%**")
    lines.append("")
    lines.append("## Coverage Summary")
    lines.append("")
    lines.append("| Claim | Covered | Coverage% | Required Jobs | Missing Evidence |")
    lines.append("|---|---:|---:|---|---|")

    for row in matrix_rows:
        claim = row["claim"]
        covered = "✅" if row["covered"] else "❌"
        pct = row["coverage_pct"]
        req_jobs = ", ".join(row["required_jobs"]) if row["required_jobs"] else "-"
        missing_ev = [ec["path"] for ec in row["evidence_checks"] if not ec["exists"]]
        missing_ev_s = ", ".join(missing_ev) if missing_ev else "-"
        lines.append(f"| {claim} | {covered} | {pct}% | {req_jobs} | {missing_ev_s} |")

    lines.append("")
    lines.append("## Claim ↔ Job ↔ Evidence (Details)")
    lines.append("")

    for row in matrix_rows:
        lines.append(f"### {row['claim']} — {row['title']}".rstrip())
        lines.append("")
        lines.append(f"- Covered: **{'YES' if row['covered'] else 'NO'}**")
        lines.append(f"- Coverage%: **{row['coverage_pct']}%**")
        lines.append("")
        lines.append("**Jobs**")
        if not row["job_checks"]:
            lines.append("- (no required jobs)")
        else:
            for jc in row["job_checks"]:
                ok = "✅" if jc["ok"] else "❌"
                lines.append(f"- {ok} required: `{jc['required']}` — {jc['reason']}")
                if jc["matched"]:
                    for m in jc["matched"]:
                        lines.append(f"  - matched: `{m['name']}` (conclusion: `{m['conclusion']}`)")
        lines.append("")
        lines.append("**Evidence**")
        if not row["evidence_checks"]:
            lines.append("- (no required evidence)")
        else:
            for ec in row["evidence_checks"]:
                ok = "✅" if ec["exists"] else "❌"
                lines.append(f"- {ok} `{ec['path']}`")
        lines.append("")

    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    summary_lines: List[str] = []
    summary_lines.append("")
    summary_lines.append("## Claim Coverage (auto)")
    summary_lines.append("")
    summary_lines.append(f"- **Coverage:** {overall_pct}% ({covered_count}/{total_claims})")
    summary_lines.append("- **Matrix:** `docs/claim_coverage_matrix.md`")
    summary_lines.append("")

    new_block = _render_summary_block(summary_lines)
    updated, msg = _update_readme_block(new_block)

    print(f"[OK] wrote: {OUT_JSON.relative_to(ROOT)}")
    print(f"[OK] wrote: {OUT_MD.relative_to(ROOT)}")
    print(msg)
    if updated:
        print("[NOTE] README.md changed. Commit it.")


if __name__ == "__main__":
    main()
