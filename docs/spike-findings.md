# Spike findings

Filled in from the throwaway notebook on branch `spike/model`.
Pipeline work (roadmap items 6 and 7) depends on these answers.

## Environment
- OS / WSL distro:
- GPU driver version:
- CUDA version:
- Python version:
- PyTorch version:
- OpenSlide version:
- wsinfer-mil version:

## Model
- MIL model repo/name and revision:
- Where weights live on disk, and their SHA-256:
- Model config (patch size in microns, feature extractor, class names):
- Patch encoder (name, weights source, embedding dimension):
- Model card: what data was it trained on? Is the CAMELYON16 test split
  held out?
- License of the model weights:
- License of the patch encoder weights:

## Attention access
- Output of `model.code` (paste the relevant part):
- Does `forward()` return attention? If not, how did we get it
  (submodule call, re-implemented ABMIL with `state_dict()`)?
- Attention shape and value range on a real slide:

## Pipeline behaviour
- Tissue segmentation method WSInfer-MIL uses (and whether we reuse it):
- Can we run the stages individually (for progress reporting), or only
  end-to-end?
- Do CAMELYON16 files report microns per pixel?

## Timing on the RTX 3090
| Slide | Size | Patches | Segment | Patch | Features | MIL | Total | Peak GPU mem |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

## Demo slides chosen
| Slide | Ground truth | Why chosen |
|---|---|---|
| | positive (large metastasis) | heatmap should clearly light up |
| | negative | contrast |
| | | small, for live run |
| | positive (small metastasis) | optional hard case |

## Surprises / gotchas
-
