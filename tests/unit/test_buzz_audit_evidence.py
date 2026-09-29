"""The independent audit reconstructs typed JSON empties, not invalid covers."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from topogym.evaluation.terminal.clearance import validate_robot_planes


spec = importlib.util.spec_from_file_location(
    "buzz_audit", Path(__file__).resolve().parents[2] / "scripts/audit_buzz_wire_policy.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_inline_empty_cover_preserves_box_fallback():
    world = {"release_geometry": {"schema_version": 2,
        "robot_convex_planes_m": [[], [[1., 0., 0., -2.]]]}}
    assert audit.restore_release_geometry_shapes(world) == 1
    planes = validate_robot_planes(world["release_geometry"]["robot_convex_planes_m"], 2)
    assert planes[0].shape == (0, 4)
    np.testing.assert_array_equal(planes[1], [[1., 0., 0., -2.]])
    assert audit.restore_release_geometry_shapes(world) == 0


@pytest.mark.parametrize("invalid", [[[0., 0., 0., 0.]], [[]], [1., 0., 0., 0.]])
def test_nonempty_invalid_covers_remain_rejected(invalid):
    world = {"release_geometry": {"schema_version": 2,
        "robot_convex_planes_m": [invalid]}}
    assert audit.restore_release_geometry_shapes(world) == 0
    with pytest.raises(ValueError, match="Invalid release convex planes"):
        validate_robot_planes(world["release_geometry"]["robot_convex_planes_m"], 1)
