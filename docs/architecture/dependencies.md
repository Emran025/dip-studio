# DIP Studio Dependencies

| Dependency | Role | Boundary | Policy |
|---|---|---|---|
| Python 3.12+ | Runtime | all | Required baseline |
| PySide6 | Desktop presentation | presentation | Optional during domain tests |
| NumPy | Array processing | infrastructure/processing | Never imported by domain |
| OpenCV/scikit-image | Algorithms and CV | infrastructure | Add only with a contract and license review |
| pytest/ruff/mypy | Quality gates | development | Required in CI |

Any new dependency requires version, license, platform support, owner, and removal/alternative notes before merge.
