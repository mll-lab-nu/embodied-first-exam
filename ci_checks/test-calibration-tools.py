#!/usr/bin/env python3
"""Development contracts and real geometric probes. No implicit GPU/physics run."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.planning.calibration_tools import open_session
from topogym.planning.calibration_tools.contracts import (Budgets, CalibrationError, OperationTimeout,
                                                         RequestConflict, UnsupportedCapability)
from topogym.planning.calibration_tools.supervisor import Supervisor


def contract_worker(pipe, cancel, config, output, session_id, kind):
    """Deliberately tiny protocol peer for failure injection, not a physics fallback."""
    if os.name == "posix":
        os.setsid()
    count = 0
    pipe.send(dict(kind="ready", progress=dict(stage="idle", physics_step=0)))
    while True:
        request = pipe.recv()
        method = request["method"]
        if method == "step_until":
            while not cancel.wait(.01):
                pass
        if method == "run_policy":
            time.sleep(30)
        if method == "step":
            count += 1
        pipe.send(dict(kind="result", operation_id=request["operation_id"], result=dict(count=count)))
        if method == "close":
            pipe.close()
            return


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.supervisor = Supervisor({}, Path(self.directory.name) / "run", kind="geometry",
            budgets=Budgets(startup_s=20), worker_target=contract_worker)

    def tearDown(self):
        self.supervisor.close()
        self.directory.cleanup()

    def test_duplicate_mutation_and_conflict(self):
        first = self.supervisor.call("step", {"action": {}}, request_id="same")
        second = self.supervisor.call("step", {"action": {}}, request_id="same")
        self.assertEqual(first, second)
        with self.assertRaises(RequestConflict):
            self.supervisor.call("step", {"action": {"x": 1}}, request_id="same")
        self.assertEqual(self.supervisor.call("step", {"action": {}})["count"], 2)

    def test_cancel_while_worker_busy(self):
        op = self.supervisor.submit("step_until")
        with self.assertRaises(CalibrationError):
            self.supervisor.submit("inspect")
        self.assertTrue(self.supervisor.status()["worker_alive"])
        self.supervisor.cancel(op)
        self.assertEqual(self.supervisor.wait(op)["count"], 0)

    def test_close_seals_an_active_operation(self):
        from topogym.planning.calibration_tools.contracts import WorkerLost
        op = self.supervisor.submit("step_until")
        self.supervisor.close()
        with self.assertRaises(WorkerLost):
            self.supervisor.wait(op)
        self.assertFalse(self.supervisor.status()["worker_alive"])

    def test_timeout_seals_receipt_and_stops_owned_worker(self):
        op = self.supervisor.submit("run_policy", request_id="hang", timeout_s=.15)
        with self.assertRaises(OperationTimeout):
            self.supervisor.wait(op)
        # Repeating the receipt retrieves failure, never reissues the action.
        self.assertEqual(self.supervisor.submit("run_policy", request_id="hang"), op)
        with self.assertRaises(OperationTimeout):
            self.supervisor.wait(op)
        deadline = time.monotonic() + 3
        while self.supervisor.status()["worker_alive"] and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertFalse(self.supervisor.status()["worker_alive"])
        self.assertTrue((self.supervisor.output / "operations/hang.json").is_file())


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.sessions = {level: open_session(dict(task_id="cast_keyhole", variation_id=level,
            enable_rgb=False, compute_backend="cpu", seed=0),
            Path(cls.directory.name) / level, kind="geometry") for level in ("very_easy", "easier")}

    @classmethod
    def tearDownClass(cls):
        for session in cls.sessions.values():
            session.close()
        cls.directory.cleanup()

    def test_geometry_edits_checkpoint_and_stale_future(self):
        for dev in self.sessions.values():
            start = dev.inspect()
            mark = dev.checkpoint("before")
            name = "keyhole_silver"
            value = {key: start["bodies"][name][key] for key in ("position_m", "quaternion_wxyz")}
            changed = deepcopy(value)
            changed["position_m"][0] += .1
            edit = dev.set_object_pose(name, changed, request_id="move-once")
            self.assertEqual(edit, dev.set_object_pose(name, changed, request_id="move-once"))
            future = dev.checkpoint("after")
            dev.restore(mark)
            restored = dev.inspect()
            self.assertEqual(start["bodies"], restored["bodies"])
            self.assertTrue(restored["exploration"])
            with self.assertRaises(CalibrationError):
                dev.restore(future)
            bad = dict(mark, session_id="another")
            with self.assertRaises(CalibrationError):
                dev.restore(bad)
            with self.assertRaises(UnsupportedCapability):
                dev.set_object_pose(name, value, scope="physics")

    def test_pin_relative_pose_and_probe_grasp(self):
        dev = self.sessions["very_easy"]
        mark = dev.checkpoint("pin-test")
        original = dev.inspect()["bodies"]["keyhole_silver"]
        value = {key: original[key] for key in ("position_m", "quaternion_wxyz")}
        dev.pin_object("keyhole_silver")
        with self.assertRaises(CalibrationError):
            dev.set_object_pose("keyhole_silver", value)
        dev.unpin_object("keyhole_silver")
        identity = dict(position_m=[0, 0, 0], quaternion_wxyz=[1, 0, 0, 0])
        grasp = dev.set_probe_grasp("right", "keyhole_silver", identity, hand_pose=value)
        self.assertFalse(grasp["probe_grasps"]["right"]["contact_acquired"])
        dev.set_probe_grasp("right", None)
        relative = dev.set_relative_pose("keyhole_silver", "keyhole_gold", identity)
        self.assertEqual(relative["bodies"]["keyhole_silver"]["position_m"], dev.inspect()["bodies"]["keyhole_gold"]["position_m"])
        dev.restore(mark)

    def test_real_mesh_sweep_and_invalid_inputs(self):
        for dev in self.sessions.values():
            state = dev.inspect()["bodies"]["keyhole_silver"]
            value = {key: state[key] for key in ("position_m", "quaternion_wxyz")}
            result = dev.sweep_object("keyhole_silver", [value], obstacles=["keyhole_gold"])
            self.assertTrue(result["passed"], result)
            self.assertGreater(result["minimum_sampled_clearance_m"], 0)
            self.assertEqual(result["physics_steps"], 0)
            with self.assertRaises(CalibrationError):
                dev.sweep_object("keyhole_silver", [value], resolution={"translation_m": 0, "rotation_rad": .1})
            with self.assertRaises(UnsupportedCapability):
                dev.step({})
            with self.assertRaises(UnsupportedCapability):
                dev.capture_frame("cam_high")

    def test_candidate_assets_and_inertia_are_separate(self):
        dev = self.sessions["easier"]
        before = dev.inspect()
        baseline = dev.preview_geometry({})
        changed = dev.preview_geometry({"density_kg_m3": 7000})
        comparison = dev.compare_geometry(baseline["candidate_id"], changed["candidate_id"])
        self.assertTrue(all(row["mass_delta_kg"] > 0 for row in comparison["bodies"].values()))
        patch = dev.export_geometry_patch(changed["candidate_id"])
        self.assertFalse(patch["applied_to_official_assets"])
        self.assertTrue(Path(patch["patch"]).is_file())
        self.assertEqual(before["scene_revision"], dev.inspect()["scene_revision"])
        self.assertEqual(before["bodies"], dev.inspect()["bodies"])
        self.assertFalse(dev.export_report()["robot_success_certified"])

    def test_restart_invalidates_old_handles(self):
        dev = self.sessions["easier"]
        old = dev.checkpoint("before-restart")
        with self.assertRaises(ValueError):
            dev.restart(replay_to=1)  # No physical action exists in this geometry session.
        self.assertEqual(dev.status()["session_id"], old["session_id"])
        result = dev.restart()
        self.assertNotEqual(result["session_id"], old["session_id"])
        self.assertEqual(result["replayed_control_steps"], 0)
        with self.assertRaises(CalibrationError):
            dev.restore(old)


class SensorAndEventsTests(unittest.TestCase):
    def test_sweep_checks_between_waypoints_and_detects_containment(self):
        import numpy as np
        import trimesh
        from scipy.spatial.transform import Rotation
        from topogym.planning.calibration_tools.geometry import RigidProbe
        probe = RigidProbe.__new__(RigidProbe)
        probe.meshes = {"fixed": trimesh.creation.box([.1, .1, .1]),
                        "moving": trimesh.creation.box([.02, .02, .02])}
        probe.poses = {"fixed": (np.zeros(3), Rotation.identity())}
        probe.scene_revision, probe.revision = "fixture", 0
        def at(x):
            return dict(position_m=[x, 0, 0], quaternion_wxyz=[1, 0, 0, 0])
        crossing = probe.sweep("moving", [at(-.2), at(.2)],
                               resolution=dict(translation_m=.025, rotation_rad=.1))
        self.assertFalse(crossing["passed"])
        self.assertGreater(crossing["first_collision"]["sample"], 0)
        contained = probe.sweep("moving", [at(0.)])
        self.assertFalse(contained["passed"])
        self.assertTrue(contained["first_collision"]["intersection"])

    def test_on_demand_sensors_do_not_render_during_observe(self):
        from types import SimpleNamespace
        from topogym.sensors.observation import SensorSuite
        from topogym.planning.calibration_tools.rendering import DevelopmentSensors
        import numpy as np
        calls = []
        class Camera:
            res = (4, 4)
            fov = 60.
            transform = np.eye(4)
            def render(self, **kwargs):
                calls.append(1)
                return np.zeros((4, 4, 3), dtype=np.uint8)
        world = SimpleNamespace(cameras={"test": Camera()}, physics_step=0, sim_time_s=0.)
        robot, task = SimpleNamespace(observe=lambda: {}), SimpleNamespace(observe=lambda: {})
        args = dict(episode_id="one", branch_id=0, state_id=0, task=task)
        dev = DevelopmentSensors(world, robot, enable_rgb=True)
        self.assertEqual(dict(dev.sample(**args)[0]["rgb"]), {})
        self.assertEqual(calls, [])
        ordinary = SensorSuite(world, robot, enable_rgb=True)
        ordinary.sample(**args)
        ordinary.sample(**args)
        self.assertEqual(len(calls), 1)
        args["branch_id"] = 1
        ordinary.sample(**args)
        self.assertEqual(len(calls), 2)

    def test_event_windows_do_not_cross_rewind(self):
        from topogym.planning.calibration_tools.inspection import EventWindows
        out = []
        events = EventWindows(lambda kind, **row: out.append(dict(kind=kind, **row)))
        events.watch(["always"], before_steps=1, after_steps=2)
        events.push(dict(physics_step=1))
        events.reset("rewind")
        self.assertEqual(out[0]["kind"], "event_window_incomplete")
        self.assertEqual(out[0]["reason"], "rewind")
        self.assertEqual(list(events.history), [])


if __name__ == "__main__":
    unittest.main()
