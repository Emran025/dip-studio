"""Context-aware shortcut definitions owned by the application layer."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShortcutBinding:
    command_id: str
    key: str
    context: str = "Application"
    priority: int = 0
    enabled: bool = True
    user_customizable: bool = True


class ShortcutRegistry:
    def __init__(self, bindings: tuple[ShortcutBinding, ...] = ()) -> None:
        self._bindings: dict[str, ShortcutBinding] = {}
        for binding in bindings:
            self.register(binding)

    def register(self, binding: ShortcutBinding) -> None:
        if not binding.command_id.strip() or not binding.key.strip():
            raise ValueError("Shortcut command and key cannot be empty")
        previous = self._bindings.pop(binding.command_id, None)
        conflict = next(
            (
                item
                for item in self._bindings.values()
                if item.enabled
                and binding.enabled
                and item.key.casefold() == binding.key.casefold()
                and item.context == binding.context
            ),
            None,
        )
        if conflict is not None:
            if previous is not None:
                self._bindings[previous.command_id] = previous
            raise ValueError(
                f"Shortcut conflict: {binding.key} is already assigned to {conflict.command_id}"
            )
        self._bindings[binding.command_id] = binding

    def get(self, command_id: str) -> ShortcutBinding:
        try:
            return self._bindings[command_id]
        except KeyError as error:
            raise KeyError(f"Unknown shortcut command: {command_id}") from error

    def list(self) -> tuple[ShortcutBinding, ...]:
        return tuple(self._bindings.values())

    def overrides(self, defaults: "ShortcutRegistry") -> dict[str, str]:
        """Return only user-visible key changes relative to ``defaults``."""
        return {
            command_id: binding.key
            for command_id, binding in self._bindings.items()
            if command_id in defaults._bindings
            and binding.key != defaults._bindings[command_id].key
        }

    def apply_overrides(self, overrides: Mapping[str, str]) -> tuple[str, ...]:
        """Apply persisted keys and return command IDs that were rejected."""
        rejected: list[str] = []
        for command_id, key in overrides.items():
            if command_id not in self._bindings:
                rejected.append(command_id)
                continue
            current = self._bindings[command_id]
            if not current.user_customizable:
                rejected.append(command_id)
                continue
            try:
                self.register(
                    ShortcutBinding(
                        command_id,
                        str(key),
                        current.context,
                        current.priority,
                        current.enabled,
                        current.user_customizable,
                    )
                )
            except ValueError:
                rejected.append(command_id)
        return tuple(rejected)

    def resolve(self, key: str, contexts: tuple[str, ...]) -> ShortcutBinding | None:
        candidates = [
            binding
            for binding in self._bindings.values()
            if binding.enabled
            and binding.key.casefold() == key.casefold()
            and binding.context in contexts
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda binding: (
                contexts.index(binding.context),
                -binding.priority,
            ),
        )


def default_shortcut_bindings() -> tuple[ShortcutBinding, ...]:
    return (
            ShortcutBinding("file.new", "Ctrl+N"),
            ShortcutBinding("file.save", "Ctrl+S"),
            ShortcutBinding("edit.undo", "Ctrl+Z"),
            ShortcutBinding("edit.redo", "Ctrl+Y"),
            ShortcutBinding("layer.add", "Ctrl+Shift+N", "Layer Panel", 10),
            ShortcutBinding("layer.duplicate", "Ctrl+J", "Layer Panel", 10),
            ShortcutBinding("layer.remove", "Delete", "Layer Panel", 10),
            ShortcutBinding("layer.move_up", "Ctrl+Up", "Layer Panel", 10),
            ShortcutBinding("layer.move_down", "Ctrl+Down", "Layer Panel", 10),
            ShortcutBinding("layer.toggle_visibility", "Ctrl+Shift+H", "Layer Panel", 10),
            ShortcutBinding("layer.rename", "F2", "Layer Panel", 10),
            ShortcutBinding("application.command_palette", "Ctrl+K"),
            ShortcutBinding("canvas.zoom_in", "+", "Canvas"),
            ShortcutBinding("canvas.zoom_out", "-", "Canvas"),
            ShortcutBinding("tool.select", "V", "Tool", 20),
            ShortcutBinding("tool.selection", "M", "Tool", 20),
            ShortcutBinding("tool.ellipse_selection", "O", "Tool", 20),
            ShortcutBinding("tool.lasso", "L", "Tool", 20),
            ShortcutBinding("tool.polygon_selection", "P", "Tool", 20),
            ShortcutBinding("tool.crop", "C", "Tool", 20),
            ShortcutBinding("tool.blur", "B", "Tool", 20),
            ShortcutBinding("tool.edge", "E", "Tool", 20),
            ShortcutBinding("tool.gradient", "G", "Tool", 20),
            ShortcutBinding("tool.brush", "Shift+B", "Tool", 20),
            ShortcutBinding("tool.hand", "H", "Tool", 20),
            ShortcutBinding("tool.zoom", "Z", "Tool", 20),
            ShortcutBinding("tool.eyedropper", "I", "Tool", 20),
            ShortcutBinding("tool.text", "T", "Tool", 20),
            ShortcutBinding("tool.shape", "U", "Tool", 20),
            ShortcutBinding("canvas.pan", "Space", "Canvas", 30),
            ShortcutBinding("canvas.zoom_wheel", "Ctrl+Wheel", "Canvas", 30),
        )


def default_shortcut_registry() -> ShortcutRegistry:
    return ShortcutRegistry(default_shortcut_bindings())
