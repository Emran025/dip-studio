from uuid import uuid4

from dip_studio.domain.model import DocumentId, ImageDocument, ImageSpec, Layer, LayerId


def new_document(name: str, width: int, height: int) -> ImageDocument:
    background = Layer(LayerId(uuid4()), "Background")
    return ImageDocument(
        DocumentId(uuid4()),
        name,
        ImageSpec(width, height),
        (background,),
    )
