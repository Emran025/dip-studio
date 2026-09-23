"""Frequency-domain processors using NumPy FFT.

All processors convert colour images to per-channel float, apply a
frequency-domain filter, then reconstruct the image.  No external library
beyond NumPy is required.

Operations
----------
fft_spectrum   : log-magnitude spectrum visualisation
fft_lowpass    : ideal / Butterworth / Gaussian low-pass filter
fft_highpass   : ideal / Butterworth / Gaussian high-pass filter
fft_bandpass   : band-pass (inner + outer radius)
fft_notch      : notch (reject) filter at a custom frequency coordinate
"""

from __future__ import annotations

import numpy as np

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _param, _to_gray

# ---------------------------------------------------------------------------
# Frequency-domain mask builders
# ---------------------------------------------------------------------------


def _distance_map(h: int, w: int) -> np.ndarray:
    """Return (H, W) float64 array of Euclidean distance from the DC centre."""
    cy, cx = h // 2, w // 2
    y = np.arange(h, dtype=np.float64) - cy
    x = np.arange(w, dtype=np.float64) - cx
    yy, xx = np.meshgrid(y, x, indexing="ij")
    return np.sqrt(yy**2 + xx**2)


def _lowpass_mask(h: int, w: int, radius: float, kind: str, order: int = 2) -> np.ndarray:
    """Build a centred low-pass frequency mask in [0, 1]."""
    d = _distance_map(h, w)
    r = max(radius, 1e-9)
    if kind == "ideal":
        return (d <= r).astype(np.float64)
    elif kind == "butterworth":
        return 1.0 / (1.0 + (d / r) ** (2 * order))
    else:  # gaussian (default)
        return np.exp(-0.5 * (d / r) ** 2)


def _highpass_mask(h: int, w: int, radius: float, kind: str, order: int = 2) -> np.ndarray:
    return 1.0 - _lowpass_mask(h, w, radius, kind, order)


def _apply_fft_filter(channel: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Apply *mask* (centred) to the FFT of *channel* and return real uint8."""
    f = np.fft.fft2(channel.astype(np.float64))
    f_shift = np.fft.fftshift(f)
    filtered_shift = f_shift * mask
    f_back = np.fft.ifftshift(filtered_shift)
    result = np.real(np.fft.ifft2(f_back))
    return np.clip(result, 0, 255).astype(np.uint8)


def _per_channel_filter(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Apply *mask* to every colour channel independently; preserve shape."""
    if arr.ndim == 2:
        return _apply_fft_filter(arr, mask)
    result = arr.copy()
    ch = arr.shape[2]
    n = min(ch, 3)  # apply to RGB, leave alpha untouched
    for c in range(n):
        result[:, :, c] = _apply_fft_filter(arr[:, :, c], mask)
    return result


# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------


class FftSpectrumProcessor(BaseProcessor):
    """Render the log-magnitude FFT spectrum as a displayable greyscale image."""

    operation = "fft_spectrum"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        gray = _to_gray(arr)
        f = np.fft.fft2(gray.astype(np.float64))
        f_shift = np.fft.fftshift(f)
        magnitude = np.log1p(np.abs(f_shift))
        magnitude = magnitude / (magnitude.max() + 1e-9) * 255.0
        spec = magnitude.astype(np.uint8)
        # Return as 3-channel so it can be viewed like any layer.
        out = np.stack([spec, spec, spec], axis=-1)
        if arr.ndim == 3 and arr.shape[2] == 4:
            alpha = np.full((*out.shape[:2], 1), 255, dtype=np.uint8)
            out = np.concatenate([out, alpha], axis=-1)
        return out


class FftLowpassProcessor(BaseProcessor):
    """Low-pass filter in the frequency domain.

    Parameters
    ----------
    radius      : float  cutoff radius in pixels (default 30)
    filter_type : str    'gaussian' | 'butterworth' | 'ideal' (default 'gaussian')
    order       : int    Butterworth filter order (default 2)
    """

    operation = "fft_lowpass"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        h, w = arr.shape[:2]
        radius = float(_param(request, "radius", "30"))
        kind = _param(request, "filter_type", "gaussian").lower()
        order = int(float(_param(request, "order", "2")))
        mask = _lowpass_mask(h, w, radius, kind, order)
        return _per_channel_filter(arr, mask)


class FftHighpassProcessor(BaseProcessor):
    """High-pass filter in the frequency domain.

    Parameters
    ----------
    radius      : float  cutoff radius (default 30)
    filter_type : str    'gaussian' | 'butterworth' | 'ideal'
    order       : int    Butterworth order (default 2)
    """

    operation = "fft_highpass"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        h, w = arr.shape[:2]
        radius = float(_param(request, "radius", "30"))
        kind = _param(request, "filter_type", "gaussian").lower()
        order = int(float(_param(request, "order", "2")))
        mask = _highpass_mask(h, w, radius, kind, order)
        return _per_channel_filter(arr, mask)


class FftBandpassProcessor(BaseProcessor):
    """Band-pass filter: passes frequencies between *low_radius* and *high_radius*.

    Parameters
    ----------
    low_radius  : float  inner cutoff (high-pass part, default 10)
    high_radius : float  outer cutoff (low-pass part, default 40)
    filter_type : str    'gaussian' | 'butterworth' | 'ideal'
    """

    operation = "fft_bandpass"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        h, w = arr.shape[:2]
        low_r = float(_param(request, "low_radius", "10"))
        high_r = float(_param(request, "high_radius", "40"))
        kind = _param(request, "filter_type", "gaussian").lower()
        order = int(float(_param(request, "order", "2")))
        mask = _highpass_mask(h, w, low_r, kind, order) * _lowpass_mask(h, w, high_r, kind, order)
        return _per_channel_filter(arr, mask)


class FftNotchProcessor(BaseProcessor):
    """Notch (reject) filter: suppresses a specific frequency and its conjugate.

    Parameters
    ----------
    notch_x      : float  x-frequency offset from DC centre (default 0)
    notch_y      : float  y-frequency offset from DC centre (default 0)
    notch_radius : float  Gaussian notch width in pixels (default 5)
    """

    operation = "fft_notch"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        h, w = arr.shape[:2]
        nx = float(_param(request, "notch_x", "0"))
        ny = float(_param(request, "notch_y", "0"))
        nr = float(_param(request, "notch_radius", "5"))
        cy, cx = h // 2, w // 2
        y = np.arange(h, dtype=np.float64) - cy
        x = np.arange(w, dtype=np.float64) - cx
        yy, xx = np.meshgrid(y, x, indexing="ij")

        def _gauss_notch(ox: float, oy: float) -> np.ndarray:
            d2 = (xx - ox) ** 2 + (yy - oy) ** 2
            return np.exp(-0.5 * d2 / (nr**2 + 1e-9))

        # Reject the notch frequency and its symmetric partner.
        mask = 1.0 - _gauss_notch(nx, ny) - _gauss_notch(-nx, -ny)
        mask = np.clip(mask, 0.0, 1.0)
        return _per_channel_filter(arr, mask)
