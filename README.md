<!-- BEGIN CLAIM COVERAGE MATRIX -->

## Claim Coverage (auto)

- **Coverage:** 100% (4/4)
- **Generated:** 2026-02-25T07:55:34+09:00 (JST)
- **Matrix:** `docs/claim_coverage_matrix.md`
- **Lemma layer:** enabled

<!-- END CLAIM COVERAGE MATRIX -->

# QSP Stage191
## Quantum-Safe Protocol — Claim Enforcement Fixed Snapshot
## © 2025 Motohiro Suzuki
## License: MIT

---

## Overview

Stage191 represents a structural milestone in QSP development.

This snapshot:

- Fixes the Internet-Draft structure
- Integrates Claim Enforcement into the protocol specification
- Binds security guarantees (A2–A5) to CI job verification
- Enforces fail-closed validation semantics

QSP is no longer only an implementation.
It is a protocol specification with embedded continuous verification.

---

## Internet-Draft (Fixed Specification)

- I-D v1.0:
  `docs/id/draft-qsp-stage191-v1.0.md`

Stage191 formally integrates Claim Enforcement into the normative
protocol structure.

Claims A2–A5 are CI-bound and fail-closed.

---

## Security Claims (Normative)

- A2: Replay Resistance
- A3: Downgrade Protection
- A4: Interoperability Safety
- A5: Rekey Integrity

Claim status is dynamically computed from CI job results.
Static declaration of claim satisfaction is not permitted.

---

## Claim Enforcement Model

Each claim is bound to required CI jobs and evidence artifacts.

Example mapping:

A2 → attack_replay  
A3 → attack_downgrade  
A4 → interop_smoke  
A5 → rekey_race  

A claim is marked FAILED if:

- A required job fails
- A job result cannot be retrieved
- Required evidence artifacts are missing
- Parsing errors occur

QSP operates under a strict fail-closed policy.

---

## Continuous Integration

Security guarantees are continuously validated via:

- Attack-driven CI execution
- Evidence artifact validation
- Dynamic claim status computation

This reduces:

- Specification drift
- Silent regression
- Incomplete test coverage

---

## Repository Structure (Relevant to Stage191)

- `claims/` — Claim definitions and mappings
- `audit/` — Evidence and verification outputs
- `docs/id/` — Internet-Draft specification
- `stage176/`–`stage178/` — Prior enforcement and attack modules

---

## Threat Model

QSP assumes an active adversary capable of:

- Replay attacks
- Downgrade attempts
- Session confusion
- Rekey race injection

Continuous enforcement ensures regression detection.

---

## Non-Goals

QSP does not replace formal proof systems.
It provides operational assurance through executable verification.

---

## License

MIT License © 2025 Motohiro Suzuki

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, subject to the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

---

## Internet-Draft (Fixed Specification)

- **I-D v1.0:** `docs/id/draft-qsp-stage191-v1.0.md`
- Stage191 fixes the Internet-Draft structure and integrates **Claim Enforcement** into the protocol specification.
- Claims **A2–A5 are CI-bound and fail-closed** (job binding + evidence requirements).

## Dynamic claim_status (CI)

- The latest `claim_status.json` / `claim_status.md` is generated from real GitHub Actions job results.
- See **GitHub → Actions → "Stage191 - Claim Status (dynamic)" → Artifacts → `stage191-claim-status`**.

