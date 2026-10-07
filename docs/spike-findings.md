# Spike findings

Filled in from the throwaway notebook on branch `spike/model`.
Pipeline work (roadmap items 6 and 7) depends on these answers.

Spike run on 2026-10-07. Decisions that came out of it: D-038 to D-048. Notebook: `spike/spike_model.ipynb` (scratch uv
project in `spike/`, separate from `services/inference/`). Executed with
`HF_HUB_OFFLINE=1`, so the whole pipeline runs without network access once
the weights are cached.

## Environment
- OS / WSL distro: Ubuntu 26.04.1 LTS on WSL2, kernel 6.18.40.1-microsoft-standard-WSL2
  (Windows host; WSL has 15 GiB RAM, 16 logical CPUs)
- GPU: NVIDIA GeForce RTX 3090, 24 GiB
- GPU driver version: 610.57.01 (WSL `nvidia-smi`); Windows kernel-mode driver 610.88
- CUDA version: driver supports CUDA 13.3; PyTorch wheel bundles CUDA runtime 13.2
  and cuDNN 9.24.0. No system CUDA toolkit (`nvcc`) is installed or needed.
- Python version: 3.12.15 (provisioned by uv)
- PyTorch version: 2.14.1+cu132 (torchvision 0.29.1+cu132)
- OpenSlide version: 4.0.1 (openslide-bin 4.0.1.2), openslide-python 1.4.6
- wsinfer-mil version: 0.1.0 (the only release; Apache-2.0)
- Other libraries the wsinfer-mil stages use: tiffslide 2.5.0, opencv-python-headless
  5.0.0.93, scikit-image 0.26.0, shapely 2.2.0, numpy 2.5.3, huggingface-hub 2.1.1
- Spike-only pins needed to make wsinfer-mil 0.1.0 import at all: `zarr<3`
  (2.18.7) and `tifffile<2025.5` (2025.3.30). See Surprises.

## Model
- MIL model repo/name and revision: `kaczmarj/breast-lymph-nodes-metastasis.camelyon16`,
  revision `507b473a727db6f216902b062d9b677f8a298689`. Not gated.
  (The newer `kaczmarj/metastasis-detection.camelyon16.abmil.*` family is gated,
  CC-BY-NC-ND, and its access form rejects non-institutional email, so it is not usable.)
- Where weights live on disk, and their SHA-256 (Hugging Face cache, `~/.cache/huggingface/hub/`):
  - MIL model `torchscript_model.pt` (1.3 MiB):
    `b3e58653c39af79b5d2111ca1661c2c7e9bd12656ef8a11f1319a8aceaddac9c`
  - CTransPath `torchscript_model.pt` from `kaczmarj/CTransPath` revision
    `d426c122c59cf1db044745ceebdf775064020a89` (106.2 MiB):
    `8c5e08e059f553087e124aea270dcb8daf147f7b2bc88624725bef68c7335fe2`
- Model config: `{"type": "abmil", "patch_size_um": 128, "feature_extractor": "ctranspath",
  "num_classes": 2, "class_names": ["no-metastasis", "metastasis"]}`
- Patch encoder: CTransPath (TorchScript), weights from Hugging Face `kaczmarj/CTransPath`.
  Input: 128 µm patch resized to 224 px, ImageNet mean/std normalisation.
  Embedding dimension 768.
- Model card: trained on CAMELYON16 only. Train 243 / validation 27 slides (stratified
  split of the CAMELYON16 training set); test 129 = the official CAMELYON16 test set.
  Reported test AUC 0.91. **The test split is held out:** the repo ships
  `slide_ids_{train,val,test}.txt`; `test_001`, `test_062`, `test_065` and `test_128`
  appear only in the test list. This confirms the assumption in D-018.
- License of the model weights: CC-BY-4.0 (Hugging Face model card). Research use only,
  not for clinical use.
- License of the patch encoder weights: GPL-3.0 according to the `kaczmarj/CTransPath`
  model card. Still to verify against the original CTransPath release before marking
  it verified in `docs/soup.md`.

## Attention access
- Output of `model.code` (relevant part):
  ```
  H0 = (encoder).forward(H, )               # Linear 768->256, ReLU, Dropout
  A = (attention_weights).forward(H0, )     # gated attention: Linear(tanh) * Linear(sigmoid) -> Linear 256->1
  A0 = torch.transpose(A, 1, 0)
  A1 = softmax(A0, 1)
  M = torch.mm(A1, H0)                      # attention-weighted bag embedding
  logits = (head).forward(M, )              # Linear 256->2
  return AttentionMILModelOutput(logits, A)
  ```
  Gated ABMIL, 329,219 parameters. Submodules: `encoder` (Sequential),
  `attention_weights` (GatedAttentionLayer), `head` (Linear).
- Does `forward()` return attention? **Yes.** `model(H)` returns `(logits, A)`. No
  submodule calls or re-implementation are needed. Note that `A` is the **raw
  pre-softmax score**, not the softmax weights the model actually uses. For the
  heatmap that doesn't matter: softmax is monotonic, so percentile normalisation
  gives the same ranking. If we ever want the weights, compute `softmax(A.T, dim=1)`.
- Attention shape and value range on a real slide (test_062, default mask, 11,728 patches):
  shape `(N, 1)` float32; raw scores from -8.43 to -1.25, mean -5.03; percentiles
  1/50/99/99.9 = -7.81 / -4.75 / -3.54 / -3.04. GPU and CPU outputs agree to within 2e-6.
- **Must call `.eval()`.** The TorchScript file loads with `training=True` and
  wsinfer-mil never calls `.eval()`, so its three dropout layers (one in `encoder`,
  `dropout(0.25)` in each attention branch) stay active and
  every run gives a different answer. See Surprises.

## Pipeline behaviour
- Tissue segmentation method WSInfer-MIL uses: 2048 px thumbnail → HSV saturation
  channel → median blur (7) → **fixed threshold at 7** → morphological closing (6 px) →
  remove objects < 200² µm² and fill holes < 190² µm². Patching: a global,
  non-overlapping grid of 128 µm patches (566 px at 0.226 mpp) from the slide origin;
  a patch is kept if its centre is inside the tissue polygon (shapely STRtree).
  - **Do not reuse the threshold of 7.** The Philips CAMELYON16 scans have a lavender
    background at saturation of about 8, so the mask covers 96% / 65% / 100% of
    test_062 / test_001 / test_128. Patches on blank glass dominate the bag and get
    *higher* attention than most tissue (2 of the top 6 patches on test_062 are empty).
  - **Decided (D-039): same method, fixed threshold of 20.** Every other
    parameter stays as in wsinfer-mil. Tissue fractions after closing and small-object
    removal (notebook section 13):

    | Slide | Background sat (p25) | @ 7 (wsinfer-mil) | @ 20 (recommended) | @ Otsu (threshold) |
    |---|---|---|---|---|
    | test_001 | 7 | 0.652 | 0.277 | 0.157 (63) |
    | test_062 | 8 | 0.962 | 0.189 | 0.124 (60) |
    | test_065 | 2 | 0.270 | 0.098 | 0.059 (38) |
    | test_128 | 8 | 0.999 | 0.217 | 0.134 (58) |

  - Effect on test_062 (same embeddings, only the patch set changes):

    | Mask | Patches | Tissue area | P(metastasis) |
    |---|---|---|---|
    | @ 7 | 11,728 | 190.9 mm² | 0.163 |
    | @ 20 | 2,226 | 37.5 mm² | 0.135 |
    | @ Otsu | 1,435 | 24.5 mm² | 0.218 |

    With threshold 20, all six top-attention patches are cellular tissue, the same six
    that Otsu finds.
  - **Why not Otsu (per-slide)?** Tried and rejected. Random full-resolution patches from
    the band that 20 keeps and Otsu drops are real tissue: dense lymphocytes between fat
    cells (lymph-node tissue, where a metastasis could be), perinodal fat with
    lymphocytes, loose stroma and collagen. Otsu (about 60) splits "dense purple node"
    from "everything else", not tissue from glass, so it discards 30–40% of real tissue.
    The only thing it removes that we'd want removed is some blue margin ink on test_128.
  - **Known limitation of 20.** Pale fat (mostly empty adipocytes) has the same
    saturation (about 7–20) as the tinted Philips background, so no single saturation
    threshold can keep it on these slides. On test_001 and test_065 (lighter background),
    the 7-only band follows the tissue outline and looks like perinodal fat in the
    thumbnail. That was not checked at full resolution. Losing mostly empty fat matters
    least for metastasis detection. The threshold is tuned to these scans: a scanner
    with a more saturated background would need retuning. Proposed controls for the
    risk register / item 7: record the threshold in the decision log (D-039), and flag
    tissue fraction > 0.6 as a likely segmentation failure (REQ-021, RISK-003) (both failed slides were
    0.96–1.00 at threshold 7; the highest at 20 is 0.28).
  - Possible later step (future work): a threshold relative to each slide's own background
    (e.g. the most common saturation value plus a margin) would adapt across scanners.
  - The prediction depends on the mask (0.135–0.218 on test_062). Ground truth for the
    staged slides is still needed before judging which is "right"; P(metastasis) is
    below 0.3 under all three masks.

  - The segmentation and patching functions only need a thumbnail, the level-0
    dimensions and mpp, so they work with **OpenSlide** in place of tiffslide. Masks
    and patch coordinates came out identical.
- Can we run the stages individually (for progress reporting), or only end-to-end?
  **Individually.** `infer_one_slide()` is just a sequence of stages: `segment_tissue`,
  `patch_tissue`, `WSIPatches` + `DataLoader` + encoder, then the MIL model. Calling them
  one by one gives bit-identical coordinates and embeddings to the CLI run.
  - Per-batch progress: `get_embeddings()` has only a tqdm bar, so we write the same
    10-line loop ourselves and call `report(done, total)` after each batch. On test_062
    that gave 184 callbacks, a median of 79 ms apart; the first one arrives after about
    1.3 s while DataLoader workers start.
  - The prototype `run_pipeline(path, report)` (notebook section 12, the D-036 shape)
    produced 189 progress events. Stages: segmenting 0.10 s, patching 0.07 s,
    extracting features 23.5 s, aggregating 0.04 s. **Feature extraction is about 99%
    of the run**, so the progress bar should be driven by patch count, and the other
    stages can be fast stage labels.
- Do CAMELYON16 files report microns per pixel? **Yes**, for all four staged slides
  (Philips TIFF): `openslide.mpp-x/y` ≈ 0.2263 µm/px (test_062: 0.226321 / 0.226316).
  `objective-power` is not set. OpenSlide and tiffslide agree on dimensions, levels
  (10, downsample 1–512) and mpp.
- Slide reader: wsinfer-mil reads with **tiffslide**, but OpenSlide works as a drop-in.
  Level-0 `read_region` pixels are identical (max diff 0 over 100 patches); embeddings
  differ by at most 6e-8; the probability is unchanged.
- DataLoader worker processes (feature throughput, first 3,200 patches):
  0 → 82, 2 → 181, 4 → 300, 8 → 467, 16 → 504 patches/s. With 0 workers the GPU is
  starved by JPEG decoding; 8 workers reaches about 93% of the maximum.

## Timing on the RTX 3090
Stage-by-stage pipeline with `.eval()`, 8 DataLoader workers, batch 64, default
wsinfer-mil segmentation (threshold 7). Values from the first notebook run; later runs
were within a few percent.

| Slide | Size | Patches | Segment | Patch | Features | MIL | Total | Peak GPU mem |
|---|---|---|---|---|---|---|---|---|
| test_062 (135168 × 28672), threshold 7 | 455 MiB | 11,728 | 0.11 s | 0.07 s | 23.8 s | 46 ms (CPU), 9 ms (GPU) | 23.7 s | 0.80 GiB torch-allocated; about 1.9 GB above idle in `nvidia-smi` (includes CUDA context) |
| test_062, threshold 20 (recommended) | 455 MiB | 2,226 | ~0.1 s | ~0.1 s | ~4.6 s (estimated: 2,226 patches at 486 patches/s; not run separately) | | | |

End-to-end CLI (`wsinfer-mil run`, 16 workers, includes Python start-up and model
loading): 31.6 s wall, 2.0 GB peak RAM, no-metastasis 0.834961 / metastasis 0.165039
(with dropout on, so not reproducible; see Surprises).

## Demo slides chosen
Staged in `~/slides-staging/` (all in the model's test split). Ground truth still to
be filled in from the CAMELYON16 reference file.

| Slide | Ground truth | Why chosen |
|---|---|---|
| | positive (large metastasis) | heatmap should clearly light up |
| | negative | contrast |
| | | small, for live run |
| | positive (small metastasis) | optional hard case |

Staged so far: test_001 (1.09 GiB), test_062 (455 MiB), test_065 (428 MiB),
test_128 (472 MiB).

## Surprises / gotchas
- **Non-deterministic output from wsinfer-mil.** The MIL TorchScript file is saved in
  training mode, and `infer_one_slide()` never calls `.eval()`. Its dropout layers are
  active, so five runs on the same embeddings gave P(metastasis) of 0.164–0.167.
  With `.eval()` the result is a stable 0.162904. Our pipeline must call `.eval()` after
  loading, and a test should check that two runs give identical output. This is a
  risk-register item. CTransPath is not affected: its loader calls `.eval()`.
- **wsinfer-mil's tissue threshold (7) fails on these slides** (see Pipeline behaviour).
  This affects the prediction, the attention heatmap, the patch count and the
  tissue-area quality metric (D-011): it reports 191 mm² of "tissue" for test_062
  instead of about 38 mm². Decided: threshold 20 (D-039). Per-slide Otsu was tried and
  rejected because it drops real tissue.
- **Intermittent pinned-memory failure under WSL2.** One of six notebook runs failed in
  the DataLoader's `pin_memory` thread with `CUDA error: out of memory`
  (`cuMemHostAlloc` returned `CUDA_ERROR_OUT_OF_MEMORY`): page-locked *host* memory,
  not GPU memory (GPU and RAM were mostly free). An identical re-run passed. WSL2
  limits pinned memory. Decided: `pin_memory=False` (D-045); the transfer cost is
  small next to JPEG decoding.
- **wsinfer-mil 0.1.0 does not import with current libraries.** It patches
  `zarr.storage.KVStore` (removed in zarr 3), and its tiffslide 2.x needs a pre-2025.5
  tifffile when used with zarr 2. The package is unmaintained against today's stack,
  which argues against making it a runtime dependency.
- **`torch.jit.load` is deprecated** in PyTorch 2.14 (FutureWarning: "switch to
  torch.export"). It still works. The MIL repo also ships `model.safetensors` and
  `model.onnx`, and the ABMIL architecture is small and fully visible in `model.code`,
  so loading the safetensors into a re-implemented module is a fallback if TorchScript
  goes away.
- **CTransPath is downloaded without a pinned revision** by wsinfer-mil
  (`hf_hub_download(repo_id="kaczmarj/CTransPath", ...)`). We must pin the revision
  and verify the hash ourselves (REQ-016).
- **The wsinfer-mil cache is keyed by file name** (`~/.cache/wsinfer-mil/cache/128um/<filename>_md5-<quickhash>/`).
  That conflicts with D-009 (no original filenames). Don't use its `Cache`; our
  SHA-256 feature cache (D-008) replaces it.
- scikit-image 0.26 prints FutureWarnings for `binary_closing`, `min_size` and
  `area_threshold` in wsinfer-mil's segmentation. Behaviour is unchanged for now.
- The CLI uses one DataLoader worker *process* per core by default (16 here). The
  service runs extraction from a worker thread inside the FastAPI process, so
  forking worker processes from there needs care (or a fixed, smaller count).
- The uv cache was corrupted when the WSL disk filled up during the first install
  ("Invalid Wheel-Version in WHEEL file"). `uv cache clean` fixed it.
