from types import SimpleNamespace

import numpy as np
import pytest

from topogym.evaluation.cloth_binding import audit_visual_binding
from topogym.world.physics.pbd_binding import read_birth_visual_binding


def audit(p, v, puv, vuv, idx, weights):
    return audit_visual_binding(p, v, puv, vuv, idx, weights,
        material_distance_limit_m=.02, reconstruction_tolerance_m=1e-8,
        material_reconstruction_tolerance_m=1e-8)


def flat():
    p = np.array([[0., 0., 0.], [.01, 0., 0.], [0., .01, 0.]])
    v = np.array([[.002, .002, 0.]])
    return p, v, p[:, :2].copy(), v[:, :2].copy(), np.array([[0, 1, 2]]), np.array([[.6, .2, .2]])


def test_flat_binding_accepts_rank_two_and_affine_negative_weights():
    args = list(flat())
    assert audit(*args)["passed"]
    args[1][0, 0] = args[3][0, 0] = -.002
    args[5] = np.array([[1., -.2, .2]])
    report = audit(*args)
    assert report["passed"]
    assert report["negative_weight_count"] == 1
    assert report["maximum_absolute_weight_sum"] == pytest.approx(1.4)


def test_exact_birth_reconstruction_does_not_hide_cross_layer_binding():
    p, v, puv, vuv, _, _ = flat()
    particles = np.vstack([p, p+[0, 0, .001]])
    material = np.vstack([puv, puv+[1, 0]])
    visual = v+[0, 0, .0005]
    idx = np.array([[0, 1, 2, 3, 4, 5]])
    weights = np.array([[.3, .1, .1, .3, .1, .1]])
    report = audit(particles, visual, material, vuv, idx, weights)
    assert report["checks"]["position_reconstruction"]
    assert report["checks"]["affine_weight_sum"]
    assert report["nonlocal_support_count"] == 3
    assert not report["passed"]
    moved = particles.copy()
    moved[3:, 0] += .02
    reconstructed = np.einsum("vk,vkj->vj", weights, moved[idx])
    assert np.linalg.norm(reconstructed-visual) == pytest.approx(.01)


@pytest.mark.parametrize("bad_index", [-1, 3])
def test_foreign_entity_support_is_rejected(bad_index):
    args = list(flat())
    args[4][0, 0] = bad_index
    with pytest.raises(ValueError, match="outside this entity"):
        audit(*args)


def test_nonfinite_and_non_affine_bindings_fail_without_json_nan():
    import json
    args = list(flat())
    args[5][0, 0] = np.nan
    report = audit(*args)
    assert not report["passed"]
    json.dumps(report, allow_nan=False)
    args = list(flat())
    args[5] *= 2
    assert not audit(*args)["checks"]["affine_weight_sum"]


def test_material_order_shape_and_fractional_indices_are_rejected():
    args = list(flat())
    args[2] = args[2][:-1]
    with pytest.raises(ValueError, match="order/count"):
        audit(*args)
    args = list(flat())
    args[4] = args[4].astype(float)
    with pytest.raises(ValueError, match="integer supports"):
        audit(*args)


def entity(particle_start=7):
    p, v, _, _, idx, weights = flat()
    global_idx = np.full((4, 3), -100, dtype=int)
    global_w = np.zeros((4, 3))
    global_idx[2] = idx[0]+particle_start
    global_w[2] = weights[0]
    # Expose backend fields, and no stepping/particle-position setter/getter.
    info = SimpleNamespace(support_idxs=SimpleNamespace(to_numpy=lambda: global_idx),
                           support_weights=SimpleNamespace(to_numpy=lambda: global_w))
    return SimpleNamespace(particle_start=particle_start, vvert_start=2,
        n_particles=3, n_vverts=1, _particles=p, _vverts=v,
        solver=SimpleNamespace(vverts_info=info)), global_idx, global_w


def test_readonly_adapter_owns_arrays_and_normalizes_entity_offsets():
    e, indices, weights = entity()
    captured = read_birth_visual_binding(e)
    np.testing.assert_array_equal(captured.support_indices, [[0, 1, 2]])
    assert captured.sha256 == read_birth_visual_binding(entity(20)[0]).sha256
    old_hash = captured.sha256
    indices[2] = 100
    weights[2] = 0
    e._particles[:] = 10
    assert captured.sha256 == old_hash
    with pytest.raises(ValueError):
        captured.support_weights[0, 0] = 0


def test_adapter_fails_closed_for_foreign_support_and_unknown_schema():
    e, indices, _ = entity()
    indices[2, 0] = e.particle_start-1
    with pytest.raises(ValueError, match="outside this entity"):
        read_birth_visual_binding(e)
    with pytest.raises(RuntimeError, match="Unsupported/unbuilt"):
        read_birth_visual_binding(SimpleNamespace())
    e, _, _ = entity()
    e._particles = np.zeros((1, 3, 3))
    with pytest.raises(RuntimeError, match="buffer shapes"):
        read_birth_visual_binding(e)
