# Contributing

Read `.agent/skills/*/SKILL.md` before changing architecture or adding a component. Search existing components and theme tokens first. Run `python .agent/scripts/architecture_guard.py`, `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest` before opening a pull request. Every new dependency needs a role, version, license, platform support, and removal/alternative note in `docs/architecture/dependencies.md`.
