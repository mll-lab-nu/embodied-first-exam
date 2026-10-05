#!/usr/bin/env python3
"""Default Buzz strategy/data dispatch, with no simulated success claims."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.config.registry import task_definition
from topogym.planning.buzz_wire_3d import public_session, reference_policy
from topogym.planning.harbor_bridge import suite
from topogym.planning.harbor_bridge.references import reference_data
from topogym.simulator.config import SimulatorConfig
from topogym.utils.io import to_jsonable


def fake_session(tier, recipe):
    config = SimulatorConfig(task_id="buzz_wire_3d", variation_id=tier, seed=0,
        robot_id="panda_robotiq", control_mode="JOINT_ABS", compute_backend="cuda",
        physics_dt_s=.0025, control_decimation=10, solver_substeps=4,
        grasp_assist=recipe["provenance"]["source_config"]["grasp_assist"])
    initial = copy.deepcopy(recipe["initial_robot"])
    state = dict(physics_step=0, branch_id=0)
    env = SimpleNamespace(config=config, _task=task_definition("buzz_wire_3d", tier)(seed=0),
        tick_record=lambda: {"state": state}, timing_spec=dict(control_dt_s=.025, control_decimation=10),
        _robot=SimpleNamespace(observe=lambda: {"arm": initial}), _world=SimpleNamespace(physics_step=0))
    session = SimpleNamespace(task="buzz_wire_3d", n_steps=0, _resets=0, env=env,
        runtime_binding={"test": "synthetic"}, instance_sha="synthetic", successful=False)
    session.success = lambda: session.successful
    return session


class ReferenceDispatch(unittest.TestCase):
    def test_default_suite_selects_complete_inputs_for_each_tier(self):
        for tier, expected in (("easy", "selection.json"), ("medium", "policy_actions.json"),
                               ("hard", "policy_actions.json")):
            with self.subTest(tier=tier):
                row = dict(task=ROOT / "nonexistent-task", mode="privileged", family="buzz_wire_3d",
                    difficulty=tier, seed=0,
                    session_callback="topogym.planning.buzz_wire_3d.public_session:run_feedback_policy")
                recipe = suite.reference_for(row, {})
                self.assertEqual(recipe["kwargs"], {"variation": tier})
                prefix = f"topogym/planning/harbor_bridge/reference_data/buzz_wire_3d/{tier}/"
                self.assertIn(prefix + expected, recipe["data_files"])
                self.assertIn(prefix + "recipe.json", recipe["data_files"])

    def test_easy_default_uses_all_eleven_selected_feedback_stages(self):
        recipe, selected = reference_policy.load_reference("easy")
        session = fake_session("easy", recipe)
        before = to_jsonable(session.env.config)
        def run(session_arg, output, factory, *, selection):
            self.assertIs(session_arg, session)
            steps = list(factory(session.env, SimpleNamespace(output=output)))
            self.assertEqual([s.name for s in steps], [s["step"] for s in selected])
            self.assertEqual(len(steps), 11)
            self.assertEqual(selection, selected)
            self.assertEqual(steps[-1].name, "final_release")
            session.successful = True
            return {"synthetic": True}
        with tempfile.TemporaryDirectory() as out, \
             patch.object(public_session, "worker", side_effect=AssertionError("Generic worker selected")), \
             patch.object(reference_policy, "run_stages", side_effect=run):
            report = public_session.run_feedback_policy(session, out, variation="easy")
        self.assertEqual(report["policy_kind"], "staged_feedback")
        self.assertEqual(to_jsonable(session.env.config), before)

    def test_medium_hard_default_emit_every_archived_action_at_harbor_decimation(self):
        for tier, count in (("medium", 29544), ("hard", 43568)):
            recipe, expected = reference_policy.load_reference(tier)
            session = fake_session(tier, recipe)
            before = to_jsonable(session.env.config)
            def execute(**kwargs):
                policy = kwargs["policy"]
                policy.initialize(dict(action_spec={"mode": "JOINT_ABS"}, timing_spec=session.env.timing_spec))
                for index, action in enumerate(expected["actions"]):
                    observation = dict(state={"physics_step": index * 10, "branch_id": 0},
                        privileged={"world": {"contact_events": {"events": []}}})
                    self.assertEqual(policy.act(observation), action)
                observation["state"]["physics_step"] = count * 10
                self.assertIsNone(policy.act(observation))
                session.n_steps = count
                session.env._world.physics_step = count * 10
                session.successful = True
                return {"reason": "env_terminal", "synthetic": True}
            with tempfile.TemporaryDirectory() as out, \
                 patch.object(public_session, "worker", side_effect=AssertionError("Generic worker selected")), \
                 patch.object(reference_policy, "run_stages", side_effect=AssertionError("Incomplete stages selected")), \
                 patch.object(reference_policy, "SessionPolicyRunner") as runner:
                runner.return_value.run_policy.side_effect = execute
                report = public_session.run_feedback_policy(session, out, variation=tier)
                runner.assert_called_once_with(session)
            self.assertEqual(report["control_steps"], count)
            self.assertEqual(report["policy_kind"], "compiled_joint_actions")
            self.assertEqual(to_jsonable(session.env.config), before)

    def test_reference_completion_without_native_success_is_failure(self):
        recipe, _ = reference_policy.load_reference("medium")
        session = fake_session("medium", recipe)
        with tempfile.TemporaryDirectory() as out, patch.object(reference_policy, "SessionPolicyRunner") as runner:
            runner.return_value.run_policy.return_value = {"reason": "policy_done"}
            with self.assertRaisesRegex(RuntimeError, "without current Task success"):
                public_session.run_feedback_policy(session, out, variation="medium")
            report = json.loads((Path(out) / "reference_report.json").read_text())
            self.assertFalse(report["task_success"])
            self.assertFalse(report["harbor_qualified"])
            self.assertEqual(report["status"], "failed")

    def test_incompatible_session_is_rejected_before_actions(self):
        recipe, _ = reference_policy.load_reference("hard")
        def timing(s): s.env.timing_spec["control_dt_s"] = .04
        def home(s): s.env._robot.observe()["arm"]["joint_position_rad"][0] += .01
        def layout(s): s.env._task.model_revision = "other-layout"
        def seed(s): s.env.config = replace(s.env.config, seed=1)
        def robot(s): s.env.config = replace(s.env.config, robot_id="aloha")
        def advanced(s): s.n_steps = 1
        def rewind(s): s.env.tick_record()["state"]["branch_id"] = 1
        def assistance(s): s.env.config = replace(s.env.config, grasp_assist={"model": "none"})
        for change in (timing, home, layout, seed, robot, advanced, rewind, assistance):
            with self.subTest(change=change.__name__):
                session = fake_session("hard", recipe)
                change(session)
                with tempfile.TemporaryDirectory() as out, patch.object(reference_policy, "SessionPolicyRunner") as runner:
                    with self.assertRaises(ValueError):
                        public_session.run_feedback_policy(session, out, variation="hard")
                    runner.assert_not_called()

    def test_nonzero_seeds_and_unsupported_tiers_do_not_fall_back(self):
        for tier in ("easy", "medium", "hard"):
            with self.assertRaisesRegex(ValueError, "seed 0"):
                reference_data(ROOT, "buzz_wire_3d", tier, 1)
        for tier in ("very_easy", "easier", "base", "buzz_wire_3d_medium"):
            with self.assertRaisesRegex(ValueError, "No complete Harbor Buzz reference"):
                reference_policy.load_reference(tier)


if __name__ == "__main__":
    unittest.main(verbosity=2)
