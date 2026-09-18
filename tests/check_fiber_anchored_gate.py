"""The current task cannot reuse a mismatched asset, timestep or drifting run."""
import json
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

import numpy as np

from topogym.tasks.fiber_bundling.assess_anchored import assess
from topogym.tasks.fiber_bundling.geometry import FiberLayout
from topogym.tasks.fiber_bundling.anchored_geometry import AnchoredLayout


class AnchoredGateChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        for name, dt in (("baseline", .002), ("half_step", .001)):
            p = self.folder/name
            (p/"assets").mkdir(parents=True)
            (p/"assets/bundle.xml").write_text("fixed-terminal-test-asset")
            (p/"report.json").write_text(json.dumps(dict(passed=True, terminal_fixed=True, pose_writes=0,
                spec=dict(dt=dt, substeps=4, load_force_world_N=[-.04, .008, .01],
                          anchor=asdict(AnchoredLayout())), final_link_speed_m_s=0.)))
            fibers = np.stack([FiberLayout().fibers()]*2)
            np.savez(p/"states.npz", time=[.02, .04], fibers=fibers, coarse=fibers[:, :, 0])

    def test_identical_valid_runs_pass(self):
        self.assertTrue(assess(self.folder)["stability_passed"])

    def test_different_assets_fail(self):
        (self.folder/"half_step/assets/bundle.xml").write_text("detached-cable-asset")
        self.assertFalse(assess(self.folder)["stability_passed"])

    def test_same_cable_but_different_support_does_not_qualify(self):
        p = self.folder/"half_step/report.json"
        r = json.loads(p.read_text())
        r["spec"]["anchor"]["cradle_x_m"] = .10
        p.write_text(json.dumps(r))
        result = assess(self.folder)
        self.assertTrue(result["checks"]["same_anchored_asset"])
        self.assertFalse(result["checks"]["same_explicit_fixture_layout"])
        self.assertFalse(result["stability_passed"])

    def test_same_asset_but_different_contact_model_does_not_qualify(self):
        p = self.folder/"half_step/report.json"
        r = json.loads(p.read_text())
        r["spec"]["contact_model"] = "capsule_closest_points_scale_relative_v1"
        p.write_text(json.dumps(r))
        result = assess(self.folder)
        self.assertFalse(result["checks"]["same_contact_model"])
        self.assertFalse(result["stability_passed"])

    def test_different_numerical_precision_cannot_share_gate(self):
        p = self.folder/"half_step/report.json"
        r = json.loads(p.read_text())
        r["spec"]["precision"] = "64"
        p.write_text(json.dumps(r))
        result = assess(self.folder)
        self.assertFalse(result["checks"]["same_loading"])
        self.assertFalse(result["stability_passed"])

    def test_different_solver_cannot_share_gate(self):
        from topogym.tasks.fiber_bundling.numerics import require_solver_evidence
        p=self.folder/"half_step/report.json"
        r=json.loads(p.read_text())
        r["spec"]["constraint_solver"]="CG"
        p.write_text(json.dumps(r))
        self.assertFalse(assess(self.folder)["stability_passed"])
        with self.assertRaisesRegex(RuntimeError,"constraint solver"):
            require_solver_evidence({"numerics":{"constraint_solver":"CG"}}, {})
        self.assertEqual(require_solver_evidence({}, {}),"Newton")

    def test_rigid_world_drift_cannot_hide_in_local_shape_comparison(self):
        p = self.folder/"half_step/states.npz"
        with np.load(p) as d:
            arrays = {key: d[key].copy() for key in d.files}
        arrays["fibers"] += [.003, 0., 0.]
        arrays["coarse"] += [.003, 0., 0.]
        np.savez(p, **arrays)
        result = assess(self.folder)
        self.assertTrue(result["checks"]["final_local_max"])
        self.assertFalse(result["stability_passed"])

    def test_free_terminal_or_pose_writes_fail(self):
        p = self.folder/"baseline/report.json"
        r = json.loads(p.read_text())
        r.update(terminal_fixed=False, pose_writes=1)
        p.write_text(json.dumps(r))
        self.assertFalse(assess(self.folder)["stability_passed"])


if __name__ == "__main__":
    unittest.main()
