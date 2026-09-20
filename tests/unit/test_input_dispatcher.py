from dip_studio.application.input_dispatcher import (
    FocusResolver,
    FocusState,
    InputDispatcher,
)
from dip_studio.application.shortcut_registry import (
    ShortcutBinding,
    ShortcutRegistry,
)


def test_focus_resolver_prioritizes_input_fields_and_panels() -> None:
    resolver = FocusResolver()

    assert resolver.resolve(FocusState(input_field=True)) == (
        "Input Field",
        "Text Editing",
    )
    assert resolver.resolve(FocusState(panel_context="Layer Panel")) == (
        "Layer Panel",
        "Application",
        "Global",
    )
    assert resolver.resolve(FocusState(canvas=True)) == (
        "Canvas",
        "Tool",
        "Application",
        "Global",
    )


def test_dispatcher_uses_focus_context_and_invokes_handler() -> None:
    registry = ShortcutRegistry(
        (
            ShortcutBinding("application.command", "X", "Application"),
            ShortcutBinding("layer.command", "X", "Layer Panel", 10),
        )
    )
    calls: list[str] = []
    dispatcher = InputDispatcher(registry)
    dispatcher.register("application.command", lambda: calls.append("application"))
    dispatcher.register("layer.command", lambda: calls.append("layer"))

    binding = dispatcher.dispatch("x", FocusState(panel_context="Layer Panel"))

    assert binding is not None and binding.command_id == "layer.command"
    assert calls == ["layer"]


def test_dispatcher_does_not_consume_unbound_input() -> None:
    dispatcher = InputDispatcher(ShortcutRegistry())

    assert dispatcher.dispatch("X", FocusState(input_field=True)) is None
