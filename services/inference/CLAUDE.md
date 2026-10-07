# CLAUDE.md - inference service

## Role
The "device." Runs on the desktop (WSL2, RTX 3090). Owns slide files, model
weights, the feature cache, and all job state. Nothing else touches these.

## Commands
- Install / sync: `uv sync`
- Config: `cp .env.example .env` and set `DEVICE_TOKEN`, `ACQUISITION_DIR`,
  `DATA_DIR`
- Run (local only):
  `uv run --env-file .env uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5`
  (the timeout keeps open SSE streams from blocking Ctrl+C; D-037)
- Run (reachable over Tailscale): bind `--host` to the Tailscale IP, never
  `0.0.0.0` on an untrusted network
- Tests: `uv run pytest`
- Format / lint: `uv run ruff format app tests && uv run ruff check app tests`

## Suggested layout
```
app/
  main.py          FastAPI app; lifespan loads + verifies models, starts
                   registry poller and job worker
  config.py        settings from environment (.env); see .env.example
  auth.py          X-Device-Token check (pure ASGI middleware)
  health.py        GET /v1/health
  gpu.py           GPU probe (torch imported lazily)
  db.py            sqlite3 access; schema in docs/api-contract.md
  registry.py      acquisition-folder polling, size-stability check,
                   hashing, PHI-safe metadata extraction
  tiles.py         Deep Zoom tile serving (OpenSlide DeepZoomGenerator)
  jobs.py          FIFO queue, single GPU worker thread, in-memory progress
  jobs_api.py      /v1/jobs routes and the SSE progress stream
  pipeline/
    __init__.py    pipeline interface: Stage, PipelineError, PipelineResult
    stub.py        stand-in pipeline until item 6 (sleeps, reports progress)
    segment.py     tissue segmentation
    patch.py       patch coordinates
    features.py    patch encoder (feature extraction)
    mil.py         MIL aggregation; returns probabilities + attention
    heatmap.py     percentile-normalized attention -> PNG
    quality.py     tissue area / fraction, patch count, uncertainty flag
  errors.py        error codes (see docs/api-contract.md)
models/
  manifest.json    model names, versions, sources, SHA-256 hashes
tests/
```

## Rules
- Load models once at startup. Verify file hashes against
  `models/manifest.json`; refuse to start on mismatch (REQ-016).
- GPU work runs in ONE background worker thread. Never block the asyncio
  event loop with slide reading or inference.
- Throttle SQLite progress writes (at most about once per second); publish
  finer-grained progress in memory for the SSE stream.
- On startup, mark any job left `running` or `queued` as failed with
  `INTERRUPTED` (REQ-009). No automatic retries anywhere (REQ-017).
- PHI: never call or expose `associated_images`; build slide metadata from
  an explicit allowlist; never log file paths or original filenames.
- Every endpoint except `/v1/health` requires the `X-Device-Token` header.
- No network calls during inference. Weights are loaded from local disk.
- Use the `logging` module, not print. Include job ID and slide ID in log
  lines.
- Read `docs/spike-findings.md` before touching `pipeline/`.
