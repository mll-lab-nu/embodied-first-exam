"""Portable numeric archives reject corruption and mismatched layouts."""
import json
import numpy as np
import pytest

from topogym.world.initial_state import save_numeric_archive, load_numeric_archive, require_same_layout
from topogym.utils.io import sha256_file


def test_numeric_roundtrip_preserves_types_and_values(tmp_path):
    import torch
    data = dict(particles=np.arange(12, dtype=np.float64).reshape(4, 3),
        controller=torch.tensor([.1, .2], dtype=torch.float64),
        nested=(None, [False, 8, "stage"], {"rng": np.arange(4, dtype=np.uint32)}))
    path = save_numeric_archive(tmp_path/"state", data, {"scope": "test"})
    actual, metadata = load_numeric_archive(path, expected_sha256=sha256_file(path))
    require_same_layout(actual, data)
    np.testing.assert_array_equal(actual["particles"], data["particles"])
    assert torch.equal(actual["controller"], data["controller"])
    assert metadata == {"scope": "test"}


@pytest.mark.parametrize("shape", [(0,), (3, 0), (0, 3)])
def test_restored_empty_tensor_supports_snapshot_byte_comparison(tmp_path, shape):
    import torch
    original = torch.empty(shape, dtype=torch.int32, device="cpu")
    path = save_numeric_archive(tmp_path/"state", original, {})
    restored, _ = load_numeric_archive(path)
    require_same_layout(restored, original)
    assert torch.equal(restored.reshape(-1).view(torch.uint8),
                       original.reshape(-1).view(torch.uint8))


@pytest.mark.parametrize("corruption", ["manifest_hash", "arrays", "schema", "traversal", "shape"])
def test_archive_rejects_corruption(tmp_path, corruption):
    path = save_numeric_archive(tmp_path/"state", np.ones((3, 2)), {})
    manifest = json.loads(path.read_text())
    expected = None
    if corruption == "manifest_hash":
        expected = "0"*64
    elif corruption == "arrays":
        (path.parent/"arrays.npz").write_bytes(b"damaged")
    elif corruption == "schema":
        manifest["schema_version"] = 77
    elif corruption == "traversal":
        manifest["arrays"]["path"] = "../arrays.npz"
    elif corruption == "shape":
        manifest["tree"]["shape"] = [1, 6]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_numeric_archive(path, expected_sha256=expected)


def test_archive_does_not_pickle_live_objects(tmp_path):
    with pytest.raises(TypeError, match="Unsupported"):
        save_numeric_archive(tmp_path/"live", {"scene": object()}, {})
    with pytest.raises(ValueError, match="numeric"):
        save_numeric_archive(tmp_path/"object", np.array([object()], dtype=object), {})


@pytest.mark.parametrize("value", [np.zeros((2, 3)), np.zeros(6, dtype=np.float32), {"wrong": 0}])
def test_layout_mismatch(value):
    with pytest.raises(ValueError):
        require_same_layout(value, np.zeros(6, dtype=np.float64))


def test_unqualified_archive_is_rejected_before_world_access(tmp_path):
    from topogym.tasks.base import InitialStateSpec
    from topogym.world.initial_state import restore_declared_initial_state
    path = save_numeric_archive(tmp_path/"state", {}, {"qualification": {"passed": False}})
    with pytest.raises(ValueError, match="qualification"):
        restore_declared_initial_state(None, None, InitialStateSpec(path, sha256_file(path)), identity={})
