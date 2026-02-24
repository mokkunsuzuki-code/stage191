# Review in 5 Minutes (Stage191)

This kit shows how Stage191 enforces claims A2–A5 using real CI job results.

## 1) Read the fixed specification (Internet-Draft)
- `docs/id/draft-qsp-stage191-v1.0.md`
- See Section 8: Claim Enforcement and Continuous Verification

## 2) Verify the latest dynamic claim_status (CI artifacts)
1. Open GitHub Actions
2. Run: "Stage191 - Claim Status (dynamic)"
3. Download artifact: `stage191-claim-status`
4. Check:
   - `claim_status.md`
   - `claim_status.json`
   - `actions_jobs.json` (raw CI job results)

## 3) Local reproduction (optional)
From repository root:

- Fetch CI results:
  `python tools/fetch_actions_results.py --repo mokkunsuzuki-code/stage191`

- Compute claim_status (fail-closed):
  `python tools/compute_claim_status.py`

Outputs:
- `out/ci/claim_status.md`
- `out/ci/claim_status.json`

## What matters
- Claims are not declared statically.
- Claim status is derived from real CI job results (CI-bound).
- Missing/failed jobs => FAIL (fail-closed).
