# Risk register (ISO 14971-style, lightweight)

Write entries in your own words. Each risk control should map to a
requirement, and each requirement to a test.

Severity: 1 (negligible) to 4 (serious). Likelihood: 1 (rare) to 4 (likely).

| ID | Hazard | Hazardous situation | Potential harm | Sev | Lik | Risk control | Control requirement | Verified by |
|---|---|---|---|---|---|---|---|---|
| RISK-001 | Model reports a confident wrong result | (example) Borderline probability shown as a definitive answer | Missed or delayed diagnosis | | | Uncertainty flag for probabilities in [0.3, 0.7] | REQ-012 | |
| RISK-002 | | | | | | | | |

## Known limitations (accepted for v0.1)
- PHI: identifiers inside the slide file itself are not removed; we only
  prevent them from being exposed (REQ-004 to REQ-006).
- The model was trained on H&E lymph-node slides; other inputs produce
  meaningless output with no input-type check.
- Slide files removed from, or replaced in, the acquisition folder after
  registration are not detected; the slide stays listed with its original
  metadata and hash (D-029).
