import pytest

from dip_studio.application.shortcut_registry import (
    ShortcutBinding,
    ShortcutRegistry,
    default_shortcut_registry,
)


def test_default_shortcuts_are_unique_within_context() -> None:
    registry = default_shortcut_registry()
    keys = [(binding.context, binding.key.casefold()) for binding in registry.list()]

    assert len(keys) == len(set(keys))
    assert registry.get("layer.rename").key == "F2"


def test_shortcut_registry_rejects_context_conflicts() -> None:
    registry = ShortcutRegistry((ShortcutBinding("first", "Ctrl+J", "Layer Panel"),))

    with pytest.raises(ValueError, match="Shortcut conflict"):
        registry.register(ShortcutBinding("second", "ctrl+j", "Layer Panel"))


def test_same_key_can_be_registered_for_different_contexts() -> None:
    registry = ShortcutRegistry(
        (
            ShortcutBinding("canvas", "B", "Canvas"),
            ShortcutBinding("tool", "B", "Tool"),
        )
    )

    assert len(registry.list()) == 2


def test_re_registering_command_replaces_binding_and_resolves_context_priority() -> None:
    registry = ShortcutRegistry(
        (
            ShortcutBinding("application", "F2", "Application"),
            ShortcutBinding("layer", "F2", "Layer Panel", 10),
        )
    )

    registry.register(ShortcutBinding("application", "F3", "Application"))

    assert registry.get("application").key == "F3"
    assert registry.resolve("F2", ("Layer Panel", "Application")).command_id == "layer"
    assert registry.resolve("F2", ("Application",)) is None


def test_shortcut_overrides_round_trip_against_defaults() -> None:
    defaults = default_shortcut_registry()
    registry = default_shortcut_registry()

    assert registry.apply_overrides({"file.save": "Ctrl+Shift+S"}) == ()
    assert registry.overrides(defaults) == {"file.save": "Ctrl+Shift+S"}


def test_shortcut_overrides_reject_unknown_non_customizable_and_conflicting_keys() -> None:
    registry = ShortcutRegistry(
        (
            ShortcutBinding("first", "Ctrl+J"),
            ShortcutBinding("fixed", "F1", user_customizable=False),
        )
    )

    rejected = registry.apply_overrides(
        {
            "missing": "M",
            "fixed": "F2",
            "first": "F1",
        }
    )

    assert rejected == ("missing", "fixed", "first")
    assert registry.get("first").key == "Ctrl+J"
