from dataclasses import dataclass

from dip_studio.processing.contracts import ProcessingRequest
from dip_studio.processing.engine import ProcessingEngine


@dataclass
class UppercaseProcessor:
    operation: str = "uppercase"

    def validate(self, request: ProcessingRequest) -> None:
        if request.operation != self.operation:
            raise ValueError("operation mismatch")

    def process(self, image: str, request: ProcessingRequest) -> str:
        return image.upper()


def test_processing_engine_delegates_without_owning_algorithm() -> None:
    engine = ProcessingEngine({"uppercase": UppercaseProcessor()})
    assert engine.run("dip", ProcessingRequest("uppercase")) == "DIP"


def test_processing_engine_rejects_unknown_operation() -> None:
    try:
        ProcessingEngine({}).run("dip", ProcessingRequest("missing"))
    except KeyError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("unknown operations must fail")
