#!/usr/bin/env python3
"""Cross-task oracle packaging and execution contracts; no physical success claim."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
from topogym.planning.harbor_bridge.actions import SessionExecutor, native_row, public_row
from topogym.planning.harbor_bridge.batch import assess_job, plan
from topogym.planning.harbor_bridge.catalog import inventory
from topogym.planning.harbor_bridge.contracts import (
    BridgeError, check_session, digest, file_hashes, instance_binding, load_trajectory, read_json)
from topogym.planning.harbor_bridge.packaging import check_package, collect_helpers, package
from topogym.planning.harbor_bridge.runtime import execute, stream_standard, verify_files
from topogym.planning.harbor_bridge.timing import joint_step_limit, rate_limit_rows


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(root, family="cast_keyhole", mode="privileged"):
    """Different families/robots exercise the same contracts and generic packager."""
    task = root / f"topogym-{family.replace('_', '-')}-easy-i00-{mode}"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "solution").mkdir()
    (task / "task.toml").write_text(
        f'schema_version = "1.3"\n[task]\nname = "fixture/{task.name}"\n'
        f'[metadata]\nfamily = "{family}"\nmode = "{mode}"\noracle = "full"\n'
        'oracle_evidence = "old evidence must not be inherited"\n[agent]\ntimeout_sec = 30\n')
    (task / "README.md").write_text('# Task\n\n## Reference solution\n\nQualified original\n\n## Verification\n\nReplay\n')
    (task / "environment/Dockerfile").write_text('FROM example:1\n')
    (task / "tests/Dockerfile").write_text('FROM example:1\n')
    arms = ["arm"] if family == "cube_pick_place" else ["left", "right"]
    layout = [name for arm in arms for name in (arm + "/joint", arm + "_gripper")]
    instance = dict(task=family, variation_id=family + "_easy", seed=0, state_sha="frozen-state",
        action_dim=len(layout), action_layout=layout, asset_identity={"mesh": "mesh-hash"},
        topogym_source={"sha256": "source-hash", "files": 1},
        simulator=dict(task_id=family, variation_id=family + "_easy", seed=0, control_mode="JOINT_ABS",
            robot_id="panda_robotiq" if len(arms) == 1 else "aloha", physics_dt_s=.0025,
            control_decimation=10, solver_substeps=4, grasp_assist=dict(model="contact_weld_v1")))
    folder = task / ("environment/sim" if mode == "standard" else "environment")
    write_json(folder / "instance.json", instance)
    (folder / "rcb_topogym.py").write_text('BINDING_API = 1\n')
    write_json(folder / "instance_assets/state.json", {"state": [0, 1]})
    (task / "tests/instance.json").write_bytes((folder / "instance.json").read_bytes())
    (task / "solution/oracle.py").write_text('session.step(session.hold_action())\n')
    (task / "solution/solve.sh").write_text(
        '#!/bin/bash\npython /opt/tools/rcb_topogym.py run-oracle --code /solution/oracle.py\n')
    return task, folder / "instance.json"


def fixture_lock(task):
    from topogym.planning.harbor_bridge.binding import lock_for_task
    return lock_for_task(task, dict(reference="example:1", id="sha256:" + "0"*64, repo_digests=[]),
                         dict(source=dict(sha256="1"*64, files=1)))


def fake_session(binding, *, solved=True):
    inst = binding["instance"]
    arms = [name.removesuffix("_gripper") for name in inst["action_layout"] if name.endswith("_gripper")]
    n = len(arms)
    targets = {arm: dict(joint_position_rad=[.125], gripper_position_m=.024) for arm in arms}
    robot = SimpleNamespace(groups={arm: SimpleNamespace(gripper_field="gripper_position_m") for arm in arms},
                            capture_state=lambda: SimpleNamespace(targets=targets))
    adapter = SimpleNamespace(grip_index={arm: 2*i + 1 for i, arm in enumerate(arms)},
        arm_slice={arm: slice(2*i, 2*i+1) for i, arm in enumerate(arms)},
        native_to_width=lambda arm, value: max(0., value - .00746875),
        width_to_native=lambda arm, value: value + .00746875,
        clip=lambda row: np.clip(row, [-1., 0.] * n, [1., .05] * n))
    s = SimpleNamespace(task=inst["task"], config=deepcopy(inst["simulator"]), instance_sha=inst["state_sha"],
        asset_identity=inst["asset_identity"], action_layout=inst["action_layout"], n_steps=0, _resets=0,
        instance_matches=True, instance_exact=True, env=SimpleNamespace(_robot=robot), robot=adapter,
        hold_action=lambda: np.array([.125, .01653125] * n, np.float32), success=lambda: solved)
    def step(row):
        s.n_steps += 1
        return solved
    s.step = Mock(side_effect=step)
    return s


def trajectory(path, binding, *, native=False, ticks=(10, 7)):
    inst = binding["instance"]
    n = inst["action_dim"] // 2
    names = inst["action_layout"]
    rows = np.array([[.125, .024 if native else .015625] * n] * 2,
                    dtype=np.float64 if native else np.float32)
    values = dict(task=inst["task"], scene_seed=inst["simulator"]["seed"], instance_sha=inst["state_sha"])
    values.update({"targets" if native else "actions": rows,
                   "layout" if native else "action_layout": [x.replace("_gripper", "_native_gripper") for x in names] if native else names,
                   "physics_steps" if native else "physics_steps_per_action": np.array(ticks, dtype=np.int64)})
    np.savez(path, **values)
    return values


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task, self.instance = fixture(self.root)
        self.binding = instance_binding(self.instance)

    def tearDown(self):
        self.temp.cleanup()


class Contracts(FixtureCase):
    def test_ipc_settled_state_resolves_only_to_the_bound_asset(self):
        data = read_json(self.instance)
        data["simulator"]["ipc_settled_state"] = "instance_assets/state.json"
        write_json(self.instance, data)
        binding = instance_binding(self.instance)
        session = fake_session(binding)
        session.config["ipc_settled_state"] = str(self.instance.parent / "instance_assets/state.json")
        check_session(session, binding, instance_path=self.instance)
        session.config["ipc_settled_state"] = str(self.root / "different-state.json")
        with self.assertRaises(BridgeError):
            check_session(session, binding, instance_path=self.instance)

    def test_soft_state_path_resolves_only_to_the_bound_asset(self):
        data = read_json(self.instance)
        data["simulator"]["task_parameters"] = {"initial_state_path": "instance_assets/state.json"}
        write_json(self.instance, data)
        binding = instance_binding(self.instance)
        session = fake_session(binding)
        session.config["task_parameters"]["initial_state_path"] = str(self.instance.parent / "instance_assets/state.json")
        check_session(session, binding, instance_path=self.instance)
        session.config["task_parameters"]["initial_state_path"] = str(self.root / "different-state.json")
        with self.assertRaises(BridgeError):
            check_session(session, binding, instance_path=self.instance)

    def test_inventory_marks_legacy_identity_blocked(self):
        data = read_json(self.instance)
        data.pop("asset_identity")
        write_json(self.instance, data)
        row = inventory(self.root, self.root)["tasks"][0]
        self.assertEqual(row["bridge"], "blocked_identity")
        self.assertIn("asset_identity", row["blockers"][0])

    def test_omitted_targets_and_both_robot_layouts(self):
        for family in ("cast_keyhole", "cube_pick_place"):
            if family == "cube_pick_place":
                _, path = fixture(self.root, family)
                binding = instance_binding(path)
            else:
                binding = self.binding
            session = fake_session(binding)
            targets = deepcopy(session.env._robot.capture_state().targets)
            row = public_row(session, {})
            self.assertEqual(len(row), len(binding["instance"]["action_layout"]))
            self.assertEqual(row.dtype, np.float32)
            self.assertEqual(targets, session.env._robot.capture_state().targets)

    def test_unrepresentable_gripper_and_clipping_are_rejected_before_step(self):
        session = fake_session(self.binding)
        for update in ({"left": {"gripper_position_m": .002}}, {"left": {"joint_position_rad": [2.]}}):
            with self.subTest(update=update), self.assertRaises(BridgeError):
                public_row(session, update)
        session.step.assert_not_called()

    def test_nonfinite_unknown_and_unsupported_targets_fail(self):
        session = fake_session(self.binding)
        for update in ({"other": {}}, {"left": {"velocity": 1}}, {"left": {"gripper_position_m": float('nan')}}):
            with self.subTest(update=update), self.assertRaises(BridgeError):
                public_row(session, update)

    def test_public_executor_calls_existing_compile_and_session_only(self):
        session = fake_session(self.binding)
        with patch("topogym.robot.control.compile_action", return_value={}) as compile:
            self.assertTrue(SessionExecutor(session).step({}, mode="EE_ABS"))
            compile.assert_called_once_with(session.env._robot, {}, "EE_ABS")
        session.step.assert_called_once()

    def test_bound_session_rejects_reset_seed_physics_assets_and_layout_changes(self):
        check_session(fake_session(self.binding), self.binding)
        for field, value in (("_resets", 1), ("n_steps", 1), ("instance_matches", False),
                             ("asset_identity", {}), ("action_layout", [])):
            session = fake_session(self.binding)
            setattr(session, field, value)
            with self.subTest(field=field), self.assertRaises(BridgeError): check_session(session, self.binding)
        for field, value in (("seed", 1), ("physics_dt_s", .025), ("grasp_assist", {"model": "none"})):
            session = fake_session(self.binding)
            session.config[field] = value
            with self.subTest(field=field), self.assertRaises(BridgeError): check_session(session, self.binding)

    def test_trajectory_identity_order_and_timing(self):
        path = self.root / "reference.npz"
        original = trajectory(path, self.binding)
        rows, ticks = load_trajectory(path, self.binding)
        self.assertEqual(rows.shape, (2, 4))
        self.assertEqual(ticks.tolist(), [10, 7])
        for key, value in (("task", "other"), ("instance_sha", "other"), ("scene_seed", 1),
                           ("action_layout", original["action_layout"][::-1]),
                           ("physics_steps_per_action", np.array([7, 7])),
                           ("actions", np.zeros((0, 4))), ("actions", np.full((2, 4), np.nan)),
                           ("actions", np.full((2, 4), .1, dtype=np.float64))):
            np.savez(path, **dict(original, **{key: value}))
            with self.subTest(key=key), self.assertRaises(BridgeError): load_trajectory(path, self.binding)

    def test_native_stream_preflights_late_bad_gripper_before_any_step(self):
        path = self.root / "reference.npz"
        values = trajectory(path, self.binding, native=True)
        values["targets"][-1, -1] = .002
        np.savez(path, **values)
        session = fake_session(self.binding)
        recipe = dict(binding=self.binding, execution=dict(kind="native_trajectory", artifact=path.name))
        with self.assertRaisesRegex(BridgeError, "not representable"):
            execute(session, recipe, self.root, self.root)
        session.step.assert_not_called()

    def test_native_trace_requires_explicit_native_gripper_layout(self):
        path = self.root / "native.npz"
        values = trajectory(path, self.binding, native=True)
        values["layout"] = self.binding["instance"]["action_layout"]
        np.savez(path, **values)
        with self.assertRaises(BridgeError): load_trajectory(path, self.binding, native=True)

    def test_script_exit_and_policy_done_cannot_fake_success(self):
        script = self.root / "oracle.py"
        script.write_text('pass\n')
        recipe = dict(binding=self.binding, execution=dict(kind="script", script=script.name))
        session = fake_session(self.binding, solved=False)
        session.exec_code = lambda *a, **k: {"ok": True}
        with self.assertRaisesRegex(BridgeError, "without native Task success"):
            execute(session, recipe, self.root, self.root)
        session.exec_code = lambda *a, **k: {"ok": False, "error": "failure"}
        with self.assertRaisesRegex(BridgeError, "script failed"):
            execute(session, recipe, self.root, self.root)

    def test_instance_assets_cannot_escape_or_use_symlinks(self):
        write_json(self.root / "external.json", {})
        d = read_json(self.instance)
        d["simulator"]["ipc_settled_state"] = "../../external.json"
        write_json(self.instance, d)
        with self.assertRaises(BridgeError): instance_binding(self.instance)
        d["simulator"].pop("ipc_settled_state")
        write_json(self.instance, d)
        (self.instance.parent / "instance_assets/link").symlink_to(self.root / "external.json")
        with self.assertRaises(BridgeError): instance_binding(self.instance)


class NativeCommandSpace(unittest.TestCase):
    def robot(self, limit=.041, field="gripper_position_m"):
        sys.path.insert(0, str(ROOT / "harbor_templates/topogym/common"))
        from rcb_topogym import _Robot
        r = _Robot.__new__(_Robot)
        r.gripper_space = "native"
        r.layout, r.grip_index, r.arm_slice = ["joint", "arm_native_gripper"], {"arm": 1}, {"arm": slice(0, 1)}
        group = SimpleNamespace(gripper_field=field, gripper_limits=(0., limit))
        r.groups = {"arm": group}
        r.robot = SimpleNamespace(groups=r.groups, validate_action=lambda commands: commands,
            capture_state=lambda: SimpleNamespace(targets={"arm": {"joint_position_rad": [0.], field: .024}}))
        r.width_table = {"arm": (np.array([0., .05]), np.array([.00746875, limit]))}
        hi = np.float32(limit)
        if float(hi) > limit: hi = np.nextafter(hi, np.float32(-np.inf))
        r.lo, r.hi = np.array([-1., 0.]), np.array([1., float(hi)])
        r.limits = list(zip(r.lo, r.hi))
        return SimpleNamespace(robot=r, env=SimpleNamespace(_robot=r.robot), action_layout=r.layout)

    def test_aloha_close_targets_survive_actual_command_encoder(self):
        s = self.robot()
        for value in (.002, .006):
            row = native_row(s, [0., value])
            command = s.robot.command(row)
            self.assertAlmostEqual(command["arm"]["gripper_position_m"], value, places=8)
        self.assertNotEqual(native_row(s, [0., .002])[1], native_row(s, [0., .006])[1])
        s.robot.gripper_space = "width"
        with self.assertRaisesRegex(BridgeError, "not representable"):
            native_row(s, [0., .002])

    def test_robotiq_float32_limit_rounds_inward_without_saturating_invalid_input(self):
        s = self.robot(.8, "gripper_angle_rad")
        row = native_row(s, [0., .8])
        self.assertLessEqual(float(row[1]), .8)
        self.assertAlmostEqual(s.robot.command(row)["arm"]["gripper_angle_rad"], .8, places=6)
        with self.assertRaisesRegex(BridgeError, "outside model limits"):
            native_row(s, [0., .8001])

    def test_grader_refuses_same_dimension_different_gripper_semantics(self):
        import rcb_topogym
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "trajectory.npz"
            np.savez(p, task="cast_coil", actions=np.zeros((3, 2)), action_layout=["joint", "arm_gripper"])
            with self.assertRaisesRegex(rcb_topogym.InvalidTrajectory, "layout differs"):
                rcb_topogym.load_trajectory(p, "cast_coil", 2, layout=["joint", "arm_native_gripper"])
            self.assertEqual(len(rcb_topogym.load_trajectory(p, "cast_coil", 2, layout=["joint", "arm_gripper"])[0]), 3)


class Packaging(FixtureCase):
    def test_existing_reference_preserves_public_bytes_and_original_qualification(self):
        before = file_hashes(self.task)
        result = package(self.task, self.root / "candidates", kind="existing")
        candidate = Path(result["task"])
        self.assertEqual(before, file_hashes(self.task))
        self.assertEqual(check_package(candidate)["status"], "passed")
        self.assertEqual((candidate / "solution/oracle.py").read_bytes(), (self.task / "solution/oracle.py").read_bytes())
        self.assertIn('oracle = "none"', (candidate / "task.toml").read_text())
        self.assertNotIn('Qualified original', (candidate / "README.md").read_text())
        self.assertFalse(result["harbor_qualified"])

    def test_candidate_cannot_overwrite_or_live_inside_source_task(self):
        package(self.task, self.root / "candidates", kind="existing")
        for output in (self.root / "candidates", self.task / "candidate"):
            with self.subTest(output=output), self.assertRaises(BridgeError):
                package(self.task, output, kind="existing")

    def test_changed_or_added_private_and_public_files_are_detected(self):
        for number, name in enumerate(("solution/oracle.py", "solution/extra.py", "environment/instance.json", "tests/extra.py")):
            result = package(self.task, self.root / f"candidate{number}", kind="existing")
            path = Path(result["task"]) / name
            path.write_text('changed')
            with self.subTest(name=name), self.assertRaises((BridgeError, ValueError)):
                check_package(result["task"])

    def test_cross_task_and_changed_state_assets_are_rejected(self):
        trace = self.root / "reference.npz"
        trajectory(trace, self.binding)
        _, other = fixture(self.root, "cube_pick_place")
        with self.assertRaises(BridgeError):
            package(self.task, self.root / "output", kind="public_trajectory", trajectory=trace, source_instance=other)
        write_json(other, read_json(self.instance))
        (other.parent / "instance_assets/state.json").write_text('different frozen state')
        with self.assertRaises(BridgeError):
            package(self.task, self.root / "output", kind="public_trajectory", trajectory=trace, source_instance=other)

    def test_standard_accepts_same_instance_public_trace_only(self):
        task, path = fixture(self.root, mode="standard")
        trace = self.root / "reference.npz"
        trajectory(trace, self.binding)
        for kind in ("session", "existing", "native_trajectory"):
            with self.subTest(kind=kind), self.assertRaises(BridgeError):
                package(task, self.root / "bad", kind=kind)
        result = package(task, self.root / "standard", kind="public_trajectory", trajectory=trace,
                         source_instance=self.instance)
        self.assertEqual(check_package(result["task"])["mode"], "standard")
        names = file_hashes(Path(result["task"]) / "solution")
        self.assertFalse(any(name.startswith("topogym/") for name in names))

    def test_dependency_closure_is_private_transitive_and_rejects_development_imports(self):
        root = self.root / "source"
        folder = root / "topogym/planning/example"
        folder.mkdir(parents=True)
        (folder.parent / "__init__.py").write_text('')
        (folder / "__init__.py").write_text('')
        (folder / "helper.py").write_text('VALUE = 1\n')
        (folder / "entry.py").write_text('from .helper import VALUE\ndef run(session, output):\n    pass\n')
        files = collect_helpers(root, "topogym.planning.example.entry")
        self.assertIn("topogym/planning/example/helper.py", files)
        self.assertIn("topogym/planning/__init__.py", files)
        result = package(self.task, self.root / "callback", kind="session", source_root=root,
                         entrypoint="topogym.planning.example.entry:run")
        self.assertEqual(check_package(result["task"])["execution"], "session")
        (folder / "helper.py").write_text('from topogym.planning.calibration_tools import candidates\n')
        with self.assertRaisesRegex(BridgeError, "Development-only"):
            collect_helpers(root, "topogym.planning.example.entry")

    def test_no_public_runtime_shadowing(self):
        path = self.task / "solution/topogym/world/physics.py"
        path.parent.mkdir(parents=True)
        path.write_text('pass')
        with self.assertRaises(BridgeError): package(self.task, self.root / "out", kind="existing")

    @patch("topogym_versions.require_task", return_value={})
    def test_batch_has_no_model_or_credentials_and_does_not_execute_on_plan(self, _active_guard):
        result = package(self.task, self.root / "candidates", kind="existing", runtime_lock=fixture_lock(self.task))
        output = self.root / "batch"
        document = plan([result["task"]], output, "harbor")
        self.assertEqual([j["agent"] for j in document["jobs"]], ["oracle", "nop"])
        self.assertTrue(all("-m" not in j["command"] for j in document["jobs"]))
        self.assertFalse(output.exists())
        self.assertFalse(document["harbor_qualified"])

    @patch("topogym_versions.require_task", return_value={})
    def test_original_tier_scope_rejects_simplified_tasks_before_launch(self, _active_guard):
        result = package(self.task, self.root / "candidates", kind="existing", runtime_lock=fixture_lock(self.task))
        candidate = Path(result["task"])
        document = plan([candidate], self.root / "jobs", "harbor", tiers=["easy", "medium", "hard"])
        self.assertEqual(document["jobs"][0]["difficulty"], "easy")
        for tier in ("very-easy", "easier"):
            moved = candidate.with_name(candidate.name.replace("-easy-i00-", f"-{tier}-i00-"))
            candidate.rename(moved)
            try:
                with self.subTest(tier=tier), self.assertRaisesRegex(BridgeError, "outside selected tiers"):
                    plan([moved], self.root / "jobs", "harbor", tiers=["easy", "medium", "hard"])
            finally:
                moved.rename(candidate)
        self.assertFalse((self.root / "jobs").exists())

    def test_inventory_easy_filter_excludes_very_easy_suffix_match(self):
        moved = self.task.with_name(self.task.name.replace("-easy-i00-", "-very-easy-i00-"))
        self.task.rename(moved)
        selected = inventory(self.root, self.root, tiers=["easy", "medium", "hard"])
        self.assertEqual(selected["task_count"], 0)
        self.assertEqual(inventory(self.root, self.root, tiers=["very_easy"])["task_count"], 1)


class PackagedRuntime(FixtureCase):
    """Run the copied runtime in another process, with no checkout on sys.path.

    Minimal task tooling substitutes for Genesis; these tests check packaging,
    lifecycle and saved evidence, never physical success.
    """
    def setUp(self):
        super().setUp()
        self.installed = self.root / "installed"
        (self.installed / "topogym").mkdir(parents=True)
        (self.installed / "topogym/__init__.py").write_text('')
        (self.instance.parent / "rcb_topogym.py").write_text('''
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np

def _source():
    return {"sha256": "source-hash", "files": 1}

class Session:
    def __init__(self, task, *, instance, strict):
        assert strict
        self.path = Path(instance)
        data = json.loads(self.path.read_text())
        self.task, self.config = task, data["simulator"]
        self.instance_sha, self.asset_identity = data["state_sha"], data["asset_identity"]
        self.action_layout, self.instance_matches = data["action_layout"], True
        self.instance_exact = True
        self.n_steps = self.physics_steps = self._resets = 0
        self.env = SimpleNamespace(_episode_id="frozen", _branch_id=1, _control_step=0,
            _world=SimpleNamespace(physics_step=0), config=SimpleNamespace(**self.config))
    def hold_action(self): return np.array([.125, .015625] * 2, np.float32)
    def step(self, row, *, _physics_steps=None):
        ticks = self.config["control_decimation"] if _physics_steps is None else _physics_steps
        self.n_steps += 1
        self.env._control_step += 1
        self.physics_steps += ticks
        self.env._world.physics_step += ticks
        self._recording.append(np.asarray(row, np.float32))
        self._recorded_ticks.append(ticks)
        return self.success()
    def success(self): return self.n_steps >= 2
    def record_start(self): self._recording, self._recorded_ticks = [], []
    def record_stop(self):
        result = np.array(self._recording, np.float32)
        self._recording = None
        return result
    def save_trajectory(self, actions, path, meta):
        np.savez(path, actions=actions, meta=json.dumps(meta), physics_steps_per_action=self._recorded_ticks)
    def status(self): return dict(success=self.success(), sim_steps=self.n_steps)
    def close(self): (self.path.parent / "closed.txt").write_text("closed")
    def exec_code(self, code, extra):
        try:
            exec(code, dict(session=self, np=np, **extra))
            return {"ok": True}
        except Exception as error:
            return {"ok": False, "error": str(error)}
''')

    def invoke(self, result):
        task = Path(result["task"])
        # An independently installed CPU fixture deliberately differs from the
        # instance creator; only explicit runtime binding permits its use.
        import hashlib
        from topogym.simulator.frozen_binding import installed_runtime
        files = {"topogym/" + name: value for name, value in file_hashes(self.installed / "topogym").items()}
        write_json(self.installed / "SOURCE.json", dict(
            sha256=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), files=len(files)))
        runtime = installed_runtime(self.installed, check_imports=False)
        recipe_path = task / "solution/bridge_manifest.json"
        recipe = read_json(recipe_path)
        bound = recipe["binding"]
        recipe["runtime_binding"] = dict(schema_version=1, instance_sha256=bound["instance_sha256"],
            asset_files=bound["asset_files"], tooling_sha256=recipe["tooling_sha256"],
            creation_source=bound["instance"]["topogym_source"], runtime=runtime,
            image=dict(reference="example:1", id="sha256:" + "0"*64, repo_digests=[]))
        write_json(recipe_path, recipe)
        output = self.root / (task.parent.name + "-results")
        output.mkdir()
        command = '''
import sys
from pathlib import Path
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from _harbor_oracle_bridge.runtime import run_privileged, verify_files
from _harbor_oracle_bridge.contracts import read_json
solution, output, environment = map(Path, sys.argv[2:])
recipe = read_json(solution / "bridge_manifest.json")
verify_files(solution, recipe)
run_privileged(solution, recipe, output, instance_path=environment / "instance.json",
               tooling_path=environment / "rcb_topogym.py")
'''
        process = subprocess.run([sys.executable, "-I", "-c", command, str(self.installed),
            str(task / "solution"), str(output), str(task / "environment")],
            cwd=self.root, env=dict(os.environ, OPENBLAS_NUM_THREADS="1"), capture_output=True, text=True, timeout=30)
        self.assertTrue((task / "environment/closed.txt").is_file(), process.stderr)
        return process, output, read_json(output / "bridge_report.json")

    def test_existing_script_uses_caller_recorder_and_saves_complete_evidence(self):
        (self.task / "solution/oracle.py").write_text(
            'session.step(session.hold_action())\nsession.step(session.hold_action())\n')
        result = package(self.task, self.root / "script", kind="existing")
        process, output, report = self.invoke(result)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(report["status"], "native_success_pending_harbor_verifier")
        with np.load(output / "trajectory.npz") as trace:
            self.assertEqual(trace["actions"].shape, (2, 4))
            self.assertEqual(trace["physics_steps_per_action"].tolist(), [10, 10])

    def test_private_callback_closure_lifecycle_failures_and_partial_evidence(self):
        source = self.root / "source"
        folder = source / "topogym/planning/example"
        folder.mkdir(parents=True)
        (folder.parent / "__init__.py").write_text('')
        (folder / "__init__.py").write_text('')
        (folder / "helper.py").write_text('def advance(session):\n    session.step(session.hold_action())\n')
        (folder / "entry.py").write_text('''
from .helper import advance
def run(session, output, behavior):
    (output / "callback_path.txt").write_text(__file__)
    advance(session)
    if behavior == "exception": raise RuntimeError("callback failed")
    if behavior == "unsolved": return
    advance(session)
    if behavior == "recorder": session.record_start()
    if behavior == "reset": session._resets += 1
    if behavior == "direct_step": session.env._control_step += 1
    if behavior == "direct_tick": session.env._world.physics_step += 1
    if behavior == "rewind": session.env._branch_id += 1
    if behavior == "config": session.config["physics_dt_s"] *= 2
    if behavior == "timing": session._recorded_ticks[:] = [5, 15]
''')
        for behavior in ("ok", "exception", "unsolved", "recorder", "reset", "direct_step", "direct_tick", "rewind", "config", "timing"):
            with self.subTest(behavior=behavior):
                result = package(self.task, self.root / behavior, kind="session", source_root=source,
                    entrypoint="topogym.planning.example.entry:run", kwargs=dict(behavior=behavior))
                process, output, report = self.invoke(result)
                imported = Path((output / "callback_path.txt").read_text())
                self.assertTrue(imported.is_relative_to(Path(result["task"]) / "solution"))
                self.assertEqual(process.returncode == 0, behavior == "ok", process.stderr)
                self.assertFalse(report["harbor_qualified"])
                if behavior != "ok": self.assertEqual(report["status"], "failed")
                if behavior != "recorder": self.assertTrue((output / "trajectory.npz").is_file())


class Standard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        _, path = fixture(root)
        self.recipe = dict(binding=instance_binding(path))
        self.rows = np.array([[.125, .015625] * 2] * 4, dtype=np.float32)
        self.status = dict(control_steps=0, done=False, reason=None)
        self.spec = dict(control_hz=40, max_chunk_s=.05, cameras={"front": {}}, action_types=dict(
            joint_position=dict(dim=4, layout=self.recipe["binding"]["instance"]["action_layout"],
                                limits=dict(zip(self.recipe["binding"]["instance"]["action_layout"],
                                                [[-1, 1], [0, .05]] * 2)))))
        self.robot = SimpleNamespace(spec=lambda: self.spec, status=lambda: dict(self.status))
        def submit(kind, rows, **kwargs):
            self.status["control_steps"] += len(rows)
            self.status.update(done=self.status["control_steps"] == 4,
                               reason="success" if self.status["control_steps"] == 4 else None)
            return SimpleNamespace(meta=dict(executed_rows=len(rows), control_steps_chunk=len(rows),
                                            n_clipped=0, done=self.status["done"]))
        self.robot.submit = Mock(side_effect=submit)

    def tearDown(self): self.temp.cleanup()

    def test_exact_rows_rate_and_no_implicit_settling(self):
        result = stream_standard(self.robot, self.recipe, self.rows)
        self.assertEqual(result["executed_rows"], 4)
        self.assertFalse(result["harbor_qualified"])
        self.assertEqual(self.robot.submit.call_count, 2)
        for call in self.robot.submit.call_args_list:
            self.assertEqual(call.kwargs["dt"], .025)
            self.assertEqual(call.kwargs["interpolate"], "hold")

    def test_layout_timing_limits_and_started_episode_rejected_before_submit(self):
        for change in ("rate", "order", "limits", "started"):
            with self.subTest(change=change):
                spec, status = deepcopy(self.spec), deepcopy(self.status)
                if change == "rate": self.spec["control_hz"] = 30
                elif change == "order": self.spec["action_types"]["joint_position"]["layout"] = []
                elif change == "limits": self.spec["action_types"]["joint_position"]["limits"][self.recipe["binding"]["instance"]["action_layout"][0]] = [0, .01]
                else: self.status["control_steps"] = 1
                with self.assertRaises(BridgeError): stream_standard(self.robot, self.recipe, self.rows)
                self.spec, self.status = spec, status
        self.robot.submit.assert_not_called()

    def test_service_named_limits_follow_layout_not_dictionary_insertion_order(self):
        action = self.spec["action_types"]["joint_position"]
        action["limits"] = dict(reversed(list(action["limits"].items())))
        result = stream_standard(self.robot, self.recipe, self.rows)
        self.assertEqual(result["executed_rows"], 4)

    def test_incomplete_named_limits_fail_before_any_submission(self):
        self.spec["action_types"]["joint_position"]["limits"].popitem()
        with self.assertRaisesRegex(BridgeError, "limits do not cover"):
            stream_standard(self.robot, self.recipe, self.rows)
        self.robot.submit.assert_not_called()

    def test_clipping_partial_ack_and_failure_are_not_success(self):
        for bad in (dict(n_clipped=1), dict(executed_rows=0), dict(control_steps_chunk=3)):
            self.robot.submit.side_effect = None
            self.robot.submit.return_value = SimpleNamespace(meta=dict(
                dict(executed_rows=2, control_steps_chunk=2, n_clipped=0, done=False), **bad))
            with self.subTest(bad=bad), self.assertRaises(BridgeError):
                stream_standard(self.robot, self.recipe, self.rows)

    def test_restart_resumes_only_acknowledged_rows(self):
        class ConnectionLost(Exception): pass
        original = self.robot.submit.side_effect
        calls = []
        def submit(kind, rows, **kwargs):
            calls.append(rows.copy())
            if len(calls) == 1:
                self.status["control_steps"] = 2
                raise ConnectionLost()
            return original(kind, rows, **kwargs)
        self.robot.submit.side_effect = submit
        self.robot.wait_ready = lambda **kw: dict(self.status)
        report = stream_standard(self.robot, self.recipe, self.rows, connection_errors=(ConnectionLost,))
        self.assertEqual(report["restarts"], 1)
        self.assertEqual(report["executed_rows"], 4)
        self.assertEqual(len(calls), 2)

    def test_restart_cannot_skip_rows_and_exhaustion_holds_only_the_last_row(self):
        class ConnectionLost(Exception): pass
        original = self.robot.submit.side_effect
        self.robot.submit.side_effect = ConnectionLost()
        for completed in (-1, 3, 100):
            self.robot.wait_ready = lambda **kw: dict(control_steps=completed, done=False)
            with self.subTest(completed=completed), self.assertRaisesRegex(BridgeError, "Restart ledger"):
                stream_standard(self.robot, self.recipe, self.rows, connection_errors=(ConnectionLost,))
        # oraclefix 14 (2026-10-05, a deliberate deviation for the twin method): after the reference rows the twin holds
        # only their last row, at most STANDARD_HOLD_S, until the service reports done, as an agent can hold and poll.
        self.robot.submit.reset_mock(side_effect=True)
        self.robot.submit.side_effect = original
        self.recipe["execution"] = dict(standard_timing="converted", timing_conversion={"source_rows": 1})
        report = stream_standard(self.robot, self.recipe, self.rows[:2])
        self.assertEqual(report["reference_timing"], "converted")
        self.assertEqual(report["timing_conversion"], {"source_rows": 1})
        self.assertEqual((report["executed_rows"], report["reference_rows"], report["hold_rows"]), (4, 2, 2))
        self.assertEqual(self.robot.submit.call_count, 2)
        np.testing.assert_array_equal(self.robot.submit.call_args_list[1].args[1], np.repeat(self.rows[1:2], 2, axis=0))
        # a hold that never reaches success stops after STANDARD_HOLD_S (80 rows at 40 Hz) with an error, never longer
        self.status.update(control_steps=0, done=False, reason=None)
        def never_done(kind, rows, **kwargs):
            self.status["control_steps"] += len(rows)
            return SimpleNamespace(meta=dict(executed_rows=len(rows), control_steps_chunk=len(rows), n_clipped=0,
                                             done=False))
        self.robot.submit.reset_mock(side_effect=True)
        self.robot.submit.side_effect = never_done
        with self.assertRaisesRegex(BridgeError, "without native Task success after its hold"):
            stream_standard(self.robot, self.recipe, self.rows[:2])
        self.assertEqual(self.status["control_steps"], 2 + 80)


class StandardTiming(unittest.TestCase):
    def test_real_service_executes_converted_rows_without_extra_steps_or_clipping(self):
        # Exercise the actual service loop, isolated from its GPU/server startup.
        import ast
        import math
        path = ROOT / "harbor_templates/topogym/limited/environment/sim/server.py"
        node = next(n for n in ast.parse(path.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == "run_joint_position")
        rows = np.array([[0., .015625, 0., .015625], [2.13, 0., -.19, .04],
                         [2.11, .04, -.31, 0.]], dtype=np.float32)
        converted, lineage, changed = rate_limit_rows(rows, ["left/j", "left_gripper", "right/j", "right_native_gripper"], .04)
        commands = []
        def step(row, *args, **kwargs):
            commands.append(row.astype(np.float32).copy())
            return False
        namespace = dict(np=np, math=math, L=SimpleNamespace(control_periods=lambda dt, hz: 1, Recorder=object),
            S=SimpleNamespace(hold_action=lambda: commands[-1] if commands else rows[0]),
            ARMS=["left", "right"], ARM={"left": (None, 1), "right": (None, 3)}, N=4,
            M=SimpleNamespace(JOINT_STEP_LIMIT_RAD=.04), CTRL_HZ=40, LAYOUT=["a", "g", "b", "h"],
            clip_joint_row=lambda row, clipped, ri: row, ctrl_step=step)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
        clipped = []
        # Also check the exact chunk-boundary behavior used by the HTTP bridge.
        for start in range(0, len(converted), 7):
            namespace["run_joint_position"](converted[start:start + 7], .025, "hold", None, clipped)
        np.testing.assert_array_equal(commands, converted)
        self.assertEqual(clipped, [])
        self.assertGreater(len(changed), 0)
        for index, target in enumerate(rows):
            part = converted[lineage == index]
            np.testing.assert_array_equal(part[-1], target)
            np.testing.assert_array_equal(part[:, [1, 3]], np.tile(target[[1, 3]], (len(part), 1)))
        np.testing.assert_array_equal(converted[0], rows[0])

    def test_already_compatible_rows_are_byte_identical(self):
        rows = np.array([[2.12, .01], [2.13, .04], [2.13, .04]], dtype=np.float32)
        result, lineage, changed = rate_limit_rows(rows, ["joint", "arm_gripper"], .04)
        self.assertEqual(result.tobytes(), rows.tobytes())
        self.assertEqual(lineage.tolist(), [0, 1, 2])
        self.assertEqual(changed, [])

    def test_missing_limit_or_unsafe_inputs_fail_closed(self):
        rows = np.array([[0., 0.], [.3, .02]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tooling.py"
            for value in ("", "JOINT_STEP_LIMIT_RAD = get_limit()", "JOINT_STEP_LIMIT_RAD = -1",
                          "JOINT_STEP_LIMIT_RAD = True", "JOINT_STEP_LIMIT_RAD = .04\nJOINT_STEP_LIMIT_RAD = .08"):
                path.write_text(value)
                with self.assertRaises(BridgeError): joint_step_limit(path)
        with patch("topogym.planning.harbor_bridge.timing.MAX_ROWS", 2):
            with self.assertRaisesRegex(BridgeError, "row budget"):
                rate_limit_rows(rows, ["joint", "arm_gripper"], .04)
        with self.assertRaisesRegex(BridgeError, "explicit joint and gripper"):
            rate_limit_rows(rows, ["a", "b"], .04)

    def test_conversion_is_explicit_bound_and_preserves_source_and_public_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task, instance_path = fixture(root, mode="standard")
            tooling = instance_path.parent / "rcb_topogym.py"
            tooling.write_text("BINDING_API = 1\nJOINT_STEP_LIMIT_RAD = .03125\n")
            instance = read_json(instance_path)
            trace = root / "source.npz"
            rows = np.array([[0., .015625] * 2, [.125, 0.] * 2], dtype=np.float32)
            np.savez(trace, actions=rows, action_layout=instance["action_layout"], task=instance["task"],
                     instance_sha=instance["state_sha"], scene_seed=0, meta='{"old_success": true}')
            before, trace_hash = file_hashes(task), digest(trace)
            exact = package(task, root / "exact", kind="public_trajectory", trajectory=trace, source_instance=instance_path)
            self.assertEqual(digest(Path(exact["task"]) / "solution/reference.npz"), trace_hash)
            limited = package(task, root / "limited", kind="public_trajectory", trajectory=trace,
                              source_instance=instance_path, standard_timing="rate_limited")
            solution = Path(limited["task"]) / "solution"
            report = read_json(solution / "timing_conversion.json")
            self.assertEqual(report["joint_step_limit_rad"], .03125)
            self.assertEqual(report["output_rows"], 5)
            self.assertFalse(report["harbor_qualified"])
            self.assertEqual(digest(solution / "source_reference.npz"), trace_hash)
            self.assertEqual(file_hashes(task), before)
            self.assertEqual(digest(trace), trace_hash)
            self.assertTrue(limited["public_files_unchanged"])
            check_package(limited["task"])
            with np.load(solution / "reference.npz") as data:
                self.assertNotIn("old_success", str(data["meta"].item()))
            privileged, _ = fixture(root / "privileged")
            with self.assertRaisesRegex(BridgeError, "requires a standard"):
                package(privileged, root / "invalid", kind="existing", standard_timing="rate_limited")


class Scores(unittest.TestCase):
    def test_returncode_and_infra_errors_cannot_be_zero_score_controls(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "trial/result.json"
            result = dict(finished_at="2026-10-03", exception_info=None,
                          verifier_result=dict(rewards=dict(success=0, grader_error=0)))
            write_json(path, result)
            self.assertEqual(assess_job(d, "nop", 0)["status"], "expected_score")
            self.assertEqual(assess_job(d, "oracle", 0)["status"], "unexpected_score")
            self.assertEqual(assess_job(d, "nop", 1)["status"], "infra_failed")
            result["verifier_result"]["rewards"]["grader_error"] = 1
            write_json(path, result)
            self.assertEqual(assess_job(d, "nop", 0)["status"], "infra_failed")


if __name__ == "__main__":
    unittest.main()
