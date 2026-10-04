#!/usr/bin/env python3
"""Exercise the real Session.step boundary with a fake Env; no physics proof."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'harbor_templates/topogym/common')]
import rcb_topogym as tooling
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from topogym.planning.harbor_bridge.contracts import BridgeError, SmokeComplete
from topogym.planning.harbor_bridge.evidence import SessionEvidence, evaluation_state


def session(*, guard=False, terminal=True):
    # Use the actual method used in evaluation; only its physics dependencies are fake.
    s = tooling.Session.__new__(tooling.Session)
    s.robot = SimpleNamespace(action_dim=2, layout=['joint', 'gripper'],
        clip=lambda row: row.copy(), command=lambda row: row.copy())
    s.table_guard = SimpleNamespace(apply=lambda row, previous: row / 2 if guard else row)
    s.monitor = SimpleNamespace(read=lambda **kwargs: dict(scope='episode', rules='test-fixture'))
    s.rules = dict(revision='test-fixture', contact={'deep_m': .003})
    s.pbd_depenetration_margin_m_s = .05
    s.particle_speed_guard = True
    s.instability = None
    s.episode_done, s.episode_end = False, None
    s.n_steps = s.physics_steps = 0
    s.sim_time_s = 0.
    s.max_steps = 100
    s._targets = np.zeros(2)
    s._recording, s._recorded_ticks, s._video = [], [], None
    s._video_begin = lambda: None
    s.env = SimpleNamespace(step=Mock(return_value=(None, 1., terminal, False,
        dict(physics_steps=10, action_duration_s=.025, task_success=terminal))), is_solved=lambda: terminal)
    return s


class Evidence(unittest.TestCase):
    def test_real_session_guard_remains_active_and_adjustments_are_reported(self):
        s = session(guard=True)
        audit = SessionEvidence(s)
        action = np.array([.25, .03125], dtype=np.float32)
        original = action.copy()
        self.assertTrue(s.step(action))
        audit.check()
        report = audit.report()
        np.testing.assert_array_equal(action, original)
        np.testing.assert_array_equal(s.env.step.call_args.args[0], action / 2)
        self.assertEqual(s.env.step.call_count, 1)
        self.assertEqual(report['action_transfer']['adjusted_rows'], 1)
        self.assertNotEqual(report['action_transfer']['requested_float32_sha256'],
                            report['action_transfer']['executed_float32_sha256'])
        self.assertTrue(report['initial']['particle_speed_guard'])
        self.assertEqual(report['final']['rules'], s.rules)
        audit.close()
        self.assertNotIn('step', vars(s))

    def test_exact_transfer_is_recorded_without_claiming_env_equivalence(self):
        s = session()
        audit = SessionEvidence(s)
        s.step([.25, .03125])
        audit.check()
        report = audit.report()
        self.assertEqual(report['action_transfer']['adjusted_rows'], 0)
        self.assertEqual(report['action_transfer']['requested_float32_sha256'],
                         report['action_transfer']['executed_float32_sha256'])
        self.assertIn('does not prove', report['scope'])
        audit.close()

    def test_post_terminal_calls_do_not_invent_committed_rows(self):
        s = session()
        audit = SessionEvidence(s)
        s.step([.25, .03125])
        s.step([.25, .03125])
        audit.check()
        self.assertEqual(audit.calls, 2)
        self.assertEqual(audit.rows, 1)
        self.assertEqual(s.env.step.call_count, 1)
        audit.close()

    def test_smoke_boundary_records_real_actions_and_preserves_incomplete_outcome(self):
        s = session(terminal=False)
        audit = SessionEvidence(s, smoke_steps=3)
        for _ in range(3):
            self.assertFalse(s.step([.25, .03125]))
        with self.assertRaises(SmokeComplete):
            s.step([.25, .03125])
        audit.check()
        self.assertEqual(audit.rows, 3)
        self.assertEqual(s.env.step.call_count, 3)
        self.assertFalse(s.success())
        audit.close()

    def test_physics_exception_propagates_without_inventing_success(self):
        s = session()
        s.env.step.side_effect = RuntimeError('physics failure')
        audit = SessionEvidence(s)
        with self.assertRaisesRegex(RuntimeError, 'physics failure'):
            s.step([.25, .03125])
        self.assertEqual(audit.rows, 0)
        audit.close()

    def test_disabling_rules_replacing_step_and_bypassing_step_are_rejected(self):
        for change in ('rules', 'guard', 'step', 'bypass'):
            with self.subTest(change=change):
                s = session()
                audit = SessionEvidence(s)
                if change == 'rules': s.rules['contact']['deep_m'] = 99.
                elif change == 'guard': s.table_guard = SimpleNamespace()
                elif change == 'step': s.step = audit.original
                else: audit.original([.25, .03125])
                with self.assertRaises(BridgeError): audit.check()
                audit.close()

    def test_missing_rule_evidence_is_unknown_and_snapshot_is_independent(self):
        self.assertIsNone(evaluation_state(SimpleNamespace())['rules'])
        s = session()
        snapshot = evaluation_state(s)
        before = deepcopy(s.rules)
        snapshot['rules']['contact']['deep_m'] = 99.
        self.assertEqual(s.rules, before)


class PolicyBoundary(unittest.TestCase):
    def test_feedback_stops_on_session_terminal_even_when_runaway_flag_is_false(self):
        s = SimpleNamespace(episode_done=False, episode_end=None, n_steps=0,
            success=lambda: True, _recording=[], _recorded_ticks=[], env=SimpleNamespace(_world=SimpleNamespace(physics_step=0, sim_time_s=0.),
                _robot=SimpleNamespace(description=None, observe=lambda: {'measured_joint': 0.}), timing_spec={}))
        s.env.tick_record = lambda: {"state": {"physics_step": s.env._world.physics_step, "branch_id": 0}}
        runner = SessionPolicyRunner(s)
        policy = SimpleNamespace(act=Mock(return_value={}))
        def step(*args, **kwargs):
            s._recording.append([])
            s._recorded_ticks.append(10)
            s.n_steps += 1
            s.env._world.physics_step += 10
            s.episode_end = 'success'
            if s.n_steps > 1:
                self.fail('Policy must not request another action after Session termination')
            return True
        runner.executor.step = step
        with patch('topogym.robot.control.action_spec', return_value={}):
            report = runner.run_policy(request_id='test', policy=policy, submission_hash='test')
        self.assertEqual(policy.act.call_count, 1)
        self.assertEqual(report['reason'], 'env_terminal')
        self.assertEqual(report['control_steps'], 1)


if __name__ == '__main__':
    unittest.main()
