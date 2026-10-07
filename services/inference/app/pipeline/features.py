"""Patch feature extraction with the CTransPath encoder (D-045).

Each patch is read from level 0 with OpenSlide, resized to 224 x 224 and
normalised, and the encoder turns a batch of them into 768-number feature
vectors. Reading and JPEG-decoding patches is the slow part, so a PyTorch
DataLoader does it in FEATURE_WORKERS separate processes while the GPU
encodes the previous batch (spike: 82 patches/s with 0 workers, 486/s
with 8).

- `forkserver`: worker processes are started from a small clean server
  process rather than forked from this one. Forking a process that has
  threads and a CUDA context can deadlock or crash the child.
- `pin_memory=False`: page-locked host memory failed intermittently under
  WSL2 in the spike; the copy cost is small next to decoding.
- Workers ignore Ctrl+C (SIGINT). A terminal sends it to every process in
  the group, workers included. A worker killed by it made the job fail
  INFERENCE_FAILED instead of stopping as INTERRUPTED (D-037, seen in
  manual testing). With workers ignoring it, the main process shuts down
  and the job stops at its next progress report.
- The forkserver preloads this module, so torch is imported once in the
  server rather than in every worker. Measured on test_062: worker
  start-up was about 3.1 s per job; now about 2.4 s for the first job
  (the server itself starts) and about 1 s after that.
- Progress is reported after every batch (REQ-010), which also gives the
  job worker a point to stop at on shutdown.
"""

import logging
import multiprocessing
import signal
import time
from collections.abc import Callable

import numpy as np
import openslide
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from app.pipeline import Report, Stage

logger = logging.getLogger(__name__)

BATCH_SIZE = 64
INPUT_PX = 224
# ImageNet channel statistics, which CTransPath was trained with.
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)


# The server is started on first use, with this module (and so torch)
# already imported; every worker is forked from it.
_FORKSERVER = multiprocessing.get_context("forkserver")
_FORKSERVER.set_forkserver_preload([__name__])


def _ignore_sigint(worker_id: int) -> None:
    """DataLoader worker_init_fn: leave Ctrl+C to the main process."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def to_input_tensor(patch: Image.Image) -> torch.Tensor:
    """RGB patch -> normalised (3, 224, 224) float32 tensor.

    Same three steps as wsinfer-mil's torchvision transform (Resize(224),
    ToTensor, Normalize), without torchvision: for PIL images torchvision's
    Resize calls Pillow's bilinear resize, which is what this does.
    """
    patch = patch.resize((INPUT_PX, INPUT_PX), Image.Resampling.BILINEAR)
    # (H, W, C) uint8 -> (C, H, W) float in [0, 1], as ToTensor does.
    x = torch.from_numpy(np.asarray(patch, dtype=np.uint8).copy())
    x = x.permute(2, 0, 1).float().div(255)
    return x.sub(MEAN).div(STD)


class PatchDataset(Dataset):
    """Level-0 patches of one slide, as encoder input tensors.

    Only the path, coordinates, and opener are stored, so the dataset can
    be pickled and sent to worker processes. Each process opens its own
    slide handle on first use.
    """

    def __init__(
        self,
        slide_path: str,
        coords: np.ndarray,
        patch_px: int,
        opener: Callable = openslide.OpenSlide,
    ) -> None:
        """Remember what to read; nothing is opened yet."""
        self.slide_path = slide_path
        self.coords = coords
        self.patch_px = patch_px
        self.opener = opener
        self._slide = None

    def __len__(self) -> int:
        """Number of patches."""
        return len(self.coords)

    def __getitem__(self, index: int) -> torch.Tensor:
        """Read one patch and return it as encoder input."""
        if self._slide is None:
            self._slide = self.opener(self.slide_path)
        x, y = (int(v) for v in self.coords[index])
        # read_region returns RGBA; area outside the slide is transparent
        # black, which convert("RGB") keeps as black (as in the spike).
        region = self._slide.read_region((x, y), 0, (self.patch_px, self.patch_px))
        return to_input_tensor(region.convert("RGB"))

    def __getstate__(self) -> dict:
        """Pickle without the open slide handle (it can't cross processes)."""
        state = self.__dict__.copy()
        state["_slide"] = None
        return state


def extract_features(
    dataset: PatchDataset,
    encoder,
    device: str,
    report: Report,
    num_workers: int,
) -> np.ndarray:
    """Encode every patch; return (N, 768) float32 features in patch order."""
    total = len(dataset)
    loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,  # features must stay in the same order as coords
        num_workers=num_workers,
        multiprocessing_context=_FORKSERVER if num_workers > 0 else None,
        worker_init_fn=_ignore_sigint if num_workers > 0 else None,
        pin_memory=False,
    )
    report(Stage.EXTRACTING_FEATURES, 0, total)
    started = time.perf_counter()
    batches = []
    done = 0
    with torch.inference_mode():
        for batch in loader:
            if done == 0:
                # Includes worker start-up, which D-045 asked us to measure.
                logger.info(
                    "First feature batch after %.2f s (%d workers)",
                    time.perf_counter() - started,
                    num_workers,
                )
            batches.append(encoder(batch.to(device)).float().cpu().numpy())
            done += len(batch)
            report(Stage.EXTRACTING_FEATURES, done, total)
    elapsed = time.perf_counter() - started
    logger.info(
        "Encoded %d patches in %.1f s (%.0f patches/s)",
        total,
        elapsed,
        total / elapsed if elapsed else 0.0,
    )
    return np.concatenate(batches)
