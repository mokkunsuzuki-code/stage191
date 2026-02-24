# MIT License © 2025 Motohiro Suzuki
"""
Stage192+194: Claim Coverage Matrix (Claim ↔ Job ↔ Evidence) with optional Lemma layer.

YAML formats:

(A) Direct (Stage192):
claims:
  A2:
    title: ...
    required_jobs: [...]
    evidence_paths: [...]

(B) Lemma-extended (Stage194):
lemmas:
  L_replay:
    title: ...
    required_jobs: [...]
    evidence_paths: [...]
claims:
  A2:
    title: ...
    required_lemmas: [L_replay, ...]
    # (optional) direct required_jobs/evidence_paths also allowed

Rules:
- If claim has required_lemmas: covered iff all required lemmas are covered.
- Else: direct evaluation (Stage192 compatible).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
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

JST = timezone(timedelta(hours=9))


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


def _eval_unit(name: str, title: str, required_jobs: List[str], evidence_paths: List[str], jobs: List[JobResult]) -> Dict[str, Any]:
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
    total_checks = len(required_jobs) + len(evidence_paths)
    passed_checks = sum(1 for jc in job_checks if jc["ok"]) + sum(1 for ec in evidence_checks if ec["exists"])
    pct = 100 if total_checks == 0 else int(round(100 * passed_checks / total_checks))

    return {
        "name": name,
        "title": title,
        "required_jobs": required_jobs,
        "job_checks": job_checks,
        "evidence_paths": evidence_paths,
        "evidence_checks": evidence_checks,
        "covered": covered,
        "coverage_pct": pct,
    }


def main() -> None:
    if not CLAIMS_YAML.exists():
        raise SystemExit(f"[ERROR] missing: {CLAIMS_YAML}")
    if not ACTIONS_JOBS.exists():
        raise SystemExit(f"[ERROR] missing: {ACTIONS_JOBS}")

    cfg = _read_yaml(CLAIMS_YAML)
    actions_jobs = _read_json(ACTIONS_JOBS)
    jobs = _extract_jobs(actions_jobs)
    jobs_index = [{"name": j.name, "conclusion": j.conclusion} for j in jobs]

    claims: Dict[str, Any] = cfg.get("claims", {})
    lemmas: Dict[str, Any] = cfg.get("lemmas", {})

    if not isinstance(claims, dict) or not claims:
        raise SystemExit("[ERROR] claims/claims.yaml has no 'claims' mapping.")
    if lemmas and not isinstance(lemmas, dict):
        raise SystemExit("[ERROR] claims/claims.yaml: 'lemmas' must be a mapping when present.")

    lemma_results: Dict[str, Any] = {}
    if lemmas:
        for lid, l in lemmas.items():
            title = str(l.get("title", "")).strip()
            rj = list(l.get("required_jobs") or [])
            ev = list(l.get("evidence_paths") or [])
            lemma_results[lid] = _eval_unit(lid, title, rj, ev, jobs)

    matrix_rows: List[Dict[str, Any]] = []
    covered_count = 0

    for claim_id, c in claims.items():
        title = str(c.get("title", "")).strip()
        req_lemmas = list(c.get("required_lemmas") or [])

        if req_lemmas:
            missing = [x for x in req_lemmas if x not in lemma_results]
            lemma_ok = (len(missing) == 0) and all(lemma_results[x]["covered"] for x in req_lemmas)
            pct = 0 if missing else int(round(sum(lemma_results[x]["coverage_pct"] for x in req_lemmas) / max(1, len(req_lemmas))))
            covered = lemma_ok
            row = {
                "claim": claim_id,
                "title": title,
                "mode": "lemma",
                "required_lemmas": req_lemmas,
                "missing_lemmas": missing,
                "covered": covered,
                "coverage_pct": pct,
            }
        else:
            rj = list(c.get("required_jobs") or [])
            ev = list(c.get("evidence_paths") or [])
            unit = _eval_unit(claim_id, title, rj, ev, jobs)
            row = {
                "claim": claim_id,
                "title": title,
                "mode": "direct",
                **{k: unit[k] for k in ["required_jobs","job_checks","evidence_paths","evidence_checks","covered","coverage_pct"]},
            }

        if row["covered"]:
            covered_count += 1
        matrix_rows.append(row)

    total_claims = len(matrix_rows)
    overall_pct = 0 if total_claims == 0 else int(round(100 * covered_count / total_claims))
    now = datetime.now(JST).isoformat(timespec="seconds")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    out_obj = {
        "stage": 194,
        "generated_at": now,
        "inputs": {
            "claims_yaml": str(CLAIMS_YAML.relative_to(ROOT)),
            "actions_jobs": str(ACTIONS_JOBS.relative_to(ROOT)),
        },
        "jobs": jobs_index,
        "claims_total": total_claims,
        "claims_covered": covered_count,
        "coverage_pct": overall_pct,
        "lemmas": lemma_results if lemmas else None,
        "matrix": matrix_rows,
    }
    OUT_JSON.write_text(json.dumps(out_obj, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage192: Claim Coverage Matrix")
    lines.append("")
    lines.append(f"- Generated: **{now} (JST)**")
    lines.append(f"- Claims covered: **{covered_count} / {total_claims}**")
    lines.append(f"- Coverage: **{overall_pct}%**")
    lines.append("")

    if lemmas:
        lines.append("## Lemma Summary")
        lines.append("")
        lines.append("| Lemma | Covered | Coverage% | Required Jobs | Missing Evidence |")
        lines.append("|---|---:|---:|---|---|")
        for lid, lr in lemma_results.items():
            covered = "✅" if lr["covered"] else "❌"
            pct = lr["coverage_pct"]
            req_jobs = ", ".join(lr["required_jobs"]) if lr["required_jobs"] else "-"
            missing_ev = [ec["path"] for ec in lr["evidence_checks"] if not ec["exists"]]
            missing_ev_s = ", ".join(missing_ev) if missing_ev else "-"
            lines.append(f"| {lid} | {covered} | {pct}% | {req_jobs} | {missing_ev_s} |")
        lines.append("")

    lines.append("## Claim Summary")
    lines.append("")
    lines.append("| Claim | Mode | Covered | Coverage% | Requirements |")
    lines.append("|---|---|---:|---:|---|")
    for row in matrix_rows:
        covered = "✅" if row["covered"] else "❌"
        mode = row["mode"]
        pct = row["coverage_pct"]
        if mode == "lemma":
            req = "lemmas: " + ", ".join(row["required_lemmas"])
            if row.get("missing_lemmas"):
                req += " (missing: " + ", ".join(row["missing_lemmas"]) + ")"
        else:
            req = "jobs: " + (", ".join(row["required_jobs"]) if row.get("required_jobs") else "-")
        lines.append(f"| {row['claim']} | {mode} | {covered} | {pct}% | {req} |")
    lines.append("")

    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    summary_lines: List[str] = []
    summary_lines.append("")
    summary_lines.append("## Claim Coverage (auto)")
    summary_lines.append("")
    summary_lines.append(f"- **Coverage:** {overall_pct}% ({covered_count}/{total_claims})")
    summary_lines.append(f"- **Generated:** {now} (JST)")
    summary_lines.append("- **Matrix:** `docs/claim_coverage_matrix.md`")
    if lemmas:
        summary_lines.append("- **Lemma layer:** enabled")
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
