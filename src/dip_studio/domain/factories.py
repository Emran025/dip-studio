"""Factory functions for domain objects."""

from __future__ import annotations

from uuid import uuid4

from dip_studio.domain.model import (
    DocumentId,
    ImageDocument,
    ImageSpec,
    Layer,
    LayerId,
)


def new_document(name: str, width: int, height: int) -> ImageDocument:
    """Create a blank document with a single Background layer."""
    return ImageDocument(
        id=DocumentId(uuid4()),
        name=name,
        image=ImageSpec(width, height),
        layers=(Layer(LayerId(uuid4()), "Background"),),
    )


def document_from_import(
    name: str,
    image: ImageSpec,
    layer_name: str,
    buffer_id: str | None = None,
) -> ImageDocument:
    """Create a single-layer document from an imported image."""
    return ImageDocument(
        id=DocumentId(uuid4()),
        name=name,
        image=image,
        layers=(Layer(LayerId(uuid4()), layer_name, buffer_id=buffer_id),),
    )
