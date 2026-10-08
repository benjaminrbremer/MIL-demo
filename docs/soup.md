# SOUP inventory (software of unknown provenance)

Every third-party component the system relies on. Versions come from
`services/inference/uv.lock` and `apps/web/package-lock.json` and are
updated whenever those change.

Licenses below are expected values and must be checked against each
project's own license file before marking "Verified".

## Software

| Component | Version | Used by | License (expected) | Verified | Source | Function we rely on |
|---|---|---|---|---|---|---|
| PyTorch | 2.14.1 (`+cu132` CUDA build on Linux; CPU build on macOS, D-048) | inference | BSD-3-Clause | [ ] | pytorch.org | Tensor computation, GPU inference, TorchScript model loading, `DataLoader` with forkserver worker processes, encoder input normalisation |
| OpenCV (opencv-python-headless) | 5.0.0.93 | inference | Apache-2.0 | [ ] | opencv.org | Tissue segmentation: colour conversion, median blur, threshold, morphology, connected components (D-039); heatmap colour map (TURBO) and PNG encoding (D-053) |
| CUDA runtime / driver | Runtime 13.2 and cuDNN 9.24 bundled in the PyTorch wheel; driver 610.57.01 (WSL) / 610.88 (Windows) | inference | NVIDIA EULA | [ ] | nvidia.com | GPU execution |
| OpenSlide (C library, via openslide-bin) | 4.0.1 (openslide-bin 4.0.1.2) | inference | LGPL-2.1 | [ ] | openslide.org | Reading pyramidal WSI files: dimensions, levels, microns per pixel |
| openslide-python | 1.4.6 | inference | LGPL-2.1 | [ ] | openslide.org | Python bindings, Deep Zoom generator |
| FastAPI | 0.142.2 | inference | MIT | [ ] | fastapi.tiangolo.com | HTTP API |
| Starlette | 1.7.0 | inference | BSD-3-Clause | [ ] | starlette.dev | ASGI toolkit under FastAPI; we import its exception and middleware types directly |
| Pydantic | 2.13.5 | inference | MIT | [ ] | pydantic.dev | Response models and request validation |
| Uvicorn | 0.54.0 | inference | BSD-3-Clause | [ ] | uvicorn.org | ASGI server |
| NumPy | 2.5.3 | inference | BSD-3-Clause | [ ] | numpy.org | Arrays for masks, patch coordinates, features, attention; `.npy` feature cache and job outputs |
| Pillow | 12.3.0 | inference | MIT-CMU (HPND) | [ ] | python-pillow.org | Image objects returned by openslide-python; encoder input resize (bilinear, 224 px); JPEG tile encoding |
| Express | 5.2.1 | web | MIT | [ ] | expressjs.com | HTTP server and routing |
| OpenSeadragon | 6.1.1 | web | BSD-3-Clause | [ ] | openseadragon.github.io | Deep Zoom slide viewer in the browser; served from `node_modules` at `/vendor/openseadragon/` (D-059) |
| Node.js runtime | 24 LTS (`.nvmrc`); tests run on 24.21.0 | web | MIT | [ ] | nodejs.org | JavaScript runtime |
| Python runtime | 3.12 (3.12.12 on dev Mac) | inference | PSF | [ ] | python.org | Python runtime |

Add any transitive dependency that directly affects results (for example,
the patch encoder's model-definition library) as it is identified.

wsinfer-mil 0.1.0 (Apache-2.0) was used only in the model spike
(`spike/model` branch) and is not part of the system (D-038). Neither are
torchvision, scikit-image, or shapely, which it used: our segmentation
reproduces its mask exactly with OpenCV, and our encoder transform is
bit-identical to its torchvision transform (D-051).

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
| MIL model: gated ABMIL, CAMELYON16 metastasis (`kaczmarj/breast-lymph-nodes-metastasis.camelyon16`) | revision `507b473a727db6f216902b062d9b677f8a298689` | CC-BY-4.0 (model card) | [ ] | huggingface.co/kaczmarj | `torchscript_model.pt`, SHA-256 `b3e58653…ac9c`; full hash in `models/manifest.json`. Trained on CAMELYON16; test split held out. Credited in README |
| Patch encoder: CTransPath (`kaczmarj/CTransPath`, re-hosted; original by Wang et al.) | revision `d426c122c59cf1db044745ceebdf775064020a89` | GPL-3.0 (Hugging Face card; verify against original release) | [ ] | huggingface.co/kaczmarj/CTransPath | `torchscript_model.pt`, SHA-256 `8c5e08e0…35fe2`; full hash in `models/manifest.json`. Not redistributed (D-042) |
| CAMELYON16 slides | test split | TBD | [ ] | CAMELYON16 challenge | Never committed to the repo |

## Known anomalies review
For each item that affects results (PyTorch, OpenSlide, wsinfer-mil, the
models), record the date the issue tracker / release notes were reviewed
and any known bug that could affect this use.

| Component | Reviewed on | Relevant known issues | Impact / mitigation |
|---|---|---|---|
| MIL model file | 2026-10-07 | TorchScript file saved in training mode; dropout active unless `.eval()` is called | Non-deterministic output; mitigated by `.eval()` and a repeat-run test (D-040, REQ-020) |
| PyTorch 2.14 | 2026-10-07 | `torch.jit.load` deprecated (FutureWarning) | Still works in the pinned version; fallback is the MIL model's safetensors file (D-040) |
| PyTorch `DataLoader` under WSL2 | 2026-10-07 | Intermittent `cuMemHostAlloc` out-of-memory in the pin-memory thread (1 of 6 spike runs) | `pin_memory=False` (D-045) |
| wsinfer-mil tissue segmentation | 2026-10-07 | Fixed saturation threshold 7 counts tinted backgrounds as tissue | Our own segmentation with threshold 20 (D-039) |
