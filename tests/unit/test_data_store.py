"""Tests for ImageDataStore: allocation, retrieval, CoW, release."""
import numpy as np
import pytest

from dip_studio.infrastructure.data_store import ImageDataStore


def test_allocate_and_get() -> None:
    store = ImageDataStore()
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    buf_id = store.allocate(arr)
    assert store.has(buf_id)
    result = store.get(buf_id)
    assert result.shape == (4, 4, 3)


def test_get_unknown_raises() -> None:
    store = ImageDataStore()
    with pytest.raises(KeyError, match="Buffer not found"):
        store.get("nonexistent-id")


def test_release_removes_buffer() -> None:
    store = ImageDataStore()
    arr = np.ones((2, 2, 3), dtype=np.uint8)
    buf_id = store.allocate(arr)
    assert len(store) == 1
    store.release(buf_id)
    assert not store.has(buf_id)
    assert len(store) == 0


def test_copy_on_write_produces_independent_copy() -> None:
    store = ImageDataStore()
    arr = np.zeros((3, 3, 3), dtype=np.uint8)
    original_id = store.allocate(arr)
    cow_id = store.copy_on_write(original_id)

    assert cow_id != original_id
    # Mutate the copy — original must be unchanged
    copy_arr = store.get(cow_id)
    copy_arr[0, 0, 0] = 99
    assert store.get(original_id)[0, 0, 0] == 0


def test_multiple_buffers_are_independent() -> None:
    store = ImageDataStore()
    ids = [store.allocate(np.full((2, 2, 3), i, dtype=np.uint8)) for i in range(5)]
    assert len(store) == 5
    for i, buf_id in enumerate(ids):
        assert store.get(buf_id)[0, 0, 0] == i
