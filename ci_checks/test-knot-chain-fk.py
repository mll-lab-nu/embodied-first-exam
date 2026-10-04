#!/usr/bin/env python3
"""Read-only host FK: authored joint anchors, nonzero offsets and fail-closed scope."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.knot_untying.chain_fk import StaticChainFK


class ChainFK(unittest.TestCase):
    def fixture(self, *, moving_root=False, n_envs=0):
        import genesis as gs
        fields = []
        def field(values):
            obj = SimpleNamespace(to_numpy=Mock(return_value=np.asarray(values, float)))
            fields.append(obj)
            return obj
        solver = SimpleNamespace(n_envs=n_envs,
            links_info=SimpleNamespace(pos=field([[0, 0, 0], [0, 0, 0], [.3, 0, 0], [.1, 0, 0]]),
                quat=field([[1, 0, 0, 0]]*4), parent_idx=field([-1, -1, 1, 2]),
                is_fixed=field([1, not moving_root, 0, 0]), joint_start=field([0, 0, 1, 2]),
                joint_end=field([0, 1, 2, 3])),
            joints_info=SimpleNamespace(type=field([int(gs.JOINT_TYPE.FIXED), int(gs.JOINT_TYPE.REVOLUTE),
                int(gs.JOINT_TYPE.PRISMATIC)]), q_start=field([0, 2, 3]), dof_start=field([0, 0, 1]),
                pos=field([[0, 0, 0], [.2, 0, 0], [0, 0, 0]])),
            dofs_info=SimpleNamespace(motion_ang=field([[0, 0, 1], [0, 0, 0]]),
                motion_vel=field([[0, 0, 0], [1, 0, 0]])),
            _rigid_global_info=SimpleNamespace(qpos0=field([9., 8., .1, 0.])),
            links_state=SimpleNamespace(pos=field([[0, 0, 0], [.1, 0, 1], [0, 0, 0], [0, 0, 0]]),
                quat=field([[1, 0, 0, 0]]*4)))
        entity = SimpleNamespace(_solver=solver, link_start=1, link_end=4, q_start=2, n_qs=2)
        return entity, fields

    def test_anchor_and_slide_with_nonzero_solver_offsets(self):
        entity, _ = self.fixture()
        fk = StaticChainFK(entity)
        angle, slide = .7, .05
        pose = fk.solve([.1+angle, slide])
        rotation = Rotation.from_rotvec([0, 0, angle])
        anchor = np.array([.6, 0, 1])
        turn_position = anchor-rotation.apply([.2, 0, 0])
        np.testing.assert_allclose(pose['position_world_m'],
            [[.1, 0, 1], turn_position, turn_position+rotation.apply([.1+slide, 0, 0])], atol=1e-12)
        np.testing.assert_allclose(pose['orientation_wxyz'][1:],
            np.tile(rotation.as_quat()[[3, 0, 1, 2]], (2, 1)), atol=1e-12)

    def test_queries_do_not_read_or_mutate_live_solver(self):
        entity, fields = self.fixture()
        fk = StaticChainFK(entity)
        before = fk.solve([.8, .05])
        for f in fields:
            f.to_numpy.return_value[:] = 99
            f.to_numpy.side_effect = AssertionError('Query touched solver')
        del entity
        after = fk.solve([.8, .05])
        for key in before:
            np.testing.assert_array_equal(before[key], after[key])
        for f in fields:
            self.assertEqual(f.to_numpy.call_count, 1)

    def test_invalid_query_and_unsupported_environment_are_rejected(self):
        entity, _ = self.fixture()
        fk = StaticChainFK(entity)
        for q in ([.1], [np.nan, 0], [[.1, 0]]):
            with self.assertRaises(ValueError):
                fk.solve(q)
        for args in (dict(moving_root=True), dict(n_envs=2)):
            entity, _ = self.fixture(**args)
            with self.assertRaises(ValueError):
                StaticChainFK(entity)


if __name__ == '__main__':
    unittest.main()
