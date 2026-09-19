#!/usr/bin/env python3
"""Dependency-free guard for DIP Studio's source boundaries."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "dip_studio"
RULES = {
    "domain": ("PySide6", "numpy", "cv2", "pathlib.Path", "os.", "pathlib"),
    "application": ("PySide6", "numpy", "cv2"),
    "processing": ("PySide6",),
    "rendering": ("PySide6",),
}
errors: list[str] = []
for file in SRC.rglob("*.py"):
    relative = file.relative_to(SRC).as_posix()
    layer = relative.split("/", 1)[0]
    text = file.read_text(encoding="utf-8")
    for token in RULES.get(layer, ()):
        if re.search(rf"(?:from|import)\s+[^\n]*{re.escape(token)}", text):
            errors.append(f"{relative}: {layer} imports forbidden dependency {token}")
    if layer == "presentation" and file.name != "theme.py" and re.search(r"#[0-9A-Fa-f]{6}", text):
        errors.append(f"{relative}: use centralized theme tokens instead of hard-coded color")
if errors:
    print("ARCHITECTURE GUARD FAILED")
    print("\n".join(f"- {e}" for e in errors))
    sys.exit(1)
print("ARCHITECTURE GUARD PASSED")
