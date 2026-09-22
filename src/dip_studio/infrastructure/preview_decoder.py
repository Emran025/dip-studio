"""Infrastructure adapter for decoding preview bytes into RGBA arrays."""
from __future__ import annotations

from typing import Any

import numpy as np


def decode_rgba(image: Any) -> np.ndarray:
    """Decode an opened Pillow image into a contiguous RGBA array."""
    return np.ascontiguousarray(np.asarray(image.convert("RGBA"), dtype=np.uint8))
