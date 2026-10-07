# Risk register (ISO 14971-style, lightweight)

Write entries in your own words. Each risk control should map to a
requirement, and each requirement to a test.

Severity: 1 (negligible) to 4 (serious). Likelihood: 1 (rare) to 4 (likely).

| ID | Hazard | Hazardous situation | Potential harm | Sev | Lik | Risk control | Control requirement | Verified by |
|---|---|---|---|---|---|---|---|---|
| RISK-001 | Model reports a confident wrong result | (example) Borderline probability shown as a definitive answer | Missed or delayed diagnosis | | | Uncertainty flag for probabilities in [0.3, 0.7] | REQ-012 | |
| RISK-002 | (draft) Same slide gives different results on different runs | MIL model left in training mode, so dropout changes the output each run (seen in the spike with wsinfer-mil) | A result can't be reproduced or audited; borderline cases flip | | | Load models in `.eval()` mode; test that two runs are identical (D-040) | REQ-020 | |
| RISK-003 | (draft) Background analysed as tissue | Tinted slide background passes the tissue threshold; blank glass dominates the bag and gets high attention | Wrong prediction, misleading heatmap, inflated tissue area | | | Tissue threshold 20 (D-039); flag tissue fraction > 0.6 as segmentation-suspect | REQ-021 | |
| RISK-004 | (draft) Wrong or altered model files used | A weight file is replaced, corrupted, or a different revision is downloaded | Results come from an unvalidated model | | | Pinned revisions and SHA-256 manifest; refuse to start on mismatch (D-040, D-041) | REQ-016 | |
| RISK-005 | (draft) Slide analysed at the wrong scale | Slide has no microns per pixel, so the 128 µm patch size can't be computed | Model sees patches at the wrong magnification; meaningless result | | | Fail the job with `NO_RESOLUTION` (D-044) | REQ-017 | |
| RISK-006 | (draft) Too little tissue for a meaningful result | Blank slide or a few fragments yield a handful of patches | Confident-looking result from debris | | | Fail the job with `NO_TISSUE` below 16 patches (D-043) | REQ-017 | |

## Known limitations (accepted for v0.1)
- PHI: identifiers inside the slide file itself are not removed; we only
  prevent them from being exposed (REQ-004 to REQ-006).
- The model was trained on H&E lymph-node slides; other inputs produce
  meaningless output with no input-type check.
- Slide files removed from, or replaced in, the acquisition folder after
  registration are not detected; the slide stays listed with its original
  metadata and hash (D-029).
- Tissue threshold (D-039) is tuned on CAMELYON16 Philips scans. A scanner
  with a more saturated background would need retuning. Pale fat (mostly
  empty adipocytes) falls below the threshold and is not analysed.
- The model card does not say how tissue was detected during training, so
  our patch selection may differ from what the model saw in training.
- The prediction depends on the patch set: 0.135 to 0.218 on test_062
  across three tissue masks (spike findings).
