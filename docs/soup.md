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
| OpenSlide (C library) | TBD | inference | LGPL-2.1 | [ ] | openslide.org | Reading pyramidal WSI files |
| openslide-python | TBD | inference | LGPL-2.1 | [ ] | openslide.org | Python bindings, Deep Zoom generator |
| FastAPI | TBD | inference | MIT | [ ] | fastapi.tiangolo.com | HTTP API |
| Uvicorn | TBD | inference | BSD-3-Clause | [ ] | uvicorn.org | ASGI server |
| NumPy | TBD | inference | BSD-3-Clause | [ ] | numpy.org | Array math (attention, metrics) |
| Pillow | TBD | inference | MIT-CMU (HPND) | [ ] | python-pillow.org | Heatmap PNG encoding |
| Express | TBD | web | MIT | [ ] | expressjs.com | HTTP server and routing |
| OpenSeadragon | TBD | web | BSD-3-Clause | [ ] | openseadragon.github.io | Deep Zoom slide viewer |
| Node.js runtime | TBD | web | MIT | [ ] | nodejs.org | JavaScript runtime |
| Python runtime | TBD | inference | PSF | [ ] | python.org | Python runtime |

Add any transitive dependency that directly affects results (for example,
the patch encoder's model-definition library) as it is identified.

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
