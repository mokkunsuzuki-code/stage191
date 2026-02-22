# MIT License © 2025 Motohiro Suzuki
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def load_actions_jobs(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"[NG] missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        jobs = data.get("jobs", [])
        if isinstance(jobs, list):
            return jobs
        raw = data.get("raw")
        if isinstance(raw, dict) and isinstance(raw.get("jobs"), list):
            return raw["jobs"]
        return []
    if isinstance(data, list):
        return data
    return []


def jobs_map(jobs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    m: Dict[str, Dict[str, Any]] = {}
    for j in jobs:
        if not isinstance(j, dict):
            continue
        name = j.get("name")
        if isinstance(name, str) and name:
            m[name] = j
    return m


def load_claims(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"[NG] missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    claims = data.get("claims", {})
    if not isinstance(claims, dict):
        raise ValueError("[NG] claims.yaml: 'claims' must be a mapping")
    out: Dict[str, Dict[str, Any]] = {}
    for cid, obj in claims.items():
        if isinstance(obj, dict):
            out[str(cid)] = obj
    return out


def job_ok(
    j: Optional[Dict[str, Any]],
    *,
    allow_any_in_progress: bool,
    allow_in_progress_jobs: List[str],
) -> Tuple[bool, str]:
    if j is None:
        return False, "missing"

    name = str(j.get("name", ""))
    status = j.get("status")
    concl = j.get("conclusion")

    if status == "completed" and concl == "success":
        return True, f"{status}/{concl}"

    if status == "in_progress" and (allow_any_in_progress or name in allow_in_progress_jobs):
        return True, f"{status}/{concl}"

    return False, f"{status}/{concl}"


def claim_satisfied(
    claims: Dict[str, Dict[str, Any]],
    cid: str,
    jm: Dict[str, Dict[str, Any]],
    *,
    allow_any_in_progress: bool,
    allow_in_progress_jobs: List[str],
) -> Tuple[bool, List[Tuple[str, Optional[Dict[str, Any]], str]]]:
    obj = claims.get(cid)
    if not obj:
        return False, [(f"claim:{cid}", None, "missing-claim")]

    req = obj.get("required_jobs", []) or []
    if not isinstance(req, list):
        req = []

    details: List[Tuple[str, Optional[Dict[str, Any]], str]] = []
    ok_all = True
    for r in [str(x) for x in req]:
        j = jm.get(r)
        ok, why = job_ok(j, allow_any_in_progress=allow_any_in_progress, allow_in_progress_jobs=allow_in_progress_jobs)
        details.append((r, j, why))
        if not ok:
            ok_all = False

    return ok_all, details


def main() -> None:
    ap = argparse.ArgumentParser()

    # legacy args
    ap.add_argument("--jobs-json", default="out/ci/actions_jobs.json", help="Path to actions_jobs.json")
    ap.add_argument("--require-jobs-all", action="store_true", help="Require ALL jobs in jobs.json to be success")
    ap.add_argument("--allow-any-in-progress", action="store_true", help="Allow any in_progress job to pass")
    ap.add_argument("--allow-in-progress-job", action="append", default=[], help="Allow specific in_progress job name")

    # new claim-driven args
    ap.add_argument("--jobs", default=None, help="Alias of --jobs-json")
    ap.add_argument("--claims", default=None, help="Path to claims.yaml")
    ap.add_argument("--require-claims-all", action="store_true", help="Require ALL claims in claims.yaml")
    ap.add_argument("--require-claim", action="append", default=[], help="Require specific claim id (repeatable)")

    args = ap.parse_args()

    jobs_path = Path(args.jobs if args.jobs else args.jobs_json)
    jobs = load_actions_jobs(jobs_path)
    jm = jobs_map(jobs)

    if args.require_jobs_all:
        bad: List[str] = []
        for name, j in sorted(jm.items()):
            ok, why = job_ok(
                j,
                allow_any_in_progress=args.allow_any_in_progress,
                allow_in_progress_jobs=args.allow_in_progress_job,
            )
            if not ok:
                bad.append(name)
                print(f"[NG] job NOT ok: {name} ({why})")
        if bad:
            sys.exit(2)
        print("[OK] gate passed")
        sys.exit(0)

    if args.claims and (args.require_claims_all or args.require_claim):
        claims = load_claims(Path(args.claims))
        if args.require_claims_all:
            to_check = sorted(list(claims.keys()))
        else:
            to_check = [str(x) for x in args.require_claim]

        bad: List[str] = []
        for cid in to_check:
            ok, details = claim_satisfied(
                claims,
                cid,
                jm,
                allow_any_in_progress=args.allow_any_in_progress,
                allow_in_progress_jobs=args.allow_in_progress_job,
            )
            if not ok:
                bad.append(cid)
                print(f"[NG] claim NOT satisfied: {cid}")
                for req, j, why in details:
                    if j is None:
                        print(f"  - {req}: missing")
                    else:
                        print(f"  - {req}: {why}")

        if bad:
            sys.exit(2)

        print("[OK] gate passed")
        sys.exit(0)

    print("[OK] gate passed (no requirements)")
    sys.exit(0)


if __name__ == "__main__":
    main()
