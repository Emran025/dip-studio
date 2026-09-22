"""Image restoration and noise processors.

Covers three groups:

1. **Noise addition** — Gaussian, salt-and-pepper, uniform.
2. **Denoising** — Mean (box), frequency-domain Wiener, and OpenCV NLM.
3. **Quality metrics** — PSNR and SSIM (print to console, return image unchanged
   so the layer pipeline is not disrupted).

All processors extend :class:`~dip_studio.processing.processors._base.BaseProcessor`
and operate on NumPy arrays only (no Qt / PySide6).
"""
from __future__ import annotations

import math

import numpy as np

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors._base import BaseProcessor, _ensure_3ch, _param, _to_gray
from dip_studio.core.errors import OptionalBackendError


# ---------------------------------------------------------------------------
# Noise addition
# ---------------------------------------------------------------------------

class NoiseGaussianProcessor(BaseProcessor):
    """Add zero-mean Gaussian noise to all channels.

    Parameters
    ----------
    std  : float  standard deviation of noise (default 25)
    mean : float  mean of noise distribution (default 0)
    """

    operation = "noise_gaussian"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        std = float(_param(request, "std", "25"))
        mean = float(_param(request, "mean", "0"))
        rng = np.random.default_rng()
        noisy = arr.astype(np.float32) + rng.normal(mean, std, arr.shape).astype(np.float32)
        return np.clip(noisy, 0, 255).astype(np.uint8)


class NoiseSaltPepperProcessor(BaseProcessor):
    """Add salt-and-pepper noise (impulse noise).

    Parameters
    ----------
    density : float  fraction of pixels affected (default 0.05)
    """

    operation = "noise_salt_pepper"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        density = float(_param(request, "density", "0.05"))
        density = max(0.0, min(density, 1.0))
        rng = np.random.default_rng()
        rand_map = rng.random(arr.shape[:2])
        out = arr.copy()
        # Salt: lightest pixels; pepper: darkest pixels.
        salt_mask = rand_map < density / 2
        pepper_mask = (rand_map >= density / 2) & (rand_map < density)
        if arr.ndim == 2:
            out[salt_mask] = 255
            out[pepper_mask] = 0
        else:
            ch = min(arr.shape[2], 3)  # preserve alpha channel
            out[salt_mask, :ch] = 255
            out[pepper_mask, :ch] = 0
        return out


class NoiseUniformProcessor(BaseProcessor):
    """Add uniform random noise in a given range.

    Parameters
    ----------
    low  : float  lower bound of noise range (default -30)
    high : float  upper bound of noise range (default 30)
    """

    operation = "noise_uniform"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        low = float(_param(request, "low", "-30"))
        high = float(_param(request, "high", "30"))
        rng = np.random.default_rng()
        noise = rng.uniform(low, high, arr.shape).astype(np.float32)
        return np.clip(arr.astype(np.float32) + noise, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Denoising
# ---------------------------------------------------------------------------

def _box_filter(channel: np.ndarray, k: int) -> np.ndarray:
    """Pure-NumPy box filter using integral image (2-D only, float64)."""
    k = max(1, k)
    # Pad with edge values to handle borders.
    padded = np.pad(channel.astype(np.float64), k // 2, mode="edge")
    # Compute integral image for fast area sums.
    integral = padded.cumsum(axis=0).cumsum(axis=1)
    h, w = channel.shape
    result = np.zeros_like(channel, dtype=np.float64)
    for i in range(h):
        for j in range(w):
            # This nested loop is slow for large images.
            pass
    # Efficient sliding-window sum via integral image.
    r = k // 2
    p = np.pad(channel.astype(np.float64), r, mode="edge")
    ii = p.cumsum(axis=0).cumsum(axis=1)
    # Area sums using four-corner lookup.
    y1, x1 = 0, 0
    y2, x2 = h, w
    s = (
        ii[y2 + 2 * r, x2 + 2 * r]
        - ii[y1,        x2 + 2 * r]
        - ii[y2 + 2 * r, x1       ]
        + ii[y1,         x1       ]
    )
    # Use conv-like sliding window via stride tricks.
    from numpy.lib.stride_tricks import sliding_window_view
    windows = sliding_window_view(p, window_shape=(k, k))
    result = windows.mean(axis=(-2, -1))
    return result.astype(np.float64)


class DenoiseMeanProcessor(BaseProcessor):
    """Mean (box) filter denoising.

    Parameters
    ----------
    kernel_size : int  box filter size (default 3)
    """

    operation = "denoise_mean"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        k = max(1, int(float(_param(request, "kernel_size", "3"))))
        if k % 2 == 0:
            k += 1  # ensure odd
        try:
            from scipy.ndimage import uniform_filter  # type: ignore[import-untyped]
            if arr.ndim == 2:
                return np.clip(uniform_filter(arr.astype(np.float64), size=k), 0, 255).astype(np.uint8)
            out = arr.copy()
            for c in range(arr.shape[2]):
                out[:, :, c] = np.clip(uniform_filter(arr[:, :, c].astype(np.float64), size=k), 0, 255).astype(np.uint8)
            return out
        except ImportError:
            pass
        # Pure NumPy fallback
        from numpy.lib.stride_tricks import sliding_window_view
        pad = k // 2
        if arr.ndim == 2:
            p = np.pad(arr.astype(np.float64), pad, mode="edge")
            return np.clip(sliding_window_view(p, (k, k)).mean(axis=(-2, -1)), 0, 255).astype(np.uint8)
        out = arr.copy()
        for c in range(arr.shape[2]):
            p = np.pad(arr[:, :, c].astype(np.float64), pad, mode="edge")
            out[:, :, c] = np.clip(sliding_window_view(p, (k, k)).mean(axis=(-2, -1)), 0, 255).astype(np.uint8)
        return out


class DenoiseWienerProcessor(BaseProcessor):
    """Frequency-domain Wiener filter.

    Parameters
    ----------
    noise_var : float  assumed noise variance (default 1000)
    """

    operation = "denoise_wiener"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        noise_var = float(_param(request, "noise_var", "1000"))

        def _wiener_channel(ch: np.ndarray) -> np.ndarray:
            f = np.fft.fft2(ch.astype(np.float64))
            power = np.abs(f) ** 2
            h_wiener = power / (power + noise_var)
            restored = np.real(np.fft.ifft2(f * h_wiener))
            return np.clip(restored, 0, 255).astype(np.uint8)

        if arr.ndim == 2:
            return _wiener_channel(arr)
        out = arr.copy()
        for c in range(min(arr.shape[2], 3)):
            out[:, :, c] = _wiener_channel(arr[:, :, c])
        return out


class DenoiseNLMProcessor(BaseProcessor):
    """Non-local means denoising.

    Uses ``PIL.ImageFilter`` when Pillow is available, otherwise falls back to
    a simple 5×5 Gaussian approximation.

    Parameters
    ----------
    h          : float  filter strength (default 10)
    patch_size : int    patch size (default 7)

    Note
    ----
    Full NLM with arbitrary patch search requires OpenCV (``cv2.fastNlMeansDenoisingColored``)
    OpenCV is required; unavailable optional backends are reported explicitly.
    """

    operation = "denoise_nlm"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        # Try OpenCV first.
        try:
            import cv2  # type: ignore[import-untyped]
            h_val = float(_param(request, "h", "10"))
            rgb = arr[:, :, :3] if arr.ndim == 3 and arr.shape[2] >= 3 else _ensure_3ch(arr)
            denoised = cv2.fastNlMeansDenoisingColored(rgb, None, h_val, h_val, 7, 21)
            if arr.ndim == 3 and arr.shape[2] == 4:
                return np.concatenate([denoised, arr[:, :, 3:4]], axis=-1)
            return denoised
        except ImportError as exc:
            raise OptionalBackendError(
                "denoise_nlm requires the optional OpenCV backend"
            ) from exc


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------

class MetricPsnrProcessor(BaseProcessor):
    """Compute PSNR between the current layer and a reference buffer.

    The PSNR value is printed to the console and the input image is returned
    unchanged (metrics are for analysis, not pixel transformation).

    Parameters
    ----------
    reference_buffer_id : str  data-store key of the reference image (default '')
    """

    operation = "metric_psnr"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        ref_id = _param(request, "reference_buffer_id", "")
        if ref_id:
            try:
                ref = self._store.get(ref_id).astype(np.float64)
                cur = arr.astype(np.float64)
                if ref.shape == cur.shape:
                    mse = float(np.mean((cur - ref) ** 2))
                    if mse > 0:
                        psnr = 10.0 * math.log10(255.0 ** 2 / mse)
                        print(f"[DIP Studio] PSNR = {psnr:.2f} dB")
                    else:
                        print("[DIP Studio] PSNR = ∞ dB (identical images)")
                else:
                    print("[DIP Studio] PSNR: shape mismatch between current and reference")
            except KeyError:
                print(f"[DIP Studio] PSNR: reference buffer '{ref_id}' not found")
        return arr


class MetricSsimProcessor(BaseProcessor):
    """Compute a simplified SSIM between the current layer and a reference buffer.

    Prints the SSIM value and returns the input image unchanged.

    Parameters
    ----------
    reference_buffer_id : str  data-store key of the reference (default '')
    """

    operation = "metric_ssim"

    def _apply(self, arr: np.ndarray, request: ProcessingRequest) -> np.ndarray:
        ref_id = _param(request, "reference_buffer_id", "")
        if ref_id:
            try:
                ref = self._store.get(ref_id).astype(np.float64)
                cur = arr.astype(np.float64)
                if ref.shape == cur.shape:
                    ssim = _ssim(cur, ref)
                    print(f"[DIP Studio] SSIM = {ssim:.4f}")
                else:
                    print("[DIP Studio] SSIM: shape mismatch between current and reference")
            except KeyError:
                print(f"[DIP Studio] SSIM: reference buffer '{ref_id}' not found")
        return arr


def _ssim(img1: np.ndarray, img2: np.ndarray) -> float:
    """Simplified per-channel mean SSIM (Wang et al., 2004)."""
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    ssims: list[float] = []
    if img1.ndim == 2:
        channels = [(img1, img2)]
    else:
        n = min(img1.shape[2], img2.shape[2], 3)
        channels = [(img1[:, :, i], img2[:, :, i]) for i in range(n)]
    for ch1, ch2 in channels:
        mu1 = ch1.mean()
        mu2 = ch2.mean()
        sigma1_sq = ch1.var()
        sigma2_sq = ch2.var()
        sigma12 = float(np.mean((ch1 - mu1) * (ch2 - mu2)))
        numerator = (2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)
        denominator = (mu1 ** 2 + mu2 ** 2 + c1) * (sigma1_sq + sigma2_sq + c2)
        ssims.append(numerator / (denominator + 1e-12))
    return float(np.mean(ssims))
