"""MIL aggregation: one slide-level prediction from all patch features.

The model is gated attention MIL (ABMIL). It scores every patch, turns
the scores into weights with a softmax, takes the weighted average of the
patch features as one slide feature, and classifies that. `model(H)`
returns `(logits, A)`, where `A` holds the raw per-patch scores *before*
the softmax (spike findings, "Attention access"). The heatmap only needs
their ranking, and softmax doesn't change the ranking, so the raw scores
are saved as they are.
"""

import numpy as np
import torch


def aggregate(mil, features: np.ndarray, device: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (class probabilities (C,), raw attention scores (N,)) for one slide."""
    with torch.inference_mode():
        logits, attention = mil(torch.from_numpy(features).to(device))
        probabilities = torch.softmax(logits, dim=1)[0]
    return (
        probabilities.cpu().numpy().astype(np.float64),
        attention.reshape(-1).cpu().numpy().astype(np.float32),
    )
