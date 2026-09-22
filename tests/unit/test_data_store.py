"""Tests for ImageDataStore: allocation, retrieval, CoW, release."""
import numpy as np
import pytest

from dip_studio.infrastructure.data_store import ImageDataStore
from dip_studio.infrastructure.preview_cache import PreviewCache, PreviewKey
from dip_studio.infrastructure.tile_store import TileStore


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


def test_data_store_tracks_bytes_and_metadata() -> None:
    arr = np.ones((4, 4, 3), dtype=np.uint8)
    store = ImageDataStore(max_bytes=1024)
    buf_id = store.allocate(arr)

    assert store.total_bytes() == arr.nbytes
    assert store.buffer_metadata(buf_id)["bytes"] == arr.nbytes
    assert store.buffer_metadata(buf_id)["shape"] == (4, 4, 3)


def test_data_store_rejects_over_limit_allocations() -> None:
    store = ImageDataStore(max_bytes=7)
    with pytest.raises(MemoryError, match="memory limit"):
        store.allocate(np.ones((2, 2, 2), dtype=np.uint8))


def test_tile_store_validates_keys_and_limits() -> None:
    store = TileStore(tile_size=8, max_tiles=2, max_bytes=256)
    tile = np.zeros((8, 8, 3), dtype=np.uint8)

    assert store.put((0, 0), tile) == (0, 0)
    assert store.get("0,0").shape == tile.shape
    assert store.has((0, 0))

    with pytest.raises(ValueError, match="non-negative"):
        store.put((-1, 0), tile)

    with pytest.raises(ValueError, match="Tile bounds"):
        store.bounds_check(0, 0, 9, 1)


def test_preview_cache_invalidates_released_buffer_and_version_changes() -> None:
    store = ImageDataStore()
    source = store.allocate(np.zeros((16, 16, 4), dtype=np.uint8))
    cache = PreviewCache(max_entries=8)
    key = PreviewKey.build(source, 0, 64, 64, 1.0, document_id="doc-1")
    cache.put(key, b"preview-bytes")

    assert cache.get(key) == b"preview-bytes"

    store.release(source)
    cache.invalidate_buffer(source)
    assert cache.get(key) is None

    newer = store.allocate(np.zeros((16, 16, 4), dtype=np.uint8))
    stale = PreviewKey.build(newer, 0, 64, 64, 1.0, document_id="doc-1")
    cache.put(stale, b"newer")
    store.touch(newer)
    cache.invalidate_buffer(newer)
    assert cache.get(stale) is None


def test_preview_cache_invalidates_subtree_buffer_ids() -> None:
    cache = PreviewCache(max_entries=8)
    keep = PreviewKey.build("keep", 1, 64, 64, 1.0, document_id="doc-1")
    dead_a = PreviewKey.build("layer-a", 2, 64, 64, 1.0, document_id="doc-1")
    dead_b = PreviewKey.build("layer-b", 3, 64, 64, 1.0, document_id="doc-1")
    cache.put(keep, b"keep")
    cache.put(dead_a, b"stale-a")
    cache.put(dead_b, b"stale-b")

    cache.invalidate_ids(["layer-a", "layer-b"])

    assert cache.get(keep) == b"keep"
    assert cache.get(dead_a) is None
    assert cache.get(dead_b) is None
