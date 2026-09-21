"""Tests for new domain entities: Mask, SelectionRect, Transform."""
import pytest
from dip_studio.domain.model import Mask, SelectionRect, Transform, Layer, LayerId
from dip_studio.core.errors import ValidationError
from uuid import uuid4


class TestMask:
    def test_valid_mask(self) -> None:
        mask = Mask(id=str(uuid4()), name="Layer Mask", width=100, height=100)
        assert mask.mode == "reveal"
        assert mask.enabled is True

    def test_invalid_dimensions_raise(self) -> None:
        with pytest.raises(ValidationError):
            Mask(id=str(uuid4()), name="bad", width=0, height=100)

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValidationError):
            Mask(id=str(uuid4()), name="bad", width=10, height=10, mode="wrong")


class TestSelectionRect:
    def test_valid_selection(self) -> None:
        sel = SelectionRect(x=10, y=20, width=50, height=50)
        assert sel.feather == 0.0

    def test_invalid_size_raises(self) -> None:
        with pytest.raises(ValidationError):
            SelectionRect(x=0, y=0, width=0, height=10)

    def test_negative_feather_raises(self) -> None:
        with pytest.raises(ValidationError):
            SelectionRect(x=0, y=0, width=10, height=10, feather=-1.0)


class TestTransform:
    def test_identity_transform(self) -> None:
        t = Transform()
        assert t.is_identity is True

    def test_non_identity(self) -> None:
        t = Transform(tx=10.0)
        assert t.is_identity is False

    def test_zero_scale_raises(self) -> None:
        with pytest.raises(ValidationError):
            Transform(sx=0.0)


class TestLayerNewFields:
    def test_layer_defaults(self) -> None:
        layer = Layer(id=LayerId(uuid4()), name="Background")
        assert layer.blend_mode == "normal"
        assert layer.locked is False
        assert layer.mask_id is None
        assert layer.transform is None

    def test_layer_with_transform(self) -> None:
        t = Transform(tx=5.0, ty=10.0)
        layer = Layer(id=LayerId(uuid4()), name="Transformed", transform=t)
        assert layer.transform is not None
        assert layer.transform.tx == 5.0
