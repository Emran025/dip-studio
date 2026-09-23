"""Assembles the ProcessingEngine with all registered processors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dip_studio.processing.engine import ProcessingEngine

if TYPE_CHECKING:
    from dip_studio.infrastructure.data_store import ImageDataStore
    from dip_studio.infrastructure.processing_cache import ProcessingCache


def build_processing_engine(
    data_store: ImageDataStore,
    cache: ProcessingCache | None = None,
) -> ProcessingEngine:  # type: ignore[type-arg]
    """Register all available processors and return the configured engine."""
    # Phase G — Active contours
    from dip_studio.processing.processors.active_contours import (
        ActiveContoursProcessor,
    )
    from dip_studio.processing.processors.analysis import (
        SegmentationProcessor,
        ThresholdProcessor,
    )
    from dip_studio.processing.processors.color import (
        GrayscaleProcessor,
        HueSaturationProcessor,
    )

    # Phase D — Computer Vision processors
    from dip_studio.processing.processors.cv.feature_extraction import (
        FastProcessor,
        GlcmTextureProcessor,
        OrbProcessor,
        SiftProcessor,
    )
    from dip_studio.processing.processors.cv.object_detection import (
        HoughCirclesProcessor,
        HoughLinesProcessor,
        TemplateMatchProcessor,
    )
    from dip_studio.processing.processors.edge import (
        CannyProcessor,
        LaplacianProcessor,
        SobelProcessor,
    )

    # Phase 2 — Frequency-domain processors
    from dip_studio.processing.processors.frequency import (
        FftBandpassProcessor,
        FftHighpassProcessor,
        FftLowpassProcessor,
        FftNotchProcessor,
        FftSpectrumProcessor,
    )
    from dip_studio.processing.processors.histogram import (
        CLAHEProcessor,
        HistogramEqualizationProcessor,
    )
    from dip_studio.processing.processors.intensity import (
        BrightnessContrastProcessor,
        GammaProcessor,
        LogTransformProcessor,
        NegativeProcessor,
    )
    from dip_studio.processing.processors.morphology import (
        DilateProcessor,
        ErodeProcessor,
        MorphCloseProcessor,
        MorphOpenProcessor,
    )

    # Phase 2 — Restoration and noise processors
    from dip_studio.processing.processors.restoration import (
        DenoiseMeanProcessor,
        DenoiseNLMProcessor,
        DenoiseWienerProcessor,
        MetricPsnrProcessor,
        MetricSsimProcessor,
        NoiseGaussianProcessor,
        NoiseSaltPepperProcessor,
        NoiseUniformProcessor,
    )

    # Phase 2 — Advanced segmentation processors
    from dip_studio.processing.processors.segmentation_advanced import (
        ConnectedComponentsProcessor,
        ContourExtractProcessor,
        GrabCutStubProcessor,
        HuMomentsProcessor,
        RegionGrowingProcessor,
        WatershedProcessor,
    )
    from dip_studio.processing.processors.spatial import (
        BilateralFilterProcessor,
        GaussianBlurProcessor,
        MedianBlurProcessor,
    )
    from dip_studio.processing.processors.tools import (
        BlurToolProcessor,
        EdgeToolProcessor,
        MorphologyToolProcessor,
    )
    from dip_studio.processing.processors.transform import (
        CropProcessor,
        FlipProcessor,
        RotateProcessor,
    )

    processors_list = [
        # Intensity
        NegativeProcessor(data_store),
        GammaProcessor(data_store),
        LogTransformProcessor(data_store),
        BrightnessContrastProcessor(data_store),
        # Spatial / blur
        GaussianBlurProcessor(data_store),
        MedianBlurProcessor(data_store),
        BilateralFilterProcessor(data_store),
        # Edge detection
        SobelProcessor(data_store),
        CannyProcessor(data_store),
        LaplacianProcessor(data_store),
        # Histogram
        HistogramEqualizationProcessor(data_store),
        CLAHEProcessor(data_store),
        # Morphology
        ErodeProcessor(data_store),
        DilateProcessor(data_store),
        MorphOpenProcessor(data_store),
        MorphCloseProcessor(data_store),
        # Colour
        GrayscaleProcessor(data_store),
        HueSaturationProcessor(data_store),
        # Geometric transforms
        RotateProcessor(data_store),
        FlipProcessor(data_store),
        CropProcessor(data_store),
        # Analysis and segmentation (basic)
        ThresholdProcessor(data_store),
        SegmentationProcessor(data_store),
        # Interactive toolbar bridge processors
        BlurToolProcessor(data_store),
        EdgeToolProcessor(data_store),
        MorphologyToolProcessor(data_store),
        # ── Phase 2: Frequency-domain ────────────────────────────────────────
        FftSpectrumProcessor(data_store),
        FftLowpassProcessor(data_store),
        FftHighpassProcessor(data_store),
        FftBandpassProcessor(data_store),
        FftNotchProcessor(data_store),
        # ── Phase 2: Restoration & noise ─────────────────────────────────────
        NoiseGaussianProcessor(data_store),
        NoiseSaltPepperProcessor(data_store),
        NoiseUniformProcessor(data_store),
        DenoiseMeanProcessor(data_store),
        DenoiseWienerProcessor(data_store),
        DenoiseNLMProcessor(data_store),
        MetricPsnrProcessor(data_store),
        MetricSsimProcessor(data_store),
        # ── Phase 2: Advanced segmentation ───────────────────────────────────
        WatershedProcessor(data_store),
        RegionGrowingProcessor(data_store),
        ContourExtractProcessor(data_store),
        HuMomentsProcessor(data_store),
        ConnectedComponentsProcessor(data_store),
        GrabCutStubProcessor(data_store),
        # ── Active contours (Phase G) ─────────────────────────────────────────
        ActiveContoursProcessor(data_store),
        # ── Computer Vision (Phase D) ─────────────────────────────────────────
        SiftProcessor(data_store),
        OrbProcessor(data_store),
        FastProcessor(data_store),
        GlcmTextureProcessor(data_store),
        TemplateMatchProcessor(data_store),
        HoughCirclesProcessor(data_store),
        HoughLinesProcessor(data_store),
    ]

    processors_dict = {p.operation: p for p in processors_list}
    return ProcessingEngine(processors_dict, cache=cache, data_store=data_store)  # type: ignore[arg-type]
