"""Control-gate tests: fake contact feedback is not a physical qualification."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.rope_threading.feedback_actions import FeedbackThreadingActions
from topogym.tasks.rope_threading.reference_actions import ReferenceThreadingActions


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT/"runs/environment-solvability/rope_threading/reference_motion_v1"


@unittest.skipUnless((REFERENCE/"reference_motion.npz").is_file(), "Offline reference unavailable")
class FeedbackRuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a = FeedbackThreadingActions(REFERENCE, cfg=None, output=Path(self.temp.name), speed=3.)
        self.q = np.asarray(json.loads((ROOT/"tests/fixtures/rope_threading_r2_handoff.json").read_text())["qpos"])
        self.a._qpos = Mock(return_value=self.q.copy())
        self.a._snapshot = Mock(return_value=dict(qpos=self.q.tolist()))
        self.a._record = Mock()
        self.a._command = Mock()
        self.a._follow_bands = Mock()
        self.a.release = Mock()
        self.a.source_time = self.a.schedule[5]["time"]
        self.a.event_index = 5
        self.a.last_time = 66.
        self.a.local_stage = "close"
        self.a.local_start = 66.
        self.a.hold_qpos = self.q.copy()
        self.a.owners = {2: "left"}

    def test_no_contact_cannot_advance_source_or_release_left(self):
        self.a._acquire = Mock(return_value=False)
        self.a.update(66.005)
        self.assertEqual(self.a.event_index, 5)
        self.assertEqual(self.a.local_stage, "close")
        self.assertEqual(self.a.source_time, self.a.schedule[5]["time"])
        self.a.release.assert_not_called()
        self.a._acquire.assert_called_once_with(self.a.schedule[5], 66.005, minimum_aperture=.010)

    def test_contact_requires_dual_hold_and_screen_before_narrow_release(self):
        order = []

        def acquire(event, t, **kwargs):
            self.a.owners[3] = "right"
            return True

        self.a._acquire = Mock(side_effect=acquire)
        self.a.update(66.005)
        self.assertEqual(self.a.event_index, 6)
        self.assertEqual(self.a.local_stage, "dual_hold")
        self.a.update(66.49)
        self.a.release.assert_not_called()
        path = SimpleNamespace(audit=dict(passed=True))
        self.a.planner = SimpleNamespace(unpinch=Mock(side_effect=lambda q: (order.append("screen"), path)[1]))
        self.a.release.side_effect = lambda *args, **kwargs: order.append("release")
        self.a._begin_path = Mock(side_effect=lambda *args: order.append("start_path"))
        self.a.update(66.51)
        self.assertEqual(order, ["screen", "release", "start_path"])
        self.a.release.assert_called_once_with("left", 66.51, open_qpos=float(self.q[6]))
        self.assertEqual(self.a.event_index, 7)

    def test_handoff_trigger_rejects_missing_left_support(self):
        self.a.local_stage = None
        self.a.owners = {}
        self.a.source_time = 194.99
        with self.assertRaisesRegex(RuntimeError, "left node-77"):
            self.a.update(66.005)

    def test_first_release_freezes_measured_left_pose_and_screens_before_release(self):
        self.a.local_stage = None
        self.a.event_index = 4
        self.a.source_time = self.a.schedule[4]["time"]-.005
        self.a.owners = {2: "left", 3: "right"}
        order = []
        path = SimpleNamespace(audit=dict(passed=True))
        self.a.planner = SimpleNamespace(unpinch=Mock(side_effect=lambda *a, **k: (order.append("screen"), path)[1]))
        self.a._command.side_effect = lambda q: order.append("hold_measured")
        self.a.release.side_effect = lambda *a, **k: order.append("release")

        def begin(stage, *args):
            self.a.local_stage = stage
            order.append("start_path")

        self.a._begin_path = Mock(side_effect=begin)
        self.a.update(66.005)
        self.assertEqual(order, ["screen", "hold_measured", "release", "start_path"])
        self.a.release.assert_called_once_with("right", 66.005, open_qpos=float(self.q[14]))
        self.assertEqual(self.a.local_stage, "first_unpinch")
        self.assertEqual(self.a.event_index, 5)

    def test_failed_first_unpinch_screen_keeps_both_supports(self):
        self.a.local_stage = None
        self.a.event_index = 4
        self.a.source_time = self.a.schedule[4]["time"]-.005
        self.a.owners = {2: "left", 3: "right"}
        self.a.planner = SimpleNamespace(unpinch=Mock(side_effect=ValueError("unsafe path")))
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            self.a.update(66.005)
        self.a.release.assert_not_called()

    def test_rejected_unpinch_path_cannot_release_support(self):
        self.a.local_stage = "dual_hold"
        self.a.owners[3] = "right"
        self.a.event_index = 6
        self.a.planner = SimpleNamespace(unpinch=Mock(side_effect=ValueError("collision")))
        with self.assertRaisesRegex(ValueError, "collision"):
            self.a.update(66.6)
        self.a.release.assert_not_called()

    def test_late_reference_release_avoids_full_open_impulse(self):
        q = self.a._sample(332.705)[0]
        self.assertIsNone(self.a.release_aperture("left", q))
        self.a.handoff_done = True
        self.assertEqual(self.a.release_aperture("left", q), q[6])
        self.assertLess(self.a.release_aperture("left", q), .02)

    def test_early_clearance_vanishes_at_every_grasp_event(self):
        self.a.ik = SimpleNamespace(mount_rotation=Rotation.identity())
        for event in self.a.schedule:
            if event["kind"] == "acquire":
                phase = self.a._sample(event["time"])[3]
                for side in ("left", "right"):
                    np.testing.assert_array_equal(self.a.task_clearance(event["time"], phase, side), np.zeros(3))

    def test_unfinished_handoff_cannot_report_completion(self):
        with patch.object(ReferenceThreadingActions, "report", return_value=dict(checks=dict(other=True), passed=True)):
            result = self.a.report()
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["measured_R2_handoff_completed"])


if __name__ == "__main__":
    unittest.main()
