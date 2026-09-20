"""Named shortcut profiles built from the application's default bindings."""

from collections.abc import Mapping

from dip_studio.application.shortcut_registry import (
    ShortcutRegistry,
    default_shortcut_bindings,
)

DEFAULT_PROFILE = "DIP Studio Default"
PHOTOSHOP_PROFILE = "Photoshop-like"
LABORATORY_PROFILE = "DIP Laboratory"
CUSTOM_PROFILE = "Custom"

PROFILE_NAMES = (
    DEFAULT_PROFILE,
    PHOTOSHOP_PROFILE,
    LABORATORY_PROFILE,
    CUSTOM_PROFILE,
)

_PROFILE_OVERRIDES: dict[str, dict[str, str]] = {
    PHOTOSHOP_PROFILE: {
        "edit.redo": "Ctrl+Shift+Z",
        "tool.selection": "M",
        "tool.lasso": "L",
        "tool.crop": "C",
        "tool.hand": "H",
        "tool.zoom": "Z",
    },
    LABORATORY_PROFILE: {
        "edit.redo": "Ctrl+Shift+Y",
        "tool.select": "S",
        "tool.selection": "R",
        "tool.lasso": "L",
        "tool.gradient": "G",
        "tool.eyedropper": "P",
        "tool.text": "T",
    },
}


def profile_overrides(profile_name: str) -> Mapping[str, str]:
    try:
        return _PROFILE_OVERRIDES[profile_name]
    except KeyError:
        return {}


def create_profile_registry(profile_name: str) -> ShortcutRegistry:
    if profile_name not in PROFILE_NAMES:
        raise ValueError(f"Unknown shortcut profile: {profile_name}")
    registry = ShortcutRegistry(default_shortcut_bindings())
    rejected = registry.apply_overrides(profile_overrides(profile_name))
    if rejected:
        raise ValueError(
            f"Invalid built-in shortcut profile {profile_name}: {', '.join(rejected)}"
        )
    return registry
