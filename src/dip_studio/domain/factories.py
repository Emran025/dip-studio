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


def document_from_import(name: str, image: ImageSpec, layer_name: str) -> ImageDocument:
    layer = Layer(LayerId(uuid4()), layer_name or "Imported image")
    return ImageDocument(DocumentId(uuid4()), name, image, (layer,))
