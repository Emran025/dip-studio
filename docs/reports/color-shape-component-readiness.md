# Color and Shape Components Readiness Report

**Assessment date:** 2026-09-22  
**Scope:** the newly added color swatch/picker and shape drawing components, including their UI, application, domain, persistence, rendering, and tests.

## Executive summary

The two components are present and usable in the main desktop workflow, but they are not yet complete production-grade features.

| Component | Implementation completeness | Integration completeness | Test confidence | Overall readiness |
|---|---:|---:|---:|---:|
| Color swatch/picker | 82% | 62% | 72% | **73%** |
| Shape tool | 76% | 58% | 70% | **68%** |
| Combined feature set | — | — | — | **71%** |

The most important architectural gap is that the domain already defines a serializable `ShapeLayer`, but the active drawing path uses `DrawShape` to rasterize pixels into the currently active layer. Consequently, shapes are not currently first-class editable vector layers despite the documented target architecture.

The focused validation run completed successfully:

```text
15 passed in 2.88s
```

The run covered the color widget, shape interaction, shape undo, and JSON/ZIP-related layer persistence tests. It does not prove full GUI behavior, all keyboard workflows, or production behavior when optional OpenCV is unavailable.

## What is implemented

### Color component

- `ColorSwatchButton` stores and displays an RGBA `QColor`.
- Alpha is visualized using a checkerboard.
- A modal `QColorDialog` supports alpha selection.
- `DualColorSwatchWidget` provides foreground/background colors.
- Foreground/background swap and default black/white reset are implemented.
- The tool panel exposes foreground/background RGBA values to the main window.
- Shape drawing consumes the panel colors for fill and stroke.
- Focused unit tests cover color changes, signals, swap, and reset.

### Shape component

- The shape tool is registered and exposed in the Vector tool group.
- Rectangle, ellipse/circle, line, and regular hexagon polygon paths are implemented.
- Shift constrains the drag to a square/circle.
- Alt changes the origin to the center.
- Fill color, stroke color, and stroke width are passed from the UI.
- Drawing is undoable through the application command history.
- Locked layers are rejected.
- Shape-related project serialization exists for `ShapeLayer`.
- Focused tests cover constrained geometry, rectangle/ellipse drawing, and undo.

## Confirmed gaps and risks

### P0 — Shape architecture mismatch

**Evidence:** `ShapeLayer` contains `shape_type`, colors, stroke width, and vertices, and ZIP persistence serializes it. However, `EditorController.draw_shape()` imports and executes `DrawShape`, which allocates a pixel buffer and replaces the active layer buffer. The main-window shape event therefore creates raster content rather than a `ShapeLayer`.

**Impact:**

- Shape geometry cannot be edited after creation.
- Stroke/fill/vertices are not independently editable.
- Scaling or transforming a shape is raster-based rather than vector-based.
- The documented first-class `ShapeLayer` contract is not fulfilled by the user-facing tool.

**Required integration:**

1. Add a command that creates or updates a `ShapeLayer`.
2. Store normalized geometry and style in the domain model.
3. Render the shape in the compositor/rendering layer.
4. Keep rasterization as an explicit export or flatten operation.
5. Add undo/redo and JSON/ZIP round-trip tests for a shape created through the UI path.

### P1 — OpenCV is a hard dependency of shape drawing

**Evidence:** `shape_commands.py` imports `cv2` at module import time. The project declares NumPy and Pillow as base dependencies and treats OpenCV as optional elsewhere.

**Impact:**

- Importing the shape command fails in installations without OpenCV.
- This contradicts the existing optional-backend behavior.
- The feature has no controlled `OptionalBackendError` path or pure-NumPy/Pillow fallback.

**Required integration:**

- Either add OpenCV to the required dependency set, or preferably move the OpenCV import inside the rasterization path and provide a supported fallback.
- Add a test that simulates OpenCV absence and verifies the documented behavior.

### P1 — Color state is presentation-only

**Evidence:** foreground/background state lives inside `DualColorSwatchWidget` and is not represented in document/session/workspace metadata.

**Impact:**

- Colors reset when the main window/tool panel is recreated.
- Color state is not restored with a workspace or project.
- Multiple documents do not have an explicit color-state policy.

**Required integration:**

- Decide whether colors are application-global, workspace-scoped, or document-scoped.
- Persist the chosen scope in workspace metadata if restoration is required.
- Add restore and isolation tests.

### P1 — Photoshop-style keyboard behavior is incomplete

**Evidence:** the widget tooltips advertise `X` for swap and `D` for reset, but the shortcut registry contains no color-swap or color-reset commands and the main-window input dispatch has no corresponding handlers.

**Impact:** the visible affordance promises behavior that is not wired to the application shortcut system.

**Required integration:**

- Add `color.swap` and `color.reset` command IDs.
- Register `X` and `D` in the shortcut registry.
- Dispatch them through the existing input/command boundary.
- Add shortcut conflict and execution tests.

### P1 — RGBA validation is incomplete

**Evidence:** color tuples are accepted directly by the swatch and shape command. There is no shared validation for tuple length, integer range, or alpha range.

**Impact:** malformed or out-of-range colors can fail late in Qt/OpenCV or produce inconsistent behavior.

**Required integration:**

- Introduce one shared RGBA value validator.
- Validate exactly four integer channels in the range 0–255.
- Use it in UI adapters, commands, and persistence boundaries.
- Add invalid-input tests.

### P2 — Shape API validation is incomplete

**Evidence:** unknown shape types silently allocate a new buffer without drawing. Rectangle coordinates and dimensions are not validated at the command boundary.

**Impact:** invalid requests can appear successful and mark the document dirty without visible output.

**Required integration:**

- Reject unsupported shape types with `ValidationError`.
- Validate rectangle dimensions and stroke width.
- Clip or explicitly reject out-of-canvas geometry.
- Add tests for invalid shape names, zero/negative dimensions, and out-of-bounds input.

### P2 — Polygon behavior is narrower than the domain contract

**Evidence:** the command always creates a regular six-sided polygon. The domain model supports arbitrary vertices and custom paths conceptually, while the UI exposes only “Polygon”.

**Impact:** the current polygon feature is a hexagon tool, not a general polygon/path tool.

**Required integration:**

- Either rename/document the tool as a hexagon, or implement point collection for arbitrary polygons.
- Add vertex editing and persistence tests if the first-class vector route is adopted.

### P2 — UI and accessibility hardening is missing

- The swatches have tooltips but no explicit accessible names.
- The swap/reset controls use glyph text rather than themed icons or localized labels.
- No high-DPI, keyboard-focus, or theme regression test exists for the new widget.
- `color_swatch.py` contains unused widget imports that should be cleaned by the project lint gate.

## Integration matrix

| Surface | Color component | Shape component | Status |
|---|---|---|---|
| Presentation widget | Implemented | Implemented through tool event | Partial |
| Tool registry | Indirectly available through shape tool | Implemented | Good |
| Application command boundary | No color command/state boundary | Raster command implemented | Partial |
| Domain model | No color-state model | `ShapeLayer` exists but is bypassed | Gap |
| Rendering/compositor | Colors appear in raster buffers | No first-class vector shape rendering path | Gap |
| Undo/redo | Color changes are UI-local | Raster draw undo exists | Partial |
| Project/workspace persistence | Not implemented for picker state | `ShapeLayer` persistence exists, UI-created shapes do not use it | Gap |
| Optional backend policy | Not applicable directly | Hard `cv2` import conflicts with optional backend policy | Gap |
| Keyboard shortcuts | Tooltip only | Shape shortcut exists | Partial |
| Tests | Widget behavior covered | Geometry/drawing/undo covered | Partial |

## Readiness and estimated remaining effort

These estimates assume one engineer familiar with the repository and existing test conventions.

| Work package | Estimated effort | Exit condition |
|---|---:|---|
| Vector `ShapeLayer` creation/rendering path | 1.5–2.5 days | UI-created shapes remain editable and survive JSON/ZIP round-trip |
| Optional OpenCV handling or dependency decision | 0.5 day | Shape feature behaves predictably without OpenCV |
| Shared RGBA and geometry validation | 0.5–1 day | Invalid inputs fail explicitly with tested errors |
| Color state scope and persistence | 0.5–1 day | State restoration/isolation behavior is defined and tested |
| X/D shortcut integration | 0.25–0.5 day | Registered commands execute through input dispatcher |
| UI accessibility/theme/HIDPI hardening | 0.5–1 day | Accessible names, focus, theme, and high-DPI tests pass |
| Additional regression and integration coverage | 1–1.5 days | Full targeted feature matrix passes in CI |

**Estimated time to production-ready completion:** **4.75–7.5 engineering days**.  
**Estimated time for a minimum safe patch without vectorization:** **1.5–2.5 days**, but that would leave the documented ShapeLayer architecture incomplete.

## Recommended completion order

1. Resolve the `ShapeLayer` versus raster-command decision.
2. Fix the OpenCV optional-backend boundary.
3. Add shared color and geometry validation.
4. Wire `X`/`D` through the shortcut registry.
5. Define and persist color-state scope.
6. Add integration tests through the actual main-window/tool path.
7. Run the full quality gate with Ruff, mypy, architecture checks, and the complete test suite.

## Validation limitations

- The focused tests passed, but Ruff is not available as a command in the current environment, so lint status is unverified.
- Workspace diagnostics contain pre-existing Pylance issues, including `reportUndefinedVariable` diagnostics in unrelated/currently edited files. No new diagnostic was reported for the two new component files in the workspace diagnostic output.
- The focused run used `pytest -o addopts=''` to bypass the repository-wide coverage gate; coverage percentage for these components was therefore not measured by that command.
