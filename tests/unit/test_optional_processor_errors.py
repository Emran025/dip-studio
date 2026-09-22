import numpy as np
import pytest
import builtins

from dip_studio.core.errors import OptionalBackendError
from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.processors.active_contours import ActiveContoursProcessor
from dip_studio.processing.processors.restoration import DenoiseNLMProcessor
from dip_studio.processing.processors.segmentation_advanced import GrabCutStubProcessor


@pytest.mark.parametrize(
    ("processor_type", "operation"),
    [
        (DenoiseNLMProcessor, "denoise_nlm"),
        (GrabCutStubProcessor, "grabcut"),
        (ActiveContoursProcessor, "active_contours"),
    ],
)
def test_optional_processor_does_not_return_success_without_backend(
    processor_type: type, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ImageDataStore()
    source = store.allocate(np.zeros((8, 8, 3), dtype=np.uint8))
    if operation == "active_contours":
        import dip_studio.processing.processors.active_contours as module
        monkeypatch.setattr(module, "_SKIMAGE", False)
    else:
        backend = "cv2"
        original_import = builtins.__import__

        def blocked_import(name: str, *args: object, **kwargs: object) -> object:
            if name == backend:
                raise ImportError(name)
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(OptionalBackendError):
        processor_type(store).process(source, ProcessingRequest(operation))
