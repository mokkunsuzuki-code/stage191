# MIT License © 2025 Motohiro Suzuki
"""
Stage195: Inject last N coverage history entries into README.md.

Inputs:
  - docs/coverage_history.json
Outputs:
  - README.md (replaces block between markers)
"""

from __future__ import annotations
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "docs" / "coverage_history.json"
README = ROOT / "README.md"

BEGIN = "<!-- BEGIN COVERAGE HISTORY -->"
END = "<!-- END COVERAGE HISTORY -->"

def main() -> None:
    if not HIST.exists():
        raise SystemExit(f"[ERROR] missing: {HIST} (run tools/update_coverage_history.py first)")
    if not README.exists():
        raise SystemExit(f"[ERROR] missing: {README}")

    hist = json.loads(HIST.read_text(encoding="utf-8"))
    rows = hist.get("history", [])
    if not isinstance(rows, list):
        raise SystemExit("[ERROR] coverage_history.json: history must be a list")

    last = rows[-5:]  # last 5
    last = list(reversed(last))  # newest first

    block_lines = []
    block_lines.append("")
    block_lines.append("## Coverage History (auto)")
    block_lines.append("")
    block_lines.append("| Timestamp (JST) | Coverage | Covered/Total |")
    block_lines.append("|---|---:|---:|")
    for r in last:
        ts = r.get("ts","")
        cov = r.get("coverage_pct",0)
        c = r.get("claims_covered",0)
        t = r.get("claims_total",0)
        block_lines.append(f"| {ts} | {cov}% | {c}/{t} |")
    block_lines.append("")
    new_block = "\n".join([BEGIN, *block_lines, END])

    text = README.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise SystemExit(f"[ERROR] README markers not found. Add:\n{BEGIN}\n...\n{END}")

    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), flags=re.DOTALL)
    out, n = pattern.subn(new_block, text, count=1)
    if n == 0:
        raise SystemExit("[ERROR] failed to replace README block")
    README.write_text(out, encoding="utf-8")
    print("[OK] updated README coverage history block")

if __name__ == "__main__":
    main()
