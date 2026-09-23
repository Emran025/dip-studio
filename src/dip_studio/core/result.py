"""Small typed result primitive shared by application boundaries."""

from dataclasses import dataclass
from typing import TypeVar

ValueT = TypeVar("ValueT")


@dataclass(frozen=True, slots=True)
class Result[ValueT]:
    value: ValueT | None = None
    error: Exception | None = None

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @classmethod
    def ok(cls, value: ValueT) -> "Result[ValueT]":
        return cls(value=value)

    @classmethod
    def failure(cls, error: Exception) -> "Result[ValueT]":
        return cls(error=error)
