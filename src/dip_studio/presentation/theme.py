"""Theme tokens are centralized; widgets consume these instead of hard-coded colors."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    surface: str
    surface_alt: str
    foreground: str
    accent: str
    border: str


LIGHT = ThemeTokens("#FFFFFF", "#F5F7FA", "#17202A", "#2563EB", "#D7DEE8")
DARK = ThemeTokens("#171A21", "#222733", "#F5F7FA", "#60A5FA", "#3A4352")
