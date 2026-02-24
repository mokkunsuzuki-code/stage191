# QSP: Quantum-Safe Protocol
## Internet-Draft (Stage191 Snapshot)
## Version 1.0
## © 2025 Motohiro Suzuki
## License: MIT

---

# 1. Introduction

QSP (Quantum-Safe Protocol) is a hybrid cryptographic protocol
designed to integrate post-quantum primitives, classical safety,
and structured verification enforcement.

Stage191 fixes the protocol structure and integrates
Claim Enforcement into the specification.

---

# 2. Terminology

- Claim: A normative security guarantee (A2–A5)
- Required Job: CI job bound to a claim
- Evidence Artifact: Verifiable output required to validate a claim
- Fail-Closed: Any verification failure results in claim invalidation

---

# 3. Security Claims

A2: Replay Resistance  
A3: Downgrade Protection  
A4: Interoperability Safety  
A5: Rekey Integrity  

Claims are dynamically validated via CI.

---

# 4. Implementation Status

The reference implementation includes CI-based verification.

Claims A2–A5 are programmatically enforced via CI job binding
and fail-closed gating as specified in Section 8.

---

# 5. Protocol Overview

This document specifies the verification and enforcement structure
for the Stage191 snapshot of QSP.

The reference implementation and verification artifacts reside in
the Stage191 repository, including prior stages imported for evidence
generation and attack-driven CI.

---

# 6. Threat Model

The protocol assumes an active network adversary capable of:

- replaying messages,
- attempting downgrade of negotiated security parameters,
- injecting messages from a different session (session confusion),
- racing rekey procedures.

The enforcement mechanism described in Section 8 ensures that these
threats are continuously tested and regressions are detected.

---

# 7. Non-Goals

QSP does not claim that CI-based verification replaces formal proofs.
Instead, it provides operational assurance that the implementation
continues to satisfy declared normative guarantees.

---

# 8. Claim Enforcement and Continuous Verification

## 8.1 Overview

QSP defines security guarantees A2–A5 as normative claims.
These claims are programmatically enforced via Continuous Integration (CI).

Each claim is bound to required verification jobs and evidence artifacts.
A claim is considered valid only if all associated jobs succeed and
required evidence files are present.

## 8.2 Claim-to-Job Binding

Each claim is mapped to one or more CI jobs.

Example mapping:

A2 → attack_replay  
A3 → attack_downgrade  
A4 → interop_smoke  
A5 → rekey_race  

A claim MUST be marked FAILED if any required job fails.

Static declaration of claim satisfaction is NOT permitted.

## 8.3 Evidence Requirements

Required evidence may include:

- Structured attack logs  
- Summary reports  
- CI JSON results  

Absence of required evidence invalidates the claim even if CI reports success.

## 8.4 CI Gating Policy

QSP enforces a fail-closed policy.

If a required job is missing, fails, or cannot be retrieved,
the claim MUST be treated as FAILED.

Implementations MUST NOT downgrade enforcement to warning mode.

## 8.5 External Reproducibility

All enforcement artifacts and mappings are reproducible by third parties
via repository CI workflows and published artifacts.

## 8.6 Security Considerations

Claim Enforcement reduces drift between specification and implementation.
It ensures normative guarantees are continuously validated.

---

# 9. License

MIT License © 2025 Motohiro Suzuki
