"""Compression caching preserves exact engine bytes across changes and rewind."""
from types import SimpleNamespace

import numpy as np
import pytest

from topogym.world.state import capture_engine_buffers, restore_engine_buffers, unpack_buffer


class Field:
    def __init__(self):
        self.values = np.zeros(20000, dtype=np.uint64)
        self.values[:3] = [0x8000000000000000, 0x7FF8000000001234, 3]
        self.reads = 0

    def to_numpy(self):
        self.reads += 1
        return self.values.view(np.float64).copy()

    def from_numpy(self, data):
        self.values[:] = data.view(np.uint64)


def scene_with_field():
    solver_type = type("Solver", (), {"__module__": "genesis.engine.solvers.test"})
    solver = solver_type()
    solver.field = Field()
    return SimpleNamespace(sim=SimpleNamespace(_active_solvers=[solver], coupler=None, entities=[])), solver


def test_unchanged_large_field_is_read_but_compressed_only_once(monkeypatch):
    import topogym.world.state as state
    scene, solver = scene_with_field()
    original = state.zlib.compress
    calls = []
    def compress(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(state.zlib, "compress", compress)
    cache = {}
    first = capture_engine_buffers(scene, comparison_cache=cache)
    second = capture_engine_buffers(scene, first, cache)
    assert solver.field.reads == 2
    assert len(calls) == 1
    assert first[0] is second[0]
    assert first[0].value is second[0].value
    np.testing.assert_array_equal(unpack_buffer(second[0].value).view(np.uint64), solver.field.values)


def test_changed_nan_bits_signed_zero_and_rewind_match_uncached_snapshots():
    scene, solver = scene_with_field()
    cache = {}
    first = capture_engine_buffers(scene, comparison_cache=cache)
    original = solver.field.values.copy()
    solver.field.values[:3] = [0, 0x7FF8000000004321, 4]
    changed = capture_engine_buffers(scene, first, cache)
    uncached = capture_engine_buffers(scene, first)
    assert changed[0].value.data == uncached[0].value.data
    assert changed[0].value is not first[0].value
    restore_engine_buffers(first)
    np.testing.assert_array_equal(solver.field.values, original)
    # Deliberately leave the future's cache in place: snapshot identity must
    # prevent its raw bytes being paired with an older compressed payload.
    rewound = capture_engine_buffers(scene, first, cache)
    np.testing.assert_array_equal(unpack_buffer(rewound[0].value).view(np.uint64), original)
    restore_engine_buffers(changed)
    np.testing.assert_array_equal(solver.field.values[:3], [0, 0x7FF8000000004321, 4])


def test_removed_fields_do_not_leave_raw_copies_in_cache():
    scene, solver = scene_with_field()
    cache = {}
    first = capture_engine_buffers(scene, comparison_cache=cache)
    assert cache
    del solver.field
    assert capture_engine_buffers(scene, first, cache) == ()
    assert not cache


def test_adapter_returning_a_live_view_cannot_mutate_remembered_bytes():
    scene, solver = scene_with_field()
    solver.field.to_numpy = lambda: solver.field.values.view(np.float64)
    cache = {}
    first = capture_engine_buffers(scene, comparison_cache=cache)
    solver.field.values[100] = 12345
    second = capture_engine_buffers(scene, first, cache)
    assert unpack_buffer(first[0].value).view(np.uint64)[100] == 0
    assert unpack_buffer(second[0].value).view(np.uint64)[100] == 12345


def test_large_contact_tensor_compression_rewind_and_numeric_archive():
    import torch
    from topogym.world.state import PackedArray
    from topogym.world.initial_state import NumericTree, require_same_layout

    scene, solver = scene_with_field()
    del solver.field
    bits = np.zeros((200, 200), dtype=np.uint64)
    bits[0, :3] = [0x8000000000000000, 0x7FF8000000001234, 3]
    solver.contacts = torch.from_numpy(bits.view(np.float64)).T
    cache = {}
    first = capture_engine_buffers(scene, comparison_cache=cache)
    packed = first[0].value
    assert isinstance(packed, PackedArray) and packed.tensor
    assert packed.stored_nbytes < packed.nbytes/10
    repeated = capture_engine_buffers(scene, first, cache)
    assert repeated[0] is first[0]
    assert repeated[0].value is packed
    solver.contacts[100, 0] = 2.
    changed = capture_engine_buffers(scene, repeated, cache)
    assert changed[0].value is not packed
    restore_engine_buffers(first)
    assert torch.equal(solver.contacts.contiguous().view(torch.uint8),
                       unpack_buffer(packed).contiguous().view(torch.uint8))
    assert solver.contacts[100, 0] == 0.
    restore_engine_buffers(changed)
    assert solver.contacts[100, 0] == 2.
    tree = NumericTree()
    restored = NumericTree.decode(tree.encode(packed), tree.arrays)
    require_same_layout(restored, packed)
    assert isinstance(restored, torch.Tensor)
    assert torch.equal(restored.view(torch.uint8), unpack_buffer(packed).view(torch.uint8))
    # A restored tensor is writable and cannot mutate the saved checkpoint.
    restored.zero_()
    assert unpack_buffer(packed)[1, 0].view(torch.int64).item() == 0x7FF8000000001234


@pytest.mark.parametrize("size", (600, 30000), ids=("uncompressed", "cached_compressed"))
def test_genesis_tensor_subclass_cache_and_rewind_preserve_independent_bytes(size):
    """The real FEM entity tensor subclass cannot use Torch's deepcopy path."""
    import torch
    from genesis.grad.tensor import Tensor as GenesisTensor

    scene, solver = scene_with_field()
    del solver.field
    solver.vertices = GenesisTensor(torch.arange(size, dtype=torch.float64).reshape(-1, 3))
    original = solver.vertices.detach().as_subclass(torch.Tensor).clone()
    cache = {}
    first = capture_engine_buffers(scene, comparison_cache=cache)
    repeated = capture_engine_buffers(scene, first, cache)
    assert repeated[0] is first[0]
    solver.vertices[100, 1] = -123.
    changed = capture_engine_buffers(scene, repeated, cache)
    assert changed[0].value is not first[0].value
    assert torch.equal(unpack_buffer(first[0].value), original)
    restore_engine_buffers(first)
    assert torch.equal(solver.vertices.as_subclass(torch.Tensor), original)
    restore_engine_buffers(changed)
    assert solver.vertices[100, 1].item() == -123.
