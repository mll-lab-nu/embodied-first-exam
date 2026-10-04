#!/usr/bin/env python3
"""Synthetic evidence/dispatch regressions; these tests do not claim physical success."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "ci_checks")]
from topogym.planning.harbor_bridge.contracts import digest
from topogym.planning.harbor_bridge import suite
from topogym.planning.harbor_bridge.verification import assess_trial, assess_smoke_trial
from topogym.simulator.frozen_binding import binding_id
from topogym_versions import task_lock
from v15_fixtures import bound_task


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class Evidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task = bound_task(self.root / "tasks/topogym-cast-coil-easy-i00-privileged")
        self.lock = task_lock(self.task)
        self.receipt = dict(binding_id=binding_id(self.lock))
        self.job = self.root / "job"
        self.trial = self.job / "trial"
        self.verifier = self.trial / "verifier"
        trajectory = self.trial / "artifacts/app/output/trajectory.npz"
        trajectory.parent.mkdir(parents=True)
        trajectory.write_bytes(b"synthetic trace for evidence hash tests only")
        self.reward = dict(success=1, all_success=1, replays=2, instance_ok=1,
                           instance_exact=1, runtime_binding_ok=1, deterministic=0, gpu_backend=1,
                           grader_error=0, infra_error=0, video_rendered=0)
        self.evidence = dict(runtime_binding=self.receipt, replays=[dict(success=True), dict(success=True)],
                             trajectory_sha256=digest(trajectory), instance_sha256=digest(self.task / "tests/instance.json"))
        self.commit()

    def tearDown(self):
        self.temp.cleanup()

    def commit(self):
        write(self.trial / "result.json", dict(task_name="topogym/" + self.task.name, finished_at="now",
                                               verifier_result=dict(rewards=self.reward)))
        write(self.verifier / "reward.json", self.reward)
        write(self.verifier / "reward.txt", self.reward["success"])
        write(self.verifier / "verdict.json", dict(success=bool(self.reward["success"]), reward=self.reward, evidence=self.evidence))

    def assess(self, mode="privileged", **kwargs):
        return assess_trial(self.job, self.task, mode, self.lock, **kwargs)

    def standard(self):
        self.task = bound_task(self.root / "tasks/topogym-cast-coil-easy-i00-standard", mode="standard")
        self.lock = task_lock(self.task)
        receipt = dict(instance_exact=True, runtime_binding=dict(binding_id=binding_id(self.lock)))
        write(self.verifier / "startup_binding.json", receipt)
        write(self.verifier / "replay.verdict.json", dict(receipt, replays=[dict(success=True)]))
        write(self.verifier / "final.json", dict(success=True, replay_success=True, finalized=True))
        (self.verifier / "trajectory.npz").write_bytes(b"service history")
        self.reward = dict(success=1, live_success=1, replay_success=1, runtime_binding_ok=1,
                           finalized=1, deterministic=0, gpu_backend=1)
        self.commit()

    def test_privileged_two_successful_gpu_replays_need_not_be_bit_exact(self):
        result = self.assess()
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["grade_one"])
        self.assertEqual(result["replay_success"], [True, True])

    def test_reward_one_cannot_replace_missing_second_replay(self):
        self.evidence["replays"].pop(); self.commit()
        self.assertEqual(self.assess()["status"], "evidence_failed")

    def test_replay_failure_and_unstable_episode_are_rejected(self):
        for row in (dict(success=False), dict(success=True, episode_end="simulator_instability")):
            self.evidence["replays"][1] = row; self.commit()
            self.assertFalse(self.assess()["grade_one"])

    def test_tampered_agent_trajectory_is_not_accepted(self):
        (self.trial / "artifacts/app/output/trajectory.npz").write_bytes(b"different trace")
        self.assertEqual(self.assess()["status"], "evidence_failed")

    def test_stale_runtime_and_wrong_task_cannot_borrow_success(self):
        self.evidence["runtime_binding"] = {"binding_id": "wrong"}; self.commit()
        self.assertFalse(self.assess()["grade_one"])
        self.evidence["runtime_binding"] = self.receipt; self.commit()
        data = json.loads((self.trial / "result.json").read_text()); data["task_name"] = "wrong"
        write(self.trial / "result.json", data)
        self.assertFalse(self.assess()["grade_one"])

    def test_harbor_and_verifier_rewards_must_agree(self):
        write(self.verifier / "reward.json", dict(self.reward, success=0))
        self.assertEqual(self.assess()["status"], "evidence_failed")

    def test_zero_score_is_separate_from_infrastructure_failure(self):
        self.reward = dict(success=0, missing_trajectory=1); self.commit()
        self.assertEqual(self.assess()["status"], "score_failed")
        self.assertEqual(self.assess(agent="nop")["status"], "passed")
        self.reward["grader_error"] = 1; self.commit()
        self.assertEqual(self.assess(agent="nop")["status"], "infra_failed")
        self.assertEqual(self.assess(returncode=90)["status"], "infra_failed")

    def test_unsuccessful_privileged_replays_are_retained_as_negative_evidence(self):
        self.reward.update(success=0, all_success=0)
        self.evidence["replays"][1]["success"] = False
        self.commit()
        result = self.assess()
        self.assertEqual(result["status"], "score_failed")
        self.assertEqual(result["replay_success"], [True, False])

    def test_scored_prefix_connectivity_is_not_full_oracle_qualification(self):
        self.reward.update(success=0, all_success=0, n_actions=3, video_rendered=1)
        self.evidence["replays"] = [dict(success=False), dict(success=False)]
        write(self.trial / "artifacts/app/output/bridge_report.json", dict(status="connectivity_smoke_complete",
              smoke_steps=3, evaluation=dict(action_transfer=dict(committed_rows=3))))
        self.commit()
        result = assess_smoke_trial(self.job, self.task, "privileged", self.lock, steps=3)
        self.assertEqual(result["status"], "smoke_passed")
        self.assertFalse(result["grade_one"])
        self.assertFalse(result["harbor_qualified"])
        document = dict(tasks=[result], smoke_steps=3)
        suite.summarize(document)
        self.assertTrue(document["connectivity_all_passed"])
        self.assertFalse(document["all_passed"])
        self.evidence["replays"].pop(); self.commit()
        self.assertEqual(assess_smoke_trial(self.job, self.task, "privileged", self.lock, steps=3)["status"], "evidence_failed")

    def test_incomplete_harbor_trial_is_not_success(self):
        data = json.loads((self.trial / "result.json").read_text()); data["finished_at"] = None
        write(self.trial / "result.json", data)
        self.assertEqual(self.assess()["status"], "infra_failed")

    def test_standard_live_and_fresh_replay_accept_gpu_nondeterminism(self):
        self.standard()
        self.assertEqual(self.assess("standard")["status"], "passed")
        from check_topogym_trial import check
        self.assertEqual(check(self.job, 1, self.task)["deterministic"], 0)

    def test_standard_needs_both_binding_receipts_and_actual_history(self):
        self.standard()
        for name in ("startup_binding.json", "replay.verdict.json", "trajectory.npz"):
            path = self.verifier / name; data = path.read_bytes(); path.unlink()
            self.assertEqual(self.assess("standard")["status"], "evidence_failed", name)
            path.write_bytes(data)

    def test_standard_cannot_inherit_success_from_live_or_reward_alone(self):
        self.standard()
        write(self.verifier / "final.json", dict(success=False, replay_success=True, finalized=True))
        self.assertFalse(self.assess("standard")["grade_one"])

    def test_inventory_never_runs_published_fallback_when_active_is_missing(self):
        out = self.root / "inventory"
        with patch("topogym_versions.task_root", side_effect=ValueError("active tree missing")), \
             patch("topogym_versions.require_task") as check:
            document = suite.prepare(out, families=["cast_coil"])
        self.assertEqual(document["counts"], {"blocked": 6})
        self.assertFalse(document["all_passed"])
        check.assert_not_called()
        with self.assertRaises(FileExistsError):
            suite.prepare(out)

    def test_candidate_and_registered_release_are_explicit_separate_scopes(self):
        for candidate in (False, True):
            with patch("topogym_versions.require_task", return_value=dict(runtime_binding=self.lock)) as check:
                document = suite.prepare(self.root / f"plan-{candidate}", tasks_root=self.root / "tasks", candidate=candidate)
            self.assertEqual(check.call_args.kwargs["registered"], not candidate)
            self.assertEqual(document["tasks"][0]["reference"]["kind"], "session")

    def test_missing_standard_twin_is_explicit_coverage_failure(self):
        document = suite.prepare(self.root / "missing-twin", tasks_root=self.root / "tasks", candidate=True)
        self.assertEqual(len(document["tasks"]), 2)
        self.assertEqual(document["tasks"][1]["mode"], "standard")
        self.assertEqual(document["tasks"][1]["status"], "blocked")

    def test_standard_without_privileged_proof_remains_blocked(self):
        self.standard()
        with patch("topogym_versions.require_task", return_value=dict(runtime_binding=self.lock)), \
             patch("topogym.utils.process_limits.run_guarded") as run:
            document = suite.prepare(self.root / "standard-only", tasks_root=self.root / "tasks",
                                     modes=["standard"], candidate=True)
            self.assertEqual(suite.execute(document), 1)
        run.assert_not_called()
        self.assertEqual(document["counts"], {"blocked_dependency": 1})

    def test_unknown_reference_fields_fail_closed(self):
        row = dict(task=str(self.task))
        with self.assertRaisesRegex(ValueError, "Unknown reference"):
            suite.reference_for(row, {self.task.name: dict(kind="session", bypass_rules=True)})

    def test_successful_privileged_trace_drives_standard_then_both_nop_controls(self):
        self.standard()
        trace = str(self.root / "verified-privileged-trajectory.npz")
        def assessment(*args, agent, **kwargs):
            return dict(status="passed", grade=int(agent == "oracle"), grade_one=agent == "oracle",
                        trajectory=trace, errors=[])
        with patch("topogym_versions.require_task", return_value=dict(runtime_binding=self.lock)), \
             patch("topogym.utils.process_limits.run_guarded", return_value=0) as run, \
             patch.object(suite, "package", side_effect=lambda task, *a, **kw: dict(task=str(task))) as package, \
             patch.object(suite, "check_package"), patch.object(suite, "assess_trial", side_effect=assessment):
            document = suite.prepare(self.root / "both-modes", tasks_root=self.root / "tasks", candidate=True)
            self.assertEqual(suite.execute(document), 0)
        self.assertTrue(document["all_passed"])
        self.assertEqual(document["grade_one_count"], 2)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual([cmd[cmd.index("-a") + 1] for cmd in commands], ["oracle", "nop", "oracle", "nop"])
        self.assertTrue(all(cmd[cmd.index("--max-retries") + 1] == "0" for cmd in commands))
        self.assertEqual(package.call_args.kwargs["kind"], "public_trajectory")
        self.assertEqual(package.call_args.kwargs["trajectory"], trace)

    def test_infrastructure_failure_stops_remaining_jobs_without_marking_pass(self):
        self.standard()
        with patch("topogym_versions.require_task", return_value=dict(runtime_binding=self.lock)), \
             patch("topogym.utils.process_limits.run_guarded", return_value=90) as run, \
             patch.object(suite, "package", side_effect=lambda task, *a, **kw: dict(task=str(task))), \
             patch.object(suite, "check_package"):
            document = suite.prepare(self.root / "infra-stop", tasks_root=self.root / "tasks", candidate=True)
            self.assertEqual(suite.execute(document), 1)
        run.assert_called_once()
        self.assertEqual(document["counts"], {"infra_failed": 1, "not_run": 1})
        self.assertEqual(document["grade_one_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
