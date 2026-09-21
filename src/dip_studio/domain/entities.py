"""Framework-independent domain entities — re-exports from model for backward compatibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from dip_studio.domain.model import ImageDocument  # noqa: F401 — re-export


@dataclass(frozen=True, slots=True)
class DocumentId:
    value: UUID = field(default_factory=uuid4)
