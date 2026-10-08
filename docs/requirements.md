# Requirements - v0.1

Every requirement maps to code and, where practical, to tests that carry
its ID in their name (`test_req_004_...` in Python, `req_004: ...` in
JavaScript). "Verified by" lists those tests; `*` stands for every test in
that file whose name starts with the prefix. What only a browser can show
is checked by hand and marked "manual check", with the date where one was
recorded.

Run the tests with `uv run pytest` in `services/inference/` and `npm test`
in `apps/web/`. Paths in the first table are relative to
`services/inference/`.

Risk controls in `docs/risk-register.md` point at these IDs.

## Inference service (device)

| ID | Requirement | Verified by |
|---|---|---|
| REQ-001 | The service shall detect new slide files in the acquisition folder and register them without user action. | `tests/test_registry.py::test_req_001_*` |
| REQ-002 | The service shall not register a slide until its file size has been unchanged for at least 5 seconds. | `tests/test_registry.py::test_req_002_*` |
| REQ-003 | The service shall assign each slide a UUID and store the SHA-256 of its contents. | `tests/test_registry.py::test_req_003_*` |
| REQ-004 | The service shall not read or serve slide associated images (label, macro). | `tests/test_registry.py::test_req_004_*`, `tests/test_tiles.py::test_req_004_*` |
| REQ-005 | The service shall serve only allowlisted slide metadata (dimensions, level count, microns per pixel). | `tests/test_registry.py::test_req_005_*`, `tests/test_slides.py::test_req_005_*` |
| REQ-006 | The service shall not include original filenames or file paths in API responses or logs. | `tests/test_registry.py::test_req_006_*`, `tests/test_slides.py::test_req_006_*`, `tests/test_errors.py::test_req_006_*`, `tests/test_tiles.py::test_req_006_*`, `tests/test_heatmap.py::test_req_006_*` |
| REQ-007 | The service shall serve ready slides as Deep Zoom tiles. | `tests/test_tiles.py::test_req_007_*` |
| REQ-008 | The service shall run at most one analysis job at a time and queue others in FIFO order. | `tests/test_jobs.py::test_req_008_*` |
| REQ-009 | The service shall persist job state in SQLite and, on startup, mark jobs left queued or running as failed with `INTERRUPTED`. | `tests/test_jobs.py::test_req_009_*`, `tests/test_jobs_api.py::test_req_009_*` |
| REQ-010 | The service shall report job progress by stage and, during feature extraction, by patches processed of total. | `tests/test_jobs.py::test_req_010_*`, `tests/test_jobs_api.py::test_req_010_*`, `tests/test_mil_pipeline.py::test_req_010_*` |
| REQ-011 | The service shall produce slide-level class probabilities and a predicted class using the pinned MIL model. | `tests/test_mil_pipeline.py::test_req_011_*` |
| REQ-012 | The service shall flag a result as uncertain when the predicted-class probability lies within [0.3, 0.7]. | `tests/test_quality.py::test_req_012_*`, `tests/test_mil_pipeline.py::test_req_012_*` |
| REQ-013 | The service shall report tissue area in mm², tissue fraction, and usable patch count. Jobs on slides without microns per pixel fail with `NO_RESOLUTION` (D-044). | `tests/test_quality.py::test_req_013_*`, `tests/test_mil_pipeline.py::test_req_012_req_013_*` |
| REQ-014 | The service shall produce a heatmap image of percentile-normalized attention aligned to the slide. | `tests/test_heatmap.py::test_req_014_*`, `tests/test_mil_pipeline.py::test_req_014_*`, `tests/test_jobs_api.py::test_req_014_*` |
| REQ-015 | The service shall record model names, versions, hashes, and per-stage timings with every completed job. | `tests/test_mil_pipeline.py::test_req_015_*` |
| REQ-016 | The service shall verify model file hashes at startup and refuse to start on mismatch. | `tests/test_models.py::test_req_016_*`, `tests/test_fetch_models.py::test_req_016_*` |
| REQ-017 | The service shall fail jobs with one of the defined error codes and shall not retry automatically. | `tests/test_jobs.py::test_req_017_*`, `tests/test_jobs_api.py::test_req_017_*`, `tests/test_mil_pipeline.py::test_req_017_*`; a user message for every code: `apps/web/test/messages.test.js` (`req_017`) |
| REQ-018 | The service shall expose a health endpoint reporting GPU availability, model versions, and queue depth. | `tests/test_health.py::test_req_018_*`, `tests/test_models.py::test_req_018_*` |
| REQ-019 | The service shall reject every request other than `GET /v1/health` that lacks a valid `X-Device-Token` header. | `tests/test_auth.py::test_req_019_*`, `tests/test_slides.py::test_req_019_*`, `tests/test_tiles.py::test_req_019_*` |
| REQ-020 | The service shall run both models in inference mode, so that analysing the same slide twice gives identical probabilities and attention (D-040). | `tests/test_models.py::test_req_020_*`; on the desktop also `tests/test_mil_pipeline.py::test_req_020_*` and the real-model test (`uv run pytest -m "models or slide"`, D-048) |
| REQ-021 | The service shall flag a result as segmentation-suspect when the tissue fraction exceeds 0.6. | `tests/test_quality.py::test_req_021_*` |

## Web app

| ID | Requirement | Verified by |
|---|---|---|
| REQ-101 | The web app shall list slides on the device with their status and refresh the list automatically. | `apps/web/test/slides.test.js` (`req_101`); list rendering and auto-refresh in the browser: manual check |
| REQ-102 | The web app shall display a selected ready slide in a zoomable viewer. | `apps/web/test/slides.test.js` and `apps/web/test/deviceClient.test.js` (`req_102`); viewing and zooming in the browser: manual check |
| REQ-103 | The web app shall allow the user to start analysis of a ready slide. | `apps/web/test/jobs.test.js` (`req_103`); button in the browser: manual check |
| REQ-104 | The web app shall display live job progress and recover it after a browser refresh. | `apps/web/test/jobs.test.js` (`req_104`); progress bar and reload recovery in the browser: manual check; live run against the device, 2026-10-08 (D-060) |
| REQ-105 | The web app shall display the prediction, uncertainty flag, and quality metrics for a completed job. | `apps/web/test/describe.test.js` (`req_105`); panel shown in the browser: manual check, 2026-10-08 |
| REQ-106 | The web app shall allow the heatmap overlay to be shown, hidden, and adjusted in opacity. | `apps/web/test/jobs.test.js` (`req_106`, heatmap proxy); overlay alignment, toggle and opacity in the browser: manual check, 2026-10-08 |
| REQ-107 | The web app shall display a device-offline state when the inference service is unreachable. | `apps/web/test/deviceClient.test.js`, `apps/web/test/server.test.js`, `apps/web/test/slides.test.js`, `apps/web/test/jobs.test.js` and `apps/web/test/messages.test.js` (`req_107`); banner shown in the browser: manual check |
| REQ-108 | The browser client shall communicate only with the web server, never directly with the inference service. | `apps/web/test/client.test.js`, `apps/web/test/deviceClient.test.js`, `apps/web/test/server.test.js`, `apps/web/test/slides.test.js` and `apps/web/test/jobs.test.js` (`req_108`) |
| REQ-109 | The web app shall display a "research demo, not for clinical use" notice and the model versions in use. | `apps/web/test/server.test.js` (`req_109`, notice); model versions shown in the browser: manual check |

## Traceability by test file

The same mapping, from the other direction. Files without requirement IDs
test supporting code that no single requirement covers.

### Inference service (`services/inference/tests/`)
| Test file | Requirements |
|---|---|
| `test_auth.py` | REQ-019 |
| `test_config.py` | (none: config loading and validation, D-022) |
| `test_errors.py` | REQ-006 |
| `test_fetch_models.py` | REQ-016 |
| `test_health.py` | REQ-018 |
| `test_heatmap.py` | REQ-006, REQ-014 |
| `test_jobs.py` | REQ-008, REQ-009, REQ-010, REQ-017 |
| `test_jobs_api.py` | REQ-009, REQ-010, REQ-014, REQ-017 |
| `test_mil_pipeline.py` | REQ-010, REQ-011, REQ-012, REQ-013, REQ-014, REQ-015, REQ-017, REQ-020 |
| `test_models.py` | REQ-016, REQ-018, REQ-020 |
| `test_quality.py` | REQ-012, REQ-013, REQ-021 |
| `test_registry.py` | REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006 |
| `test_segment_patch.py` | (none: tissue segmentation and the patch grid, D-039, D-051) |
| `test_slides.py` | REQ-005, REQ-006, REQ-019 |
| `test_tiles.py` | REQ-004, REQ-006, REQ-007, REQ-019 |
| `test_version.py` | (none: `app.__version__` matches `pyproject.toml`) |

Tests marked `models` or `slide` (part of REQ-007, REQ-020) are skipped
unless the real weights and `MIL_TEST_SLIDE` are present; they run on the
desktop GPU (D-048).

### Web app (`apps/web/test/`)
| Test file | Requirements |
|---|---|
| `client.test.js` | REQ-108 |
| `describe.test.js` | REQ-105 |
| `deviceClient.test.js` | REQ-102, REQ-107, REQ-108 |
| `errors.test.js` | (none: Node's error handler keeps device errors and hides its own, D-057) |
| `jobs.test.js` | REQ-103, REQ-104, REQ-106, REQ-107, REQ-108 |
| `messages.test.js` | REQ-017, REQ-107 |
| `server.test.js` | REQ-107, REQ-108, REQ-109 |
| `slides.test.js` | REQ-101, REQ-102, REQ-107, REQ-108 |

## Manual checks
Browser behaviour that automated tests don't cover. Repeat these at the
release rehearsal (roadmap item 13).

| Requirement | Check |
|---|---|
| REQ-101 | A slide copied into the acquisition folder appears in the list within a few seconds, as arriving and then ready, without reloading |
| REQ-102 | Selecting a ready slide opens it in the viewer; zoom to full resolution |
| REQ-103 | Start analysis of a ready slide from the UI |
| REQ-104 | Progress moves through the five stages with a patch count during feature extraction; reload mid-job and progress continues |
| REQ-105 | A completed job shows the prediction, probabilities, warnings and metrics |
| REQ-106 | The heatmap lines up with the tissue; hide, show and change its opacity |
| REQ-107 | Stop the inference service: the page shows the device as offline (banner on load, list status line while open) |
| REQ-109 | The research notice and both model versions are visible |
| REQ-017 | Trigger each error code that can be triggered on purpose (see the contract's error table) and read its message |
