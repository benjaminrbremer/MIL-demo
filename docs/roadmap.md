# Roadmap - v0.1

Status: `[ ]` not started, `[~]` in progress, `[x]` done.
Each numbered item is one feature branch, squash-merged into `main`.

## Day 0 - before the clean history starts
- [~] Start downloading 3-4 CAMELYON16 test-split slides: one clear
      positive, one negative, one small slide for live runs, optionally one
      hard case (small metastasis). Record which in `docs/spike-findings.md`.
      Four staged (test_001, test_062, test_065, test_128); ground truth and
      roles still to record.
- [~] Spike notebook on branch `spike/model` (never merged). Answer every
      question in `docs/spike-findings.md`. All answered except the demo
      slide table and timings for the other three slides. Outcomes recorded
      as D-038 to D-048.

## Day 1 - inference service
- [x] **1. `chore(repo): initialize repository`**
  README, LICENSE (MIT), `.gitignore`, `docs/` set, CLAUDE.md files,
  `.claude/commands/`.
- [x] **2. `feat(inference): scaffold FastAPI service with health endpoint`**
  `uv` project, config from `.env`, `/v1/health` (GPU info, versions),
  token check middleware, `.env.example`. REQ-018.
- [x] **3. `feat(inference): add slide registry with folder polling and PHI-safe metadata`**
  Poll acquisition folder every 2 s; size-stability check before
  registering; UUID slide IDs; SHA-256 stored; allowlisted metadata;
  `unreadable` status on OpenSlide failure; `GET /v1/slides`,
  `GET /v1/slides/{id}`. REQ-001 to REQ-006.
- [x] **4. `feat(inference): serve Deep Zoom tiles`**
  `.dzi` descriptor and tile endpoints for ready slides. REQ-007.
- [x] **5. `feat(inference): add SQLite job store and single-worker queue`**
  Schema from `docs/api-contract.md`; FIFO queue; one worker thread;
  startup marks unfinished jobs `INTERRUPTED`; `POST /v1/jobs`,
  `GET /v1/jobs`, `GET /v1/jobs/{id}`, SSE `GET /v1/jobs/{id}/events`
  (with a stub pipeline that just sleeps and reports progress).
  REQ-008 to REQ-010, REQ-017.
- [x] **6. `feat(inference): implement MIL pipeline with progress reporting`**
  Replace the stub with the real stages; model hash verification at
  startup; feature cache keyed by SHA-256; models and timings recorded on
  the job. Weight fetch script and `models/manifest.json`; `.eval()` and a
  repeat-run test; tissue threshold 20; `NO_TISSUE` below 16 patches; new
  `NO_RESOLUTION` code; attention and coordinates saved for item 7.
  D-038 to D-048. REQ-010, REQ-011, REQ-015, REQ-016, REQ-020.
- [x] **7. `feat(inference): add heatmap rendering and quality metrics`**
  Percentile-normalized attention PNG; tissue area and fraction, patch
  count, uncertainty flag, segmentation-suspect flag (tissue fraction
  > 0.6). REQ-012 to REQ-014, REQ-021. Rendered in the pipeline as the
  `rendering` stage; p1-p99 clip, TURBO, RGBA PNG on the mask grid. D-053,
  D-054.

## Day 2 - web app
- [x] **8. `feat(web): scaffold Express server and static client`**
  `deviceClient.js`, `/api/health` with DEVICE_OFFLINE mapping, research
  notice, `.env.example`, `.nvmrc`. REQ-107 to REQ-109. 5 s device
  timeout, `BAD_GATEWAY`, built-in `--env-file` and `node:test`. D-056,
  D-057.
- [x] **9. `feat(web): add slide list and viewer`**
  Auto-refreshing list with statuses; OpenSeadragon viewer via tile proxy.
  REQ-101, REQ-102. `deviceGetRaw` proxy with a header allowlist;
  OpenSeadragon 6.1.1 from `node_modules`. D-058, D-059.
- [ ] **10. `feat(web): run jobs with live progress`**
  Start job; SSE relay; progress bar by stage and patch count; recovery on
  browser refresh. REQ-103, REQ-104.
- [ ] **11. `feat(web): add results panel, heatmap overlay, and error states`**
  Prediction, uncertainty flag, quality metrics, heatmap toggle and
  opacity, clear error display per code. REQ-105, REQ-106, REQ-017.

## Day 3 - documentation and release
- [ ] **12. `docs: add architecture, SOUP, requirements, risk register, and traceability`**
  Fill `docs/architecture.md`, finish `docs/soup.md` (versions from lock
  files), traceability column in `docs/requirements.md`, risk register.
- [ ] **13. Release**
  Bump versions, tag `inference-v0.1.0` and `web-v0.1.0`.
- [ ] Rehearsal over Tailscale from the interview location: full live run,
      trigger each error state, confirm timing.
      Mac to device path (`/v1/health` over Tailscale) first verified
      2026-10-07 at home (D-055).

## Stretch (only after 13)
See `docs/future-work.md`.
