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
| GET | `/v1/jobs?slide_id={id}` | Jobs for a slide, newest first |
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
`gpu.name` is `null` when no GPU is available. Until roadmap items 6 and 5
land, `models` is `[]` and `queue` is always zero.

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
- `202` with the job object (status `queued`)
- `404` unknown slide; `409` slide not `ready`

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
      "blur_fraction": null
    }
  }
}
```
`result` is `null` until `completed`. Class names come from the model
config (see spike findings). `error` is `{"code", "message"}` when failed.

### `GET /v1/jobs/{id}/events` (SSE)
On connect, the server immediately sends the current job snapshot, so a
client that reconnects after a refresh is up to date.

| Event | Data |
|---|---|
| `snapshot` | full job object |
| `progress` | `{"status", "stage", "progress": {"done", "total"}}` |
| `completed` | full job object |
| `failed` | full job object |

The stream closes after `completed` or `failed`.

## Error codes

| Code | Where | Meaning | How to trigger on purpose |
|---|---|---|---|
| `DEVICE_OFFLINE` | Web only | Node cannot reach the inference service | Stop the Python service |
| `SLIDE_UNREADABLE` | Slide status / tiles / job | OpenSlide cannot open the file | Drop a renamed text file in the folder |
| `NO_TISSUE` | Job | Segmentation found no usable tissue | Blank or background-only image |
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
| `SLIDE_NOT_READY` | 409 | The slide exists but its status is not `ready` (tiles; job creation from item 5) |
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
```

## Web app routes (Node)
The browser calls only these. Node forwards to `/v1/...` with the token and
returns `503 {"error": {"code": "DEVICE_OFFLINE"}}` when the device is
unreachable.

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
