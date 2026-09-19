# DIP Studio

**DIP Studio** is a planned professional desktop workspace for Digital Image Processing and Computer Vision. It is designed as a reusable platform—not a GUI that directly calls algorithms—with a clean separation between domain state, application commands, infrastructure adapters, rendering, and Qt/PySide6 presentation.

## Architecture at a glance

```text
Presentation (PySide6) → Application (commands/use cases) → Domain (pure model/policies)
                                  ↑
                   Infrastructure adapters (files, codecs, NumPy/OpenCV)
```

The first slice is intentionally small and executable: a framework-independent `ImageDocument`, an application use case, and an in-memory adapter with tests. New processing algorithms, file formats, and widgets must pass the reuse/theme gate in `.agent/skills/reusable-components/SKILL.md` before implementation.

## Repository map

- `src/dip_studio/domain/` — pure entities and policies.
- `src/dip_studio/application/` — use cases and ports.
- `src/dip_studio/infrastructure/` — filesystem, image-library, and process adapters.
- `src/dip_studio/presentation/` — PySide6 composition and views only.
- `docs/architecture/` — the complete DIP Studio architecture documents.
- `.agent/` — project skills, constraints, decision records, and automated architecture guards.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[gui,dev]'
pytest
ruff check .
python .agent/scripts/architecture_guard.py
```

Install the optional desktop UI with `pip install -e '.[gui,dev]'` after the domain/application checks pass.
