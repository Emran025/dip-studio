"""Theme tokens are centralized; widgets consume these instead of hard-coded colors."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    surface: str
    surface_alt: str
    foreground: str
    foreground_muted: str
    field: str
    field_foreground: str
    accent: str
    accent_foreground: str
    border: str


LIGHT = ThemeTokens(
    "#F3F5F8",
    "#FFFFFF",
    "#17202A",
    "#536174",
    "#FFFFFF",
    "#17202A",
    "#2563EB",
    "#FFFFFF",
    "#CBD5E1",
)
DARK = ThemeTokens(
    "#171A21",
    "#222733",
    "#F5F7FA",
    "#AAB6C7",
    "#10141B",
    "#F5F7FA",
    "#60A5FA",
    "#10141B",
    "#3A4352",
)
