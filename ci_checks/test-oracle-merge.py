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
from topogym.planning.standard_rate import RateLimiter, rate_limited_runner
from topogym.planning.solvability import QualificationWorkflow


class OracleMerge(unittest.TestCase):
    def test_live_limited_lock_rows_replay_one_to_one_through_standard_service(self):
        # Lock's pickup requested ~0.041656 rad per row against the 0.04 service
        # limit. Check the real service loop, without starting physics or HTTP.
        import ast
        import math
        initial = np.array([.3, -.2, .04], dtype=np.float32)
        current = initial.copy()
        recorded = []
        def step(row):
            current[:] = row
            recorded.append(current.copy())
            return False
        session = SimpleNamespace(env=SimpleNamespace(_robot=object()),
            robot=SimpleNamespace(grip_index={'arm': 2}), action_layout=['q0', 'q1', 'gripper'],
            hold_action=lambda: current.copy(), step=step)
        targets = np.array([[.34165614, -.22, 0.], [.351, -.23, .04]], dtype=np.float32)
        with patch('topogym.robot.control.compile_action', return_value={}) as compile_action, \
                patch('topogym.planning.harbor_bridge.actions.public_row', side_effect=targets):
            runner = rate_limited_runner(session, control_mode='EE_ABS')
            for _ in targets:
                runner.executor.step({}, mode='EE_ABS')
            self.assertEqual(compile_action.call_count, 2)
        self.assertEqual(runner.rate_limiter.inserted, 1)
        np.testing.assert_array_equal(recorded[1:], targets)
        self.assertEqual(recorded[0][2], targets[0][2])

        path = ROOT / 'harbor_templates/topogym/limited/environment/sim/server.py'
        node = next(n for n in ast.parse(path.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'run_joint_position')
        commands = []
        def commit(row, *args, **kwargs):
            commands.append(row.astype(np.float32).copy())
            return False
        namespace = dict(np=np, math=math, L=SimpleNamespace(control_periods=lambda dt, hz: 1, Recorder=object),
            S=SimpleNamespace(hold_action=lambda: commands[-1] if commands else initial),
            ARMS=['arm'], ARM={'arm': (None, 2)}, N=3, CTRL_HZ=40,
            M=SimpleNamespace(JOINT_STEP_LIMIT_RAD=.04), LAYOUT=session.action_layout,
            clip_joint_row=lambda row, clipped, ri: row, ctrl_step=commit)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        for rows, expected_clipping in ((targets, True), (np.asarray(recorded), False)):
            commands.clear()
            clipped = []
            for row in rows:  # Include request boundaries, including the first row from home.
                namespace['run_joint_position'](row[None], .025, 'hold', None, clipped)
            self.assertEqual(bool(clipped), expected_clipping)
            if not expected_clipping:
                np.testing.assert_array_equal(commands, rows)

    def test_live_limiter_stops_at_session_terminal_without_unrecorded_tail(self):
        rows = []
        def step(row):
            rows.append(row.copy())
            return True
        session = SimpleNamespace(robot=SimpleNamespace(grip_index={'arm': 1}),
            action_layout=['q', 'gripper'], hold_action=lambda: np.zeros(2, dtype=np.float32), step=step)
        limiter = RateLimiter(session, limit_rad=.04)
        self.assertTrue(limiter.step([.2, .04]))
        self.assertEqual(len(rows), 1)
        self.assertLess(abs(rows[0][0]), .04)
        self.assertEqual(rows[0][1], np.float32(.04))

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
