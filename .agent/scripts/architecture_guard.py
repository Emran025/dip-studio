#!/usr/bin/env python3
"""AST-based dependency guard for DIP Studio's source boundaries."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "dip_studio"
FORBIDDEN = {
    "domain": {"PySide6", "numpy", "cv2", "pathlib", "os", "io"},
    "application": {"PySide6", "numpy", "cv2"},
    "processing": {"PySide6"},
    "rendering": {"PySide6"},
}
FORBIDDEN_EDGES = {
    "presentation": {"infrastructure", "domain"},
    "shared": {
        "presentation",
        "application",
        "infrastructure",
        "domain",
        "processing",
        "rendering",
    },
}
errors: list[str] = []


def import_root(value: str) -> str:
    return value.split(".", 1)[0]


for file in SRC.rglob("*.py"):
    relative = file.relative_to(SRC).as_posix()
    layer = relative.split("/", 1)[0]
    text = file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(file))
    except SyntaxError as error:
        errors.append(f"{relative}: syntax error: {error}")
        continue
    for node in ast.walk(tree):
        imported: str | None = None
        if isinstance(node, ast.Import):
            imported = node.names[0].name
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported = node.module
        if imported is None:
            continue
        root = import_root(imported)
        if root in FORBIDDEN.get(layer, set()):
            message = f"{relative}:{node.lineno}: {layer} imports forbidden dependency {imported}"
            errors.append(message)
        if imported.startswith("dip_studio."):
            target = imported.split(".")[1]
            if target in FORBIDDEN_EDGES.get(layer, set()):
                errors.append(f"{relative}:{node.lineno}: forbidden edge {layer} -> {target}")
    if layer == "presentation" and file.name != "theme.py":
        for line_no, line in enumerate(text.splitlines(), 1):
            if any(token in line for token in ("Color(0x", "Colors.", 'QColor("#')):
                errors.append(f"{relative}:{line_no}: use centralized theme tokens")

if errors:
    print("ARCHITECTURE GUARD FAILED")
    print("\n".join(f"- {error}" for error in errors))
    sys.exit(1)
print("ARCHITECTURE GUARD PASSED")
