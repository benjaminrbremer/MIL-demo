# Risk register (ISO 14971-style, lightweight)

What could go wrong if someone relied on this system's output, what we do
about it, and how we know the control works. Each risk control maps to a
requirement in `docs/requirements.md`, and each requirement to tests.

This is a research demo, not a medical device (REQ-109). The scores assume
the worst realistic case: someone reads the output as if it could inform a
decision about a patient.

## Scales
- **Severity (Sev):** 1 negligible (inconvenience), 2 minor (wasted time,
  a repeat run), 3 serious (a misleading result, a privacy breach), 4
  critical (a result that could plausibly lead to a missed or wrong
  diagnosis).
- **Likelihood (Lik):** 1 rare, 2 unlikely, 3 possible, 4 likely (already
  seen in the spike or in testing).
- **Risk** = Sev x Lik. "Lik before" is without the control; "Lik after"
  is with it.
- **Acceptability:** a residual risk (Sev x Lik after) of 4 or less is
  acceptable for v0.1. Anything above that is listed under "Accepted
  limitations" with the reason, or must be reduced before release.

## Register

| ID | Hazard | Hazardous situation | Potential harm | Sev | Lik before | Risk control | Control requirement | Lik after | Verified by |
|---|---|---|---|---|---|---|---|---|---|
| RISK-001 | Wrong result presented with confidence | A borderline probability is shown as a plain class label | Missed or delayed diagnosis | 4 | 3 | Flag a result as uncertain when the predicted-class probability is in [0.3, 0.7], ends included; the flag is computed on the device and shown as a warning with the probability and band | REQ-012, REQ-105 | 2 | `test_quality.py::test_req_012_*`, `test_mil_pipeline.py::test_req_012_*`, `describe.test.js` (`req_105`) |
| RISK-002 | Same slide gives different results on different runs | The MIL model file is saved in training mode, so dropout changes the output on each run (seen in the spike: 0.164 to 0.167 on identical input) | A result can't be reproduced or audited; a borderline case can flip class | 3 | 4 | Load both models with `.eval()`; test that two runs give identical probabilities and attention (D-040) | REQ-020 | 1 | `test_models.py::test_req_020_*`; on the GPU, `test_mil_pipeline.py::test_req_020_*` |
| RISK-003 | Background analysed as tissue | Tinted slide background passes the tissue threshold; blank glass fills the bag and draws attention | Wrong prediction, misleading heatmap, inflated tissue area | 3 | 4 | Tissue threshold 20 instead of 7 (D-039); flag tissue fraction above 0.6 as segmentation-suspect and show a warning | REQ-021, REQ-105 | 2 | `test_quality.py::test_req_021_*`, `test_segment_patch.py` (threshold), `describe.test.js` (`req_105`) |
| RISK-004 | Wrong or altered model files used | A weight file is replaced, corrupted, or a different revision is downloaded | Results come from a model nobody validated | 4 | 2 | Pinned revisions and SHA-256 values in `models/manifest.json`; refuse to start on a missing or mismatched file; record model names, revisions and hashes on every job; show them in the UI (D-040, D-041) | REQ-016, REQ-015, REQ-018, REQ-109 | 1 | `test_models.py::test_req_016_*`, `test_fetch_models.py::test_req_016_*`, `test_mil_pipeline.py::test_req_015_*` |
| RISK-005 | Slide analysed at the wrong scale | The slide has no microns per pixel, so the 128 µm patch size can't be computed | The model sees patches at the wrong magnification; the result is meaningless | 3 | 2 | Fail the job with `NO_RESOLUTION`; never assume a default (D-044) | REQ-017, REQ-013 | 1 | `test_mil_pipeline.py::test_req_017_no_resolution_without_mpp` |
| RISK-006 | Too little tissue for a meaningful result | A blank slide or a few fragments yield a handful of patches | A confident-looking result from debris | 3 | 2 | Fail the job with `NO_TISSUE` below 16 patches, before the encoder runs (D-043) | REQ-017 | 1 | `test_mil_pipeline.py::test_req_017_no_tissue_*` |
| RISK-007 | Patient identifiers exposed | The label or macro image, identifying metadata, or the original file name reaches the API, logs or UI | Privacy breach | 3 | 3 | Never read associated images; serve only allowlisted metadata; UUIDs instead of file names; no exception text in errors or logs; no text chunks in PNGs (D-009, D-024, D-028) | REQ-004, REQ-005, REQ-006 | 1 | `test_registry.py`, `test_tiles.py`, `test_slides.py`, `test_errors.py`, `test_heatmap.py` (`test_req_004_*` to `test_req_006_*`) |
| RISK-008 | Unauthorised access to the device | Another machine on the network reads slides or starts jobs | Privacy breach; GPU time used by someone else | 3 | 2 | Bind to the Tailscale address only (D-055); deny-by-default token check on every route but health (D-023); the token never reaches the browser | REQ-019, REQ-108 | 1 | `test_auth.py::test_req_019_*`, `test_slides.py` and `test_tiles.py` (`test_req_019_*`), `server.test.js` (`req_108`) |
| RISK-009 | Result attributed to the wrong slide | After switching slides, the previous slide's result or heatmap stays on screen, or a slow heatmap lands on the new slide | Another patient's result read as this one's | 4 | 2 | The results panel follows the selected slide's newest job and hides for anything not completed (D-062); a counter discards a heatmap that loads after the user moved on (D-063); IDs come from the device, never from file names | REQ-105, REQ-106 | 1 | Manual check (switch slides quickly while a heatmap is loading). No automated test: the logic is in DOM code |
| RISK-010 | Unfinished work reported as finished | The service stops mid-job and the job is resumed silently or left `running` forever | A result built from partial work; or the user waits for a result that never comes | 3 | 2 | No resumption: on startup, jobs left queued or running are failed with `INTERRUPTED`; no automatic retries (D-004, D-012, D-037) | REQ-009, REQ-017 | 1 | `test_jobs.py::test_req_009_*`, `test_jobs_api.py::test_req_009_*`, `test_jobs.py::test_req_017_unexpected_error_is_inference_failed_and_not_retried` |
| RISK-011 | Device outage hidden from the user | The device or network is down but the UI looks like it is still working or waiting | Delay; the user acts on an old slide list or an old result | 2 | 3 | 5 s timeout on every device call; no answer becomes `DEVICE_OFFLINE` with a message saying what to check (D-057) | REQ-107 | 1 | `deviceClient.test.js`, `server.test.js`, `slides.test.js`, `jobs.test.js`, `messages.test.js` (`req_107`) |
| RISK-012 | Heatmap read as a probability map | Heatmap colours are relative to each slide, so a negative slide shows red areas too | A negative slide read as positive, or attention read as tumour location | 3 | 3 | The heatmap is titled "Attention heatmap", with the note "Where the model looked, relative to this slide only. Not a probability of metastasis: a negative slide has red areas too."; the overlay can be hidden or faded (D-053, D-063) | REQ-014, REQ-106 | 2 | Manual check of the note. The note itself has no requirement (see "Open items") |
| RISK-013 | Demo used for clinical decisions | Someone treats the output as a diagnostic result | Missed or wrong diagnosis | 4 | 2 | "Research demo, not for clinical use" notice on every page and in the README; model versions shown | REQ-109 | 1 | `server.test.js` (`req_109`) |
| RISK-014 | Slide outside the model's training domain | A non-lymph-node, non-H&E, or differently scanned slide is analysed | A meaningless result that looks like any other | 4 | 2 | None in v0.1 beyond the notice (REQ-109) and the segmentation-suspect flag (REQ-021), which catches some scanner differences | REQ-109, REQ-021 | 2 | Accepted (see below). Input-type check is future work |
| RISK-015 | Cached features from different input reused | A feature cache entry from another slide, encoder or patch setting is used | A result for the wrong input | 4 | 2 | Cache key is slide SHA-256 + encoder SHA-256 + patch size + tissue threshold; entries written atomically (D-046, D-051) | REQ-003 | 1 | `test_mil_pipeline.py::test_cache_is_keyed_by_slide_content`, `test_second_run_uses_feature_cache`; `test_registry.py::test_req_003_*` |

## Accepted limitations (v0.1)
Residual risks that v0.1 does not reduce further, with the reason.

- **PHI stays in the file.** Identifiers inside the slide file itself are
  not removed; we only prevent them from being exposed (REQ-004 to
  REQ-006). Full de-identification is future work.
- **No input-type check (RISK-014).** The model was trained on H&E
  lymph-node slides; other inputs produce meaningless output. Residual
  risk 8 is above the acceptability line and is accepted only because
  this is a research demo with a permanent notice (REQ-109).
- **Confident wrong results (RISK-001).** The uncertainty flag only covers
  borderline probabilities. A wrong result outside [0.3, 0.7] is not
  flagged. Residual risk 8, accepted for the same reason as RISK-014.
- **Files changed after registration** are not detected; the slide stays
  listed with its original metadata and hash, so a replaced file would be
  analysed under the old hash and could hit the old cache entry (D-029,
  RISK-015). Registry change detection is future work.
- **Tissue threshold tuned on one scanner (RISK-003).** Residual risk 6.
  The threshold (D-039) is tuned on CAMELYON16 Philips scans. A scanner
  with a more saturated background would need retuning; the
  segmentation-suspect flag catches the gross case, not a partial one.
  Pale fat (mostly empty adipocytes) falls below the threshold and is not
  analysed.
- **Training-time patch selection unknown.** The model card does not say
  how tissue was detected during training, so our patch selection may
  differ from what the model saw.
- **Prediction depends on the patch set:** 0.135 to 0.218 on test_062
  across three tissue masks (spike findings). Small changes to
  segmentation move the probability.
- **Heatmap misreading (RISK-012).** Residual risk 6. The relative colour
  scale is a deliberate choice (D-053); the legend is the only control.

## Open items
Found while writing this register; not fixed in item 12.

- **RISK-012:** the "Not a probability of metastasis" note has no
  requirement and no automated test. Candidate: a requirement that the
  heatmap is labelled as relative attention, verified by a client test.
- **RISK-009:** the stale-result guards are only checked by hand.
- **RISK-011:** the browser checks `/api/health` only once, at page load.
  If the device goes down later, the offline banner does not appear; the
  slide list shows "Can't refresh the list (DEVICE_OFFLINE)" instead, and
  `slideList.js` has a comment saying the banner explains the outage.
  Candidate: poll health alongside the slide list.
