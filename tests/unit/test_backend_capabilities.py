from dip_studio.application.backend_capabilities import (
    backend_capability,
    discover_backend_capabilities,
)


def test_backend_capabilities_are_discoverable_without_importing_processors() -> None:
    capabilities = discover_backend_capabilities()

    assert {capability.name for capability in capabilities} == {"opencv", "scikit-image", "scipy"}
    assert all(isinstance(capability.available, bool) for capability in capabilities)


def test_unknown_backend_capability_is_explicit() -> None:
    try:
        backend_capability("missing")
        raise AssertionError("unknown capability was accepted")
    except KeyError as error:
        assert "Unknown backend" in str(error)
