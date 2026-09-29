"""Physical NaN/Inf cannot silently become a saved successful tick."""

import numpy as np
import pytest
from topogym.world.state import (
    PackedArray,
    pack_buffer,
    unpack_buffer,
    require_finite_state,
)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_invalid_fem_numbers_explain_the_entity_and_field(bad):
    state = {"fem": {"rope": {"velocity_m_s": np.array([[0.0, bad, 0.0]])}}}
    with pytest.raises(FloatingPointError, match="world/fem/rope/velocity_m_s"):
        require_finite_state(state)


def test_empty_contacts_and_non_numeric_identity_are_valid():
    require_finite_state(
        {
            "contacts": {"force": np.empty((0, 3))},
            "frame": 0,
            "units": "SI",
            "native_valid": True,
        }
    )


def test_scalar_physical_diagnostics_are_not_omitted():
    with pytest.raises(FloatingPointError, match="minimum"):
        require_finite_state({"ipc": {"volume_ratio": {"rope": {"minimum": np.nan}}}})


def test_large_checkpoint_preserves_nan_payloads_and_signed_zero_bits():
    bits = np.zeros(20000, dtype=np.uint64)
    bits[:4] = [0, 0x8000000000000000, 0x7FF8000000001234, 0x7FF0000000000000]
    packed = pack_buffer(bits.view(np.float64))
    assert isinstance(packed, PackedArray)
    np.testing.assert_array_equal(unpack_buffer(packed).view(np.uint64), bits)
    assert packed.stored_nbytes < packed.nbytes / 10


def test_compressed_strided_checkpoint_is_independent_of_live_and_restored_arrays():
    source = np.arange(40000, dtype=np.int32).reshape(200, 200).T
    expected = source.copy()
    first = pack_buffer(source)
    source[:] = -1
    second = pack_buffer(source)
    restored = unpack_buffer(first)
    np.testing.assert_array_equal(restored, expected)
    restored[:] = 5
    np.testing.assert_array_equal(unpack_buffer(first), expected)
    np.testing.assert_array_equal(unpack_buffer(second), -np.ones_like(source))


def test_structured_and_nested_physics_buffers_keep_their_schema():
    values = np.zeros(10000, dtype=[("index", "<i4"), ("velocity", "<f8", (3,))])
    values["index"] = np.arange(len(values))
    packed = pack_buffer({"contacts": values, "small": np.array([3.0])})
    restored = unpack_buffer(packed)
    assert restored["contacts"].dtype == values.dtype
    np.testing.assert_array_equal(restored["contacts"], values)
    assert restored["small"].flags.writeable
