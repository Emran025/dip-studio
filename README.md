# DIP Studio

**DIP Studio** is a planned professional desktop workspace for Digital Image Processing and Computer Vision. It is designed as a reusable platform—not a GUI that directly calls algorithms—with a clean separation between domain state, application commands, infrastructure adapters, rendering, and Qt/PySide6 presentation.

## Architecture at a glance

```text
Presentation (PySide6) → Application (commands/use cases) → Domain (pure model/policies)
                                  ↑
                   Infrastructure adapters (files, codecs, NumPy/OpenCV)
```

The first slice is intentionally small and executable: a framework-independent `ImageDocument`, an application use case, and an in-memory adapter with tests. New processing algorithms, file formats, and widgets must pass the reuse/theme gate in `.agent/skills/reusable-components/SKILL.md` before implementation.

The first editor surface is now wired as a vertical slice: `EditorController` owns the
active document, `BlankDocumentRenderer` produces the preview frame, and the Qt shell
provides the canvas, tool/properties/layers/navigator/history docks, menus, toolbar,
theme toggle, and command-palette entry point. Launch it after installing the optional
GUI dependency with:

The current workspace also includes reusable presentation components for the New Project
dialog, searchable command palette, and schema-driven tool parameter panel. Selecting
Blur or Edge in the Tools dock demonstrates generated parameter controls; the controls
are presentation-only until their application commands are wired.

The right side of the workspace uses a single dock with a Photoshop-style top tab bar
for Properties, Layers, Channels, Navigator, and History. Tabs can be reordered, while
the complete dock can be floated, resized, closed, or restored from `View > Workspace
sidebar` or `Window > Workspace sidebar`. Timeline remains a separate bottom dock.

Tools are now supplied by the application-owned `ToolRegistry`, so the left Tools panel,
the generated Properties controls, and the Command Palette all use the same definitions.
Application commands also have a single `CommandHandler` dispatch boundary for future
menu, toolbar, keyboard, and automation integrations.

The canvas surface now exposes shared view commands for zoom in, zoom out, fit to view,
and actual size. They are available from the View menu, the main toolbar, keyboard
shortcuts, and the command palette, while the document model remains unchanged.

Workspace layout is persisted with Qt settings. `Window` provides direct navigation to
each right-sidebar panel, plus `Save workspace` and `Reset workspace`; closing the
window saves geometry, dock state, and the selected sidebar tab for the next session.

Document transitions are guarded when a document is dirty. Creating a project, opening
a project or image, and closing the application offer `Save`, `Discard`, and `Cancel`;
the window title marks unsaved state with `*`.

Tool Properties panels expose a staged `Preview / Apply / Cancel` workflow. Parameter
values are collected by the reusable panel and surfaced to presentation callbacks;
Preview remains non-mutating while Apply is routed through the processing command.

Processing commands are now connected to the application `ProcessingEngine`: Preview
validates and runs without changing the document, while Apply records the operation
and parameters in the document, marks it dirty, and supports Undo/Redo from the Edit
menu, toolbar, and command palette. Pixel backends can replace the current symbolic
processor without changing these presentation boundaries.

Imported PPM images now carry their source preview frame through the application
boundary, so the Canvas displays the imported pixels instead of the blank-document
fallback frame. Blank documents continue to use the rendering adapter until a full
pixel store is introduced.

The Canvas also supports presentation-only pan by left-dragging, a toggleable grid,
and a before/after display mode. These controls are available from `View`, the main
toolbar, and the command palette; the before/after mode is prepared for the processed
frame boundary and currently applies a visual overlay to the available preview.

The Layers panel is now interactive: each layer has a visibility checkbox and an
opacity control. Each item carries its domain `LayerId`, so changes remain attached
to the intended layer even when the presentation order changes. Changes are routed
through application layer commands, mark the document dirty, and participate in
Undo/Redo rather than mutating widgets as the source of truth.

Layer management controls are available below the Layers list for adding, removing,
duplicating, and moving the selected layer. Removing the last remaining layer is
rejected by the domain boundary, and all structural changes are undoable.

The Layers list supports extended multi-selection and a context menu for rename,
duplicate, and removing selected layers. Multi-layer removal is committed as one
application command, so it is restored by a single Undo action.

Visibility and opacity edits apply to every selected layer and are also committed
as one undoable command. The selected layer identity is persisted with the workspace
settings and restored when the document is shown again.

Layer shortcuts are available from the `Edit` menu and Command Palette:
`Ctrl+J` duplicates, `Delete` removes selected layers, `Ctrl+Up`/`Ctrl+Down`
reorders the active layer, and `Ctrl+Shift+H` toggles visibility for the selection.

Layer selection is preserved while structural commands rebuild the panel. Adding or
duplicating selects the new layer, while moving, renaming, and batch state changes
retain the existing single or multi-selection.

`Ctrl+Shift+N` adds a layer and `F2` opens the rename dialog for the active layer.
These actions are also available from the Edit menu and Command Palette.

Shortcut definitions are centralized in the application-owned shortcut registry.
It validates duplicate assignments within a context and exposes the default tool
shortcuts (`V` Select, `C` Crop, `B` Blur, `E` Edge) to the presentation layer.

The registry also resolves enabled bindings by ordered context and priority. The
application now includes a focus-aware `InputDispatcher` and `FocusResolver`: text
inputs and modal dialogs retain keyboard ownership, while Canvas, Layer Panel, Tool,
and Application contexts are resolved in priority order. Customized
bindings are persisted in the application `QSettings` store and restored on startup;
invalid, conflicting, or unavailable saved bindings are rejected and reported in the
status bar. The current Qt actions remain the presentation adapter over the centralized
definitions.

The current workspace now includes a searchable Keyboard Shortcuts dialog with
recording through `QKeySequenceEdit`, conflict validation, reset to defaults, and
immediate refresh of the bound application actions. Named preset profiles remain
available from `View > Shortcut profile`: `DIP Studio Default`, `Photoshop-like`,
`DIP Laboratory`, and `Custom`. The active profile and each profile's custom
overrides are persisted independently in `QSettings`.

```bash
python -m dip_studio.presentation.app
# or, after installing the package:
dip-studio
```

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
