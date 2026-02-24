# Stage192: Claim Coverage Matrix

- Claims covered: **4 / 4**
- Coverage: **100%**

## Coverage Summary

| Claim | Covered | Coverage% | Required Jobs | Missing Evidence |
|---|---:|---:|---|---|
| A2 | ✅ | 100% | attack_replay | - |
| A3 | ✅ | 100% | attack_downgrade | - |
| A4 | ✅ | 100% | interop_smoke | - |
| A5 | ✅ | 100% | zeroize_rules, no_secret_logging, proverif, tamarin | - |

## Claim ↔ Job ↔ Evidence (Details)

### A2 — Replay attack is detected / rejected

- Covered: **YES**
- Coverage%: **100%**

**Jobs**
- ✅ required: `attack_replay` — passed
  - matched: `attack_replay` (conclusion: `success`)

**Evidence**
- ✅ `out/ci/actions_jobs.json`
- ✅ `out/ci/claim_status.md`

### A3 — Downgrade attack is detected / rejected

- Covered: **YES**
- Coverage%: **100%**

**Jobs**
- ✅ required: `attack_downgrade` — passed
  - matched: `attack_downgrade` (conclusion: `success`)

**Evidence**
- ✅ `out/ci/actions_jobs.json`
- ✅ `out/ci/claim_status.md`

### A4 — Interop / compatibility checks are validated

- Covered: **YES**
- Coverage%: **100%**

**Jobs**
- ✅ required: `interop_smoke` — passed
  - matched: `interop_smoke` (conclusion: `success`)

**Evidence**
- ✅ `out/ci/actions_jobs.json`

### A5 — Audit / security checks are executed

- Covered: **YES**
- Coverage%: **100%**

**Jobs**
- ✅ required: `zeroize_rules` — passed
  - matched: `zeroize_rules` (conclusion: `success`)
- ✅ required: `no_secret_logging` — passed
  - matched: `no_secret_logging` (conclusion: `success`)
- ✅ required: `proverif` — passed
  - matched: `proverif` (conclusion: `success`)
- ✅ required: `tamarin` — passed
  - matched: `tamarin` (conclusion: `success`)

**Evidence**
- ✅ `out/ci/claim_status.md`
- ✅ `audit.log`
