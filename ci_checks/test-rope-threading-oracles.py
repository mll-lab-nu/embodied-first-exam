#!/usr/bin/env python3
"""Wang relay integration contracts; synthetic observations, no physics claim."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.rope_threading.profiles import candidate_plans, ASSIGNMENT
from topogym.planning.rope_threading.relay_artifact import load_plan, save_samples, validate_scene
from topogym.planning.rope_threading.relay_policy import RopeRelayPolicy
from topogym.planning.rope_threading.object_oracle import Track
from scripts.oracle_runners.run_rope_threading_relay import completion_status


def sample(phase="transit:A:R1/via_home", side="right", position=(.01, 0., 0.), angle=0.):
    quat = Rotation.from_rotvec([0., 0., angle]).as_quat()[[3, 0, 1, 2]]
    return dict(phase=phase, side=side, sigma=0., station=np.array([0., 0., 0., .9]),
                qpos=np.r_[position, 0., 0., angle, np.zeros(10)],
                tcp_left=np.r_[position, quat, .03], tcp_right=np.r_[position, quat, .03])


class LinearKinematics:
    """Test double: arm joints are the TCP position and rotation vector, so joint and TCP interpolation agree."""
    def __init__(self):
        self.seeds = []

    def planned(self, qpos, side):
        return np.asarray(qpos, float)[:6]

    def solve(self, side, p, r, qpos):
        self.seeds.append(np.asarray(qpos, float))
        return np.r_[p, r.as_rotvec()]


def relay(samples, **options):
    return RopeRelayPolicy(samples, kinematics=LinearKinematics(), **options)


def observation():
    return dict(robot={s: dict(joint_position_rad=[0.]*6, tcp_position_world_m=[0., 0., 0.],
                               tcp_orientation_wxyz=[1., 0., 0., 0.]) for s in ("left", "right")},
                privileged=dict(world=dict(fem=dict(rope=dict(material_s_m=[.9], position_m=[[0., 0., 0.]])),
                    grasp=dict(hands={s: dict(binding=None, phase="idle", solved_ticks=0) for s in ("left", "right")}))))


class ProfileTests(unittest.TestCase):
    def test_contact_allowance_matches_native_and_planner_apertures(self):
        from topogym.tasks.rope_threading.common import RopeThreadingTask, usable_rope_aperture_radius
        from topogym.planning.rope_threading.geometry import task_like_evaluation
        ring = dict(name="R1", center_m=[0., 0., 0.], center_world_m=[0., 0., 0.],
                    normal=[1., 0., 0.], radius_m=.025, tube_radius_m=.003)
        points = np.array([[-.02, .0184, 0.], [.02, .0184, 0.]])
        terminal = dict(maximum_speed_m_s=.001, aperture_margin_m=.0001)
        layout = SimpleNamespace(rope_radius_m=.004, rings=lambda: [ring], required_crossings=lambda: [("R1", 1)])
        state = dict(fem=dict(rope=dict(position_m=points, velocity_m_s=points*0)),
                     bodies=dict(R1=dict(position_m=[0., 0., 0.], quaternion_wxyz=[1., 0., 0., 0.])),
                     ipc=dict(native_valid=True, volume_ratio=dict(rope=dict(minimum=1., maximum=1.)), attachment_residual_m={}))
        slanted = np.array([[-.01, .0164+.01*2/3, 0.], [.01, .0164-.01*2/3, 0.]])
        cases = [(points, 0., "cylindrical", False), (points, .001, "cylindrical", True),
                 (slanted, 0., "cylindrical", False), (slanted, 0., "round_ring", True),
                 (points, 0., "round_ring", False)]  # Round rims do not enlarge the middle aperture.
        for polyline, allowance, profile, expected in cases:
            parameters = dict(aperture_contact_allowance_m=allowance, aperture_check_profile=profile)
            task = RopeThreadingTask(config=parameters)
            task.layout, task.centerline_map = layout, (None, None)
            problem = SimpleNamespace(layout=layout, rings=[ring], required=[("R1", 1)],
                identity=dict(terminal=terminal, task_parameters=parameters))
            with patch("topogym.tasks.rope_threading.common.sample_material_centerline", return_value=polyline):
                native = task.evaluate_state(state)
            planned = task_like_evaluation(polyline, problem)
            self.assertEqual(native[0], expected)
            self.assertEqual(planned["sequence_matches"], expected)
            self.assertEqual(native[2]["crossing_sequence"], planned["crossing_sequence"])
        for bad in (-.001, .0021, float("nan"), True):
            with self.assertRaises(ValueError):
                usable_rope_aperture_radius(ring, .004, terminal, bad)

    def test_exact_selected_plans_and_distinct_hard_defaults(self):
        expected = dict(easy=("A10_B_pull19_B20_recvA", 2, .20, .06),
                        medium=("A10_B_pull19_B24_keep_recvA5", 3, .24, .05),
                        hard=("A10_B_pull19_B24_keep_recvA5", 3, .24, .05))
        for tier, (name, n, station, poke) in expected.items():
            with self.subTest(tier=tier):
                actual, plan = candidate_plans("rope_threading_"+tier)[0]
                self.assertEqual(actual, name)
                self.assertEqual(len(plan), n)
                self.assertEqual(plan[0]["pull_m"], .19)
                self.assertEqual(plan[1]["pusher_station_m"], station)
                self.assertEqual(plan[-1]["poke_m"], poke)
                self.assertEqual(plan[-1]["receiver"], "A")
                self.assertEqual(ASSIGNMENT, dict(A="right", B="left"))
                if n == 3:
                    self.assertIsNone(plan[1]["receiver"])
                    self.assertEqual(plan[1]["pull_m"], 0.)

    def test_simplified_tasks_do_not_silently_select_a_three_ring_recipe(self):
        for tier in ("very_easy", "easier", "base", "unknown"):
            with self.assertRaises(ValueError):
                candidate_plans(tier)

    def test_recipes_are_independent_on_each_call(self):
        candidate_plans("hard")[0][1][0]["pull_m"] = 10.
        self.assertEqual(candidate_plans("hard")[0][1][0]["pull_m"], .19)


class ArtifactTests(unittest.TestCase):
    def test_leading_hold_reuse_requires_exact_endpoint_and_complete_source(self):
        from topogym.planning.rope_threading.relay_artifact import leading_holds
        samples = [sample("pinch:A:R1"), sample("hold:A:R1"), sample("retreat:A/up")]
        samples[1]["sigma"] = .1
        holds = [dict(hand="A", ring="R1", role="pusher", sigma_start=0., sigma_end=.1, station_m=.9)]
        self.assertEqual(len(leading_holds(samples, dict(complete_relay=True), holds, ASSIGNMENT)), 2)
        with self.assertRaisesRegex(ValueError, "complete source"):
            leading_holds(samples, dict(complete_relay=False), holds, ASSIGNMENT)
        holds[0]["sigma_end"] = .11
        with self.assertRaisesRegex(ValueError, "exact final"):
            leading_holds(samples, dict(complete_relay=True), holds, ASSIGNMENT)

    def test_rechecked_cache_cannot_drop_a_required_keeper(self):
        from topogym.planning.rope_threading.relay_artifact import validate_hold_timeline
        holds = [dict(hand="A", ring="R2_keeper", role="keeper", sigma_start=0., station_m=.9),
                 dict(hand="B", ring="R2", role="pusher", sigma_start=0., station_m=.9)]
        samples = [sample("pinch:A:R2_keeper"), sample("pinch:B:R2", side="left")]
        validate_hold_timeline(samples, holds, ASSIGNMENT)
        with self.assertRaisesRegex(ValueError, "timeline"):
            validate_hold_timeline(samples[1:], holds, ASSIGNMENT)
        samples[0]["station"][3] = .8
        with self.assertRaisesRegex(ValueError, "timeline"):
            validate_hold_timeline(samples, holds, ASSIGNMENT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"samples.npz"
        self.identity = dict(task_id="rope_threading", variation_id="rope_threading_easy", seed=0,
                             rope_length_m=1., model_revision="test", terminal_revision="test", instance_id="test")
        kin = SimpleNamespace(home=np.zeros(16),
            robot=SimpleNamespace(_q_indices=dict(left=list(range(8)), right=list(range(8, 16)))),
            tcp_pose=lambda q, side: (np.zeros(3), Rotation.identity()))
        track = Track([[0., 0., 0.], [1., 0., 0.]], [[1., 0., 0.], [2., 0., 0.]])
        holds = [dict(hand="A", ring="R1", sigma_start=0., sigma_end=.1, station_m=.9)]
        samples = [dict(phase="transit:A:R1/via_home", sigma=0., q=np.zeros(16)),
                   dict(phase="park:A/fold_then_turn", sigma=.1, q=np.zeros(16))]
        save_samples(self.path, samples, kin=kin, track=track, holds=holds, identity=self.identity,
                     plan="test", assignment=ASSIGNMENT, options={})

    def rewrite(self, key, value):
        with np.load(self.path) as data:
            arrays = {k: data[k] for k in data.files}
        arrays[key] = value
        np.savez_compressed(self.path, **arrays)

    def test_suffix_phases_round_trip_with_correct_arm(self):
        rows, meta = load_plan(self.path, variant="easy", seed=0)
        self.assertEqual([r["side"] for r in rows], ["right", "right"])
        self.assertTrue(np.isnan(rows[1]["station"]).all())
        self.assertEqual(rows[0]["station"][3], .9)
        self.assertFalse(meta["robot_execution_verified"])
        self.assertFalse(meta["task_success"])

    def test_tier_seed_and_legacy_artifacts_are_rejected(self):
        for args in (dict(variant="hard"), dict(seed=1)):
            with self.assertRaises(ValueError):
                load_plan(self.path, **args)
        np.savez(self.path, sigma=[0.])
        with self.assertRaisesRegex(ValueError, "regenerate"):
            load_plan(self.path)

    def test_partial_probe_requires_explicit_runner_flag(self):
        import subprocess
        _, meta = load_plan(self.path)
        meta["complete_relay"] = False
        self.rewrite("metadata_json", json.dumps(meta))
        output = Path(self.tmp.name)/"execution"
        result = subprocess.run([sys.executable, str(ROOT/"scripts/oracle_runners/run_rope_threading_relay.py"),
            "--variant", "easy", "--samples", str(self.path), "--output", str(output)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("partial relay probe", result.stderr)
        self.assertFalse(output.exists())

    def test_side_mismatch_is_rejected(self):
        self.rewrite("side", np.array(["left", "right"]))
        with self.assertRaisesRegex(ValueError, "phase/side"):
            load_plan(self.path)

    def test_nonmoving_holder_cannot_teleport_at_pinch(self):
        q = np.zeros((2, 16))
        q[1, 0] = .4  # Both samples name right; left must remain at its previous pose.
        self.rewrite("qpos", q)
        with self.assertRaisesRegex(ValueError, "inactive arm jumps"):
            load_plan(self.path)



    def test_invalid_motion_and_station_are_rejected(self):
        for key, value in (("sigma", [.1, 0.]), ("qpos", np.full((2, 16), np.nan)),
                           ("station", np.full((2, 4), np.nan))):
            with self.subTest(key=key):
                original = self.path.read_bytes()
                self.rewrite(key, value)
                with self.assertRaises(ValueError):
                    load_plan(self.path)
                self.path.write_bytes(original)

    def test_scene_validation_rejects_model_revision_before_robot_access(self):
        _, meta = load_plan(self.path)
        task = SimpleNamespace(**self.identity)
        task.model_revision = "changed"
        with self.assertRaisesRegex(ValueError, "model_revision"):
            validate_scene(meta, task=task, scene=None, home_qpos=[], asset_dir=self.tmp.name)


class BranchTests(unittest.TestCase):
    def test_relaxed_contact_depth_uses_metres_and_handles_managers(self):
        import fcl
        from topogym.planning.rope_threading.relay_kinematics import contact_depth
        from topogym.planning.buzz_wire_3d.kinematics import manager
        first = fcl.CollisionObject(fcl.Box(.1, .1, .1))
        second = fcl.CollisionObject(fcl.Box(.1, .1, .1), fcl.Transform([.098, 0., 0.]))
        self.assertAlmostEqual(contact_depth(first, second), .002)
        self.assertAlmostEqual(contact_depth(manager([first]), manager([second])), .002)
        second.setTranslation(np.array([.2, 0., 0.]))
        self.assertEqual(contact_depth(first, second), float("inf"))

    def test_partial_planner_status_survives_report_wrapper(self):
        from topogym.planning.rope_threading.relay_ik import plan_relay_ik
        planner = SimpleNamespace(o={}, samples=[], stays=[], kin=SimpleNamespace(pad_offset={}),
            plan=lambda: dict(passed=True, complete_relay=False, phases=[]))
        with patch("topogym.planning.rope_threading.relay_ik.RelayPlanner", return_value=planner):
            result, _ = plan_relay_ik(None, {}, assignment=ASSIGNMENT, holds=[], track=object())
        self.assertTrue(result["passed"])
        self.assertFalse(result["complete_relay"])

    def test_material_direction_transport_including_half_turn(self):
        from topogym.planning.rope_threading.relay_kinematics import track_material_orientation
        rotation = Rotation.from_euler("xyz", [.2, -.3, .5])
        for family, axis in (("across", [0, 0, 1]), ("along", [-1, 0, 0]), ("along_lead", [1, 0, 0])):
            for target in (rotation.apply(axis), -rotation.apply(axis), np.array([0., 1., 0.])):
                transported = track_material_orientation(rotation, target, family)
                np.testing.assert_allclose(transported.apply(axis), target, atol=1e-10)
                self.assertAlmostEqual(float(transported.apply([0, 1, 0])@target), 0., places=10)

    def test_home_branch_seed_preserves_the_other_arm_and_gripper(self):
        from topogym.planning.rope_threading.relay_ik import RelayPlanner
        planner = RelayPlanner.__new__(RelayPlanner)
        planner.o, planner.rng = dict(branch_seeds=0), np.random.default_rng(0)
        planner.kin = SimpleNamespace(home=np.zeros(16), limits=dict(right=np.tile([-3., 3.], (6, 1))),
            robot=SimpleNamespace(_q_indices=dict(right=list(range(8, 16))),
                _indices=dict(right=list(range(8, 16))), groups=dict(right=SimpleNamespace(hand_link="right"))),
            solve=lambda side, pose, seed, **kwargs: np.array(seed),
            hand_target=lambda side, pose: pose,
            ik=SimpleNamespace(solve_checked=lambda **kw: kw["initial_qpos"]))
        seed = np.full(16, .7)
        candidates = planner.branches("right", (np.zeros(3), Rotation.identity()), seed)
        self.assertEqual(len(candidates), 2)
        for candidate in candidates:
            np.testing.assert_array_equal(candidate[:8], seed[:8])
            np.testing.assert_array_equal(candidate[14:], seed[14:])


    def test_short_joint_detour_clears_obstacle_without_moving_holder(self):
        from topogym.planning.rope_threading.relay_ik import RelayPlanner, DEFAULT_OPTIONS
        planner = RelayPlanner.__new__(RelayPlanner)
        planner.o = dict(DEFAULT_OPTIONS)
        planner.q = np.r_[np.full(8, .7), np.zeros(8)]
        planner.kin = SimpleNamespace(robot=SimpleNamespace(_q_indices=dict(right=list(range(8, 16)))),
                                     limits=dict(right=np.tile([-3., 3.], (6, 1))))
        def check(q, holding):
            blocked = .4 <= q[8] <= .6 and q[9] > -.15
            return dict(passed=not blocked, issues=["barrier"] if blocked else [])
        planner.check = check
        target = planner.q.copy();target[8] = 1.
        rows = []
        q, checks = planner.transit("right", target, holding={"left"}, phase="transit:test", sigma=0., record=rows)
        np.testing.assert_allclose(q[8:14], target[8:14])
        self.assertTrue(rows)
        self.assertTrue(all(row["phase"].endswith("/detour") for row in rows))
        self.assertTrue(all(item["passed"] for item in checks))
        for row in rows:
            np.testing.assert_array_equal(row["q"][:8], planner.q[:8])
            self.assertTrue(check(row["q"], {"left"})["passed"])


class PolicyTests(unittest.TestCase):
    def test_replanned_hold_preserves_source_tcp_path_and_grasp_wait(self):
        rows = [sample("transit:A:R2"), sample("pinch:A:R2"),
                sample("hold:A:R2", position=(.02, 0., 0.)), sample("hold:A:R2", position=(.03, 0., 0.)),
                sample("retreat:A/tool")]
        before = deepcopy(rows)
        received = []
        def planner(*args, **kwargs):
            received.extend(kwargs["follow_targets"])
            return dict(passed=True, rows=[dict(phase="pinch:measured_keeper")],
                        follow_rows=[dict(index=i, qpos=np.full(16, .1*i)) for i in (2, 3)])
        policy = relay(rows, keeper_planner=planner, measured_regrasps=True)
        obs = observation()
        obs["privileged"]["world"]["grasp"]["hands"]["left"].update(
            binding=dict(target=["rope", 1]), phase="holding", solved_ticks=1)
        policy.expected_holders = {"left"}
        policy.act(obs)
        self.assertEqual([row["index"] for row in received], [2, 3])
        self.assertEqual(policy.waiting[:2], ("acquire", "right"))
        self.assertEqual(policy.expected_holders, {"left"})
        for i in (2, 3):
            np.testing.assert_array_equal(rows[i]["qpos"], before[i]["qpos"])
            np.testing.assert_array_equal(policy.samples[i]["tcp_right"], before[i]["tcp_right"])
            np.testing.assert_array_equal(policy.samples[i]["qpos"], np.full(16, .1*i))

    def test_partial_branch_replan_is_rejected_before_acquisition(self):
        rows = [sample("transit:A:R2"), sample("pinch:A:R2"), sample("hold:A:R2"), sample("hold:A:R2")]
        policy = relay(rows, keeper_planner=lambda *a, **kw: dict(passed=True,
            rows=[dict(phase="pinch:measured_keeper")], follow_rows=[dict(index=2, qpos=np.zeros(16))]),
            measured_regrasps=True)
        obs = observation()
        obs["privileged"]["world"]["grasp"]["hands"]["left"].update(
            binding=dict(target=["rope", 1]), phase="holding", solved_ticks=1)
        policy.expected_holders = {"left"}
        with self.assertRaisesRegex(ValueError, "complete upcoming hold"):
            policy.act(obs)
        self.assertIsNone(policy.repair)
        self.assertIsNone(policy.waiting)
        self.assertEqual(policy.expected_holders, {"left"})

    def test_later_regrasp_uses_calibration_before_translation_limit(self):
        rows = [sample("transit:A:R2"), sample("pinch:A:R2"), sample("hold:A:R2")]
        calls = []
        def planner(*args, **kwargs):
            calls.append(kwargs)
            return dict(passed=True, rows=[dict(phase="pinch:measured_keeper")])
        policy = relay(rows, keeper_planner=planner, measured_regrasps=True)
        obs = observation()
        obs["privileged"]["world"]["fem"]["rope"]["position_m"] = [[.15, 0., 0.]]
        obs["privileged"]["world"]["grasp"]["hands"]["left"].update(
            binding=dict(target=["rope", 1]), phase="holding", solved_ticks=1)
        policy.expected_holders = {"left"}
        action = policy.act(obs)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["normalize_target"]["phase"], "pinch:A:R2")
        self.assertEqual(policy.index, 2)  # Keep the full post-acquisition hold.
        self.assertEqual(policy.waiting[:2], ("acquire", "right"))

    def test_keeper_shape_motion_waits_for_health_and_keeps_both_grasps(self):
        rows = [sample("transit:A:R2_keeper"), sample("pinch:A:R2_keeper"), sample("retreat:B/tool", "left")]
        def planner(*args, **kwargs):
            return dict(passed=True, rows=[dict(phase="pinch:measured_keeper"),
                dict(phase="hold:measured_keeper/shape", q=np.r_[.01, np.zeros(15)], tcp=[.01, 0, 0, 1, 0, 0, 0])])
        policy = relay(rows, keeper_planner=planner, control_dt_s=.1, speed_m_s=1.)
        obs = observation()
        hands = obs["privileged"]["world"]["grasp"]["hands"]
        hands["left"].update(binding=dict(target=["rope", 1]), phase="holding", solved_ticks=1)
        policy.targets = {s: (np.zeros(6), np.zeros(3), Rotation.identity(), policy.pinch)
                          for s in ("left", "right")}
        policy.expected_holders = {"left"}
        policy.act(obs)
        self.assertEqual(policy.index, 0)
        policy.act(obs)
        self.assertEqual(policy.index, 0)  # No shape motion before actual acquisition.
        hands["right"].update(binding=dict(target=["rope", 2]), phase="holding", solved_ticks=1)
        action = policy.act(obs)
        self.assertEqual(policy.index, 2)
        for side in ("left", "right"):
            self.assertEqual(action[side]["gripper_position_m"], policy.pinch)
        self.assertAlmostEqual(action["right"]["joint_position_rad"][0], .01)
        action = policy.act(obs)
        self.assertEqual(action["left"]["gripper_position_m"], policy.free)

    def test_measured_keeper_preserves_holder_until_native_acquisition(self):
        rows = [sample("transit:A:R2_keeper"), sample("approach:A:R2_keeper"),
                sample("pinch:A:R2_keeper"), sample("retreat:B/tool", "left")]
        calls = []
        def planner(obs, row, targets, **kwargs):
            calls.append(kwargs)
            return dict(passed=True, rows=[dict(phase="approach:measured_keeper", q=np.zeros(16),
                tcp=[0, 0, 0, 1, 0, 0, 0]), dict(phase="pinch:measured_keeper")])
        policy = relay(rows, keeper_planner=planner, control_dt_s=.1)
        obs = observation()
        # This offset would fail the ordinary 8 cm translation feedback.
        obs["privileged"]["world"]["fem"]["rope"]["position_m"] = [[.15, 0., 0.]]
        hands = obs["privileged"]["world"]["grasp"]["hands"]
        hands["left"].update(binding=dict(target=["rope", 1]), phase="holding", solved_ticks=1)
        policy.expected_holders = {"left"}
        policy.targets = {s: (np.zeros(6), np.zeros(3), Rotation.identity(), policy.pinch if s == "left" else policy.free)
                          for s in ("left", "right")}
        action = policy.act(obs)
        self.assertEqual(action["left"]["gripper_position_m"], policy.pinch)
        policy.act(obs)  # helper closes, original keeper block is skipped
        self.assertEqual(policy.index, 3)
        self.assertEqual(policy.waiting[:2], ("acquire", "right"))
        hands["right"].update(binding=dict(target=["rope", 2]), phase="registered", solved_ticks=0)
        action = policy.act(obs)
        self.assertEqual(action["left"]["gripper_position_m"], policy.pinch)
        self.assertEqual(policy.index, 3)
        hands["right"].update(phase="holding", solved_ticks=1)
        action = policy.act(obs)
        self.assertEqual(action["left"]["gripper_position_m"], policy.free)
        self.assertEqual(policy.expected_holders, {"right"})
        self.assertEqual(len(calls), 1)

    def test_failed_measured_keeper_does_not_release_existing_holder(self):
        policy = relay([sample("transit:A:R2_keeper"), sample("pinch:A:R2_keeper")],
            keeper_planner=lambda *a, **kw: dict(passed=False, failures=["collision"]))
        with self.assertRaisesRegex(ValueError, "collision-checked"):
            policy.act(observation())
        self.assertEqual(policy.index, 0)
        self.assertFalse(policy.done)

    def test_measured_material_direction_rotates_approach_about_rope_station(self):
        row = sample(phase="approach:A:R1")
        row["station_tangent"] = np.array([1., 0., 0.])
        obs = observation()
        direction = np.array([np.cos(.4), np.sin(.4), 0.])
        obs["privileged"]["world"]["fem"]["rope"] = dict(material_s_m=[.89, .9, .91],
            position_m=np.array([-.01*direction, np.zeros(3), .01*direction]))
        policy = relay([row], material_feedback=True)
        while policy.index == 0:
            policy.act(obs)
        _, p, r, _ = policy.targets["right"]
        np.testing.assert_allclose(r.apply([1., 0., 0.]), direction, atol=1e-9)
        np.testing.assert_allclose(p+r.apply([-.01, 0., 0.]), np.zeros(3), atol=1e-9)
        self.assertAlmostEqual(policy.tracking["material_feedback_rad"]["right"], .4)
        p, r = policy._feedback_pose(row, "right", 0.)
        np.testing.assert_allclose(p, [.01, 0., 0.])
        self.assertAlmostEqual(r.magnitude(), 0.)
        with self.assertRaisesRegex(ValueError, "station_tangent"):
            relay([sample()], material_feedback=True)

    def test_large_rope_deviation_is_not_clipped_to_an_unreachable_grasp(self):
        obs = observation()
        obs["privileged"]["world"]["fem"]["rope"]["position_m"] = [[.14, 0., 0.]]
        policy = relay([sample()])
        with self.assertRaisesRegex(ValueError, "feedback limit"):
            policy.act(obs)
        self.assertEqual(policy.tracking["failures"][-1]["kind"], "station_out_of_range")

    def test_translation_uses_fixed_start_and_respects_speed(self):
        policy = relay([sample(position=(.1, 0., 0.))], speed_m_s=.1, control_dt_s=.1)
        obs = observation()
        positions = [policy.act(obs)["right"]["joint_position_rad"][0] for _ in range(10)]
        np.testing.assert_allclose(positions, np.linspace(.01, .1, 10))

    def test_rotation_in_place_is_interpolated(self):
        policy = relay([sample(position=(0., 0., 0.), angle=.8)], control_dt_s=.1, angular_speed_rad_s=.8)
        angles = [np.linalg.norm(policy.act(observation())["right"]["joint_position_rad"][3:]) for _ in range(10)]
        np.testing.assert_allclose(angles, np.linspace(.08, .8, 10))

    def test_joint_reconfiguration_is_bounded_even_when_tcp_does_not_move(self):
        row = sample(position=(0., 0., 0.))
        row["qpos"][3] = .8
        policy = relay([row], control_dt_s=.1, joint_speed_rad_s=.8)
        angles = [policy.act(observation())["right"]["joint_position_rad"][3] for _ in range(10)]
        np.testing.assert_allclose(angles, np.linspace(.08, .8, 10))

    def test_planned_joints_are_replayed_and_measured_shift_is_seeded_on_them(self):
        shifted = observation()
        shifted["privileged"]["world"]["fem"]["rope"]["position_m"] = [[.002, 0., 0.]]
        policy = relay([sample(position=(.01, 0., 0.))], speed_m_s=1., control_dt_s=.1)
        np.testing.assert_allclose(policy.act(shifted)["right"]["joint_position_rad"], [.01, 0, 0, 0, 0, 0])
        self.assertEqual(policy.kin.seeds, [])          # transit replays the planned joints even when shifted
        policy = relay([sample("approach:A:R1", position=(.01, 0., 0.))], speed_m_s=1., control_dt_s=.1)
        np.testing.assert_allclose(policy.act(shifted)["right"]["joint_position_rad"], [.012, 0, 0, 0, 0, 0])
        np.testing.assert_allclose(policy.kin.seeds[-1], sample(position=(.01, 0., 0.))["qpos"])

    def test_registered_grasp_waits_for_native_solve_then_lost_grasp_stops(self):
        policy = relay([sample("pinch:A:R1"), sample("hold:A:R1")], control_dt_s=.1)
        obs = observation()
        policy.act(obs)
        hand = obs["privileged"]["world"]["grasp"]["hands"]["right"]
        hand.update(binding=dict(target=["rope", 42]), phase="registered", solved_ticks=0)
        policy.act(obs)
        self.assertEqual(policy.waiting[0], "acquire")
        hand.update(phase="holding", solved_ticks=1)
        policy.act(obs)
        self.assertIsNone(policy.waiting)
        self.assertIn("right", policy.expected_holders)
        hand.update(binding=None, phase="lost")
        with self.assertRaisesRegex(RuntimeError, "grasp lost"):
            policy.act(obs)

    def test_release_waits_for_unbinding_before_retreat(self):
        policy = relay([sample("retreat:A/up")], control_dt_s=.1)
        policy.targets = {s: (np.zeros(6), np.zeros(3), Rotation.identity(), policy.pinch) for s in ("left", "right")}
        policy.expected_holders = {"right"}
        obs = observation()
        hand = obs["privileged"]["world"]["grasp"]["hands"]["right"]
        hand.update(binding=dict(target=["rope", 42]), phase="holding", solved_ticks=1)
        action = policy.act(obs)
        self.assertEqual(action["right"]["gripper_position_m"], policy.free)
        np.testing.assert_allclose(action["right"]["joint_position_rad"], 0.)
        self.assertEqual(policy.waiting[0], "release")
        hand.update(binding=None, phase="idle")
        policy.act(obs)
        self.assertIsNone(policy.waiting)

    def test_acquisition_timeout_is_not_policy_success(self):
        policy = relay([sample("pinch:A:R1")], control_dt_s=.1, acquire_wait_s=.1)
        policy.act(observation())
        policy.act(observation())
        with self.assertRaisesRegex(RuntimeError, "did not acquire"):
            policy.act(observation())
        self.assertFalse(policy.done)

    def test_narrow_release_is_retained_until_checked_park(self):
        row = sample("retreat:A/tool")
        row["tcp_right"][7] = .017
        policy = relay([row], control_dt_s=.1)
        policy.targets = {s: (np.zeros(6), np.zeros(3), Rotation.identity(), policy.pinch)
                          for s in ("left", "right")}
        policy.expected_holders = {"right"}
        obs = observation()
        hand = obs["privileged"]["world"]["grasp"]["hands"]["right"]
        hand.update(binding=dict(target=["rope", 42]), phase="holding", solved_ticks=1)
        self.assertEqual(policy.act(obs)["right"]["gripper_position_m"], .017)
        hand.update(binding=None, phase="idle")
        self.assertEqual(policy.act(obs)["right"]["gripper_position_m"], .017)
        self.assertIsNone(policy.waiting)

    def test_receiver_motion_keeps_sender_pinched(self):
        policy = relay([sample("approach:B:R2", "left")], control_dt_s=.1)
        policy.targets = {s: (np.zeros(6), np.zeros(3), Rotation.identity(), policy.pinch) for s in ("left", "right")}
        self.assertEqual(policy.act(observation())["right"]["gripper_position_m"], policy.pinch)

    def test_final_grasp_is_retained_for_native_quiet_window(self):
        policy = relay([sample("hold:A:R2", position=(0., 0., 0.)), sample("retreat:A/tool")], control_dt_s=.1)
        obs = observation()
        obs["privileged"]["world"]["grasp"]["hands"]["right"].update(
            binding=dict(target=["rope", 42]), phase="holding", solved_ticks=1)
        policy.expected_holders = {"right"}
        policy.act(obs)
        action = policy.act(obs)
        self.assertEqual(action["right"]["gripper_position_m"], policy.pinch)
        self.assertEqual(policy.phase, "settle:held")
        self.assertFalse(policy.done)


class DiagnosticTests(unittest.TestCase):
    def test_measured_retreat_does_not_serialize_nan_material_markers(self):
        from topogym.planning.calibration_tools.adapters.rope_threading import MeasuredKeeperPlanner
        with tempfile.TemporaryDirectory() as folder:
            planner = MeasuredKeeperPlanner(folder, dict(home_qpos=[0.]*16))
            row, target = sample("retreat:A/tool"), sample("park:A/raise")
            for item in (row, target):
                item["station"][:] = np.nan
                item["station_tangent"] = [np.nan]*3
            targets = {side: (np.zeros(6), np.zeros(3), Rotation.identity(), .03) for side in ("left", "right")}
            def worker(command, **kwargs):
                directory = Path(command[-1])
                payload = json.loads((directory/"input.json").read_text())
                self.assertNotIn("station", payload["sample"])
                self.assertNotIn("station", payload["retreat_target"])
                self.assertEqual(payload["retreat_target"]["phase"], "park:A/raise")
                (directory/"result.json").write_text(json.dumps(dict(passed=True, rows=[])))
                return SimpleNamespace(returncode=0)
            with patch("subprocess.run", side_effect=worker):
                result = planner(observation(), row, targets, retreat_target=target)
            self.assertTrue(result["passed"])

    def test_side_grasp_may_disable_only_the_gravity_up_exposure_gate(self):
        import trimesh
        from dataclasses import replace
        from topogym.utils.grasp import SoftGraspTarget, GraspAssistConfig
        from topogym.world.physics.grasp_soft import SoftGraspBackend
        backend = SoftGraspBackend.__new__(SoftGraspBackend)
        backend.specs = dict(rope=SoftGraspTarget("rope"))
        backend.material = dict(rope=np.array([[0.], [.004], [.008]]))
        backend.config = GraspAssistConfig()
        backend.robot = SimpleNamespace(groups=dict(right=SimpleNamespace(tcp_position_in_hand_m=(0., 0., 0.))))
        backend.world, backend.evidence_source = SimpleNamespace(physics_step=0), "test"
        backend.regions, backend.active, backend.last_candidates, backend._admission = {}, {}, {}, {}
        backend.positions = lambda name: np.array([[0., -.004, 0.], [0., 0., 0.], [0., .004, 0.]])
        backend.strain_ratio = lambda name, x: 1.
        backend.penetration_reason = lambda name, patch: None
        mesh = trimesh.creation.box(extents=[.005]*3)
        geometry = dict(position=np.zeros(3), quaternion=[1., 0., 0., 0.],
            surfaces=[(mesh.vertices+[0., offset, 0.], mesh.faces) for offset in (-.015, .015)])
        with patch("topogym.world.physics.grasp_soft.read_grasp_geometry", return_value=geometry), \
             patch("topogym.world.physics.grasp_soft.surface_distances", side_effect=lambda p, *args: np.zeros(len(p))), \
             patch("topogym.world.physics.grasp_soft.exposed_patch", return_value=False):
            self.assertEqual(backend.candidates("right"), [])
            self.assertGreater(backend._admission["right"]["occluded_region_centers"], 0)
            backend.specs["rope"] = replace(backend.specs["rope"], require_exposed_patch=False)
            self.assertEqual(len(backend.candidates("right")), 1)
            self.assertEqual(backend._admission["right"]["occluded_region_centers"], 0)

    def test_cached_success_is_rejected_by_new_fixture_check(self):
        from topogym.planning.calibration_tools.adapters.rope_threading import recheck_relay
        row = sample()
        scene = {"mount": "same"}
        kin = SimpleNamespace(home=np.zeros(16), set_rope=lambda points: None,
            check=lambda q, **kwargs: dict(passed=False, issues=["right/fixtures"]))
        problem = SimpleNamespace(identity=dict(robot_scene=scene), stations_m=np.array([.9]))
        track = SimpleNamespace(rope=lambda s, sigma: np.zeros((len(s), 3)))
        meta = dict(assignment=ASSIGNMENT, identity=dict(robot_scene=scene), home_qpos=np.zeros(16),
            options=dict(fixture_margin_m=.005, rope_margin_m=.003, inter_arm_m=.01), robot_ik_verified=True)
        result, prefix = recheck_relay([row], meta, problem=problem, kin=kin, track=track, assignment=ASSIGNMENT)
        self.assertFalse(result["passed"])
        self.assertEqual(prefix, [])
        self.assertEqual(result["sample_count"], 0)
        self.assertEqual(result["failures"][0]["issues"], ["right/fixtures"])
        row["station"][0] = .01
        with self.assertRaisesRegex(ValueError, "station path differs"):
            recheck_relay([row], meta, problem=problem, kin=kin, track=track, assignment=ASSIGNMENT)

    def test_material_station_reference_and_binding_summary_are_passive(self):
        from topogym.planning.calibration_tools.adapters.rope_threading import relay_diagnostics
        policy = relay([sample(), sample()])
        policy.samples[1]["station"] = np.array([10., 0., 0., .2])
        policy.active_index, policy.index = 0, 1
        obs = observation()
        world = obs["privileged"]["world"]
        world["grasp"]["hands"]["right"]["binding"] = dict(
            target=["rope", 42], indices=[1, 2, 3], local_offsets=[[0., 0., 0.]]*3)
        before = deepcopy(world)
        result = relay_diagnostics(dict(world=world, robot=obs["robot"]), policy)
        self.assertEqual(result["station"]["sample_index"], 0)
        self.assertEqual(result["station"]["error_m"], 0.)
        binding = result["grasp"]["hands"]["right"]["binding"]
        self.assertEqual(binding["vertex_count"], 3)
        self.assertNotIn("local_offsets", binding)
        self.assertEqual(world, before)

    def test_shape_comparison_preserves_material_correspondence_and_sag(self):
        from topogym.planning.calibration_tools.adapters.rope_threading import compare_material_track
        # Vertex order differs from material order; the end has sagged 10 cm.
        world = dict(fem=dict(rope=dict(material_s_m=[1., 0., .5],
            position_m=[[1., 0., -.1], [0., 0., 0.], [.5, 0., 0.]])))
        before = deepcopy(world)
        track = Track([[0., 0., 0.], [1., 0., 0.]], [[1., 0., 0.], [2., 0., 0.]])
        result = compare_material_track(world, track, 0., [0., .5, 1.])
        self.assertAlmostEqual(result["max_error_m"], .1)
        self.assertEqual(result["stations"][0]["error_m"], 0.)
        self.assertAlmostEqual(result["stations"][-1]["error_m"], .1)
        self.assertEqual(world, before)
        with self.assertRaises(ValueError):
            compare_material_track(world, track, 0., [1.2])


class SceneIdentityTests(unittest.TestCase):
    def test_finger_contact_candidate_is_explicit_and_keeps_native_obstacles(self):
        from topogym.tasks.base import TaskSpec
        task = type(self.problem.task)(config=dict(rope_robot_contact="fingers"))
        spec = task.finalize_spec(TaskSpec((), {"ipc": {}}, {}), asset_dir=self.tmp.name, scene_config=self.scene)
        self.assertEqual(spec.physics_options["ipc"]["robot_collision_links"],
            [side+"/"+name for side in ("left", "right") for name in ("left_finger_link", "right_finger_link")])
        self.assertEqual(spec.metadata["rope_robot_contact"], "fingers")
        self.assertNotEqual(task.instance_id, self.problem.task.instance_id)
        self.assertEqual(len(spec.entities), 2)  # Existing physical base risers remain.
        self.assertEqual(self.problem.task.config["rope_robot_contact"], "full")

    @classmethod
    def setUpClass(cls):
        from topogym.planning.rope_threading.geometry import frozen_problem
        from topogym.config.scene import load_scene_config
        from topogym.simulator import SimulatorConfig
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.problem = frozen_problem(cls.tmp.name, variation="easy")
        cls.scene = load_scene_config(SimulatorConfig(task_id="rope_threading", variation_id="easy", enable_rgb=False))
        cls.meta = dict(identity=cls.problem.identity, home_qpos=np.zeros(16).tolist())

    def check_scene(self, *, meta=None, scene=None, home=None):
        validate_scene(meta or self.meta, task=self.problem.task, scene=self.scene if scene is None else scene,
                       home_qpos=np.zeros(16) if home is None else home, asset_dir=Path(self.tmp.name)/"assets")

    def test_current_wang_geometry_and_assets_match(self):
        self.check_scene()
        self.assertEqual(self.problem.layout.yaw_deg, 0.)
        self.assertEqual(len(self.problem.risers), 2)
        self.assertAlmostEqual(self.scene.robot_control.robot.base_riser_height_m, .0209)
        self.assertEqual(self.problem.identity["required_crossings"], ["R1-", "R2+"])

    def test_changed_mount_and_home_are_rejected(self):
        scene = deepcopy(self.scene)
        scene.env.robot_mount.pos[2] += .0209
        with self.assertRaisesRegex(ValueError, "robot scene"):
            self.check_scene(scene=scene)
        home = np.zeros(16)
        home[0] = .001
        with self.assertRaisesRegex(ValueError, "default home"):
            self.check_scene(home=home)

    def test_stale_asset_hash_is_rejected(self):
        meta = deepcopy(self.meta)
        meta["identity"]["asset_sha256"]["rope.obj"] = "0"*64
        with self.assertRaisesRegex(ValueError, "task asset differs"):
            self.check_scene(meta=meta)

    def test_model_candidates_keep_material_identity_and_native_ring_goal(self):
        from topogym.planning.rope_threading.geometry import frozen_problem
        from topogym.utils.geometry.rope import load_centerline_map, sample_material_centerline
        parameters = dict(rope_mesh=dict(spacing=.0055, sides=12), rope_material=dict(E=5e6),
                          rope_reference_shape="initial", robot_riser_height_m=.0509)
        with tempfile.TemporaryDirectory() as folder:
            candidate = frozen_problem(folder, variation="easy", task_parameters=parameters)
            self.assertNotEqual(candidate.task.instance_id, self.problem.task.instance_id)
            self.assertEqual(candidate.identity["task_parameters"], parameters)
            self.assertEqual(candidate.identity["rings"], self.problem.identity["rings"])
            self.assertEqual(candidate.required, self.problem.required)
            self.assertAlmostEqual(candidate.risers[0].extents[2], .0509)
            path = Path(folder)/"assets/rope_volume.npz"
            with np.load(path) as volume:
                np.testing.assert_array_equal(volume["rest"][:, 0], volume["material_s_m"])
                np.testing.assert_array_equal(volume["elastic_rest"], volume["spawn"])
                self.assertFalse(np.allclose(volume["rest"], volume["elastic_rest"]))
                indices, material = load_centerline_map(path)
                points = sample_material_centerline(dict(position_m=volume["spawn"], material_s_m=material), indices, material)
                self.assertEqual(len(points), 201)

    def test_model_candidate_rejects_invalid_physics_and_unknown_parameters(self):
        task_type = type(self.problem.task)
        for parameters in (dict(rope_mesh=dict(unknown=1)), dict(rope_material=dict(E=-1)),
                           dict(rope_reference_shape="unknown"), dict(robot_riser_height_m=.2)):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                task_type(config=parameters)


class RegraspSupportTests(unittest.TestCase):
    def test_keeper_bridges_same_hand_regrasp_without_material_travel(self):
        from topogym.planning.rope_threading.object_oracle import support_regrasps
        from topogym.planning.rope_threading.relay_ik import RelayPlanner
        holds = [dict(hand="B", station_behind_tip_m=.02, station_m=1.08,
                      sigma_start=.6, sigma_end=.8, role="receiver", ring="R1"),
                 dict(hand="B", station_behind_tip_m=.24, station_m=.86,
                      sigma_start=.8, sigma_end=1., role="pusher", ring="R2", unheld_regrasp=True)]
        before = deepcopy(holds)
        result = support_regrasps(holds, 1.1)
        self.assertEqual(holds, before)
        self.assertEqual([h["hand"] for h in result], ["B", "A", "B"])
        self.assertEqual(result[1]["sigma_start"], result[1]["sigma_end"])
        self.assertFalse(result[2]["unheld_regrasp"])
        self.assertEqual(result[2]["regrasp_support"], "A")
        planner = RelayPlanner.__new__(RelayPlanner)
        planner.holds, planner.assignment = result, ASSIGNMENT
        self.assertEqual(planner.other_holder(result[1], .8), "left")
        self.assertEqual(planner.other_holder(result[2], .8), "right")

    def test_ring_pose_candidates_move_mounts_and_preserve_signed_goal(self):
        from topogym.assets.geometry.rope_threading import ThreadingLayout
        original = ThreadingLayout()
        offset = np.array([-.035, -.05, 0.])
        changed = ThreadingLayout(ring_offsets_m={"R2": offset.tolist()}, ring_yaw_deg={"R2": 53.13})
        before, after = original.rings()[1], changed.rings()[1]
        rotation = Rotation.from_euler("z", 53.13, degrees=True)
        np.testing.assert_allclose(after["center_m"], np.asarray(before["center_m"])+offset)
        np.testing.assert_allclose(after["normal"], rotation.apply(before["normal"]))
        for kind in ("stand", "base"):
            np.testing.assert_allclose(np.asarray(after[kind]["position"])-after["center_m"],
                rotation.apply(np.asarray(before[kind]["position"])-before["center_m"]))
        self.assertEqual(original.required_crossings(), changed.required_crossings())
        self.assertEqual([r["radius_m"] for r in original.rings()], [r["radius_m"] for r in changed.rings()])
        for parameters in (dict(ring_yaw_deg={"unknown": 0.}), dict(ring_offsets_m={"R2": [0., 0.]}),
                           dict(ring_yaw_deg={"R1": float("nan")})):
            with self.assertRaises(ValueError):
                ThreadingLayout(**parameters)

    def test_local_aperture_resize_keeps_other_rings_and_mount_connection(self):
        from topogym.assets.geometry.rope_threading import ThreadingLayout
        original = ThreadingLayout(ring_inner_radius_m=.050)
        changed = ThreadingLayout(ring_inner_radius_m=.050, ring_inner_radii_m={"R2": .058})
        before, after = original.rings(), changed.rings()
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[2], after[2])
        self.assertEqual(before[1]["center_m"], after[1]["center_m"])
        self.assertEqual(before[1]["normal"], after[1]["normal"])
        self.assertAlmostEqual(after[1]["radius_m"]-before[1]["radius_m"], .008)
        for kind in ("stand", "base"):
            np.testing.assert_allclose(np.asarray(after[1][kind]["position"])-before[1][kind]["position"],
                                       .008*np.asarray(before[1]["basis_u"]), atol=1e-12)
        self.assertEqual(original.required_crossings(), changed.required_crossings())
        for mapping in ({"unknown": .058}, {"R2": .004}, {"R2": True}, {"R2": float("nan")}):
            with self.assertRaises(ValueError):
                ThreadingLayout(ring_inner_radii_m=mapping)


class ReferenceTests(unittest.TestCase):
    def test_registered_references_match_native_evidence_and_current_profile(self):
        from topogym.planning.rope_threading import profiles
        manifest = json.loads((profiles.REFERENCE_DIR/"manifest.json").read_text())
        self.assertTrue(manifest["variants"])
        for variant in manifest["variants"]:
            with self.subTest(variant=variant):
                samples, metadata = load_plan(profiles.reference_samples(variant), variant=variant)
                self.assertTrue(samples)
                self.assertTrue(metadata["complete_relay"])
                self.assertEqual(metadata["identity"]["seed"], 0)
                self.assertEqual(metadata["identity"]["task_parameters"],
                                 profiles.contact_relaxed_profile(variant)["task_parameters"])

    def test_changed_samples_and_incomplete_execution_evidence_are_rejected(self):
        import shutil
        from topogym.planning.rope_threading import profiles
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/"references"
            shutil.copytree(profiles.REFERENCE_DIR, target)
            with patch.object(profiles, "REFERENCE_DIR", target):
                path = profiles.reference_samples("easy")
                original = path.read_bytes()
                path.write_bytes(original+b"changed")
                with self.assertRaisesRegex(ValueError, "executed artifact"):
                    profiles.reference_samples("easy")
                path.write_bytes(original)
                evidence_path = target/"easy_evidence.json"
                evidence = json.loads(evidence_path.read_text())
                for field, value in (("evidence_complete", False), ("physics_tick_complete", False),
                                     ("control_step_complete", False), ("uncheckpointed_physics_steps", 1)):
                    changed = deepcopy(evidence)
                    changed["segments"][0][field] = value
                    evidence_path.write_text(json.dumps(changed))
                    with self.subTest(field=field), self.assertRaisesRegex(ValueError, "complete native"):
                        profiles.reference_samples("easy")


class CompletionTests(unittest.TestCase):
    def test_only_native_stable_success_with_complete_evidence_passes(self):
        good = dict(reason="env_terminal", evidence_complete=True, physics_tick_complete=True)
        task = SimpleNamespace(task_success=True, terminated=True)
        self.assertEqual(completion_status(task, good), "task_success")
        self.assertEqual(completion_status(task, dict(good, evidence_complete=False)), "incomplete_evidence")
        self.assertEqual(completion_status(task, dict(good, reason="policy_error")), "execution_failed")
        task.task_success = False
        self.assertEqual(completion_status(task, dict(good, reason="policy_done")), "not_passed")


if __name__ == "__main__":
    unittest.main()
