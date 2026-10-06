#!/usr/bin/env python3
"""Private reference relocation/tamper tests; no simulator or success claims."""
import importlib.util
import builtins
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "ci_checks")]
from topogym.planning.harbor_bridge.contracts import BridgeError, digest
from topogym.planning.harbor_bridge.packaging import package, check_package
from topogym.planning.harbor_bridge.references import reference_data
from v15_fixtures import bound_task

spec = importlib.util.spec_from_file_location("portability", ROOT / "ci_checks/check-oracle-portability.py")
portability = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portability)


class Portability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="relocated oracle ")
        cls.root = Path(cls.temp.name)
        # Deliberately no runs/, solvability_proof/, symlinks or checkout fallback.
        shutil.copytree(ROOT / "topogym/planning", cls.root / "topogym/planning",
                        ignore=shutil.ignore_patterns("__pycache__", "calibration_tools"))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_33_default_references_resolve_without_local_evidence(self):
        result = portability.check(self.root)
        self.assertEqual(len(result["tasks"]), 33)
        self.assertTrue(result["all_passed"], result)

    def test_bundled_data_preserve_original_provenance_hashes(self):
        base = self.root / "topogym/planning/harbor_bridge/reference_data"
        manifest = json.loads((base / "manifest.json").read_text())
        # The original 33 inputs plus the local Fiber below-easy selections, Hedgehog below-easy pickups and the six
        # Horseshoe below-easy inputs of each tier.
        self.assertEqual(len(manifest["files"]), 49)
        for tier in ("very_easy", "easier"):
            self.assertIn(f"fiber_bundling/{tier}/selection.json", manifest["files"])
            self.assertIn(f"hedgehog_in_cage/{tier}/pickup.json", manifest["files"])
            for name in ("recipe", "grasps", "reference", "fold", "support", "approach"):
                self.assertIn(f"horseshoe_ring/{tier}/{name}.json", manifest["files"])
        for name, record in manifest["files"].items():
            self.assertEqual(digest(base / name), record["sha256"], name)
            self.assertEqual((base / name).stat().st_size, record["bytes"], name)

    def test_missing_or_modified_input_is_rejected_before_packaging(self):
        path = self.root / "topogym/planning/harbor_bridge/reference_data/fiber_bundling/easy/selection.json"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")
            with self.assertRaisesRegex(BridgeError, "changed reference"):
                reference_data(self.root, "fiber_bundling", "easy", 0)
            path.unlink()
            with self.assertRaisesRegex(BridgeError, "Missing reference"):
                reference_data(self.root, "fiber_bundling", "easy", 0)
        finally:
            path.write_bytes(original)

    def test_hedgehog_and_rope_dynamic_data_reach_the_solution(self):
        for family, module, required in (
            ("hedgehog_in_cage", "public_session", "reference_routes.json"),
            ("rope_threading", "public_session", "hard_plans.json"),
        ):
            with tempfile.TemporaryDirectory() as folder:
                task = bound_task(Path(folder) / "task-privileged")
                data, includes = reference_data(self.root, family, "hard", 0)
                result = package(task, Path(folder) / "candidates", kind="session",
                    entrypoint=f"topogym.planning.{family}.{module}:run_feedback_policy",
                    source_root=self.root, includes=includes, data_files=data, kwargs=dict(variation="hard"))
                candidate = Path(result["task"])
                check_package(candidate)
                self.assertTrue((candidate / "solution/topogym/planning" / family / required).is_file())

    def test_buzz_medium_missing_or_changed_guide_blocks_portability(self):
        path = self.root / "topogym/planning/harbor_bridge/reference_data/buzz_wire_3d/medium/medium_traverse_guide.json"
        original = path.read_bytes()
        try:
            for content in (original + b" ", None):
                if content is None:
                    path.unlink()
                else:
                    path.write_bytes(content)
                result = portability.check(self.root, families=["buzz_wire_3d"])
                self.assertFalse(result["all_passed"])
                self.assertEqual([r["tier"] for r in result["tasks"] if r["errors"]], ["medium"])
                self.assertIn("medium_traverse_guide.json", str(result["tasks"][1]["errors"]))
        finally:
            path.write_bytes(original)

    def test_buzz_complete_default_inputs_are_required_and_relocatable(self):
        for tier in ("easy", "medium", "hard"):
            with self.subTest(tier=tier), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                task = bound_task(root / "task-privileged")
                data, includes = reference_data(self.root, "buzz_wire_3d", tier, 0)
                result = package(task, root / "candidates", kind="session",
                    entrypoint="topogym.planning.buzz_wire_3d.public_session:run_feedback_policy",
                    source_root=self.root, includes=includes, data_files=data, kwargs=dict(variation=tier))
                candidate = Path(result["task"])
                check_package(candidate)
                solution = root / "relocated solution"
                shutil.move(str(candidate / "solution"), solution)
                code = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import topogym.planning
solution = Path(sys.argv[2])
topogym.planning.__path__ = [str(solution / 'topogym/planning')]
from topogym.planning.buzz_wire_3d.reference_policy import load_reference
recipe, document = load_reference(sys.argv[3])
assert recipe['kind'] == ('staged_feedback' if sys.argv[3] == 'easy' else 'compiled_joint_actions')
assert len(document if sys.argv[3] == 'easy' else document['actions']) == {'easy': 11, 'medium': 29544, 'hard': 43568}[sys.argv[3]]
path = solution / 'topogym/planning/harbor_bridge/reference_data/buzz_wire_3d' / sys.argv[3] / recipe['input']['file']
path.write_bytes(path.read_bytes() + b' ')
try:
    load_reference(sys.argv[3])
except ValueError as error:
    assert 'input changed' in str(error)
else:
    raise AssertionError('Changed complete policy was accepted')
'''
                completed = subprocess.run([sys.executable, "-c", code, str(ROOT), str(solution), tier],
                    cwd=root, text=True, capture_output=True, timeout=60)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                name = "selection.json" if tier == "easy" else "policy_actions.json"
                path = self.root / "topogym/planning/harbor_bridge/reference_data/buzz_wire_3d" / tier / name
                original = path.read_bytes()
                try:
                    path.unlink()
                    result = portability.check(self.root, families=["buzz_wire_3d"], tiers=[tier])
                    self.assertFalse(result["all_passed"])
                    self.assertIn(name, str(result["tasks"][0]["errors"]))
                finally:
                    path.write_bytes(original)

    def test_buzz_staged_guide_loads_from_relocated_solution_without_local_runs(self):
        with tempfile.TemporaryDirectory(prefix="buzz portable solution ") as folder:
            root = Path(folder)
            task = bound_task(root / "task-privileged")
            data, includes = reference_data(self.root, "buzz_wire_3d", "medium", 0)
            result = package(task, root / "candidates", kind="session",
                entrypoint="topogym.planning.buzz_wire_3d.public_session:run_feedback_policy",
                source_root=self.root, includes=includes, data_files=data, kwargs=dict(variation="medium"))
            candidate = Path(result["task"])
            check_package(candidate)
            # Move the actual packaged solution and resolve private imports only
            # there; installed public simulator/task modules remain authoritative.
            solution = root / "relocated solution"
            shutil.move(str(candidate / "solution"), solution)
            cwd = root / "unrelated cwd"
            cwd.mkdir()
            code = '''
import itertools, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import topogym.planning
solution = Path(sys.argv[2])
topogym.planning.__path__ = [str(solution / 'topogym/planning')]
from topogym.planning.buzz_wire_3d import stages
from topogym.planning.harbor_bridge import callbacks
assert Path(stages.__file__).is_relative_to(solution)
assert Path(callbacks.__file__).is_relative_to(solution)
env = SimpleNamespace(config=SimpleNamespace(variation_id='medium'))
context = SimpleNamespace(output=Path.cwd())
step = list(itertools.islice(stages.stages(env, context), 4))[-1]
assert step.name == 'traverse'
parameters = step.candidates[0]
document = stages.load_traverse_guide(parameters)
assert len(document['guide']) == 1187
path = callbacks.data_path(parameters['guide_file'])
assert path.is_relative_to(solution)
original = path.read_bytes()
path.write_bytes(original + b' ')
try:
    stages.load_traverse_guide(parameters)
except ValueError as error:
    assert 'Traverse guide changed' in str(error)
else:
    raise AssertionError('Changed guide was accepted')
path.unlink()
try:
    stages.load_traverse_guide(parameters)
except ValueError as error:
    assert 'Missing private reference data' in str(error)
else:
    raise AssertionError('Missing guide silently fell back to the original checkout')
'''
            completed = subprocess.run([sys.executable, "-c", code, str(ROOT), str(solution)],
                cwd=cwd, text=True, capture_output=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_git_gate_rejects_existing_but_uncommittable_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            shutil.copytree(self.root / "topogym/planning", root / "topogym/planning")
            result = portability.check(root, families=["fiber_bundling"], tiers=["easy"], check_git=True)
            self.assertFalse(result["all_passed"])
            self.assertTrue(any("selection.json" in e for e in result["tasks"][0]["errors"]))
            subprocess.run(["git", "-C", str(root), "add", "topogym"], check=True)
            self.assertTrue(portability.check(root, families=["fiber_bundling"], tiers=["easy"], check_git=True)["all_passed"])
            helper = root / "topogym/planning/fiber_bundling/public_session.py"
            helper.write_text(helper.read_text() + "\n# unstaged change\n")
            result = portability.check(root, families=["fiber_bundling"], tiers=["easy"], check_git=True)
            self.assertFalse(result["all_passed"])
            self.assertTrue(any("differs from Git index" in e for e in result["tasks"][0]["errors"]))

    def test_session_workers_do_not_import_pruned_segment_runner(self):
        import torch
        from topogym.planning.cast_keyhole.runner import worker as keyhole, simplified_worker
        from topogym.planning.buzz_wire_3d.runner import worker as buzz
        from topogym.planning.lock_picking.runner import worker as lock

        class ImportsComplete(Exception):
            pass

        original = builtins.__import__

        def checked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if "rollout_simulation" in name or name == "topogym.simulator" and "SegmentRunner" in (fromlist or ()):
                raise ModuleNotFoundError("Development recorder was pruned from the image")
            return original(name, globals, locals, fromlist, level)

        calls = [lambda: keyhole(SimpleNamespace(variation="easy"), self.root, session=object()),
                 lambda: simplified_worker(SimpleNamespace(), self.root, session=object()),
                 lambda: buzz(SimpleNamespace(), session=object()),
                 lambda: lock(self.root, setting=None, part=None, grasp_roll_deg=None, grasp_style=None,
                              physics_dt=None, solver_substeps=None, control_decimation=None,
                              no_rgb=True, compute_backend="cpu", session=object())]
        # Stop after the actual lazy imports, before scene generation or physics.
        for call in calls:
            with patch("builtins.__import__", side_effect=checked_import), \
                 patch.object(torch, "set_num_threads", side_effect=ImportsComplete):
                with self.assertRaises(ImportsComplete):
                    call()

    def test_record_fingerprint_preserves_existing_numeric_hash(self):
        import numpy as np
        from topogym.planning.harbor_bridge.callbacks import fingerprint
        from topogym.simulator.rollout_simulation.segment_contract import fingerprint as original
        value = dict(array=np.array([.1, .2]), count=np.int64(3), nested={"a": [True, None]})
        self.assertEqual(fingerprint(value), original(value))

    def test_all_callbacks_import_without_development_recorder(self):
        code = '''
import builtins, importlib
from topogym.planning.harbor_bridge.catalog import SESSION_CALLBACKS
original = builtins.__import__
def checked(name, globals=None, locals=None, fromlist=(), level=0):
    if 'rollout_simulation' in name or name == 'topogym.simulator' and 'SegmentRunner' in (fromlist or ()):
        raise ModuleNotFoundError('Development recorder is absent')
    return original(name, globals, locals, fromlist, level)
builtins.__import__ = checked
for callback in SESSION_CALLBACKS.values():
    module, function = callback.split(':')
    assert callable(getattr(importlib.import_module(module), function))
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_relay_robot_identity_survives_asset_relocation_and_detects_changes(self):
        from omegaconf import OmegaConf
        from topogym.planning.rope_threading.geometry import robot_scene_identity
        from topogym.planning.rope_threading.profiles import reference_samples
        from topogym.planning.rope_threading.relay_artifact import load_plan
        _, metadata = load_plan(reference_samples("easy"))
        expected = metadata["identity"]["robot_scene"]
        scene = OmegaConf.create(dict(robot_control=expected["control"], env=dict(robot_mount=expected["mount"])))
        with tempfile.TemporaryDirectory(prefix="installed robot assets ") as folder:
            assets = Path(folder)
            shutil.copytree(ROOT / "assets/robots/aloha", assets / "robots/aloha")
            with patch.dict(os.environ, TOPOGYM_ASSET_ROOT=str(assets)):
                self.assertEqual(robot_scene_identity(scene), expected)
                path = assets / "robots/aloha/aloha.xml"
                path.write_bytes(path.read_bytes() + b"\n")
                self.assertNotEqual(robot_scene_identity(scene)["asset_sha256"], expected["asset_sha256"])
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    robot_scene_identity(scene)


if __name__ == "__main__":
    unittest.main(verbosity=2)
