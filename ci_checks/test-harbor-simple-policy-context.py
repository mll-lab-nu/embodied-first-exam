#!/usr/bin/env python3
"""Real simple-controller initialization and frozen-session workflow boundaries."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from topogym.planning.solvability import QualificationWorkflow
from topogym.planning.interlocked_claws.simplified_policy import SimplifiedClawsPolicy
from topogym.planning.lock_picking.lock_picking_medium_planning import LockPickingMediumPolicy


class Context(unittest.TestCase):
    def test_actual_claws_and_lock_initializers_receive_declared_contract(self):
        for robot_id, policy in (("aloha", SimplifiedClawsPolicy(part="acquire")),
                ("panda_robotiq", LockPickingMediumPolicy(geometry={}))):
            env = SimpleNamespace(_robot=SimpleNamespace(description=None),
                _world=SimpleNamespace(physics_step=0), config=SimpleNamespace(grasp_assist={"model": "contact_weld_v1"}),
                timing_spec={"control_dt_s": .025})
            session = SimpleNamespace(env=env, n_steps=0, episode_done=True, episode_end=None,
                success=lambda: False, _recording=[], _recorded_ticks=[])
            with patch("topogym.robot.control.action_spec", return_value={"mode": "EE_ABS", "robot_id": robot_id}):
                result = SessionPolicyRunner(session, control_mode="EE_ABS").run_policy(
                    request_id="contract", policy=policy, submission_hash="test", state_fields=("world",))
            self.assertEqual(result["control_steps"], 0)
            self.assertFalse(result["task_success"])


class FrozenOrigin(unittest.TestCase):
    def make_runner(self):
        state = dict(episode_id="episode", state_id=0, branch_id=1, physics_step=0,
                     sim_time_s=0., parent_state_id=None)
        env = SimpleNamespace(tick_record=lambda: dict(state=deepcopy(state)), is_solved=lambda: False)
        session = SimpleNamespace(env=env, n_steps=0, _resets=0, runtime_binding={"id": "bound"},
            instance_exact=True, S0={"episode_id": "episode", "state_id": 0})
        return SimpleNamespace(env=env, session=session), state

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch("topogym.planning.solvability.validate_identity"),
                        patch("topogym.planning.solvability.identity_for", return_value={})]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_bound_restored_origin_is_not_a_standalone_birth_proof(self):
        runner, _ = self.make_runner()
        with self.assertRaisesRegex(ValueError, "fresh episode birth"):
            QualificationWorkflow(runner, self.root / "proof", {}, mode="proof")
        flow = QualificationWorkflow(runner, self.root / "session", {}, mode="session")
        self.assertEqual(flow.report["birth"]["branch_id"], 1)
        with self.assertRaisesRegex(ValueError, "unavailable"):
            flow.rewind(runner.session.S0)
        report = flow.finish()
        self.assertFalse(report["accepted_proof"])
        self.assertFalse(report["continuous_from_birth"])

    def test_progress_reset_unbound_or_wrong_checkpoint_cannot_be_new_origin(self):
        for index, change in enumerate(("progress", "reset", "unbound", "wrong_checkpoint", "physics")):
            runner, state = self.make_runner()
            if change == "progress": runner.session.n_steps = 1
            elif change == "reset": runner.session._resets = 1
            elif change == "unbound": runner.session.runtime_binding = None
            elif change == "wrong_checkpoint": state["state_id"] = 5
            else: state["physics_step"] = 1
            with self.assertRaisesRegex(ValueError, "fresh, exactly bound"):
                QualificationWorkflow(runner, self.root / str(index), {}, mode="session")


if __name__ == "__main__":
    unittest.main()
