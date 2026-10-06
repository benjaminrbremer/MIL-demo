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
