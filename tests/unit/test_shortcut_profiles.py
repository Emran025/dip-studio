import pytest

from dip_studio.application.shortcut_profiles import (
    CUSTOM_PROFILE,
    DEFAULT_PROFILE,
    LABORATORY_PROFILE,
    PHOTOSHOP_PROFILE,
    PROFILE_NAMES,
    create_profile_registry,
)


def test_all_builtin_profiles_are_valid_and_have_unique_bindings() -> None:
    assert DEFAULT_PROFILE in PROFILE_NAMES
    assert CUSTOM_PROFILE in PROFILE_NAMES

    for profile_name in PROFILE_NAMES:
        registry = create_profile_registry(profile_name)
        keys = [(item.context, item.key.casefold()) for item in registry.list()]
        assert len(keys) == len(set(keys))


def test_profiles_provide_distinct_expected_conventions() -> None:
    photoshop = create_profile_registry(PHOTOSHOP_PROFILE)
    laboratory = create_profile_registry(LABORATORY_PROFILE)

    assert photoshop.get("edit.redo").key == "Ctrl+Shift+Z"
    assert laboratory.get("edit.redo").key == "Ctrl+Shift+Y"
    assert laboratory.get("tool.select").key == "S"


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown shortcut profile"):
        create_profile_registry("Unknown")
