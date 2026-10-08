# API contract - inference service v1

The Node server is the only client. All paths are prefixed `/v1`.
Every endpoint except `GET /v1/health` requires header
`X-Device-Token: <shared secret>`; missing or wrong token returns `401`.
Timestamps are ISO 8601 UTC. Errors use the shape
`{"error": {"code": "...", "message": "..."}}`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | Service status, GPU, model versions, queue depth |
| GET | `/v1/slides` | All slides on the device (JSON array, newest first) |
| GET | `/v1/slides/{id}` | One slide |
| GET | `/v1/slides/{id}.dzi` | Deep Zoom descriptor (ready slides only) |
| GET | `/v1/slides/{id}_files/{level}/{col}_{row}.jpeg` | Deep Zoom tile |
| POST | `/v1/jobs` | Start analysis: body `{"slide_id": "..."}` |
| GET | `/v1/jobs?slide_id={id}` | Jobs, newest first; `slide_id` (optional) filters to one slide |
| GET | `/v1/jobs/{id}` | One job |
| GET | `/v1/jobs/{id}/events` | Server-Sent Events progress stream |
| GET | `/v1/jobs/{id}/heatmap.png` | Attention overlay (completed jobs only) |

### `GET /v1/health`
```json
{
  "status": "ok",
  "service_version": "0.1.0",
  "api_version": "v1",
  "gpu": {"available": true, "name": "NVIDIA GeForce RTX 3090"},
  "models": [
    {"role": "encoder", "name": "...", "version": "...", "sha256": "..."},
    {"role": "mil", "name": "...", "version": "...", "sha256": "..."}
  ],
  "queue": {"running": 0, "queued": 0}
}
```
`gpu.name` is `null` when no GPU is available. `queue` counts jobs in
SQLite. `models` lists the encoder and the MIL model: `name` is the Hugging
Face repo, `version` the short pinned revision (e.g. `507b473a`), and
`sha256` the hash of the weight file from `models/manifest.json` (D-040, D-041).
The service does not start unless both files match their hashes (REQ-016).

### Slide object
```json
{
  "id": "uuid",
  "status": "arriving | registering | ready | unreadable",
  "width": 97792,
  "height": 221184,
  "level_count": 9,
  "mpp_x": 0.243,
  "mpp_y": 0.243,
  "detected_at": "2026-10-07T14:03:11Z",
  "registered_at": "2026-10-07T14:03:19Z",
  "error": null
}
```
Only these fields are served (allowlist). No filenames, paths, associated
images, or raw property dumps. `mpp_x`/`mpp_y` may be `null`.

### Deep Zoom: `GET /v1/slides/{id}.dzi` and tiles
- `.dzi` returns `application/xml`: the Deep Zoom descriptor with
  `TileSize="254"`, `Overlap="1"`, `Format="jpeg"`, and the level-0 width
  and height (bounds are not trimmed, so heatmap coordinates line up).
- `{id}_files/{level}/{col}_{row}.jpeg` returns `image/jpeg`, at most
  256 x 256 px (254 plus 1 px overlap on each inner edge), with
  `Cache-Control: private, max-age=3600`.
- `404 NOT_FOUND`: unknown slide, or a level, column, or row outside the
  pyramid (including non-numeric segments).
- `409 SLIDE_NOT_READY`: the slide's status is not `ready`.
- `409 SLIDE_UNREADABLE`: the slide is `ready` but its file can no longer
  be opened or read (for example, it was removed; the row is unchanged,
  D-029).

### `POST /v1/jobs`
- `202` with the job object as created (status `queued`)
- `404 NOT_FOUND`: unknown slide
- `409 SLIDE_NOT_READY`: the slide's status is not `ready`
- `409 JOB_ALREADY_ACTIVE`: the slide already has a `queued` or `running`
  job (D-033)
- `422 VALIDATION_ERROR`: body missing `slide_id`

### `GET /v1/jobs`
Without `slide_id`, all jobs. With an unknown `slide_id`, `[]`.

### Job object
```json
{
  "id": "uuid",
  "slide_id": "uuid",
  "status": "queued | running | completed | failed",
  "stage": "segmenting | patching | extracting_features | aggregating | rendering | null",
  "progress": {"done": 4210, "total": 18000},
  "error": null,
  "created_at": "...",
  "started_at": "...",
  "finished_at": null,
  "models": [{"role": "encoder", "name": "...", "version": "...", "sha256": "..."}],
  "timings_s": {"segmenting": 3.1, "patching": 0.8, "extracting_features": 92.4},
  "result": {
    "probabilities": {"<class_a>": 0.91, "<class_b>": 0.09},
    "predicted_class": "<class_a>",
    "uncertain": false,
    "uncertainty_band": [0.3, 0.7],
    "quality": {
      "tissue_area_mm2": 41.7,
      "tissue_fraction": 0.12,
      "patch_count": 18000,
      "blur_fraction": null,
      "segmentation_suspect": false
    }
  }
}
```
`result` is `null` until `completed`. Class names come from the model
config (see spike findings). `error` is `{"code", "message"}` when failed.
`progress` is always present; `done` and `total` are `null` when the
current stage has no count (only `extracting_features` reports counts).
`models` is `[]` and `timings_s` is `{}` until the job completes; a
completed job lists both models (same shape as in `/v1/health`) and the
seconds spent in each stage that ran (REQ-015). `uncertain` is `true` when the
predicted class's probability lies within `uncertainty_band`, both ends
included (REQ-012). Jobs completed before item 7 have `uncertain`,
`uncertainty_band` and `quality` set to `null` (D-047, D-054). On a feature-cache hit
(same slide contents analysed before, D-046) progress jumps straight to
`total`/`total`, and the stage changes may be merged into one SSE event or
none at all, because the job can finish within one 250 ms poll.
`quality.segmentation_suspect` is `true` when the tissue fraction is above
0.6, which on the demo slides means the background was segmented as tissue
(REQ-021). `tissue_area_mm2` is always present on a completed job, because
jobs on slides without microns per pixel fail with `NO_RESOLUTION` (D-044).

### `GET /v1/jobs/{id}/events` (SSE)
On connect, the server immediately sends the current job snapshot, so a
client that reconnects after a refresh is up to date. If the job has
already finished, the snapshot is followed straight away by its
`completed` or `failed` event. `progress` events are sent when progress
changes, checked every 250 ms; updates in between are merged (D-034).
A `: ping` comment is sent after 15 s without events. Unknown job:
`404 NOT_FOUND` (JSON, before any stream starts).

| Event | Data |
|---|---|
| `snapshot` | full job object |
| `progress` | `{"status", "stage", "progress": {"done", "total"}}` |
| `completed` | full job object |
| `failed` | full job object |

The stream closes after `completed` or `failed`.

### `GET /v1/jobs/{id}/heatmap.png`
The attention heatmap of a completed job (REQ-014, D-053, D-054), rendered
during the job's `rendering` stage.
- `200 image/png`, RGBA, `Cache-Control: private, max-age=3600`. The
  image has the slide's aspect ratio (longest side 2048 px) and covers
  exactly the level-0 rectangle `[0, width] x [0, height]`: overlay it at
  `(0, 0, width, height)` in slide coordinates.
- Each analysed 128 µm patch is coloured by its attention score, clipped
  to the slide's 1st and 99th percentiles and rescaled to [0, 1], with the
  TURBO colour map (blue low, red high). Pixels without a patch have alpha
  0. Patches are fully opaque; the client sets the overlay opacity.
- Colours are relative to this slide: they show where the model looked,
  not the probability of metastasis. A negative slide has red areas too.
- `404 NOT_FOUND`: unknown job, or a completed job with no heatmap
  (completed before item 7).
- `409 JOB_NOT_COMPLETED`: the job is queued, running or failed.

## Error codes

| Code | Where | Meaning | How to trigger on purpose |
|---|---|---|---|
| `DEVICE_OFFLINE` | Web only (503) | Node cannot reach the inference service, or it doesn't answer within 5 s (D-057) | Stop the Python service; for the timeout, point `INFERENCE_URL` at an unused tailnet address |
| `BAD_GATEWAY` | Web only (502) | Something answered at `INFERENCE_URL` with a success status, but not with JSON (D-057) | Point `INFERENCE_URL` at a different web server |
| `WEB_SERVER_OFFLINE` | Browser only, never sent by a server | The browser cannot reach the Node server, or got non-JSON from it | Stop the Node server, then reload |
| `SLIDE_UNREADABLE` | Slide status / tiles / job | OpenSlide cannot open the file | Drop a renamed text file in the folder |
| `NO_TISSUE` | Job | Segmentation found fewer than 16 patches of tissue (D-043) | Blank or background-only image |
| `NO_RESOLUTION` | Job | The slide has no microns-per-pixel value, so 128 µm patches can't be sized (D-044) | A pyramidal TIFF written without resolution tags |
| `INTERRUPTED` | Job | Service restarted while job was queued or running | Restart the service mid-job |
| `INFERENCE_FAILED` | Job | Any other pipeline failure, including GPU OOM | (catch-all) |

### HTTP-level codes
Returned in the same error shape for request failures that are not slide or
job failures. A `500` never includes exception text.

| Code | Status | Meaning |
|---|---|---|
| `BAD_REQUEST` | 4xx | Fallback for a client error with no more specific code |
| `UNAUTHORIZED` | 401 | Missing or wrong `X-Device-Token` (any path except `/v1/health`, including unknown paths) |
| `NOT_FOUND` | 404 | Unknown path or resource |
| `METHOD_NOT_ALLOWED` | 405 | Path exists, method does not |
| `VALIDATION_ERROR` | 422 | Request body or query failed validation |
| `SLIDE_NOT_READY` | 409 | The slide exists but its status is not `ready` (tiles, job creation) |
| `JOB_ALREADY_ACTIVE` | 409 | `POST /v1/jobs` for a slide that already has a queued or running job |
| `JOB_NOT_COMPLETED` | 409 | Heatmap requested for a job that is not `completed` (D-054) |
| `INTERNAL_ERROR` | 500 | Unhandled server error |

## SQLite schema
```sql
CREATE TABLE slides (
  id            TEXT PRIMARY KEY,          -- UUID
  file_path     TEXT NOT NULL UNIQUE,      -- internal only, never served
  sha256        TEXT,                      -- null until hashed
  status        TEXT NOT NULL,             -- arriving|registering|ready|unreadable
  width         INTEGER,
  height        INTEGER,
  level_count   INTEGER,
  mpp_x         REAL,
  mpp_y         REAL,
  detected_at   TEXT NOT NULL,
  registered_at TEXT,
  error_code    TEXT,
  error_message TEXT
);

CREATE TABLE jobs (
  id             TEXT PRIMARY KEY,         -- UUID
  slide_id       TEXT NOT NULL REFERENCES slides(id),
  status         TEXT NOT NULL,            -- queued|running|completed|failed
  stage          TEXT,
  progress_done  INTEGER,
  progress_total INTEGER,
  error_code     TEXT,
  error_message  TEXT,
  created_at     TEXT NOT NULL,
  started_at     TEXT,
  finished_at    TEXT,
  models_json    TEXT,                     -- model names, versions, hashes
  timings_json   TEXT,                     -- seconds per stage
  result_json    TEXT                      -- probabilities, class, uncertain, quality
);

CREATE INDEX idx_jobs_slide ON jobs(slide_id, created_at);

-- At most one active job per slide (D-033)
CREATE UNIQUE INDEX idx_jobs_one_active
  ON jobs(slide_id) WHERE status IN ('queued', 'running');
```

## Device data on disk (internal, never served)
Under `DATA_DIR`, besides the SQLite database:
- `cache/<key>/coords.npy`, `features.npy`: feature cache. The key is a
  SHA-256 of slide SHA-256, encoder SHA-256, patch size and tissue
  threshold (D-046). No filenames.
- `jobs/<job_id>/coords.npy` (patch top-left x, y at level 0),
  `attention.npy` (raw attention score per patch, same row order) and
  `mask.npy` (tissue mask on the thumbnail grid): saved by every completed
  job for the heatmap and quality metrics (D-047, D-050).
- `jobs/<job_id>/heatmap.png`: the rendered heatmap, served by
  `GET /v1/jobs/{id}/heatmap.png` (D-054).

## Web app routes (Node)
The browser calls only these. Node forwards to `/v1/...` with the token and
returns `503 {"error": {"code": "DEVICE_OFFLINE"}}` when the device is
unreachable. Device errors pass through unchanged (same status, code and
message); an error body without the contract shape, or one that isn't
JSON, becomes `INTERNAL_ERROR` with the device's status. Unknown
`/api/...` paths return `404 NOT_FOUND`, and an error in Node itself
returns `500 INTERNAL_ERROR` with a fixed message (D-057).

The Deep Zoom routes pass the device's body through unchanged and copy only
its `Content-Type` and `Cache-Control` headers. A slide ID that isn't a
lowercase UUID, or a tile path that isn't `{level}/{col}_{row}.jpeg` with
numbers, is answered `404 NOT_FOUND` by Node without contacting the device
(D-058).

| Browser route | Forwards to |
|---|---|
| `GET /api/health` | `/v1/health` |
| `GET /api/slides` | `/v1/slides` |
| `GET /api/slides/:id.dzi`, `/api/slides/:id_files/...` | tile endpoints |
| `POST /api/jobs` | `/v1/jobs` |
| `GET /api/jobs?slide_id=` | `/v1/jobs?slide_id=` |
| `GET /api/jobs/:id` | `/v1/jobs/{id}` |
| `GET /api/jobs/:id/events` | SSE relay of `/v1/jobs/{id}/events` |
| `GET /api/jobs/:id/heatmap.png` | `/v1/jobs/{id}/heatmap.png` |
