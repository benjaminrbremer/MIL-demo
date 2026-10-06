# Decision log

Short records of decisions and why. Add new entries at the bottom.
Do not reverse a decision without discussing it first.

| ID | Decision | Rationale | Alternatives considered |
|---|---|---|---|
| D-001 | One repo, two independently versioned components | One product, one developer, a shared API contract that changes on both sides at once | Separate repos (adds cross-repo version coordination) |
| D-002 | Slides arrive via a local acquisition folder on the device; no upload | Mirrors a real instrument, where capture and analysis happen on the same device; avoids streaming multi-GB files through two hops | Browser upload through Node (moved to future work) |
| D-003 | The browser never calls the inference service; Node mediates | Device exposes a narrow, versioned API; UI layer can't reach the instrument directly | Browser calls Python directly (simpler, but weaker boundary) |
| D-004 | Python owns job state in SQLite; unfinished jobs become `INTERRUPTED` on restart | Single source of truth on the device; no silent resumption of partial work | In-memory state; Node-side state |
| D-005 | One GPU worker, FIFO queue | One RTX 3090; predictable memory use and timing | Concurrent jobs |
| D-006 | Poll the acquisition folder every 2 s; register only after file size is stable | Files appear before copying finishes; file-change notifications are unreliable across the WSL2/Windows boundary | inotify / watchdog library |
| D-007 | Acquisition folder lives inside the WSL2 filesystem | Reading slides across `/mnt/c` is slow and file events are unreliable; Windows can still copy in via `\\wsl$\` | Folder on the Windows drive |
| D-008 | Slide IDs are UUIDs; SHA-256 stored for feature-cache keys | IDs never derive from filenames; re-analysing an identical file reuses cached features | Filename-based IDs; hash as primary key |
| D-009 | Minimal PHI controls: no associated images, allowlisted metadata, no filenames in API/logs/UI | Real WSI files can carry patient identifiers in label images and metadata; cheap to prevent exposure | Full de-identification of files (future work); skipping PHI entirely |
| D-010 | Heatmap is a server-rendered PNG of percentile-normalized attention | Simple and robust; raw softmax attention is tiny and skewed and would look uniform | Per-patch JSON drawn in the browser (future work) |
| D-011 | Quality metrics for v0.1: tissue area (mm², or fraction if no mpp), usable patch count, uncertainty flag (probability in [0.3, 0.7]) | All are byproducts of steps that already run; uncertainty flag is a risk control | Blur fraction (stretch); artifact detection |
| D-012 | Fixed error codes, plain UI errors, no automatic retries | Failures are visible and explainable; each code can be triggered on purpose | Retry logic |
| D-013 | Progress via SSE (Python to Node to browser); slide list via polling | SSE fits one-way progress; polling is simplest for an infrequently changing list | WebSockets; polling for progress |
| D-014 | Plain JavaScript, Express, ES modules, no bundler or framework | Matches the target team's stack; keeps the client inspectable | TypeScript; React; Vite |
| D-015 | Python environment via `uv` with a lockfile; no Docker in v0.1 | Simple; lockfile gives exact versions for SOUP | conda; Docker (future work) |
| D-016 | Prefer standard library and built-ins over new dependencies | Smaller SOUP surface | ORMs, HTTP client libraries |
| D-017 | Mac and desktop connect over Tailscale; shared `X-Device-Token` header | Private network, works off home Wi-Fi, nothing exposed publicly | SSH tunnel; LAN only |
| D-018 | Pretrained WSInfer-MIL CAMELYON16 metastasis model; demo on CAMELYON16 test-split slides | Ready-to-run open MIL model on gigapixel slides; test split is held out if the model trained only on the training split (verify in spike) | MIL-Lab FEATHER (no classifier head, gated, non-commercial) |
| D-019 | Git: Conventional Commits, feature branches, squash merge, per-component tags | Clean, reviewable history; shows disciplined process | Merge commits; single version |
| D-020 | MIT license for this repository's code | Simple and permissive; compatible with Apache-2.0 dependencies when their notices are kept | Apache-2.0 |
| D-021 | Inference service pinned to Python 3.12 (`.python-version`, `requires-python`) | Broadest wheel support across PyTorch, OpenSlide, and the MIL stack on both macOS and WSL2; uv provisions it on either machine | 3.13 (newer, some ML wheels lag) |
| D-022 | Inference config comes from environment variables, read with `os.environ` into a frozen dataclass; `.env` is loaded by `uv run --env-file` | No extra dependency; config fails fast at startup (missing or short token) | python-dotenv; pydantic-settings |
| D-023 | Token check is deny-by-default pure ASGI middleware with constant-time comparison; only `/v1/health` is public; Swagger UI and ReDoc disabled | New routes are protected without opt-in; unknown paths return 401, not 404; pure ASGI does not wrap streaming (SSE) responses; docs pages can't send the header and load CDN scripts | Per-router FastAPI dependency (easy to forget on a new router); `BaseHTTPMiddleware` |
| D-024 | HTTP-level error codes (`UNAUTHORIZED`, `NOT_FOUND`, `VALIDATION_ERROR`, ...) alongside the pipeline codes; 500 responses and logs never include exception text | Every error keeps the contract shape; exception text can contain file paths (REQ-006) | FastAPI default `{"detail": ...}` |
