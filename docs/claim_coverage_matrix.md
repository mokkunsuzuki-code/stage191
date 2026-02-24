# Stage192: Claim Coverage Matrix

- Claims covered: **3 / 4**
- Coverage: **75%**

## Coverage Summary

| Claim | Covered | Coverage% | Required Jobs | Missing Evidence |
|---|---:|---:|---|---|
| A2 | ✅ | 100% | replay | - |
| A3 | ✅ | 100% | downgrade | - |
| A4 | ✅ | 100% | interop | - |
| A5 | ❌ | 67% | audit | - |

## Claim ↔ Job ↔ Evidence (Details)

### A2 — Replay attack is detected / rejected

- Covered: **YES**
- Coverage%: **100%**

**Jobs**
- ✅ required: `replay` — passed
  - matched: `attack_replay` (conclusion: `success`)

**Evidence**
- ✅ `out/ci/actions_jobs.json`
- ✅ `out/ci/claim_status.md`

### A3 — Downgrade attack is detected / rejected

- Covered: **YES**
- Coverage%: **100%**

**Jobs**
- ✅ required: `downgrade` — passed
  - matched: `attack_downgrade` (conclusion: `success`)

**Evidence**
- ✅ `out/ci/actions_jobs.json`
- ✅ `out/ci/claim_status.md`

### A4 — Interop / compatibility checks are validated

- Covered: **YES**
- Coverage%: **100%**

**Jobs**
- ✅ required: `interop` — passed
  - matched: `interop_smoke` (conclusion: `success`)

**Evidence**
- ✅ `out/ci/actions_jobs.json`

### A5 — Audit / security checks are executed

- Covered: **NO**
- Coverage%: **67%**

**Jobs**
- ❌ required: `audit` — no matching job

**Evidence**
- ✅ `out/ci/claim_status.md`
- ✅ `audit.log`
