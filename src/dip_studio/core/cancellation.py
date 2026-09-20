"""Cooperative cancellation and progress ports."""

from dataclasses import dataclass
from typing import Protocol

from dip_studio.core.errors import CancellationError


class CancellationToken(Protocol):
    @property
    def is_cancelled(self) -> bool: ...
    def throw_if_cancelled(self) -> None: ...


@dataclass
class MutableCancellationToken:
    is_cancelled: bool = False

    def cancel(self) -> None:
        self.is_cancelled = True

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise CancellationError("Operation cancelled")


class ProgressReporter(Protocol):
    def report(self, completed: int, total: int, message: str = "") -> None: ...
