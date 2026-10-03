#!/usr/bin/env python3
"""Tool contracts using recorded-state fixtures; never a physics or task acceptance."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import nullcontext

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.calibration_tools.tracking import Tracking, requested_tcp, read_tracking_report
from topogym.planning.calibration_tools.plan_cache import PlanCache, PlanPreparation, CacheMiss
from topogym.planning.calibration_tools.adapters.keyhole_plans import densify


def at(x=0.):
    return dict(position_m=[x, 0., 0.], quaternion_wxyz=[1., 0., 0., 0.])


def tick(n=0, *, q=.0, target=.1, branch=0):
    return dict(state=dict(episode_id="e", branch_id=branch, state_id=n, physics_step=n,
                           control_step=(n+1)//2, sim_time_s=n*.01),
        world=dict(bodies=dict(a=at(), b=at(1.))),
        robot=dict(left=dict(joint_position_rad=[q], tcp_position_world_m=[q, 0., 0.],
                             tcp_orientation_wxyz=[1., 0., 0., 0.], finger_position_m=[.02, .02])),
        targets=dict(left=dict(joint_position_rad=[target])))


def transition(ticks):
    return SimpleNamespace(physics_steps=ticks, action_duration_s=ticks*.01,
                           info=dict(executed_joint_targets={"left": {"joint_position_rad": [.1]}}))


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.messages = []
        self.tracking = Tracking(self.tmp.name, self.messages.append)
        self.key = self.tracking.start(tick(), entities=["a", "b"], relative_pairs=[["b", "a"]],
            thresholds=dict(joint_rad=.05))["tracking_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def samples(self):
        path = self.tracking.report(self.key)["samples"]
        return [json.loads(line) for line in Path(path).read_text().splitlines()]

    def begin(self, action=None, mode="JOINT_ABS", policy=None):
        self.tracking.begin({} if action is None else action, tick(), mode,
                            segment_id=2, action_index=0, policy=policy)

    def test_committed_targets_tick_maximum_and_early_termination(self):
        self.begin({"left": {"joint_delta_rad": [.1]}}, "JOINT_DELTA")
        self.tracking.tick(tick(1, q=.01, target=.2))
        self.tracking.tick(tick(2, q=.17, target=.2))
        self.tracking.finish(transition(2))
        row = self.samples()[-1]
        self.assertAlmostEqual(row["maxima"]["joint_rad/left"], .19)
        self.assertAlmostEqual(row["last"]["errors"]["joint_rad/left"], .03)
        self.assertEqual(row["first_violation"]["state"]["physics_step"], 1)
        self.assertEqual(row["action_duration_s"], .02)
        self.assertEqual(row["segment_id"], 2)
        self.assertEqual(self.samples()[0]["kind"], "initial")

    def test_empty_and_omitted_commands_compare_held_targets(self):
        self.begin()
        self.tracking.tick(tick(1, q=.025))
        self.tracking.finish(transition(1))
        self.assertAlmostEqual(self.samples()[-1]["maxima"]["joint_rad/left"], .075)
        self.assertEqual(self.samples()[-1]["reference_status"], "reference_unavailable")

    def test_rejected_partial_and_no_pause_samples(self):
        self.begin({"bad": {}})
        self.tracking.finish()
        self.begin()
        self.tracking.tick(tick(1))
        self.tracking.finish()
        self.tracking.tick(tick(2))  # no current action: no fabricated sample
        report = self.tracking.report(self.key)
        self.assertEqual((report["rejected_attempts"], report["incomplete_attempts"], report["completed_samples"]), (1, 1, 0))

    def test_tcp_delta_uses_measured_before_and_world_rotation(self):
        robot = tick(q=.2)["robot"]
        goal = requested_tcp({"left": {"translation_world_m": [.3, 0, 0],
                                       "rotation_world_rad": [0, 0, np.pi/2]}}, robot, "EE_DELTA")["left"]
        np.testing.assert_allclose(goal["position_m"], [.5, 0, 0])
        np.testing.assert_allclose(goal["quaternion_wxyz"], [2**-.5, 0, 0, 2**-.5])
        absolute = requested_tcp({"left": {"position_world_m": [.7, 0, 0], "orientation_wxyz": [1, 0, 0, 0]}}, robot, "EE_ABS")
        self.assertEqual(absolute["left"]["position_m"][0], .7)

    def test_reference_frozen_for_action_and_relative_errors(self):
        ref = dict(plan_id="route-1", version=1, phase="hold", frame="world", units="m_wxyz",
            progress_used=.3, objects=dict(a=at(.1)), relative_targets=[dict(entity="b", reference="a", pose=at(.9))],
            clearances=dict(a=dict(geometry_id="fixture", clearance_m=.02, radius_m=.1)))
        self.begin(policy=SimpleNamespace(debug_reference=lambda: ref))
        ref["progress_used"] = .4
        self.tracking.tick(tick(1))
        self.tracking.finish(transition(1))
        sample = self.samples()[-1]
        self.assertEqual(sample["reference"]["progress_used"], .3)
        self.assertAlmostEqual(sample["maxima"]["relative_m/b@a"], .1)
        self.assertAlmostEqual(sample["maxima"]["clearance_excess_m/a"], .08)

    def test_bad_reference_does_not_suppress_robot_tracking(self):
        self.begin(policy=SimpleNamespace(debug_reference=lambda: {"frame": "wrong"}))
        self.tracking.tick(tick(1))
        self.tracking.finish(transition(1))
        self.assertTrue(self.samples()[-1]["reference_error"])
        self.assertEqual(self.tracking.report(self.key)["completed_samples"], 1)

    def test_rewind_preserves_old_branch_and_offline_valid_path(self):
        self.begin()
        self.tracking.tick(tick(1))
        self.tracking.finish(transition(1))
        self.tracking.rewind([0], dict(state_id=0, branch_id=1))
        folder = Path(self.tracking.report(self.key)["summary"]).parent
        self.assertEqual(read_tracking_report(folder)["completed_samples"], 1)
        self.assertEqual(read_tracking_report(folder, valid_only=True)["completed_samples"], 0)
        self.assertEqual(self.samples()[-1]["invalidated_attempts"], [1])

    def test_worker_loss_retains_committed_ticks_and_ignores_torn_tail(self):
        self.begin()
        self.tracking.tick(tick(1))
        folder = Path(self.tracking.report(self.key)["summary"]).parent
        with (folder / "samples.jsonl").open("a") as stream:
            stream.write('{"kind":')
        report = read_tracking_report(folder)
        self.assertEqual(report["incomplete_attempts"], 1)
        self.assertTrue(report["torn_tail_ignored"])

    def test_keyhole_reference_captures_before_generator_increment(self):
        from scipy.spatial.transform import Rotation
        from topogym.planning.calibration_tools.adapters.keyhole_reference import ReferenceMixin
        class Base:
            reference, plan = {}, None
            origins = {s: np.zeros(3) for s in ("left", "right")}
            assembly_rotations = {s: Rotation.identity() for s in origins}
            def follow_bodies(self, pose_at, seconds, phase, **kwargs):
                pose_at(.25)
                pose_at(.75)  # next target lookahead must not be labelled current
                yield {"action": 1}
                pose_at(.25)  # hold the same route point for a second control step
                yield {"action": 2}
        class Annotated(ReferenceMixin, Base): pass
        policy = Annotated()
        program = policy.follow_bodies(lambda p: {"left": (np.zeros(3), Rotation.identity()),
                    "right": (np.array([p, 0, 0]), Rotation.identity())}, 1., "route")
        self.assertEqual(next(program), {"action": 1})
        self.assertEqual(policy.debug_reference()["progress_used"], .25)
        self.assertEqual(next(program), {"action": 2})
        self.assertEqual(policy.debug_reference()["objects"]["keyhole_silver"]["position_m"][0], .25)

    def test_worker_wrapper_uses_previous_tick_and_does_not_change_action(self):
        from topogym.planning.calibration_tools.worker import BoundedPolicy, DevelopmentOwner
        owner = DevelopmentOwner.__new__(DevelopmentOwner)
        owner.tracking = self.tracking
        owner.profiler = SimpleNamespace(span=lambda *a, **k: nullcontext())
        owner.runner = SimpleNamespace(_last_tick=tick(), _active=7, _records={7: {"steps": [1, 2]}})
        owner.env = SimpleNamespace(action_spec={"mode": "EE_ABS"})
        action = {"left": {"position_world_m": [.1, 0, 0], "orientation_wxyz": [1, 0, 0, 0]}}
        policy = SimpleNamespace(act=lambda obs: action)
        wrapper = BoundedPolicy({"policy": policy}, 1, lambda: False, owner.before_action)
        self.assertIs(wrapper.act({}), action)
        self.assertEqual(self.tracking.pending["segment_id"], 7)
        self.assertEqual(self.tracking.pending["action_index"], 2)
        self.tracking.tick(tick(1))
        self.tracking.finish(transition(1))
        self.assertEqual(self.samples()[-1]["action"], action)


class FixtureAdapter:
    required_coverage = ("limits", "joins", "pieces")
    def __init__(self):
        self.current = dict(qpos=[0.], objects={"a": at()}, grasps={}, contacts=[])
        self.dependencies = dict(geometry="g", joints="j", execution="e")
        self.plans = self.repairs = 0
        self.missing_coverage = self.reject_repair = False
        self.validator_state_mutation = None
    def identity(self, request): return deepcopy(self.dependencies)
    def snapshot(self, request): return deepcopy(self.current)
    def validate(self, bundle):
        if self.validator_state_mutation: self.validator_state_mutation()
        return dict(passed=True, coverage=["limits"] if self.missing_coverage else list(self.required_coverage))
    def plan(self, request, seed=None):
        self.plans += 1
        return dict(identity=self.identity(request), start=self.snapshot(request), joint_names=["j"],
                    qpos=[self.current["qpos"], [.5]], request=deepcopy(request), coverage={})
    def repair(self, bundle, request):
        self.repairs += 1
        if self.reject_repair: raise ValueError("local budget exhausted")
        # Fixture mechanics, deliberately not a physics or solver stand-in.
        return dict(bundle, start=self.snapshot(request), qpos=[self.current["qpos"], [.5]])


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache, self.adapter = PlanCache(self.tmp.name), FixtureAdapter()
        self.state = dict(episode_id="one", state_id=0, branch_id=0)
        self.prep = PlanPreparation(self.cache, self.adapter, lambda: self.state)
        self.tolerance = dict(joint_rad=.01, object_m=.001, object_rad=.01, relative_m=.001,
                             relative_rad=.01, grasp_m=.001, grasp_rad=.01, source="fixture budget", repair_multiplier=3.)
        self.request = dict(route="route-1")
    def tearDown(self): self.tmp.cleanup()
    def prepare(self, **kwargs):
        return self.prep.prepare(self.request, tolerances=self.tolerance, **kwargs)

    def test_reuse_without_full_planning_and_bound_state(self):
        first, second = self.prepare(), self.prepare()
        self.assertEqual((first["selection"], second["selection"]), ("planned", "reused"))
        self.assertEqual(self.adapter.plans, 1)
        self.assertEqual(first["plan_id"], second["plan_id"])
        self.assertEqual(second["bound_state"], self.state)
        self.assertNotIn("plan_s", second["timings"])

    def test_small_shift_repairs_and_checks_same_coverage(self):
        first = self.prepare()
        self.adapter.current["qpos"] = [.02]
        second = self.prepare()
        self.assertEqual(second["selection"], "repaired")
        self.assertEqual(self.adapter.plans, 1)
        self.assertEqual(second["plan"]["coverage"]["coverage"], first["plan"]["coverage"]["coverage"])
        self.assertNotEqual(first["plan_id"], second["plan_id"])

    def test_local_repair_failure_falls_back_to_full_planning(self):
        self.prepare()
        self.adapter.current["qpos"] = [.02]
        self.adapter.reject_repair = True
        result = self.prepare()
        self.assertEqual(result["selection"], "planned")
        self.assertEqual((self.adapter.repairs, self.adapter.plans), (1, 2))
        self.assertIn("repair_error", result["attempts"][0])

    def test_assets_robot_and_execution_dependencies(self):
        first = self.prepare()
        for layer, expected in (("geometry", "miss"), ("joints", "miss"), ("execution", "seed_only")):
            old = self.adapter.dependencies[layer]
            self.adapter.dependencies[layer] = "changed"
            self.assertEqual(self.prep.check(first["plan_id"], self.tolerance)["decision"], expected)
            self.adapter.dependencies[layer] = old

    def test_missing_validation_never_grants_reuse(self):
        first = self.prepare()
        self.adapter.missing_coverage = True
        self.assertEqual(self.prep.check(first["plan_id"], self.tolerance)["decision"], "seed_only")
        with self.assertRaises(ValueError): self.prepare()

    def test_contacts_or_large_start_delta_require_full_plan(self):
        first = self.prepare()
        self.adapter.current["contacts"] = ["new contact"]
        self.assertEqual(self.prep.check(first["plan_id"], self.tolerance)["decision"], "miss")
        self.adapter.current["contacts"] = []
        self.adapter.current["objects"]["a"] = at(.1)
        self.assertEqual(self.prepare()["selection"], "planned")

    def test_corrupt_bytes_are_miss_and_preserved_on_regeneration(self):
        first = self.prepare()
        path = self.cache.root / first["plan_id"] / "arrays.npz"
        path.write_bytes(b"damaged")
        self.assertEqual(self.prep.check(first["plan_id"], self.tolerance)["decision"], "miss")
        repaired = self.prepare()
        self.assertEqual(repaired["selection"], "planned")
        self.assertTrue(list(self.cache.root.glob(".corrupt-*")))
        self.cache.get(repaired["plan_id"])

    def test_parallel_equal_content_has_one_valid_entry(self):
        bundle = self.adapter.plan(self.request)
        with ThreadPoolExecutor(max_workers=4) as executor:
            values = list(executor.map(lambda _: self.cache.put(bundle), range(8)))
        self.assertEqual(len({v["plan_id"] for v in values}), 1)
        self.cache.get(values[0]["plan_id"])

    def test_nonfinite_and_pickle_payloads_not_accepted(self):
        bundle = self.adapter.plan(self.request)
        bundle["qpos"] = [[float("nan")]]
        with self.assertRaises(ValueError): self.cache.put(bundle)
        with self.assertRaises(CacheMiss): self.cache.get("../escape")

    def test_state_mutation_during_validation_invalidates_decision(self):
        first = self.prepare()
        self.adapter.validator_state_mutation = lambda: self.state.update(state_id=1)
        result = self.prep.check(first["plan_id"], self.tolerance)
        self.assertEqual(result["decision"], "miss")
        self.assertIn("state_changed_during_check", result["reasons"])

    def test_cache_disabled_plans_again_and_cancellation(self):
        self.prepare()
        self.assertEqual(self.prepare(use_cache=False)["selection"], "planned")
        self.prep.cancelled = lambda: True
        with self.assertRaises(InterruptedError): self.prepare()

    def test_planner_cannot_return_an_old_start_or_different_request(self):
        old = self.adapter.plan(self.request)
        self.adapter.current["qpos"] = [.2]
        self.adapter.plan = lambda request, seed=None: old
        with self.assertRaisesRegex(ValueError, "measured snapshot"):
            self.prepare(use_cache=False)
        self.adapter.current["qpos"] = [0.]
        old["request"] = {"route": "another"}
        with self.assertRaisesRegex(ValueError, "different request"):
            self.prepare(use_cache=False)

    def test_joint_and_finger_sampling_and_budget(self):
        values, indices = densify([[0., 0.], [.1, .01]], np.array([.025, .001]))
        self.assertEqual(indices, [0, 10])
        self.assertLessEqual(np.max(np.diff(np.asarray(values), axis=0)[:, 1]), .001+1e-12)
        with self.assertRaises(ValueError): densify([[0.], [1.]], np.array([.01]), maximum=10)


if __name__ == "__main__":
    unittest.main()
