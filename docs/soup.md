# SOUP inventory (software of unknown provenance)

Every third-party component the system relies on. Versions come from
`services/inference/uv.lock` and `apps/web/package-lock.json` and are
updated whenever those change.

"Verified" means the license was checked against the installed package:
its wheel or npm metadata and its bundled license file (`.venv` on the
desktop for Python, `node_modules` for the web app). The date is when that
check was made. A package that bundles other code under further licenses
says so in its metadata; those are noted where they matter.

Versions were last checked against both lock files on 2026-10-08.

## Software

| Component | Version | Used by | License | Verified | Source | Function we rely on |
|---|---|---|---|---|---|---|
| PyTorch | 2.14.1 (`+cu132` CUDA build on Linux; CPU build on macOS, D-048) | inference | BSD-3-Clause (main `LICENSE`); wheel metadata adds Apache-2.0, BSL-1.0, MIT and BSD-2-Clause for bundled third-party code | [x] 2026-10-08 | pytorch.org | Tensor computation, GPU inference, TorchScript model loading, `DataLoader` with forkserver worker processes, encoder input normalisation |
| OpenCV (opencv-python-headless) | 5.0.0.93 | inference | Apache-2.0; bundled libraries in `LICENSE-3RD-PARTY.txt` | [x] 2026-10-08 | opencv.org | Tissue segmentation: colour conversion, median blur, threshold, morphology, connected components (D-039); heatmap colour map (TURBO) and PNG encoding (D-053) |
| CUDA runtime / driver | Runtime 13.2 and cuDNN 9.24 bundled in the PyTorch wheel; driver 610.57.01 (WSL) / 610.88 (Windows) | inference | NVIDIA proprietary (`License.txt` in each `nvidia-*` wheel; listed in the appendix). Driver: NVIDIA driver licence, installed on Windows, not checked from here | [x] 2026-10-08 (wheels) | nvidia.com | GPU execution |
| OpenSlide (C library, via openslide-bin) | 4.0.1 (openslide-bin 4.0.1.2) | inference | LGPL-2.1-only; bundled libraries (libtiff, libjpeg, libpng, zlib and others) under their own permissive licences, listed in the wheel metadata | [x] 2026-10-08 | openslide.org | Reading pyramidal WSI files: dimensions, levels, microns per pixel |
| openslide-python | 1.4.6 | inference | LGPL-2.1-only (the package also ships BSD-3-Clause and MIT example code we don't use) | [x] 2026-10-08 | openslide.org | Python bindings, Deep Zoom generator |
| FastAPI | 0.142.2 | inference | MIT | [x] 2026-10-08 | fastapi.tiangolo.com | HTTP API |
| Starlette | 1.7.0 | inference | BSD-3-Clause | [x] 2026-10-08 | starlette.dev | ASGI toolkit under FastAPI; we import its exception and middleware types directly |
| Pydantic | 2.13.5 | inference | MIT | [x] 2026-10-08 | pydantic.dev | Response models and request validation |
| Uvicorn | 0.54.0 | inference | BSD-3-Clause | [x] 2026-10-08 | uvicorn.org | ASGI server |
| NumPy | 2.5.3 | inference | BSD-3-Clause (bundled parts: 0BSD, MIT, Zlib, CC0-1.0) | [x] 2026-10-08 | numpy.org | Arrays for masks, patch coordinates, features, attention; `.npy` feature cache and job outputs |
| Pillow | 12.3.0 | inference | MIT-CMU (HPND) | [x] 2026-10-08 | python-pillow.org | Image objects returned by openslide-python; encoder input resize (bilinear, 224 px); JPEG tile encoding |
| Express | 5.2.1 | web | MIT | [x] 2026-10-08 | expressjs.com | HTTP server and routing |
| OpenSeadragon | 6.1.1 | web | BSD-3-Clause | [x] 2026-10-08 | openseadragon.github.io | Deep Zoom slide viewer in the browser; served from `node_modules` at `/vendor/openseadragon/` (D-059) |
| Node.js runtime | 24 LTS (`.nvmrc`); tests run on 24.21.0 | web | MIT | [ ] (Node is installed on the Mac only; check its `LICENSE`) | nodejs.org | JavaScript runtime |
| Python runtime | 3.12 (3.12.15 on the desktop, 3.12.12 on the Mac; both provided by uv) | inference | PSF-2.0 | [x] 2026-10-08 (desktop `LICENSE.txt`) | python.org | Python runtime |

Transitive dependencies are listed in the appendix. The ones that can
change a result are the NVIDIA libraries that PyTorch runs the models on
(cuBLAS, cuDNN, the CUDA runtime); they are pinned by the PyTorch build and
recorded there. The patch encoder needs no model-definition library: it is
a self-contained TorchScript file (D-040).

wsinfer-mil 0.1.0 (Apache-2.0) was used only in the model spike
(`spike/model` branch) and is not part of the system (D-038). Neither are
torchvision, scikit-image, or shapely, which it used: our segmentation
reproduces its mask exactly with OpenCV, and our encoder transform is
bit-identical to its torchvision transform (D-051).

## Development tools (not shipped)
Used to build and test the inference service; not loaded at runtime.

| Component | Version | Used by | License | Verified | Source | Function we rely on |
|---|---|---|---|---|---|---|
| uv | 0.9.7 | inference | MIT OR Apache-2.0 | [ ] (standalone binary, not in the lock file) | docs.astral.sh/uv | Python and dependency management, lockfile |
| pytest | 9.1.1 | inference | MIT | [x] 2026-10-08 | pytest.org | Test runner |
| httpx | 0.28.1 | inference | BSD-3-Clause | [x] 2026-10-08 | python-httpx.org | HTTP client behind FastAPI's TestClient |
| Ruff | 0.16.10 | inference | MIT | [x] 2026-10-08 | docs.astral.sh/ruff | Formatting and linting |

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
| Express 5.2 | 2026-10-08 | Express 5 reads `:id_files` as one parameter named `id_files` (route syntax changed from Express 4) | Tile route is a regular expression with named groups; tested (D-058) |
| OpenSeadragon 6.1.1 | 2026-10-08 | No way to cancel a pending `addSimpleImage` | A counter discards a heatmap that loads after the user moved on (D-063) |
| Node.js 24 | 2026-10-08 | `fetch` has no default timeout | Every device call has its own 5 s timeout; for streams it covers connecting only (D-057, D-060) |

## Appendix: transitive dependencies
Generated from the installed environments on 2026-10-08. Regenerate when a
lock file changes. Licences are as declared in each package's metadata.

The Python lock file has 59 entries: the 56 packages below and in the main
tables, the project itself, the CPU build of PyTorch 2.14.1 (macOS only,
D-048) and colorama 0.4.6 (Windows only, unused).

### Inference service (Linux desktop, `uv.lock`)

| Package | Version | Scope | License (wheel metadata) | Notes |
|---|---|---|---|---|
| annotated-doc | 0.0.5 | runtime | MIT | Used by FastAPI |
| annotated-types | 0.8.0 | runtime | MIT | Used by Pydantic |
| anyio | 4.15.1 | runtime | MIT | Async I/O under Starlette |
| certifi | 2026.7.22 | dev | MPL-2.0 | Test tooling (httpx, pytest) |
| click | 8.5.0 | runtime | BSD-3-Clause | Uvicorn command line |
| cuda-bindings | 13.4.3 | runtime | Apache-2.0 | Python bindings to CUDA, used by PyTorch |
| cuda-pathfinder | 1.8.3 | runtime | Apache-2.0 | Locates CUDA libraries for cuda-bindings |
| cuda-toolkit | 13.2.2 | runtime | not stated in metadata | Meta-package selecting the NVIDIA libraries below |
| filelock | 4.0.12 | runtime | MIT | Used by PyTorch |
| fsspec | 2026.9.0 | runtime | BSD-3-Clause | Used by PyTorch |
| h11 | 0.16.0 | runtime | MIT | HTTP/1.1 parser under Uvicorn |
| httpcore | 1.0.9 | dev | BSD-3-Clause | Test tooling (httpx, pytest) |
| idna | 3.20 | dev | BSD-3-Clause | Test tooling (httpx, pytest) |
| iniconfig | 2.3.0 | dev | MIT | Test tooling (httpx, pytest) |
| jinja2 | 3.1.6 | runtime | BSD License | Used by PyTorch code generation |
| markupsafe | 3.0.4 | runtime | BSD-3-Clause | Used by Jinja2 |
| mpmath | 1.3.0 | runtime | BSD | Used by SymPy |
| networkx | 3.7 | runtime | BSD-3-Clause | Used by PyTorch graph passes |
| nvidia-cublas | 13.4.1.3 | runtime | NVIDIA proprietary | cuBLAS: matrix multiply used by both models (affects results) |
| nvidia-cuda-cupti | 13.2.86 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-cuda-nvrtc | 13.2.86 | runtime | NVIDIA proprietary | Runtime kernel compilation |
| nvidia-cuda-runtime | 13.2.86 | runtime | NVIDIA proprietary | CUDA runtime (affects results) |
| nvidia-cudnn-cu13 | 9.24.0.43 | runtime | NVIDIA proprietary | cuDNN: convolution kernels used by the encoder (affects results) |
| nvidia-cufft | 12.2.0.57 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-cufile | 1.17.1.22 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-curand | 10.4.2.66 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-cusolver | 12.2.0.11 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-cusparse | 12.7.10.12 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-cusparselt-cu13 | 0.8.1 | runtime | NVIDIA Proprietary Software | CUDA library loaded by PyTorch |
| nvidia-nccl-cu13 | 2.30.7 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-nvjitlink | 13.4.92 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-nvshmem-cu13 | 3.4.5 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| nvidia-nvtx | 13.2.86 | runtime | NVIDIA proprietary | CUDA library loaded by PyTorch |
| opentelemetry-api | 1.45.1 | runtime | Apache-2.0 | Pulled in by FastAPI; no exporter configured, so nothing is sent |
| packaging | 26.3 | dev | Apache-2.0 OR BSD-2-Clause | Test tooling (httpx, pytest) |
| pluggy | 1.6.0 | dev | MIT | Test tooling (httpx, pytest) |
| pydantic-core | 2.46.5 | runtime | MIT | Validation engine under Pydantic |
| pygments | 2.21.0 | dev | BSD-2-Clause | Test tooling (httpx, pytest) |
| setuptools | 84.0.0 | runtime | MIT | Runtime dependency declared by PyTorch |
| sympy | 1.14.0 | runtime | BSD | Used by PyTorch shape reasoning |
| triton | 3.8.0 | runtime | MIT | PyTorch kernel compiler; only used by torch.compile, which we do not call |
| typing-extensions | 4.16.0 | runtime | PSF-2.0 | Typing backports |
| typing-inspection | 0.4.4 | runtime | MIT | Used by Pydantic |

### Web app (`package-lock.json`)

All runtime dependencies of Express 5 (OpenSeadragon has none). None of them touch slide data or results.

| Package | Version | License |
|---|---|---|
| accepts | 2.0.0 | MIT |
| body-parser | 2.3.0 | MIT |
| bytes | 3.1.2 | MIT |
| call-bind-apply-helpers | 1.0.2 | MIT |
| call-bound | 1.0.4 | MIT |
| content-disposition | 1.1.0 | MIT |
| content-type | 1.0.5 | MIT |
| content-type | 2.1.0 | MIT |
| cookie | 0.7.2 | MIT |
| cookie-signature | 1.2.2 | MIT |
| debug | 4.4.3 | MIT |
| depd | 2.0.0 | MIT |
| dunder-proto | 1.0.1 | MIT |
| ee-first | 1.1.1 | MIT |
| encodeurl | 2.0.0 | MIT |
| es-define-property | 1.0.1 | MIT |
| es-errors | 1.3.0 | MIT |
| es-object-atoms | 1.1.2 | MIT |
| escape-html | 1.0.3 | MIT |
| etag | 1.8.1 | MIT |
| finalhandler | 2.1.1 | MIT |
| forwarded | 0.2.0 | MIT |
| fresh | 2.0.0 | MIT |
| function-bind | 1.1.2 | MIT |
| get-intrinsic | 1.3.0 | MIT |
| get-proto | 1.0.1 | MIT |
| gopd | 1.2.0 | MIT |
| has-symbols | 1.1.0 | MIT |
| hasown | 2.0.4 | MIT |
| http-errors | 2.0.1 | MIT |
| iconv-lite | 0.7.3 | MIT |
| inherits | 2.0.4 | ISC |
| ipaddr.js | 1.9.1 | MIT |
| is-promise | 4.0.0 | MIT |
| math-intrinsics | 1.1.0 | MIT |
| media-typer | 1.1.1 | MIT |
| merge-descriptors | 2.0.0 | MIT |
| mime-db | 1.54.0 | MIT |
| mime-types | 3.0.2 | MIT |
| ms | 2.1.3 | MIT |
| negotiator | 1.1.0 | MIT |
| object-inspect | 1.13.4 | MIT |
| on-finished | 2.4.1 | MIT |
| once | 1.4.0 | ISC |
| parseurl | 1.3.3 | MIT |
| path-to-regexp | 8.4.2 | MIT |
| proxy-addr | 2.0.8 | MIT |
| qs | 6.16.0 | BSD-3-Clause |
| range-parser | 1.3.0 | MIT |
| raw-body | 3.0.2 | MIT |
| router | 2.2.0 | MIT |
| safer-buffer | 2.1.2 | MIT |
| send | 1.2.1 | MIT |
| serve-static | 2.2.1 | MIT |
| setprototypeof | 1.2.0 | ISC |
| side-channel | 1.1.1 | MIT |
| side-channel-list | 1.0.1 | MIT |
| side-channel-map | 1.0.1 | MIT |
| side-channel-weakmap | 1.0.2 | MIT |
| statuses | 2.0.2 | MIT |
| toidentifier | 1.0.1 | MIT |
| type-is | 2.1.0 | MIT |
| unpipe | 1.0.0 | MIT |
| vary | 1.1.2 | MIT |
| wrappy | 1.0.2 | ISC |
