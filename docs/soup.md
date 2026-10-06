# SOUP inventory (software of unknown provenance)

Every third-party component the system relies on. Versions come from
`services/inference/uv.lock` and `apps/web/package-lock.json` and are
updated whenever those change.

Licenses below are expected values and must be checked against each
project's own license file before marking "Verified".

## Software

| Component | Version | Used by | License (expected) | Verified | Source | Function we rely on |
|---|---|---|---|---|---|---|
| PyTorch | TBD | inference | BSD-3-Clause | [ ] | pytorch.org | Tensor computation and GPU inference |
| CUDA toolkit / driver | TBD | inference | NVIDIA EULA | [ ] | nvidia.com | GPU execution |
| wsinfer-mil | TBD | inference | Apache-2.0 | [ ] | github.com/SBU-BMI/wsinfer-mil | Pipeline components and model loading |
| OpenSlide (C library, via openslide-bin) | 4.0.1 (openslide-bin 4.0.1.2) | inference | LGPL-2.1 | [ ] | openslide.org | Reading pyramidal WSI files: dimensions, levels, microns per pixel |
| openslide-python | 1.4.6 | inference | LGPL-2.1 | [ ] | openslide.org | Python bindings, Deep Zoom generator |
| FastAPI | 0.142.2 | inference | MIT | [ ] | fastapi.tiangolo.com | HTTP API |
| Starlette | 1.7.0 | inference | BSD-3-Clause | [ ] | starlette.dev | ASGI toolkit under FastAPI; we import its exception and middleware types directly |
| Pydantic | 2.13.5 | inference | MIT | [ ] | pydantic.dev | Response models and request validation |
| Uvicorn | 0.54.0 | inference | BSD-3-Clause | [ ] | uvicorn.org | ASGI server |
| NumPy | TBD | inference | BSD-3-Clause | [ ] | numpy.org | Array math (attention, metrics) |
| Pillow | 12.3.0 | inference | MIT-CMU (HPND) | [ ] | python-pillow.org | Image objects returned by openslide-python; heatmap PNG encoding |
| Express | TBD | web | MIT | [ ] | expressjs.com | HTTP server and routing |
| OpenSeadragon | TBD | web | BSD-3-Clause | [ ] | openseadragon.github.io | Deep Zoom slide viewer |
| Node.js runtime | TBD | web | MIT | [ ] | nodejs.org | JavaScript runtime |
| Python runtime | 3.12 (3.12.12 on dev Mac) | inference | PSF | [ ] | python.org | Python runtime |

Add any transitive dependency that directly affects results (for example,
the patch encoder's model-definition library) as it is identified.

## Development tools (not shipped)
Used to build and test the inference service; not loaded at runtime.

| Component | Version | Used by | License (expected) | Verified | Source | Function we rely on |
|---|---|---|---|---|---|---|
| uv | 0.9.7 | inference | MIT / Apache-2.0 | [ ] | docs.astral.sh/uv | Python and dependency management, lockfile |
| pytest | 9.1.1 | inference | MIT | [ ] | pytest.org | Test runner |
| httpx | 0.28.1 | inference | BSD-3-Clause | [ ] | python-httpx.org | HTTP client behind FastAPI's TestClient |
| Ruff | 0.16.10 | inference | MIT | [ ] | docs.astral.sh/ruff | Formatting and linting |

## Models and data

| Item | Version / revision | License (to verify) | Verified | Source | Notes |
|---|---|---|---|---|---|
| MIL model (CAMELYON16 metastasis) | TBD | TBD | [ ] | huggingface.co/kaczmarj | Hash in `models/manifest.json` |
| Patch encoder weights | TBD | TBD | [ ] | TBD | Hash in `models/manifest.json` |
| CAMELYON16 slides | test split | TBD | [ ] | CAMELYON16 challenge | Never committed to the repo |

## Known anomalies review
For each item that affects results (PyTorch, OpenSlide, wsinfer-mil, the
models), record the date the issue tracker / release notes were reviewed
and any known bug that could affect this use.

| Component | Reviewed on | Relevant known issues | Impact / mitigation |
|---|---|---|---|
| | | | |
