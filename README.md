# wsi-mil-demo

A device-style demo of slide-level analysis of gigapixel whole-slide images
using a pretrained multiple instance learning (MIL) model.

> Research demo only. Not for clinical use.

## Components
- `services/inference/` - Python inference service (the "device")
- `apps/web/` - Node.js web app

## Documentation
- [Architecture](docs/architecture.md)
- [API contract](docs/api-contract.md)
- [Requirements](docs/requirements.md)
- [Risk register](docs/risk-register.md)
- [SOUP inventory](docs/soup.md)
- [Decision log](docs/decisions.md)
- [Roadmap](docs/roadmap.md)

## Running
Two machines: the inference service ("device") runs on a Linux machine
with an NVIDIA GPU (developed in WSL2 with an RTX 3090), and the web app
runs on a Mac. They talk over Tailscale. More detail on each component is
in `services/inference/CLAUDE.md` and `apps/web/CLAUDE.md`; the design is
in [Architecture](docs/architecture.md).

### Prerequisites
- Device: [uv](https://docs.astral.sh/uv/), an NVIDIA driver supporting
  CUDA 13.2, and Tailscale. uv installs Python 3.12 and every dependency,
  including OpenSlide, from the lock file; no system packages are needed.
- Web app: Node.js 24 (`apps/web/.nvmrc`; e.g. `nvm use`).
- Both machines signed in to the same Tailscale account.

### 1. Inference service (device)
```sh
cd services/inference
uv sync
uv run python scripts/fetch_models.py   # once: downloads pinned weights, checks SHA-256
cp .env.example .env                    # then fill in the values below
```
In `.env`:
- `DEVICE_TOKEN`: a shared secret of at least 32 characters, e.g.
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The web
  app uses the same value.
- `ACQUISITION_DIR`: the folder to watch for slides. In WSL2, keep it in
  the Linux filesystem (e.g. `~/mil/acquisition`), not under `/mnt/c`.
- `DATA_DIR`: where the SQLite database, feature cache and job outputs go
  (e.g. `~/mil/data`).

Connect the device to Tailscale (once per machine; under WSL2, inside WSL):
```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=mil-device
```

Start the service, bound to the Tailscale address only:
```sh
uv run --env-file .env uvicorn app.main:create_app --factory \
  --host $(tailscale ip -4) --port 8000 --timeout-graceful-shutdown 5
```
For local work without Tailscale, use `--host 127.0.0.1` instead.

The service refuses to start if a model file is missing or doesn't match
its hash. Under WSL2, keep this terminal open: WSL shuts down, and leaves
the tailnet, when nothing is running in it.

Check from the Mac: `curl http://mil-device:8000/v1/health` returns JSON.

### 2. Web app (Mac)
```sh
cd apps/web
nvm use        # Node 24
npm install
cp .env.example .env
```
In `.env`:
- `INFERENCE_URL=http://mil-device:8000` (or the device's `100.x`
  Tailscale address if the name doesn't resolve)
- `DEVICE_TOKEN`: the same value as on the device
- `PORT=3000` (optional)

```sh
npm start
```
Open <http://127.0.0.1:3000>. The server listens on localhost only.

### 3. Analyse a slide
1. Copy a slide (`.tif`, `.tiff`, `.svs`, `.ndpi`, `.scn` or `.bif`) into
   `ACQUISITION_DIR`. From Windows, the WSL folder is reachable at
   `\\wsl$\<distro>\home\<user>\...`. The model was trained on
   CAMELYON16 H&E lymph-node slides; the demo uses that challenge's test
   split.
2. The slide appears in the list as arriving, then ready, a few seconds
   after the copy finishes.
3. Select it, start analysis, and watch progress. When the job completes,
   the results panel and the attention heatmap appear.

### Tests
```sh
# from the repository root
(cd services/inference && uv run pytest)   # fake models, runs anywhere
(cd apps/web && npm test)                  # fake device, no .env needed
```
Real-model tests (device GPU, needs weights and a slide), in
`services/inference`:
`MIL_TEST_SLIDE=/path/to/slide.tif uv run pytest -m "models or slide"`.

## License
MIT. Third-party components, models, and data carry their own licenses;
see `docs/soup.md`.

### Models and data
- MIL model: "Metastasis classification (CAMELYON16)" by Jakub Kaczmarzyk,
  `kaczmarj/breast-lymph-nodes-metastasis.camelyon16` on Hugging Face,
  CC-BY-4.0. Used unmodified.
- Patch encoder: CTransPath (Wang et al.), weights from `kaczmarj/CTransPath`
  on Hugging Face, GPL-3.0 per the model card. Used unmodified.
- Model weights and slides are downloaded locally and never redistributed
  with this repository.
