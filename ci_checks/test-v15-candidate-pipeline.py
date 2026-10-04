#!/usr/bin/env python3
"""CPU regression checks for waiting, activation gates and policy binding."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "ci_checks")]
import topogym_candidate_pipeline as P
from check_topogym_trial import check, bound_sidecar
from topogym.simulator.frozen_binding import binding_id


class PipelineContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def pipeline(self):
        p = P.Pipeline.__new__(P.Pipeline)
        p.folder, p.status_path, p.state = self.folder, self.folder / "status.json", {}
        p.args = SimpleNamespace(after_containers=["old-knot-hard", "old-knot-medium"], wait_timeout_s=300)
        return p

    def test_wait_observes_both_experiments_without_stopping_them(self):
        p = self.pipeline()
        replies = [subprocess.CompletedProcess([], 0, value, "") for value in ("true", "false", "false", "false")]
        with patch.object(P.subprocess, "run", side_effect=replies) as command, patch.object(P.time, "sleep") as sleep:
            p.wait_for_experiments()
        sleep.assert_called_once_with(30)
        self.assertEqual([c.args[0][-1] for c in command.call_args_list], p.args.after_containers * 2)
        self.assertTrue(all(c.args[0][:2] == ["docker", "inspect"] for c in command.call_args_list))
        self.assertEqual(p.state["status"], "running")

    def test_daemon_failure_is_not_treated_as_finished_experiment(self):
        p = self.pipeline()
        with patch.object(P.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "permission denied")):
            with self.assertRaisesRegex(ValueError, "Cannot inspect"):
                p.wait_for_experiments()

    def test_activation_requires_full_catalog_and_unchanged_source(self):
        p = self.pipeline(); p.release = {"definition": "frozen"}; p.document = {"instances": []}
        with patch.object(P, "identity", return_value={"definition": "changed"}):
            with self.assertRaisesRegex(ValueError, "definition changed"):
                p.activate()
        with patch.object(P, "identity", return_value=p.release):
            with self.assertRaisesRegex(ValueError, "39 instances"):
                p.activate()

    def test_changed_intermediate_output_cannot_be_reused(self):
        p = self.pipeline(); p.image = {"id": "frozen-image"}; p.source = ROOT
        out = self.folder / "instance.json"; out.write_text("changed")
        command = ["docker", "run", "make-instance", "--out", str(out)]
        p.rows = [dict(source=str(self.folder / "slug-privileged/environment/instance.json"),
                       commands=[dict(argv=command, env={})])]
        P.save(self.folder / "make-instance.receipt.json", dict(image_id="frozen-image", command=command, files={str(out): "0" * 64}))
        with patch.object(p, "run") as execute:
            with self.assertRaisesRegex(ValueError, "Intermediate output changed"):
                p.build()
        execute.assert_not_called()

    def test_zero_reward_does_not_hide_standard_infrastructure_failure(self):
        trial = self.folder / "job/trial"; (trial / "verifier").mkdir(parents=True)
        P.save(trial / "result.json", dict(task_name="task-standard", finished_at="now"))
        reward = dict(success=0, finalized=1, deterministic=1, runtime_binding_ok=0)
        P.save(trial / "verifier/reward.json", reward)
        with self.assertRaisesRegex(ValueError, "bound finalization"):
            check(trial.parent, 0)
        reward["runtime_binding_ok"] = 1; P.save(trial / "verifier/reward.json", reward)
        check(trial.parent, 0, Path("task-standard"))
        with self.assertRaisesRegex(ValueError, "different task"):
            check(trial.parent, 0, Path("other-standard"))

    def test_startup_and_replay_must_both_match_binding(self):
        from v15_fixtures import bound_task
        from topogym_versions import task_lock
        lock = task_lock(bound_task(self.folder / "bound-task"))
        proof = dict(instance_exact=True, runtime_binding=dict(binding_id=binding_id(lock)))
        for name in ("startup_binding.json", "replay.verdict.json"):
            P.save(self.folder / name, proof)
        bound_sidecar(self.folder, lock)
        P.save(self.folder / "replay.verdict.json", dict(proof, instance_exact=False))
        with self.assertRaisesRegex(ValueError, "frozen runtime"):
            bound_sidecar(self.folder, lock)

    def test_coil_adapter_uses_bound_geometry_seed_and_existing_session(self):
        from topogym.planning.cast_coil import public_session as C
        task = SimpleNamespace(variation_id="cast_coil_seeded", config={"geometry": "sampled"}, body_origins={})
        session = SimpleNamespace(task="cast_coil", n_steps=0, _resets=0, config={"seed": 123},
                                  instance_sha="bound-state", env=SimpleNamespace(_task=task))
        with patch.object(C, "variant_reference", return_value=(SimpleNamespace(), [])) as reference, \
             patch.object(C, "CastCoilPolicy") as policy, patch.object(C, "SessionPolicyRunner") as runner:
            C.run_feedback_policy(session, self.folder)
        reference.assert_called_once_with(variant=task.variation_id, seed=123, task_parameters=task.config)
        self.assertEqual(policy.call_args.kwargs["seed"], 123)
        runner.assert_called_once_with(session, control_mode="EE_ABS")

    def test_coil_callback_transitive_helpers_are_portable(self):
        from topogym.planning.harbor_bridge.packaging import collect_helpers
        files = collect_helpers(ROOT, "topogym.planning.cast_coil.public_session")
        self.assertIn("topogym/planning/motions/__init__.py", files)
        self.assertIn("topogym/planning/motions/cast_coil.py", files)
        self.assertTrue(all(name.startswith("topogym/planning/") for name in files))

    def test_end_effector_policy_is_compiled_without_changing_frozen_control_mode(self):
        from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
        world = SimpleNamespace(physics_step=0, sim_time_s=0.)
        env = SimpleNamespace(_world=world, _robot=SimpleNamespace(description={}, observe=lambda: {}), timing_spec={})
        env.tick_record = lambda: {"state": {"physics_step": world.physics_step, "branch_id": 0}}
        session = SimpleNamespace(_recording=[], _recorded_ticks=[], env=env, config={"control_mode": "JOINT_ABS"}, n_steps=0,
                                  episode_done=False, episode_end=None, success=lambda: False)
        policy = SimpleNamespace(initialize=lambda info: None, act=lambda obs: {"left": "pose"})
        runner = SessionPolicyRunner(session, control_mode="EE_ABS")
        with patch("topogym.robot.control.action_spec", return_value={}) as spec, \
             patch.object(runner.executor, "step", return_value=True) as step:
            runner.run_policy(request_id="test", policy=policy, submission_hash="x")
        spec.assert_called_once_with({}, "EE_ABS")
        step.assert_called_once_with({"left": "pose"}, mode="EE_ABS")
        self.assertEqual(session.config["control_mode"], "JOINT_ABS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
