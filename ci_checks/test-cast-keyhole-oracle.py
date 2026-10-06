#!/usr/bin/env python3
"""Reference command evidence checks; no claim of physical oracle success."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.cast_keyhole.oracle_artifacts import PolicyTrace, read_native_commands
from scripts.oracle_runners.package_cast_keyhole_oracle import package, digest
from topogym.planning.cast_keyhole.public_session import public_row


class PublicFeedbackAdapterTests(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        self.targets = {'left': dict(joint_position_rad=[.1, .2], gripper_position_m=.024)}
        self.session = SimpleNamespace(
            action_layout=['left/j0', 'left/j1', 'left/gripper'],
            env=SimpleNamespace(_robot=SimpleNamespace(
                capture_state=lambda: SimpleNamespace(targets=self.targets),
                groups={'left': SimpleNamespace(gripper_field='gripper_position_m')})),
            hold_action=lambda: np.array([.1, .2, .024], dtype=np.float32),
            robot=SimpleNamespace(arm_slice={'left': slice(0, 2)}, grip_index={'left': 2},
                native_to_width=lambda side, value: max(0., value-.00746875),
                width_to_native=lambda side, value: value+.00746875,
                clip=lambda row: np.clip(np.asarray(row, float), [-1., -1., 0.], [1., 1., .05])))

    def test_omitted_targets_are_preserved_without_changing_the_robot(self):
        row = public_row(self.session, {'left': {'gripper_position_m': .00746875}})
        np.testing.assert_array_equal(row, np.array([.1, .2, 0.], dtype=np.float32))
        self.assertEqual(self.targets['left']['gripper_position_m'], .024)

    def test_feedback_cannot_silently_use_an_unrepresentable_gripper_target(self):
        with self.assertRaisesRegex(ValueError, 'not representable'):
            public_row(self.session, {'left': {'gripper_position_m': .002}})

    def test_feedback_cannot_silently_clip_joint_targets(self):
        with self.assertRaisesRegex(ValueError, 'clipped'):
            public_row(self.session, {'left': {'joint_position_rad': [2., .2]}})


class NativeCommandEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "private").mkdir()
        (self.root / "config.json").write_text(json.dumps(dict(physics_dt_s=.0025, control_decimation=10)))
        self.spec = dict(arms=["left", "right"], groups={
            side: dict(arm_joint_names=[side+"/waist", side+"/elbow"]) for side in ("left", "right")})
        self.events = []
        for step, ticks in ((1, 10), (2, 7)):
            self.events.append(dict(kind="completed", physics_steps=ticks, action_duration_s=ticks*.0025,
                terminated=step == 2, truncated=False, info=dict(
                    branch_id=0, control_step=step, episode_id="episode", physics_step=10 if step == 1 else 17,
                    state_id=step*10, executed_joint_targets={side: dict(
                        joint_position_rad=[step*.1, -step*.2], gripper_position_m=.024)
                        for side in ("left", "right")})))

    def tearDown(self):
        self.temp.cleanup()

    def read(self, events):
        (self.root / "private/control_steps.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events))
        return read_native_commands(self.root, self.spec)

    def test_accepted_targets_and_partial_terminal_timing(self):
        # A proposal was rejected between the two committed controls. It must
        # never enter a reference; nor may its measured state stand in for qpos targets.
        requested = dict(kind="requested", action=dict(left=dict(position_world_m=[99, 99, 99])))
        data = self.read([requested, self.events[0], dict(kind="failed"), self.events[1]])
        np.testing.assert_allclose(data["targets"], [[.1, -.2, .024, .1, -.2, .024],
                                                   [.2, -.4, .024, .2, -.4, .024]])
        np.testing.assert_array_equal(data["physics_steps"], [10, 7])
        self.assertEqual(data["layout"].tolist(), ["left/waist", "left/elbow", "left_native_gripper",
                                                   "right/waist", "right/elbow", "right_native_gripper"])

    def test_rewind_or_missing_prefix_is_not_a_home_reference(self):
        for key, value in (("branch_id", 1), ("control_step", 4), ("episode_id", "another_episode"),
                           ("physics_step", 18)):
            events = deepcopy(self.events)
            events[1]["info"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.read(events)
        with self.assertRaises(ValueError):
            self.read(self.events[1:])

    def test_nonterminal_partial_step_and_bad_duration_rejected(self):
        events = deepcopy(self.events)
        events[1]["terminated"] = False
        with self.assertRaises(ValueError):
            self.read(events)
        events = deepcopy(self.events)
        events[1]["action_duration_s"] = .025
        with self.assertRaises(ValueError):
            self.read(events)

    def test_missing_or_nonfinite_accepted_target_rejected(self):
        events = deepcopy(self.events)
        events[1]["info"].pop("executed_joint_targets")
        with self.assertRaises(KeyError):
            self.read(events)
        events = deepcopy(self.events)
        events[1]["info"]["executed_joint_targets"]["right"]["gripper_position_m"] = float("nan")
        with self.assertRaises(ValueError):
            self.read(events)

    def test_owner_preflight_runs_once_per_phase_and_can_reject_the_action(self):
        class Candidate:
            phase, diagnostics = "created", {}
            def act(self, obs):
                self.phase = obs["phase"]
                return {"left": {"gripper_position_m": .002}}
        checked = []
        def preflight(policy):
            checked.append(policy.phase)
            if policy.phase == "blocked_goal":
                raise ValueError("carried piece hits the other arm")
        trace = PolicyTrace(Candidate(), self.root, before_phase=preflight)
        for phase in ("pickup", "pickup", "channel"):
            self.assertIsInstance(trace.act(dict(phase=phase, state=dict(sim_time_s=0.))), dict)
        with self.assertRaisesRegex(ValueError, "carried piece"):
            trace.act(dict(phase="blocked_goal", state=dict(sim_time_s=0.)))
        self.assertEqual(checked, ["pickup", "channel", "blocked_goal"])


class PrivatePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.config = dict(task_id="cast_keyhole", variation_id="cast_keyhole_easier",
                           physics_dt_s=.0025, control_decimation=10, solver_substeps=4,
                           control_mode="EE_ABS", seed=None)
        self.layout = [n for side in ("left", "right") for n in
                       [*[side+"/joint_"+str(i) for i in range(6)], side+"_native_gripper"]]
        targets = np.zeros((2, 14)); targets[:, [6, 13]] = [.024, .002]
        np.savez_compressed(self.run/"native_joint_targets.npz", targets=targets,
                            physics_steps=np.array([10, 7]), layout=np.array(self.layout))
        self.write("config.json", self.config)
        self.write("source_manifest.json", {"frozen": "source"})
        self.report = dict(status="passed", task_success=True, part="all", from_default_home=True,
                           instance_id="local-instance", asset_sha256={"plate.obj": "mesh-hash"})
        self.write("run_report.json", self.report)
        self.write("native_reference.json", dict(local_task_success=True, rows=2, physics_steps=17,
            instance_id="local-instance", artifact="native_joint_targets.npz",
            asset_sha256=self.report["asset_sha256"], sha256=digest(self.run/"native_joint_targets.npz"),
            config_sha256=digest(self.run/"config.json"),
            source_manifest_sha256=digest(self.run/"source_manifest.json")))
        self.instance = dict(task="cast_keyhole", variation_id="easier", resolved_variation_id="cast_keyhole_easier",
            evaluable_for_task_success=True, state_sha="initial-state",
            simulator=dict(self.config, control_mode="JOINT_ABS", seed=0, variation_id="easier"),
            action_layout=[n.replace("_native_gripper", "_gripper") for n in self.layout],
            asset_identity=self.report["asset_sha256"])
        self.instance_path = self.root/"instance.json"
        self.instance_path.write_text(json.dumps(self.instance))

    def write(self, name, value):
        (self.run/name).write_text(json.dumps(value))

    def tearDown(self):
        self.temp.cleanup()

    def build(self, **kwargs):
        return package(self.run, self.instance_path, self.root/"package", **kwargs)

    def feedback_sources(self):
        paths = ["planning/__init__.py", "planning/cast_keyhole/__init__.py",
                 "planning/cast_keyhole/policy.py", "planning/cast_keyhole/simplified_policy.py",
                 "planning/cast_keyhole/kinematics.py", "planning/rigid_reference/__init__.py",
                 "planning/rigid_reference/geometry.py", "planning/rigid_reference/feedback.py"]
        hashes = {}
        for name in paths:
            target = self.run/"source_snapshot/topogym"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Frozen test policy source\n")
            hashes[name] = digest(target)
        self.write("source_manifest.json", dict(source_hashes=hashes))
        reference = json.loads((self.run/"native_reference.json").read_text())
        reference["source_manifest_sha256"] = digest(self.run/"source_manifest.json")
        self.write("native_reference.json", reference)

    def test_feedback_marks_native_trace_as_basis_and_binds_private_helpers(self):
        self.feedback_sources()
        manifest = self.build(feedback=True)
        self.assertEqual(manifest["execution"], "public_session_feedback")
        self.assertIsNone(manifest["rows"])
        self.assertEqual(manifest["local_basis_rows"], 2)
        self.assertIs(manifest["harbor_qualified"], False)
        self.assertEqual(len(manifest["private_helpers_sha256"]), 9)
        for name, expected in manifest["private_helpers_sha256"].items():
            self.assertEqual(digest(self.root/"package/solution"/name), expected)
        self.assertFalse(any("calibration_tools" in name for name in manifest["private_helpers_sha256"]))

    def test_feedback_rejects_policy_changed_since_successful_run(self):
        self.feedback_sources()
        (self.run/"source_snapshot/topogym/planning/cast_keyhole/policy.py").write_text("# Changed\n")
        with self.assertRaisesRegex(ValueError, "Changed successful-run policy source"):
            self.build(feedback=True)

    def test_pickup_cannot_be_packaged_as_complete_reference(self):
        self.report.update(status="pickup_passed", task_success=False, part="pickup")
        self.write("run_report.json", self.report)
        with self.assertRaisesRegex(ValueError, "complete successful"):
            self.build()

    def test_physics_change_and_corrupt_commands_are_rejected(self):
        self.instance["simulator"]["physics_dt_s"] = .025
        self.instance_path.write_text(json.dumps(self.instance))
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            self.build()
        self.instance["simulator"]["physics_dt_s"] = .0025
        self.instance_path.write_text(json.dumps(self.instance))
        with (self.run/"native_joint_targets.npz").open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "native control artifact"):
            self.build()

    def session(self, rows):
        from types import SimpleNamespace
        return SimpleNamespace(config=self.instance["simulator"],
            asset_identity=self.instance["asset_identity"], instance_sha="initial-state",
            env=SimpleNamespace(_task=SimpleNamespace(instance_id="local-instance")),
            action_layout=self.instance["action_layout"], n_steps=0,
            robot=SimpleNamespace(grip_index={"left": 6, "right": 13},
                                  native_to_width=lambda side, value: value+.01,
                                  width_to_native=lambda side, width: width-.01),
            step=lambda row: rows.append(row.copy()) or False, success=lambda: True)

    def test_private_script_uses_width_adapter_and_rejects_another_instance(self):
        manifest = self.build()
        self.assertIs(manifest["harbor_qualified"], False)
        source = (self.root/"package/solution/oracle_cast_keyhole.py").read_text()
        rows = []
        session = self.session(rows)
        exec(compile(source, "private_oracle.py", "exec"), dict(session=session))
        np.testing.assert_allclose(np.array(rows)[:, [6, 13]], [[.034, .012], [.034, .012]])
        session.instance_sha = "another-state"
        with self.assertRaisesRegex(ValueError, "exact frozen instance"):
            exec(compile(source, "private_oracle.py", "exec"), dict(session=session))
        self.assertEqual(len(rows), 2)

    def test_closed_width_plateau_rejected_before_any_physics(self):
        self.build()
        source = (self.root/"package/solution/oracle_cast_keyhole.py").read_text()
        rows = []
        session = self.session(rows)
        session.robot.native_to_width = lambda side, value: max(0., value-.00746875)
        session.robot.width_to_native = lambda side, width: width+.00746875
        with self.assertRaisesRegex(ValueError, "not representable"):
            exec(compile(source, "private_oracle.py", "exec"), dict(session=session))
        self.assertEqual(rows, [])

    def test_lossy_experiment_requires_recorded_opt_in_and_is_not_qualified(self):
        reason = "Legacy candidate replay experiment; physical result still required"
        manifest = self.build(allow_gripper_roundtrip_loss=reason)
        self.assertEqual(manifest["gripper_roundtrip_audit"]["allowed_loss_reason"], reason)
        self.assertIs(manifest["harbor_qualified"], False)
        source = (self.root/"package/solution/oracle_cast_keyhole.py").read_text()
        rows = []
        session = self.session(rows)
        session.robot.native_to_width = lambda side, value: max(0., value-.00746875)
        session.robot.width_to_native = lambda side, width: width+.00746875
        exec(compile(source, "private_oracle.py", "exec"), dict(session=session))
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
