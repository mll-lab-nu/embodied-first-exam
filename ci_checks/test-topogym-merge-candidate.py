#!/usr/bin/env python3
"""Merged build/packaging contracts and synthetic safety states; no physics claim."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "harbor_templates/topogym/common")]
import rcb_topogym as M
from topogym_rules import grader_details, grasp_regions
from topogym_mk_task import require_current_destination
from topogym_merge_candidate import candidate_inputs, rekey_goal_parameters
from topogym.planning.harbor_bridge.packaging import collect_helpers
from topogym.planning.rope_threading.profiles import contact_relaxed_profile
from topogym.simulator.config import SimulatorConfig
from topogym.tasks.rope_threading.common import RopeThreadingTask

spec = importlib.util.spec_from_file_location("safety_fixtures", ROOT / "ci_checks/test-topogym-safety-rules.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class CandidateContracts(unittest.TestCase):
    def test_frozen_v14_hashes_and_destination(self):
        manifest = json.loads((ROOT / "ci_checks/topogym_tooling_versions.json").read_text())
        for mode, suffix in (("unlimited", "privileged"), ("limited", "standard")):
            task = ROOT / f"tasks/topogym-rope-threading-easy-i00-{suffix}"
            for rel, expected in manifest["v14"][mode].items():
                self.assertEqual(hashlib.sha256((task / rel).read_bytes()).hexdigest(), expected)
            with self.assertRaisesRegex(ValueError, "frozen tooling 14"):
                require_current_destination(task)
        self.assertEqual(manifest["version_images"]["14"], "ghcr.io/luigivamper/rcb-topogym:0.2.12-cu128")

    def test_build_options_do_not_mutate_catalog_or_allow_frozen_overrides(self):
        catalog = deepcopy(M.TASKS)
        for tier in ("easy", "medium", "hard"):
            profile = contact_relaxed_profile(tier)
            cfg = M.simulator_config("rope_threading", variation_id=tier, seed=0,
                task_parameters=profile["task_parameters"], simulator_overrides=profile["simulator_overrides"])
            self.assertEqual(cfg["physics_dt_s"] * cfg["control_decimation"], .04)
            self.assertEqual(cfg["grasp_assist"]["targets"][0]["require_exposed_patch"], False)
            self.assertEqual(cfg["task_parameters"]["rope_material"]["E"], 5e6)
        self.assertEqual(M.TASKS, catalog)
        for bad in ({"seed": 1}, {"task_parameters": {}}, {"enable_rgb": False}, {"unknown": 1}):
            with self.assertRaises(ValueError):
                M.simulator_config("rope_threading", 0, simulator_overrides=bad)
        with self.assertRaisesRegex(ValueError, "frozen instance"):
            M.Session("rope_threading", instance="not-read.json", simulator_overrides={})

    def test_options_invalid_values_fail_before_scene_creation(self):
        for bad in ({"physics_dt_s": 0}, {"control_decimation": 0}, {"ipc_options": {"newton_tolerance": -1}},
                    {"grasp_assist": {"model": "unknown"}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                M.simulator_config("rope_threading", 0, simulator_overrides=bad)

    def test_candidate_preserves_baseline_input_and_declares_changes(self):
        source = ROOT / "tasks/topogym-rope-threading-easy-i00-privileged/environment/instance.json"
        inst = json.loads(source.read_text())
        original = deepcopy(inst)
        params, overrides, cfg, changes, differences = candidate_inputs("rope_threading", "easy", inst, source)
        self.assertEqual(inst, original)
        self.assertEqual(params["terminal"]["maximum_speed_m_s"], .01)
        self.assertEqual(overrides["reset_physics_steps"], 0)
        self.assertTrue(changes)
        self.assertIn("grasp_assist", differences)
        self.assertEqual(cfg["render_backend"], "nyx")

    def test_candidate_tick_window_never_trips_early(self):
        for dt in (.0025, .025, .04, .07, .3):
            ticks = M.rule_window_ticks(dt, .25)
            self.assertGreaterEqual(ticks * dt + 1e-12, .25)
            self.assertLess((ticks - 1) * dt, .25)
        self.assertEqual(M.rule_window_ticks(.04, .25), 7)

    def test_text_reports_soft_patch_semantics_and_actual_material(self):
        profile = contact_relaxed_profile("easy")
        cfg = M.simulator_config("rope_threading", variation_id="easy", seed=0,
            task_parameters=profile["task_parameters"], simulator_overrides=profile["simulator_overrides"])
        inst = dict(simulator=cfg, effective_task_parameters=profile["task_parameters"])
        for limited in (True, False):
            words = " ".join(grader_details("rope_threading", inst, limited=limited))
            for wanted in ("5000 kPa", "round_ring", "1 mm", "7 consecutive physics ticks", "exposed patch not required"):
                self.assertIn(wanted, words)
            self.assertNotIn("50 kPa", words)
        words = M.Session.grasp_rules(SimpleNamespace(env=SimpleNamespace(config=SimulatorConfig(**cfg))))
        self.assertIn("disjoint material patches", words)
        self.assertNotIn("follows the gripper rigidly", words)
        cloth = dict(simulator=dict(grasp_assist=dict(model="pbd_local_patch_v1", targets=[dict(entity="blanket")])) )
        self.assertIn("Soft grasp patches", grasp_regions("blanket_flatten", cloth, limited=True))

    def test_rigid_and_no_assist_descriptions_still_work(self):
        for config in (SimulatorConfig(), SimulatorConfig(grasp_assist=dict(model="contact_weld_v1",
                                targets=[dict(entity="cube", link="cube")]))):
            words = M.Session.grasp_rules(SimpleNamespace(env=SimpleNamespace(config=config)))
            self.assertIn("physical grasping" if config.grasp_assist.model == "none" else "follows the gripper rigidly", words)

    def test_runtime_relay_dependencies_fit_private_solution(self):
        files = collect_helpers(ROOT, "topogym.planning.rope_threading.relay_feedback")
        self.assertIn("topogym/planning/rope_threading/relay_feedback.py", files)
        self.assertIn("topogym/planning/grasp_observation.py", files)
        self.assertFalse(any("calibration_tools" in p or p.startswith("scripts/") for p in files))
        for family in ("rope_threading", "blanket_flatten"):
            files = collect_helpers(ROOT, f"topogym.planning.{family}.public_session")
            self.assertIn("topogym/planning/harbor_bridge/actions.py", files)

    def test_private_worker_namespace_survives_fresh_process(self):
        import subprocess
        from topogym.planning.rope_threading.relay_feedback import repair_command
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public/topogym"
            private = root / "private/topogym/planning/rope_threading"
            public.mkdir(parents=True)
            private.mkdir(parents=True)
            (public / "__init__.py").write_text("PUBLIC_SENTINEL = True\n")
            (private.parent / "__init__.py").write_text("")
            (private / "__init__.py").write_text("")
            (private / "relay_feedback.py").write_text(
                "import sys, topogym\nassert topogym.PUBLIC_SENTINEL\nprint('private worker ' + sys.argv[1])\n")
            command = repair_command("bound-input")
            command[3] = str(private.parent.parent)
            import os
            env = dict(os.environ, PYTHONPATH=str(public.parent))
            result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("private worker bound-input", result.stdout)

    def test_session_policy_adapter_uses_only_recorded_steps(self):
        from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
        world = SimpleNamespace(physics_step=0, sim_time_s=0., read_state=lambda: {"marker": "measured"})
        env = SimpleNamespace(_world=world, _robot=SimpleNamespace(observe=lambda: {"arm": "measured"}), timing_spec={})
        env.tick_record = lambda: {"state": {"physics_step": world.physics_step, "branch_id": 0}}
        session = SimpleNamespace(_recording=[], _recorded_ticks=[], env=env, n_steps=0, episode_done=False, episode_end=None, success=lambda: False)
        observations = []

        class Policy:
            def act(self, obs):
                observations.append(obs)
                return {"native": "command"}

        runner = SessionPolicyRunner(session)
        def step(action, *, mode):
            self.assertEqual(mode, "JOINT_ABS")
            self.assertEqual(action, {"native": "command"})
            session._recording.append([])
            session._recorded_ticks.append(10)
            session.n_steps += 1
            world.physics_step += 10
            world.sim_time_s += .025
            session.episode_done = session.n_steps == 2
        with patch.object(runner.executor, "step", side_effect=step) as submit:
            result = runner.run_policy(request_id="route", policy=Policy(), submission_hash="proof", state_fields=("world",))
        self.assertEqual(submit.call_count, 2)
        self.assertEqual(result["physics_steps"], 20)
        self.assertEqual(result["reason"], "env_terminal")
        self.assertFalse(result["task_success"])
        self.assertEqual(observations[-1]["privileged"]["world"], {"marker": "measured"})

    def test_session_policy_adapter_never_advances_finished_policy(self):
        from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
        world = SimpleNamespace(physics_step=0, sim_time_s=0.)
        env = SimpleNamespace(_world=world, _robot=SimpleNamespace(observe=lambda: {}))
        env.tick_record = lambda: {"state": {"physics_step": world.physics_step, "branch_id": 0}}
        session = SimpleNamespace(_recording=[], _recorded_ticks=[], env=env, n_steps=0, episode_done=False, episode_end=None, success=lambda: False)
        runner = SessionPolicyRunner(session)
        with patch.object(runner.executor, "step") as submit:
            result = runner.run_policy(request_id="empty", policy=SimpleNamespace(act=lambda obs: None), submission_hash="x")
        submit.assert_not_called()
        self.assertEqual(result["control_steps"], 0)
        self.assertFalse(result["task_success"])

    def test_blanket_declares_birth_map_without_oracle_hooks(self):
        from topogym.tasks.blanket_flatten.common import BlanketFlattenTask
        from topogym.world.physics.pbd import bind_material_map
        from topogym.planning.blanket_flatten.assist_support import enable
        declare = BlanketFlattenTask.declare
        enable()
        self.assertIs(BlanketFlattenTask.declare, declare)
        with tempfile.TemporaryDirectory() as folder:
            assets = Path(folder) / "assets"
            assets.mkdir()
            task = BlanketFlattenTask(config=dict(initialization_mode="flat_for_preparation", texture=None))
            spec = task.declare(assets, .75)
            path = spec.entities[0].material_map_path
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent, assets.parent)
            with np.load(path, allow_pickle=False) as data:
                np.testing.assert_array_equal(data["uv"], task.birth_uv)
                # A few exact surface vertices are enough to exercise binding
                # and the immutable checkpoint inventory contract without GPU.
                entity = SimpleNamespace(get_particles_pos=lambda: data["vertices"][:3].copy())
                bind_material_map(entity, path)
            self.assertFalse(entity.grasp_material_coordinates.flags.writeable)


class NativeGoalAndSafety(unittest.TestCase):
    def test_relaxed_goal_keeps_volume_safety(self):
        points = np.array([[-.02, .0184, 0.], [.02, .0184, 0.]])
        ring = dict(name="R1", center_m=[0., 0., 0.], normal=[1., 0., 0.], radius_m=.025, tube_radius_m=.003)

        def make():
            task = RopeThreadingTask(config=dict(aperture_contact_allowance_m=.001,
                aperture_check_profile="round_ring", terminal=dict(maximum_speed_m_s=.01)))
            task.layout = SimpleNamespace(rope_radius_m=.004, rings=lambda: [ring], required_crossings=lambda: [("R1", 1)])
            task.centerline_map = (None, None)
            return task

        def state(tick, ratio=1., valid=True):
            return dict(physics_step=tick, sim_time_s=tick*.0025,
                fem=dict(rope=dict(position_m=points, velocity_m_s=np.full_like(points, .005))),
                bodies=dict(R1=dict(position_m=[0., 0., 0.], quaternion_wxyz=[1., 0., 0., 0.])),
                ipc=dict(native_valid=valid, volume_ratio=dict(rope=dict(minimum=ratio, maximum=1.)), attachment_residual_m={}))

        with patch("topogym.tasks.rope_threading.common.sample_material_centerline", return_value=points):
            for ratio, valid, expected, ticks in ((1., True, True, 201), (-.1, True, False, 100), (1., False, False, 1)):
                task = make()
                task.initialize(state(0))
                fixtures.fake_session(task, dict(rope=SimpleNamespace(links=())))
                for tick in range(1, ticks + 1):
                    result = task.update(state(tick, ratio, valid), .0025)
                    if ratio < 0 and tick < 100:
                        self.assertFalse(result.terminated)
                        self.assertFalse(result.task_success)
                self.assertTrue(result.terminated)
                self.assertEqual(bool(result.task_success), expected)


class FrozenStateRekey(unittest.TestCase):
    """v16's blanket coverage 0.95 against the packaged v14 cloth states (identity 0.90): a re-keyed copy, arrays untouched."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def blanket(self):
        source = ROOT / "tasks/topogym-blanket-flatten-easy-i00-privileged/environment"
        baseline = self.folder / "baseline"
        baseline.mkdir()
        (baseline / "instance.json").write_bytes((source / "instance.json").read_bytes())
        state = baseline / "instance_assets/initial_state"
        state.mkdir(parents=True)
        for name in ("manifest.json", "arrays.npz"):
            (state / name).write_bytes((source / "instance_assets/initial_state" / name).read_bytes())
        return json.loads((baseline / "instance.json").read_text()), baseline / "instance.json", state

    def test_profile_coverage_rekeys_a_copy_with_identical_arrays(self):
        from topogym.utils.io import canonical_hash
        inst, path, state = self.blanket()
        before = {name: (state / name).read_bytes() for name in ("manifest.json", "arrays.npz")}
        rekeyed, record = rekey_goal_parameters("blanket_flatten", "easy", inst, path, self.folder / "rekeyed")
        self.assertEqual({name: (state / name).read_bytes() for name in before}, before)          # the source is only read
        self.assertEqual((self.folder / "rekeyed/arrays.npz").read_bytes(), before["arrays.npz"])
        manifest = json.loads((self.folder / "rekeyed/manifest.json").read_text())["metadata"]
        self.assertEqual(manifest["identity"]["parameters"]["minimum_coverage_ratio"], .95)
        self.assertEqual(manifest["identity_sha256"], canonical_hash(manifest["identity"]))
        self.assertEqual(record["changed"], {"identity.parameters.minimum_coverage_ratio": [.9, .95]})
        self.assertEqual(record["previous_manifest_sha256"], hashlib.sha256(before["manifest.json"]).hexdigest())
        params = rekeyed["simulator"]["task_parameters"]
        self.assertEqual(params["initial_state_sha256"],
                         hashlib.sha256((self.folder / "rekeyed/manifest.json").read_bytes()).hexdigest())
        self.assertEqual(Path(params["initial_state_path"]), self.folder / "rekeyed/manifest.json")
        self.assertEqual(json.loads(path.read_text()), inst)                                      # the input is a copy
        # candidate_inputs then carries the profile's coverage and the re-keyed archive, nothing else changes
        cand, _, _, changes, _ = candidate_inputs("blanket_flatten", "easy", rekeyed, path)
        self.assertEqual(cand["minimum_coverage_ratio"], .95)
        self.assertEqual(cand["initial_state_sha256"], params["initial_state_sha256"])
        self.assertTrue(any("coverage 0.95" in c for c in changes))

    def test_no_rekey_without_a_goal_only_change(self):
        inst, path, _ = self.blanket()
        inst["simulator"]["task_parameters"]["minimum_coverage_ratio"] = .95
        manifest = path.parent / "instance_assets/initial_state/manifest.json"
        data = json.loads(manifest.read_text())
        data["metadata"]["identity"]["parameters"]["minimum_coverage_ratio"] = .95
        from topogym.utils.io import canonical_hash
        data["metadata"]["identity_sha256"] = canonical_hash(data["metadata"]["identity"])
        manifest.write_text(json.dumps(data))
        self.assertIsNone(rekey_goal_parameters("blanket_flatten", "easy", inst, path, self.folder / "rekeyed"))
        rope = ROOT / "tasks/topogym-rope-threading-easy-i00-privileged/environment/instance.json"
        self.assertIsNone(rekey_goal_parameters("rope_threading", "easy", json.loads(rope.read_text()), rope,
                                                self.folder / "rope"))
        self.assertFalse((self.folder / "rekeyed").exists() or (self.folder / "rope").exists())

    def test_rekey_refuses_an_archive_the_instance_does_not_pin(self):
        inst, path, _ = self.blanket()
        inst["simulator"]["task_parameters"]["initial_state_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "initial_state_sha256"):
            rekey_goal_parameters("blanket_flatten", "easy", inst, path, self.folder / "rekeyed")


if __name__ == "__main__":
    unittest.main()
