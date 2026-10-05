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
from topogym.planning.buzz_wire_3d import public_session, reference_policy, retimed
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
    # A Harbor Session restores its frozen birth once at construction: its first tick is branch 1, state 0, physics step 0.
    state = dict(physics_step=0, branch_id=1, state_id=0)
    env = SimpleNamespace(config=config, _task=task_definition("buzz_wire_3d", tier)(seed=0),
        tick_record=lambda: {"state": state}, timing_spec=dict(control_dt_s=.025, control_decimation=10),
        _robot=SimpleNamespace(observe=lambda: {"arm": initial}), _world=SimpleNamespace(physics_step=0))
    # The public action layout (7 arm joints, then the native gripper) that the standard-rate limiter reads.
    session = SimpleNamespace(task="buzz_wire_3d", n_steps=0, _resets=0, env=env,
        runtime_binding={"test": "synthetic"}, instance_sha="synthetic", successful=False,
        robot=SimpleNamespace(grip_index={"arm": 7}), action_layout=[f"joint{i}" for i in range(1, 8)] + ["arm_native_gripper"])
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
        def run(session_arg, output, factory, *, selection, runner=None):
            self.assertIs(session_arg, session)
            # oraclefix2 O2-2: the staged easy proof records only rows within the standard per-step joint limit.
            self.assertIsNotNone(getattr(runner, "rate_limiter", None))
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
            if recipe.get("retime") is not None:
                # oraclefix2: a tier with a "retime" entry replays its archived rows through retimed.run_retimed
                def replay(session_arg, document, retime, *, request_id, submission_hash):
                    self.assertIs(session_arg, session)
                    self.assertEqual(len(document["actions"]), count)
                    self.assertEqual(document["actions"][-1], expected["actions"][-1])
                    self.assertEqual(retime, recipe["retime"])
                    session.successful = True
                    return {"reason": "env_terminal", "synthetic": True}
                with tempfile.TemporaryDirectory() as out, \
                     patch.object(retimed, "run_retimed", side_effect=replay), \
                     patch.object(reference_policy, "SessionPolicyRunner",
                                  side_effect=AssertionError("Unretimed replay selected")):
                    report = public_session.run_feedback_policy(session, out, variation=tier)
                self.assertTrue(report["task_success"])
                self.assertEqual(report["policy_kind"], "compiled_joint_actions")
                continue
            def execute(**kwargs):
                policy = kwargs["policy"]
                policy.initialize(dict(action_spec={"mode": "JOINT_ABS"}, timing_spec=session.env.timing_spec))
                for index, action in enumerate(expected["actions"]):
                    observation = dict(state={"physics_step": index * 10, "branch_id": 1, "state_id": index * 10},
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

    def test_retimed_policy_keeps_rows_outside_segments_and_slows_near_the_wire(self):
        actions = [{"arm": {"joint_position_rad": [0.] * 7, "gripper_position_rad": .8}}]
        actions += [{"arm": {"joint_position_rad": [i * .001] * 7}} if i % 3 else {} for i in range(1, 40)]
        document = {"schema": "buzz_compiled_joint_policy_v1", "actions": actions, "control_dt_s": .025}
        gaps = iter([.005] * 8 + [.0008] * 3 + [.0003] * 3 + [.003] * 100)
        policy = retimed.RetimedJointPolicy(document, segments=[(5, 30, 3.)], clearance=lambda observation: next(gaps))
        observation = {"privileged": {"world": {"contact_events": {"events": []}}}}
        emitted = []
        while (action := policy.act(observation)) is not None:
            emitted.append(action)
        sources = [row[0] for row in policy.log]
        # 1x before the segment, 3x inside it, 1x below 1 mm, hold below 0.5 mm, 3x again above 2 mm, 1x after it
        self.assertEqual(sources, [0, 1, 2, 3, 4, 5, 8, 11, 12, 13, 14, 14, 14, 14, 17, 20, 23, 26, 29, 32, 33, 34, 35,
                                   36, 37, 38, 39])
        self.assertEqual(policy.events, dict(slowed=1, holds=1, held_rows=3))
        for action, source, step in zip(emitted, sources, [row[1] for row in policy.log]):
            if step == 1. and source == int(source):
                self.assertEqual(action, actions[int(source)])     # consecutive source rows: archived row as is
        touch = {"privileged": {"world": {"contact_events": {"events": [
            {"touching": True, "role_a": "robot", "role_b": "wire_metal"}]}}}}
        with self.assertRaisesRegex(RuntimeError, "Robot touched the wire"):
            retimed.RetimedJointPolicy(document).act(touch)

    def test_reference_completion_without_native_success_is_failure(self):
        recipe, _ = reference_policy.load_reference("medium")
        session = fake_session("medium", recipe)
        with tempfile.TemporaryDirectory() as out, patch.object(reference_policy, "SessionPolicyRunner") as runner, \
             patch.object(retimed, "run_retimed", return_value={"reason": "policy_done"}):
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
        def rewind(s): s.env.tick_record()["state"].update(branch_id=2, state_id=7)   # restored onto a later state
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
