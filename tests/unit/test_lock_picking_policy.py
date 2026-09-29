"""Regression coverage for carrying load compensation through a narrow bore."""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.lock_picking.lock_picking_medium_planning import LockPickingMediumPolicy


def test_precise_stage_preserves_the_preceding_tcp_target():
    policy = LockPickingMediumPolicy(
        geometry=dict(first_x=0., pitch=.15, center_y=0., axis_z=1.), part="solve")
    policy.dt, policy.grip = .1, .8
    policy.precise_insertion = True
    key_position = np.array([0., 0., 1.])
    measured_tcp = np.array([-.4, 0., 1.])
    previous_position = measured_tcp + [0., .0003, .0004]
    previous_rotation = Rotation.from_euler("y", .0004)
    policy.commanded_tcp = (previous_position.copy(), previous_rotation)
    policy._holding = lambda: True
    policy._key = lambda: (key_position, Rotation.identity())
    policy._tcp = lambda: (measured_tcp, Rotation.identity())

    # The next movement starts with a tiny axial advance. Neither the earlier
    # position nor the angle compensation may be dropped at this boundary.
    action = next(policy._move_key(depth=1.1, angle=0., seconds=3.))["arm"]
    target = np.array(action["position_world_m"])
    orientation = Rotation.from_quat(np.array(action["orientation_wxyz"])[[1, 2, 3, 0]])
    assert 0. < target[0] - previous_position[0] < .0001
    np.testing.assert_allclose(target[1:], previous_position[1:], atol=1e-12)
    assert (previous_rotation.inv() * orientation).magnitude() < 1e-12
    np.testing.assert_allclose(policy.commanded_tcp[0], target)
