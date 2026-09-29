"""A sparse certificate must check connections, not just their endpoints."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from topogym.planning.buzz_wire_3d.keyframes import connect_held_guide, resolve_keyframes


def pose(x, y):
    return dict(position_m=[x, y, 0.], quaternion_wxyz=[1., 0., 0., 0.])


class ObstacleIK:
    def __init__(self):
        self.seed = np.zeros(3)

    def tcp_pose(self, q):
        return np.asarray(q), Rotation.identity()

    def clearance(self, q, body=None, **kwargs):
        return float(np.linalg.norm(np.asarray(q)[:2]-[.5, 0.])-.18)

    def plan_held_waypoints(self, waypoints, *args, **kwargs):
        target = np.asarray(waypoints[-1][0])
        frames = []
        for u in np.linspace(0., 1., 51):
            q = self.seed+u*(target-self.seed)
            if self.clearance(q) < kwargs['minimum_clearance']:
                raise ValueError('crosses obstacle')
            frames.append(dict(qpos=q.tolist(), position_m=q.tolist(),
                               quaternion_wxyz=[1., 0., 0., 0.]))
        return frames

    def joint_references(self, frames, *args, **kwargs):
        return [dict(row, time_s=i*.025) for i, row in enumerate(frames)]


def test_entity_relative_keyframes_use_observed_rotation_and_position():
    world = dict(bodies=dict(wire=dict(position_m=[1., 2., 3.],
                                     quaternion_wxyz=[2**-.5, 0., 0., 2**-.5])))
    target = resolve_keyframes(world, [dict(pose(.1, 0.), entity='wire')])[0]
    np.testing.assert_allclose(target['position_m'], [1., 2.1, 3.])
    np.testing.assert_allclose(target['quaternion_wxyz'], world['bodies']['wire']['quaternion_wxyz'])


def test_free_endpoints_do_not_certify_a_colliding_connection():
    kin = ObstacleIK()
    result = connect_held_guide(kin, [pose(0., 0.), pose(0., .6), pose(1., .6), pose(1., 0.)],
                               np.zeros(3), Rotation.identity())
    assert result['rejected_shortcuts']
    assert result['keyframe_count'] >= 3
    assert all(kin.clearance(row['qpos']) >= .0015 for row in result['refs'])
    assert np.all(np.diff([row['time_s'] for row in result['refs']]) > 0.)
    assert result['task_success_verified'] is False
    np.testing.assert_array_equal(kin.seed, np.zeros(3))


def test_required_task_gate_is_not_shortcut_away():
    result = connect_held_guide(ObstacleIK(), [pose(0., 0.), pose(0., .6), pose(1., .6)],
                               np.zeros(3), Rotation.identity(), mandatory_indices=[1])
    assert result['keyframe_indices'] == [0, 1, 2]


def test_infeasible_guide_is_rejected_without_changing_seed():
    kin = ObstacleIK()
    with pytest.raises(ValueError, match='remains infeasible'):
        connect_held_guide(kin, [pose(0., 0.), pose(1., 0.)], np.zeros(3), Rotation.identity())
    np.testing.assert_array_equal(kin.seed, np.zeros(3))
