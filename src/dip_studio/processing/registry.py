"""Assembles the ProcessingEngine with all registered processors."""
from __future__ import annotations

from typing import TYPE_CHECKING

from dip_studio.processing.engine import ProcessingEngine

if TYPE_CHECKING:
    from dip_studio.infrastructure.data_store import ImageDataStore


def build_processing_engine(data_store: ImageDataStore) -> ProcessingEngine:  # type: ignore[type-arg]
    """Register all available processors and return the configured engine."""
    from dip_studio.processing.processors.analysis import (
        SegmentationProcessor,
        ThresholdProcessor,
    )
    from dip_studio.processing.processors.color import (
        GrayscaleProcessor,
        HueSaturationProcessor,
    )
    from dip_studio.processing.processors.edge import (
        CannyProcessor,
        LaplacianProcessor,
        SobelProcessor,
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
        NegativeProcessor(data_store),
        GammaProcessor(data_store),
        LogTransformProcessor(data_store),
        BrightnessContrastProcessor(data_store),
        GaussianBlurProcessor(data_store),
        MedianBlurProcessor(data_store),
        BilateralFilterProcessor(data_store),
        SobelProcessor(data_store),
        CannyProcessor(data_store),
        LaplacianProcessor(data_store),
        HistogramEqualizationProcessor(data_store),
        CLAHEProcessor(data_store),
        ErodeProcessor(data_store),
        DilateProcessor(data_store),
        MorphOpenProcessor(data_store),
        MorphCloseProcessor(data_store),
        GrayscaleProcessor(data_store),
        HueSaturationProcessor(data_store),
        # Geometric transform processors
        RotateProcessor(data_store),
        FlipProcessor(data_store),
        CropProcessor(data_store),
        # Analysis and segmentation processors
        ThresholdProcessor(data_store),
        SegmentationProcessor(data_store),
        # Interactive toolbar bridge processors
        BlurToolProcessor(data_store),
        EdgeToolProcessor(data_store),
        MorphologyToolProcessor(data_store),
    ]

    processors_dict = {p.operation: p for p in processors_list}
    return ProcessingEngine(processors_dict)  # type: ignore[arg-type]
