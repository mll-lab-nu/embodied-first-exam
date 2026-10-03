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

    def build(self):
        return package(self.run, self.instance_path, self.root/"package")

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

    def test_private_script_uses_width_adapter_and_rejects_another_instance(self):
        from types import SimpleNamespace
        manifest = self.build()
        self.assertIs(manifest["harbor_qualified"], False)
        source = (self.root/"package/solution/oracle_cast_keyhole.py").read_text()
        rows = []
        session = SimpleNamespace(config=self.instance["simulator"],
            asset_identity=self.instance["asset_identity"], instance_sha="initial-state",
            env=SimpleNamespace(_task=SimpleNamespace(instance_id="local-instance")),
            action_layout=self.instance["action_layout"], n_steps=0,
            robot=SimpleNamespace(grip_index={"left": 6, "right": 13},
                                  native_to_width=lambda side, value: value+.01),
            step=lambda row: rows.append(row.copy()) or False, success=lambda: True)
        exec(compile(source, "private_oracle.py", "exec"), dict(session=session))
        np.testing.assert_allclose(np.array(rows)[:, [6, 13]], [[.034, .012], [.034, .012]])
        session.instance_sha = "another-state"
        with self.assertRaisesRegex(ValueError, "exact frozen instance"):
            exec(compile(source, "private_oracle.py", "exec"), dict(session=session))
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
