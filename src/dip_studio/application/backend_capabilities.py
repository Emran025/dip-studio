"""Runtime capability discovery for optional processing backends."""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackendCapability:
    name: str
    available: bool
    reason: str | None = None


def discover_backend_capabilities() -> tuple[BackendCapability, ...]:
    """Return explicit availability for optional dependencies.

    Discovery is isolated from processor imports so a missing optional
    package cannot prevent core application startup.
    """
    dependencies = (
        ("opencv", "cv2"),
        ("scikit-image", "skimage"),
        ("scipy", "scipy"),
    )
    capabilities: list[BackendCapability] = []
    for name, module in dependencies:
        available = importlib.util.find_spec(module) is not None
        capabilities.append(
            BackendCapability(
                name,
                available,
                None if available else f"Optional dependency '{module}' is unavailable",
            )
        )
    return tuple(capabilities)


def backend_capability(name: str) -> BackendCapability:
    for capability in discover_backend_capabilities():
        if capability.name == name:
            return capability
    raise KeyError(f"Unknown backend capability: {name}")
