from dip_studio.application.use_cases import CreateDocument
from dip_studio.infrastructure.in_memory_repository import InMemoryDocumentRepository


def test_create_document_uses_repository() -> None:
    repository = InMemoryDocumentRepository()
    document = CreateDocument(repository).execute("  sample  ")
    assert document.name == "sample"
    assert repository.get("sample") == document


def test_create_document_rejects_empty_name() -> None:
    try:
        CreateDocument(InMemoryDocumentRepository()).execute("   ")
    except ValueError as error:
        assert "empty" in str(error)
    else:
        raise AssertionError("empty document name must fail")
