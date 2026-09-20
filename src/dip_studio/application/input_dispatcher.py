"""Context-aware keyboard input dispatch for the editor."""

from collections.abc import Callable
from dataclasses import dataclass

from dip_studio.application.shortcut_registry import ShortcutBinding, ShortcutRegistry


@dataclass(frozen=True, slots=True)
class FocusState:
    """Presentation-neutral description of the currently focused surface."""

    input_field: bool = False
    modal_dialog: bool = False
    panel_context: str | None = None
    canvas: bool = False


class FocusResolver:
    """Maps focus state to contexts ordered from most to least specific."""

    def resolve(self, state: FocusState) -> tuple[str, ...]:
        if state.input_field:
            return ("Input Field", "Text Editing")
        contexts: list[str] = []
        if state.modal_dialog:
            contexts.append("Dialog")
        if state.panel_context:
            contexts.append(state.panel_context)
        if state.canvas:
            contexts.extend(("Canvas", "Tool"))
        contexts.extend(("Application", "Global"))
        return tuple(contexts)


class InputDispatcher:
    """Resolves a key in focus order and invokes its registered command."""

    def __init__(
        self,
        registry: ShortcutRegistry,
        focus_resolver: FocusResolver | None = None,
    ) -> None:
        self._registry = registry
        self._focus_resolver = focus_resolver or FocusResolver()
        self._handlers: dict[str, Callable[[], None]] = {}

    def register(self, command_id: str, handler: Callable[[], None]) -> None:
        if not command_id.strip():
            raise ValueError("Command id cannot be empty")
        self._handlers[command_id] = handler

    def set_registry(self, registry: ShortcutRegistry) -> None:
        self._registry = registry

    def dispatch(self, key: str, state: FocusState) -> ShortcutBinding | None:
        contexts = self._focus_resolver.resolve(state)
        binding = self._registry.resolve(key, contexts)
        if binding is None:
            return None
        try:
            handler = self._handlers[binding.command_id]
        except KeyError as error:
            raise KeyError(
                f"No input handler registered for {binding.command_id}"
            ) from error
        handler()
        return binding
