# MIT License © 2025 Motohiro Suzuki
"""
Auto-tune required_jobs in claims/claims.yaml based on out/ci/actions_jobs.json job names.

Rule:
- For each required_jobs entry (pattern), try to find job names that contain it (case-insensitive).
- If exactly one unique match exists, replace pattern with that exact job name (more precise).
- If multiple matches exist, keep as-is (user can refine manually).
- If no matches exist, keep as-is (user can fix manually).
"""

from __future__ import annotations
from pathlib import Path
import json

import yaml  # pip install pyyaml

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "claims" / "claims.yaml"
ACTIONS = ROOT / "out" / "ci" / "actions_jobs.json"

def main() -> None:
    if not CLAIMS.exists():
        raise SystemExit(f"[ERROR] missing: {CLAIMS}")
    if not ACTIONS.exists():
        raise SystemExit(f"[ERROR] missing: {ACTIONS}")

    cfg = yaml.safe_load(CLAIMS.read_text(encoding="utf-8"))
    d = json.loads(ACTIONS.read_text(encoding="utf-8"))

    jobs = d.get("jobs") or []
    job_names = [str(j.get("name") or "") for j in jobs if j.get("name")]
    low_map = {n.lower(): n for n in job_names}

    claims = cfg.get("claims", {})
    if not isinstance(claims, dict):
        raise SystemExit("[ERROR] claims.yaml: 'claims' must be a mapping")

    changes = 0
    report = []

    for cid, c in claims.items():
        req = list(c.get("required_jobs") or [])
        new_req = []
        for pat in req:
            p = str(pat)
            matches = [n for n in job_names if p.lower() in n.lower()]
            uniq = sorted(set(matches))
            if len(uniq) == 1:
                new_req.append(uniq[0])
                if uniq[0] != p:
                    changes += 1
                    report.append(f"{cid}: '{p}' -> '{uniq[0]}'")
            else:
                new_req.append(p)
                if len(uniq) == 0:
                    report.append(f"{cid}: '{p}' -> (NO MATCH) keep")
                else:
                    report.append(f"{cid}: '{p}' -> (MULTI {len(uniq)}) keep")

        c["required_jobs"] = new_req

    if changes > 0:
        CLAIMS.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(f"[OK] updated {CLAIMS.relative_to(ROOT)} with {changes} precise replacements")
    else:
        print("[OK] no unique matches to replace (already precise or ambiguous)")

    print("\n[REPORT]")
    for line in report:
        print("-", line)

if __name__ == "__main__":
    main()
