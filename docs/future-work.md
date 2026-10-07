# Future work

Out of scope for v0.1. Listed so the boundaries are explicit.

- **Interactive heatmap**: serve per-patch coordinates and attention as JSON
  and draw them client-side, with hover tooltips (alternative to D-010).
- **Blur metric**: percent of patches below a variance-of-Laplacian
  threshold, computed inside the patch loop.
- **Input-type check**: detect slides the model was not trained for and
  refuse or warn.
- **Full de-identification**: strip label/macro images and identifying
  metadata from the file itself at acquisition.
- **Slide upload**: streamed, size-limited, resumable (removed by D-002).
- **Fine-tuning notebook**: e.g. adapt a pretrained MIL model with
  slide-level labels.
- **Optimized inference**: fp16 autocast benchmark, then TensorRT export of
  the patch encoder.
- **Docker image** for the inference service with GPU support.
- **CI and pre-commit**: lint, tests, OpenAPI contract drift check.
- **Cloud sync stub**: push completed results to a "cloud" endpoint to
  mirror a device-plus-cloud split.
- **Job cancellation.**
- **Registry change detection**: notice slide files that are removed or
  replaced after registration (see D-029).
- **Multi-file slide formats** such as `.mrxs` (excluded by D-026).
- **Scanner-adaptive tissue threshold**: set the saturation threshold
  relative to each slide's own background (e.g. most common value plus a
  margin) instead of the fixed 20 tuned on CAMELYON16 Philips scans (D-039).
- **Pale-fat detection**: keep adipose tissue that falls below the
  saturation threshold, e.g. with a brightness or texture cue.
- **Move off TorchScript**: load the MIL model's safetensors file into a
  re-implemented ABMIL module, and find a non-TorchScript encoder source,
  before `torch.jit` is removed from PyTorch (D-040).
- **Feature cache eviction**: size limit or age-based cleanup of
  `DATA_DIR/cache/` (D-046).
