#!/usr/bin/env python3
"""CPU contracts for remote oracle fixes coexisting with local helper work."""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from topogym.planning.knot_untying.robot_oracle import Runner
from topogym.planning.standard_rate import RateLimiter
from topogym.planning.solvability import QualificationWorkflow


class OracleMerge(unittest.TestCase):
    def test_policy_initialization_keeps_optional_assist_and_local_protocol(self):
        @dataclass
        class Assist:
            model: str = 'contact_weld_v1'
        for assist in (None, Assist()):
            with self.subTest(assist=assist):
                env = SimpleNamespace(_world=SimpleNamespace(physics_step=0),
                    _robot=SimpleNamespace(description=None), timing_spec={'control_dt_s': .025})
                if assist is not None:
                    env.config = SimpleNamespace(grasp_assist=assist)
                session = SimpleNamespace(env=env, n_steps=0, episode_done=True, episode_end='success',
                    success=lambda: True, _recording=[], _recorded_ticks=[])
                policy = SimpleNamespace(initialize=Mock())
                with patch('topogym.robot.control.action_spec', return_value={'mode': 'JOINT_ABS'}):
                    SessionPolicyRunner(session).run_policy(request_id='test', policy=policy,
                        submission_hash='test', state_fields=('world',))
                value = policy.initialize.call_args.args[0]
                self.assertEqual((value['schema_version'], value['mode'], value['rgb_available']),
                                 (2, 'unlimited', False))
                self.assertEqual(value['observation_spec']['privileged_fields'], ['world'])
                if assist is not None:
                    self.assertEqual(value['action_spec']['grasp_assist'], {'model': assist.model})
                else:
                    self.assertNotIn('grasp_assist', value['action_spec'])

    def test_below_easy_uses_one_shared_limiter_and_keeps_gripper_target(self):
        current = np.zeros(3, dtype=np.float32)
        rows = []
        def commit(row):
            current[:] = row
            rows.append(current.copy())
            return False
        session = SimpleNamespace(robot=SimpleNamespace(grip_index={'arm': 2}),
            action_layout=['q0', 'q1', 'gripper'], hold_action=lambda: current.copy(), step=commit)
        limiter = RateLimiter(session, limit_rad=.03125)
        target = np.array([.25, -.11, .007], dtype=np.float32)
        runner = SimpleNamespace(joint_step_limit=.03125,
            _step_once=lambda phase: limiter.step(target))
        with patch('topogym.planning.knot_untying.simplified_policy.step_with_joint_limit',
                   side_effect=AssertionError('double rate limiting')):
            Runner.step(runner, 'approach')
        self.assertEqual(limiter.requested, 1)
        changes = np.diff(np.vstack([np.zeros(3), rows]), axis=0)
        self.assertLessEqual(float(np.abs(changes[:, :2]).max()), .03125)
        np.testing.assert_array_equal(current, target)
        np.testing.assert_allclose(np.asarray(rows)[:, 2], target[2])

    def test_proof_accepts_restored_birth_but_proof_and_session_reject_rewind(self):
        state = dict(episode_id='episode', branch_id=1, state_id=0, physics_step=0)
        env = SimpleNamespace(tick_record=lambda: {'state': dict(state)})
        session = SimpleNamespace(env=env, n_steps=0, _resets=0, runtime_binding={'bound': True},
            instance_exact=True, S0=dict(state))
        runner = SimpleNamespace(env=env, session=session)
        with tempfile.TemporaryDirectory() as directory, \
                patch('topogym.planning.solvability.validate_identity'), \
                patch('topogym.planning.solvability.identity_for', return_value={}):
            for mode in ('proof', 'session'):
                with self.subTest(mode=mode):
                    state['branch_id'] = 1
                    workflow = QualificationWorkflow(runner, Path(directory)/mode, {}, mode=mode)
                    self.assertEqual(workflow.report['birth']['branch_id'], 1)
                    state['branch_id'] = 2
                    with self.assertRaisesRegex(ValueError, 'rewound'):
                        workflow.run(None)


if __name__ == '__main__':
    unittest.main()
