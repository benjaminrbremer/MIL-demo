# Requirements - v0.1

Draft. Edit freely; every requirement should map to real code and, where
practical, a test that references its ID. "Verified by" is filled in as
tests are written (roadmap item 12).

## Inference service (device)

| ID | Requirement | Verified by |
|---|---|---|
| REQ-001 | The service shall detect new slide files in the acquisition folder and register them without user action. | |
| REQ-002 | The service shall not register a slide until its file size has been unchanged for at least 5 seconds. | |
| REQ-003 | The service shall assign each slide a UUID and store the SHA-256 of its contents. | |
| REQ-004 | The service shall not read or serve slide associated images (label, macro). | |
| REQ-005 | The service shall serve only allowlisted slide metadata (dimensions, level count, microns per pixel). | |
| REQ-006 | The service shall not include original filenames or file paths in API responses or logs. | |
| REQ-007 | The service shall serve ready slides as Deep Zoom tiles. | |
| REQ-008 | The service shall run at most one analysis job at a time and queue others in FIFO order. | |
| REQ-009 | The service shall persist job state in SQLite and, on startup, mark jobs left queued or running as failed with `INTERRUPTED`. | |
| REQ-010 | The service shall report job progress by stage and, during feature extraction, by patches processed of total. | |
| REQ-011 | The service shall produce slide-level class probabilities and a predicted class using the pinned MIL model. | |
| REQ-012 | The service shall flag a result as uncertain when the predicted-class probability lies within [0.3, 0.7]. | |
| REQ-013 | The service shall report tissue area in mm² (or tissue fraction when microns per pixel is unavailable) and usable patch count. | |
| REQ-014 | The service shall produce a heatmap image of percentile-normalized attention aligned to the slide. | |
| REQ-015 | The service shall record model names, versions, hashes, and per-stage timings with every completed job. | |
| REQ-016 | The service shall verify model file hashes at startup and refuse to start on mismatch. | |
| REQ-017 | The service shall fail jobs with one of the defined error codes and shall not retry automatically. | |
| REQ-018 | The service shall expose a health endpoint reporting GPU availability, model versions, and queue depth. | `tests/test_health.py::test_req_018_*` |
| REQ-019 | The service shall reject every request other than `GET /v1/health` that lacks a valid `X-Device-Token` header. | `tests/test_auth.py::test_req_019_*` |

## Web app

| ID | Requirement | Verified by |
|---|---|---|
| REQ-101 | The web app shall list slides on the device with their status and refresh the list automatically. | |
| REQ-102 | The web app shall display a selected ready slide in a zoomable viewer. | |
| REQ-103 | The web app shall allow the user to start analysis of a ready slide. | |
| REQ-104 | The web app shall display live job progress and recover it after a browser refresh. | |
| REQ-105 | The web app shall display the prediction, uncertainty flag, and quality metrics for a completed job. | |
| REQ-106 | The web app shall allow the heatmap overlay to be shown, hidden, and adjusted in opacity. | |
| REQ-107 | The web app shall display a device-offline state when the inference service is unreachable. | |
| REQ-108 | The browser client shall communicate only with the web server, never directly with the inference service. | |
| REQ-109 | The web app shall display a "research demo, not for clinical use" notice and the model versions in use. | |
