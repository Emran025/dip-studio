# ADR 0001: System Boundaries and Sources of Truth

- **Status:** Accepted
- **Decision:** Domain owns document invariants; application owns use-case orchestration and commands; processing transforms data through typed processor contracts; rendering turns document state into viewport output; infrastructure owns filesystem, codecs, and external libraries; presentation owns Qt composition only.
- **State owner:** `DocumentSession` is the sole owner of the active document snapshot. Widgets never mutate domain state directly.
- **History:** All user mutations enter through `Command` and `UndoRedoHistory`; direct mutation from a view is forbidden.
- **Theme:** semantic `ThemeTokens` are the source of truth; Qt receives them through an adapter.
- **Migration:** project files carry `format_version`; writes are atomic and migrations must be explicit.
- **Plugin boundary:** plugins expose versioned capabilities and processors; discovery and failure isolation stay in infrastructure.
