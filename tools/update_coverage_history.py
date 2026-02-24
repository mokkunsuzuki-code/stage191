# MIT License © 2025 Motohiro Suzuki
"""
Append current coverage snapshot to docs/coverage_history.json (+ md summary).
Input: out/ci/claim_matrix.json
Output:
  - docs/coverage_history.json  (tracked)
  - docs/coverage_history.md    (tracked)
"""

from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
INP = ROOT / "out" / "ci" / "claim_matrix.json"
HIST_JSON = ROOT / "docs" / "coverage_history.json"
HIST_MD = ROOT / "docs" / "coverage_history.md"

JST = timezone(timedelta(hours=9))

def load_json(p: Path, default):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))

def main() -> None:
    if not INP.exists():
        raise SystemExit(f"[ERROR] missing: {INP} (run tools/build_claim_matrix.py first)")

    cur = load_json(INP, {})
    ts = datetime.now(JST).isoformat(timespec="seconds")

    snap = {
        "ts": ts,
        "coverage_pct": int(cur.get("coverage_pct", 0)),
        "claims_covered": int(cur.get("claims_covered", 0)),
        "claims_total": int(cur.get("claims_total", 0)),
    }

    hist = load_json(HIST_JSON, {"history": []})
    if "history" not in hist or not isinstance(hist["history"], list):
        hist = {"history": []}

    # de-dup: if last entry has same coverage and same totals, still append? -> NO (keep history meaningful)
    if hist["history"]:
        last = hist["history"][-1]
        if (
            last.get("coverage_pct") == snap["coverage_pct"]
            and last.get("claims_covered") == snap["claims_covered"]
            and last.get("claims_total") == snap["claims_total"]
        ):
            print("[OK] history unchanged (same as last).")
        else:
            hist["history"].append(snap)
            print("[OK] appended new history entry.")
    else:
        hist["history"].append(snap)
        print("[OK] created first history entry.")

    HIST_JSON.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # markdown summary
    rows = hist["history"][-30:]  # last 30
    lines = []
    lines.append("# Coverage History (Stage193)")
    lines.append("")
    lines.append(f"- Updated: **{ts} (JST)**")
    lines.append("")
    lines.append("| Timestamp (JST) | Coverage | Covered/Total |")
    lines.append("|---|---:|---:|")
    for r in reversed(rows):
        lines.append(f"| {r['ts']} | {r['coverage_pct']}% | {r['claims_covered']}/{r['claims_total']} |")
    lines.append("")
    HIST_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] wrote: {HIST_JSON.relative_to(ROOT)}")
    print(f"[OK] wrote: {HIST_MD.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
