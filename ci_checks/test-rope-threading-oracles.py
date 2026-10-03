#!/usr/bin/env python3
"""Wang relay integration contracts; synthetic observations, no physics claim."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

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
                tcp_left=np.r_[position, quat, .03], tcp_right=np.r_[position, quat, .03])


def observation():
    return dict(robot={s: dict(tcp_position_world_m=[0., 0., 0.], tcp_orientation_wxyz=[1., 0., 0., 0.])
                       for s in ("left", "right")},
                privileged=dict(world=dict(fem=dict(rope=dict(material_s_m=[.9], position_m=[[0., 0., 0.]])),
                    grasp=dict(hands={s: dict(binding=None, phase="idle", solved_ticks=0) for s in ("left", "right")}))))


class ProfileTests(unittest.TestCase):
    def test_exact_selected_plans_and_distinct_hard_defaults(self):
        expected = dict(easy=("A10_B_pull19_B20_recvA", 2, .20, .06),
                        medium=("A10_B_pull19_B20_keep_recvA6", 3, .20, .06),
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

    def test_side_mismatch_is_rejected(self):
        self.rewrite("side", np.array(["left", "right"]))
        with self.assertRaisesRegex(ValueError, "phase/side"):
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


class PolicyTests(unittest.TestCase):
    def test_translation_uses_fixed_start_and_respects_speed(self):
        policy = RopeRelayPolicy([sample(position=(.1, 0., 0.))], speed_m_s=.1, control_dt_s=.1)
        obs = observation()
        positions = [policy.act(obs)["right"]["position_world_m"][0] for _ in range(10)]
        np.testing.assert_allclose(positions, np.linspace(.01, .1, 10))

    def test_rotation_in_place_is_interpolated(self):
        policy = RopeRelayPolicy([sample(position=(0., 0., 0.), angle=.8)], control_dt_s=.1, angular_speed_rad_s=.8)
        angles = []
        for _ in range(10):
            quat = policy.act(observation())["right"]["orientation_wxyz"]
            angles.append(Rotation.from_quat(np.roll(quat, -1)).magnitude())
        np.testing.assert_allclose(angles, np.linspace(.08, .8, 10))

    def test_registered_grasp_waits_for_native_solve_then_lost_grasp_stops(self):
        policy = RopeRelayPolicy([sample("pinch:A:R1"), sample("hold:A:R1")], control_dt_s=.1)
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
        policy = RopeRelayPolicy([sample("retreat:A/up")], control_dt_s=.1)
        policy.targets = {s: (np.zeros(3), Rotation.identity(), policy.pinch) for s in ("left", "right")}
        policy.expected_holders = {"right"}
        obs = observation()
        hand = obs["privileged"]["world"]["grasp"]["hands"]["right"]
        hand.update(binding=dict(target=["rope", 42]), phase="holding", solved_ticks=1)
        action = policy.act(obs)
        self.assertEqual(action["right"]["gripper_position_m"], policy.free)
        np.testing.assert_allclose(action["right"]["position_world_m"], 0.)
        self.assertEqual(policy.waiting[0], "release")
        hand.update(binding=None, phase="idle")
        policy.act(obs)
        self.assertIsNone(policy.waiting)

    def test_acquisition_timeout_is_not_policy_success(self):
        policy = RopeRelayPolicy([sample("pinch:A:R1")], control_dt_s=.1, acquire_wait_s=.1)
        policy.act(observation())
        policy.act(observation())
        with self.assertRaisesRegex(RuntimeError, "did not acquire"):
            policy.act(observation())
        self.assertFalse(policy.done)

    def test_receiver_motion_keeps_sender_pinched(self):
        policy = RopeRelayPolicy([sample("approach:B:R2", "left")], control_dt_s=.1)
        policy.targets = {s: (np.zeros(3), Rotation.identity(), policy.pinch) for s in ("left", "right")}
        self.assertEqual(policy.act(observation())["right"]["gripper_position_m"], policy.pinch)


class SceneIdentityTests(unittest.TestCase):
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
