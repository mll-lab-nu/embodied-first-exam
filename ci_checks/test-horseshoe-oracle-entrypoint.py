#!/usr/bin/env python3
"""Formal import isolation and recipe integrity; no physical qualification."""
import hashlib
import importlib
import importlib.abc
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class NoCalibration(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("topogym.planning.calibration_tools"):
            raise AssertionError("Formal oracle imported development tools: " + fullname)


sys.meta_path.insert(0, NoCalibration())
from scripts.oracle_runners.run_horseshoe_oracle import prepare_recipe


class OracleEntrypointTests(unittest.TestCase):
    def test_support_retreat_requires_observed_right_release(self):
        from topogym.planning.horseshoe_ring.manipulation import ManipulationPlanner
        planner=ManipulationPlanner.__new__(ManipulationPlanner)
        for state in ({}, {'binding':{'target':['horseshoe_right','horseshoe_right']}}):
            observation={'privileged':{'world':{'grasp':{'hands':{'right':state}}}}}
            with self.assertRaisesRegex(ValueError,'observed release'):
                planner.withdraw_released_hand(observation,'right')

    def test_joint_retreat_requires_evidence_that_the_hand_released(self):
        from topogym.planning.horseshoe_ring.manipulation import ManipulationPlanner
        planner=ManipulationPlanner.__new__(ManipulationPlanner)
        for hands in ({}, {'left':{}}, {'left':{'binding':{'entity':'horseshoe_left'}}}):
            observation={'privileged':{'world':{'grasp':{'hands':hands}}}}
            with self.assertRaisesRegex(ValueError,'observed release'):
                planner.withdraw_left(observation,allow_release_contact=True,joint_retreat=True)

    def test_formal_modules_import_with_calibration_blocked(self):
        for path in sorted((ROOT / "topogym/planning/horseshoe_ring").glob("*.py")):
            importlib.import_module("topogym.planning.horseshoe_ring." + path.stem)
        self.assertFalse(any(name.startswith("topogym.planning.calibration_tools") for name in sys.modules))

    def recipe(self, folder):
        parameters = {}
        for name in ("grasps", "reference", "fold", "support", "approach"):
            source = folder / (name + ".json")
            source.write_text(json.dumps({"fixture": name}))
            parameters[name] = dict(path=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        value = dict(variant="medium", seed=0,
            config=dict(task_id="horseshoe_ring", variation_id="medium", control_mode="JOINT_ABS", enable_rgb=False),
            selection=[dict(step="prefix", parameters=parameters)])
        path = folder / "recipe.json"
        path.write_text(json.dumps(value))
        return path

    def test_recipe_copies_and_binds_all_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); recipe = self.recipe(folder)
            output = folder / "output"; output.mkdir()
            prepare_recipe(recipe, output, "medium", 0)
            copied = json.loads((output / "requested_selection.json").read_text())[0]["parameters"]
            for name, item in copied.items():
                self.assertEqual(Path(item["path"]).read_bytes(), (folder / (name + ".json")).read_bytes())
                self.assertTrue(Path(item["path"]).is_relative_to(output))

    def test_changed_instance_or_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); recipe = self.recipe(folder)
            output = folder / "output"; output.mkdir()
            with self.assertRaisesRegex(ValueError, "variant/seed"):
                prepare_recipe(recipe, output, "hard", 0)
            (folder / "fold.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "Changed planning input: fold"):
                prepare_recipe(recipe, output, "medium", 0)


if __name__ == "__main__":
    unittest.main()
