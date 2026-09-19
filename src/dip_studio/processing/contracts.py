"""Pure processing contracts; concrete algorithms live behind these ports."""

from dataclasses import dataclass
from typing import Protocol, TypeVar

InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    operation: str
    parameters: tuple[tuple[str, str], ...] = ()


class Processor(Protocol[InputT, OutputT]):
    operation: str

    def validate(self, request: ProcessingRequest) -> None: ...
    def process(self, image: InputT, request: ProcessingRequest) -> OutputT: ...
