---
name: dip-studio-quality-gates
description: Validate DIP Studio changes with deterministic architecture, style, type, and unit checks before commit.
---

# Gates

نفّذ: `python .agent/scripts/architecture_guard.py` ثم `ruff check .` ثم `mypy src` ثم `pytest`. لا تعتبر أداة غير مثبتة نجاحًا؛ ثبّت `.[dev]` أو سجّل BLOCKED.

Definition of done: لا خرق للطبقات، لا hard-coded UI palette، اختبارات domain/application دون GUI، وثائق dependency محدثة، وقرار reuse موثق عند رفض الموجود.
