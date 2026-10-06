"""GPU availability probe for the health endpoint.

PyTorch is imported lazily and is optional: until roadmap item 6 adds it,
the service reports no GPU rather than failing to start.
"""


def gpu_info() -> dict:
    """Report whether a CUDA GPU is usable, and its name; no GPU if torch is absent."""
    try:
        import torch
    except ImportError:
        return {"available": False, "name": None}

    if not torch.cuda.is_available():
        return {"available": False, "name": None}
    return {"available": True, "name": torch.cuda.get_device_name(0)}
