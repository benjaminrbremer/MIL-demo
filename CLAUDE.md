# CLAUDE.md

## Project
A device-style whole-slide image (WSI) analysis demo. A Python inference
service (the "device") watches a local acquisition folder for new slides,
runs a pretrained multiple instance learning (MIL) model on request, and
reports progress, a slide-level prediction, an attention heatmap, and basic
sample-quality metrics. A Node.js web app lets a user browse slides on the
device, start analysis, watch live progress, and review results.

Research demo only. Not for clinical use.

Built with medical-device software habits on purpose: explicit requirements,
traceability, SOUP documentation, a risk register, and pinned versions.

## Architecture (one line each)
- `services/inference/` - Python, FastAPI + PyTorch + OpenSlide. Runs on the
  desktop GPU (RTX 3090, WSL2). Owns all slide pixels, models, and job state
  (SQLite). Exposes the versioned API in `docs/api-contract.md`.
- `apps/web/` - Node.js (Express) server plus a plain-JavaScript browser
  client. Runs on the Mac. Mediates every call to the inference service.
- The browser NEVER calls the inference service directly.
- The two machines connect over Tailscale with a shared token header.

## Source of truth (read these before planning)
- `docs/roadmap.md` - ordered work items and current status
- `docs/decisions.md` - decisions already made and why. Do not reopen them
  without asking me.
- `docs/api-contract.md` - endpoints, payloads, SQLite schema, error codes
- `docs/requirements.md` - requirement IDs (REQ-xxx)
- `docs/spike-findings.md` - what the model spike proved (read before any
  pipeline work)
- `docs/soup.md` - third-party software inventory

## Scope for v0.1 (3-day build)
In scope: slide registry, tile serving, job queue, MIL pipeline with
progress, heatmap PNG, quality metrics, web viewer, live progress, results
panel, error states, documentation set.

Out of scope (see `docs/future-work.md`): slide upload, Docker, CI/CD,
pre-commit hooks, authentication beyond the shared token, fine-tuning,
interactive per-patch heatmap.

## Hard rules
- Plain JavaScript only on the web side. No TypeScript, no React, no bundler.
- Python environment managed with `uv`. Do not add conda or Docker.
- Never commit slides, model weights, `.env` files, SQLite databases, or
  feature caches.
- PHI controls (REQ-004 to REQ-006): never read or serve OpenSlide
  associated images (label, macro); serve only allowlisted metadata; never
  put original filenames in API responses, logs, or the UI.
- Do not add a third-party dependency without asking. If approved, add it
  to `docs/soup.md` in the same change.
- Prefer the standard library (sqlite3, logging, built-in fetch) to new
  dependencies. Fewer dependencies means less SOUP.

## Conventions
- Commits: Conventional Commits. Scopes: `inference`, `web`, `docs`, `repo`.
  Example: `feat(inference): add single-worker job queue`
- Branches: `feat/<scope>-<short-name>`, `fix/<scope>-<short-name>`,
  `docs/<short-name>`. Squash-merged into `main`; the squash commit message
  must also follow Conventional Commits.
- Versions: each component is versioned independently (`pyproject.toml`,
  `package.json`). Tags: `inference-vX.Y.Z`, `web-vX.Y.Z`.
- Tests that verify a requirement reference its ID in the test name or
  docstring, e.g. `test_req_004_associated_images_not_served`.
- Timestamps are ISO 8601 UTC everywhere.

## How we work
1. One roadmap item per session. Start by reading `docs/roadmap.md` and
   `docs/decisions.md`.
2. Propose a plan before writing code. List assumptions and open questions,
   then wait for my approval.
3. Work on a feature branch for that item.
4. Keep changes scoped to the item. If you notice something else that needs
   doing, note it; do not fix it in the same change.
5. Never commit, merge, push, or tag without my explicit approval. Propose
   the commit message for me to review.
6. After the item is done: mark it in `docs/roadmap.md`, add any new
   decision to `docs/decisions.md`, and update `docs/requirements.md`
   traceability if tests were added.
7. Explain non-obvious code to me as you write it. I need to be able to
   explain every file in an interview.

## Commands
- Inference service: see `services/inference/CLAUDE.md`
- Web app: see `apps/web/CLAUDE.md`
