#!/usr/bin/env python3
"""HF publishing contracts using synthetic evidence and a versioned fake Hub.

No model, physics, real HF writes or real credentials are used.
"""
from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
import os
import multiprocessing
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import difficulty_eval as evaluation
import difficulty_hf_auth as auth
import difficulty_results_hf as hf


class FakeHub:
    def __init__(self):
        self.head = "0" * 40
        self.versions = {self.head: {}}
        self.commits = []
        self.faults = []
        self.before_commit = None

    def call(self, action, **params):
        if action == "auth":
            return None
        if action == "head":
            return self.head
        if action == "read":
            value = self.versions[params["revision"]].get(params["path"])
            return json.loads(value) if value else None
        if action == "info":
            files = self.versions[params["revision"]]
            return {p: dict(size=len(files[p]), sha256=hashlib.sha256(files[p]).hexdigest(), git_blob_sha1=None)
                    for p in params["paths"] if p in files}
        if action == "commit":
            if self.before_commit:
                self.before_commit(params)
            fault = self.faults.pop(0) if self.faults else None
            if fault == "before":
                raise auth.HFError("network_error", retryable=True)
            if fault == "forbidden":
                raise auth.HFError("permission_denied")
            if params["parent"] != self.head:
                raise auth.HFError("commit_conflict", retryable=True)
            new = dict(self.versions[self.head])
            new.update({rel: Path(path).read_bytes() for rel, path in params["files"]})
            self.head = f"{len(self.commits)+1:040x}"
            self.versions[self.head] = new
            self.commits.append(params)
            if fault == "after":
                raise auth.HFError("network_error", retryable=True)
            return self.head
        raise AssertionError(action)


class HFContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.run = self.work / "runs/difficulty_trials/test-run"
        self.run.mkdir(parents=True)
        self.args = evaluation.parse_args(["--phase", "upload", "--run-id", "test-run", "--work-dir", str(self.work), "--results_to_hf"])
        self.secret = "hf_FAKE_TEST_SECRET_0123456789"
        self.stdout = io.StringIO()
        self.output = redirect_stdout(self.stdout)
        self.output.__enter__()
        self.log = hf.UploadLog(self.run, [self.secret], heartbeat_s=0.02)
        self.hub = FakeHub()
        self.make_fixture()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.temp.cleanup()

    def make_fixture(self, statuses=("solved", "interrupted")):
        sample = dict(task_id="test_task", difficulty="easy", sample_id="s00", scene_seed=123,
                      evaluable_for_task_success=True, simulator={"asset_path": "/home/private/robot.urdf"})
        sample["sample_sha256"] = hf.digest(sample)
        source = dict(files={"scripts/frozen.py": "abc"}, git_head="test", snapshot="/home/private/source")
        source["sha256"] = hf.digest(source["files"])
        manifest = dict(schema_version=1, instances=[sample], source_sha256=source["sha256"],
                        settings={"agent_wall_clock_s": 21600}, instance_count=1, trial_count=2)
        manifest["manifest_sha256"] = hf.digest(manifest)
        hf.atomic_json(self.run / "manifest.lock.json", manifest)
        hf.atomic_json(self.run / "source_identity.json", source)
        hf.atomic_json(self.run / "execution.lock.json", dict(model="test/model", agent="codex", auth="api-key"))
        rows = []
        for mode, status in zip(("unlimited", "limited"), statuses):
            row = dict(task_id="test_task", difficulty="easy", sample_id="s00", scene_seed=123, mode=mode,
                       trial=1, attempt=1, status=status, success=1 if status == "solved" else None,
                       evaluable_for_task_success=True, tokens_in=100, tokens_out=20, cost_usd_api_price=0.1,
                       job="/home/private/job", harbor_trial="/home/private/trial", exception=None)
            rows.append(row)
            target = self.run / "results/test_task/easy/s00" / mode / "trial_01/attempt_001"
            target.mkdir(parents=True, exist_ok=True)
            hf.atomic_json(target / "reward.json", dict(success=row["success"], secret=self.secret,
                                                       trace_path="/home/private/trace", note=self.secret))
            (target / "replay.mp4").write_bytes(b"synthetic media; no real video")
        self.rows = rows
        self.write_rows()

    def write_rows(self):
        (self.run / "trials.jsonl").write_bytes(b"".join(hf.encoded(row) for row in self.rows))

    def test_collect_existing_jobs_includes_unlimited_trajectory_in_export(self):
        from collect_batch_results import collect_manifest
        manifest_path = self.run / "manifest.lock.json"
        manifest = json.loads(manifest_path.read_text())
        sample = manifest["instances"][0]
        sample.update(task_number=1, slug="topogym-test-task-easy-s00")
        sample.pop("sample_sha256")
        sample["sample_sha256"] = hf.digest(sample)
        manifest.pop("manifest_sha256")
        manifest["manifest_sha256"] = hf.digest(manifest)
        hf.atomic_json(manifest_path, manifest)
        jobs = self.work / "jobs"
        for mode in ("unlimited", "limited"):
            trial = jobs / f"d01-easy-s00-{mode}-a001" / "trial"
            (trial / "verifier").mkdir(parents=True)
            hf.atomic_json(trial / "result.json", dict(
                task_name=sample["slug"] + ("-limited" if mode == "limited" else ""),
                finished_at="2026-09-30T00:00:00Z", verifier_result=dict(rewards=dict(success=1))))
            hf.atomic_json(trial / "verifier/reward.json", dict(success=1, finalized=True))
            trajectory = trial / ("artifacts/app/output" if mode == "unlimited" else "verifier") / "trajectory.npz"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            trajectory.write_bytes(f"synthetic {mode} trajectory".encode())
        self.assertEqual(collect_manifest(manifest_path, jobs), 0)
        staging, descriptor = self.export()
        for mode in ("unlimited", "limited"):
            relative = f"test_task/easy/seed_123/{mode}/trial_01/attempt_001"
            self.assertEqual((staging / relative / "trajectory.npz").read_bytes(),
                             f"synthetic {mode} trajectory".encode())
            exported = json.loads((staging / relative / "result.json").read_text())
            self.assertNotIn("trajectory.npz", exported["missing_files"])
            self.assertIn("trajectory.npz", exported["artifacts"])

    def test_collect_and_export_mode_evidence_with_sanitized_manifest_hashes(self):
        from collect_batch_results import collect_manifest
        # Use the real collector first, including its trusted verifier source rule.
        self.test_collect_existing_jobs_includes_unlimited_trajectory_in_export()
        jobs = self.work / 'jobs'
        names = {
            'unlimited': ('verdict.json', 'media.json', 'submission_error.json', 'instance_error.json'),
            'limited': ('final.json', 'replay.verdict.json'),
        }
        originals = {}
        for mode, sidecars in names.items():
            trial = jobs / f'd01-easy-s00-{mode}-a001' / 'trial'
            verifier = trial / 'verifier'
            for name in sidecars:
                hf.atomic_json(verifier / name, dict(success=0, note=self.secret, path='/home/private/data'))
            frame_map = verifier / 'replay.frame_map.jsonl'
            frame_map.write_text(json.dumps(dict(physics_step=0, note=self.secret, path='/home/private/frame')) + '\n')
            (verifier / 'replay.mp4').write_bytes(b'fixture video, no physics')
            manifest = dict(schema_version=2, frame_count=1,
                frame_map=dict(path=frame_map.name, sha256=hashlib.sha256(frame_map.read_bytes()).hexdigest()),
                videos=dict(combined=dict(path='replay.mp4', sha256=hashlib.sha256((verifier / 'replay.mp4').read_bytes()).hexdigest())))
            hf.atomic_json(verifier / 'replay.recording_manifest.json', manifest)
            names_for_mode = (*sidecars, frame_map.name, 'replay.recording_manifest.json')
            originals[mode] = {name: (verifier / name).read_bytes() for name in names_for_mode}
            untrusted = trial / 'artifacts/app/output'; untrusted.mkdir(parents=True, exist_ok=True)
            (untrusted / sidecars[0]).write_text('{"injected":true}')
            (verifier / 'unlisted.log').write_text('not allowlisted')
        self.assertEqual(collect_manifest(self.run / 'manifest.lock.json', jobs), 0)
        staging, descriptor = self.export()
        for mode, sidecars in names.items():
            local = self.run / 'results/test_task/easy/s00' / mode / 'trial_01/attempt_001'
            target = staging / 'test_task/easy/seed_123' / mode / 'trial_01/attempt_001'
            item = hf.json_file(target / 'result.json')
            self.assertEqual(item['artifact_contract_version'], 2)
            for name, raw in originals[mode].items():
                self.assertEqual((local / name).read_bytes(), raw)
                self.assertNotIn(self.secret, (target / name).read_text())
                self.assertNotIn('/home/private', (target / name).read_text())
                self.assertEqual(item['artifacts'][name]['source_sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(item['artifacts'][name]['sha256'], hashlib.sha256((target / name).read_bytes()).hexdigest())
                self.assertNotIn(name, item['missing_files'])
            exported_manifest = hf.json_file(target / 'replay.recording_manifest.json')
            self.assertEqual(exported_manifest['frame_map']['sha256'], hashlib.sha256((target / 'replay.frame_map.jsonl').read_bytes()).hexdigest())
            self.assertEqual(exported_manifest['videos']['combined']['sha256'], hashlib.sha256((target / 'replay.mp4').read_bytes()).hexdigest())
            self.assertNotEqual(exported_manifest['frame_map']['sha256'], hashlib.sha256(originals[mode]['replay.frame_map.jsonl']).hexdigest())
            other = names['limited' if mode == 'unlimited' else 'unlimited'][0]
            self.assertNotIn(other, item['missing_files'])
            self.assertFalse((target / 'unlisted.log').exists())
        self.assertEqual(self.export()[1], descriptor)

    def test_sidecars_remain_optional_for_old_runs_and_metrics_stays_small(self):
        staging, _ = self.export()
        target = staging / 'test_task/easy/seed_123/unlimited/trial_01/attempt_001'
        self.assertIn('verdict.json', hf.json_file(target / 'result.json')['missing_files'])
        self.assertNotIn('submission_error.json', hf.json_file(target / 'result.json')['missing_files'])
        self.assertNotIn('instance_error.json', hf.json_file(target / 'result.json')['missing_files'])
        # A separate publication uses the existing metrics-only contract.
        (self.run / 'hf_publication.lock.json').unlink()
        self.args.hf_artifacts = 'metrics'
        staging, _ = self.export()
        item = hf.json_file(staging / 'test_task/easy/seed_123/unlimited/trial_01/attempt_001/result.json')
        self.assertEqual(set(item['artifacts']), {'reward.json'})
        self.assertEqual(item['missing_files'], [])

    def export(self):
        return hf.export_snapshot(self.run, self.args, self.log)

    def publisher(self):
        return hf.Publisher(self.run, self.args, self.secret, self.log, hub=self.hub, sleep=lambda _: None)

    def test_export_maps_seed_modes_status_and_sanitizes(self):
        staging, descriptor = self.export()
        paths = descriptor["files"]
        self.assertIn("test_task/easy/seed_123/unlimited/trial_01/attempt_001/result.json", paths)
        self.assertIn("test_task/easy/seed_123/limited/trial_01/attempt_001/replay.mp4", paths)
        self.assertFalse(descriptor["evaluation_complete"])
        self.assertEqual(descriptor["evaluable_trials"], 1)
        self.assertEqual(descriptor["solved_trials"], 1)
        text = b"".join(p.read_bytes() for p in staging.rglob("*") if p.is_file()).decode()
        self.assertNotIn(self.secret, text)
        self.assertNotIn("/home/private", text)
        self.assertNotIn('"job":', text)
        self.assertIn("[LOCAL_PATH]/robot.urdf", text)
        self.assertEqual(self.export()[1], descriptor)

    def test_metrics_and_missing_failed_records(self):
        self.args.hf_artifacts = "metrics"
        self.rows[1]["status"] = "infra_failed"
        self.write_rows()
        staging, descriptor = self.export()
        self.assertFalse(any(p.endswith(".mp4") for p in descriptor["files"]))
        limited = hf.json_file(staging / "test_task/easy/seed_123/limited/trial_01/attempt_001/result.json")
        self.assertEqual(limited["status"], "infra_failed")
        self.assertIsNone(limited["success"])

    def test_snapshot_identity_and_date_are_persistent(self):
        self.args.hf_exp_date = "2026-09-30"
        first = self.export()[1]
        self.args.hf_exp_date = None
        self.assertEqual(self.export()[1], first)
        self.args.hf_repo_id = "other/repo"
        with self.assertRaisesRegex(auth.HFError, "identity changed"):
            self.export()

    def test_manifest_tampering_and_missing_planned_trial_rejected(self):
        self.rows.pop()
        self.write_rows()
        with self.assertRaises(auth.HFError):
            self.export()
        self.make_fixture()
        data = hf.json_file(self.run / "manifest.lock.json")
        data["trial_count"] = 400
        hf.atomic_json(self.run / "manifest.lock.json", data)
        with self.assertRaises(auth.HFError):
            self.export()

    def test_symlink_and_modified_staging_rejected(self):
        staging, descriptor = self.export()
        target = staging / next(p for p in descriptor["files"] if p.endswith(".mp4"))
        target.write_bytes(b"tampered")
        with self.assertRaisesRegex(auth.HFError, "staging snapshot changed"):
            self.export()
        target = self.run / "results/test_task/easy/s00/unlimited/trial_01/attempt_001/reward.json"
        target.unlink()
        target.symlink_to(self.run / "execution.lock.json")
        with self.assertRaisesRegex(auth.HFError, "symlinks"):
            self.export()

    def test_lost_commit_responses_and_idempotent_reupload(self):
        staging, descriptor = self.export()
        self.hub.faults = ["after", "after", "after"]
        oid = self.publisher().publish(staging, descriptor)
        count = len(self.hub.commits)
        self.assertEqual(count, 3)
        self.assertEqual(self.publisher().publish(staging, descriptor), oid)
        self.assertEqual(len(self.hub.commits), count)
        state = hf.json_file(self.run / "hf_upload/state.json")
        self.assertEqual(state["upload_status"], "complete")
        self.assertIn("Already uploaded", self.stdout.getvalue())
        self.assertIn("evaluation_complete=false", self.stdout.getvalue())

    def test_completion_marker_is_last_and_failure_does_not_claim_success(self):
        staging, descriptor = self.export()
        self.hub.faults = [None, None, "forbidden"]
        with self.assertRaises(auth.HFError):
            self.publisher().publish(staging, descriptor)
        self.assertFalse(any(p.endswith("publication.json") for p in self.hub.versions[self.hub.head]))
        self.assertNotIn("Upload complete", self.stdout.getvalue())
        self.publisher().publish(staging, descriptor)
        self.assertTrue(any(p.endswith("publication.json") for p in self.hub.versions[self.hub.head]))
        self.assertEqual(len(self.hub.commits), 3)

    def test_completed_attempt_immutable_but_incomplete_can_advance(self):
        staging, descriptor = self.export()
        self.publisher().publish(staging, descriptor)
        self.rows[1]["status"] = "unsolved"
        self.rows[1]["success"] = 0
        self.write_rows()
        staging, descriptor = self.export()
        self.publisher().publish(staging, descriptor)
        self.assertTrue(descriptor["evaluation_complete"])
        self.rows[0]["tokens_in"] += 1
        self.write_rows()
        staging, descriptor = self.export()
        with self.assertRaisesRegex(auth.HFError, "completed attempt changed"):
            self.publisher().publish(staging, descriptor)

    def test_concurrent_parent_change_is_rechecked(self):
        staging, descriptor = self.export()
        def race(params):
            self.hub.before_commit = None
            other = self.work / "other.json"
            other.write_text("{}")
            self.hub.call("commit", parent=self.hub.head, files=[("other-run/file.json", str(other))], message="other")
        self.hub.before_commit = race
        self.publisher().publish(staging, descriptor)
        self.assertIn("other-run/file.json", self.hub.versions[self.hub.head])
        self.assertIn("commit_conflict", self.stdout.getvalue())

    def test_empty_repository_and_plain_git_objects(self):
        self.hub.head = None
        self.hub.versions = {None: {}}
        original = self.hub.call
        def plain(action, **params):
            value = original(action, **params)
            if action == "info":
                for path, info in value.items():
                    content = self.hub.versions[params["revision"]][path]
                    info["sha256"] = None
                    info["git_blob_sha1"] = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
            return value
        self.hub.call = plain
        staging, descriptor = self.export()
        self.publisher().publish(staging, descriptor)
        self.publisher().publish(staging, descriptor)
        self.assertEqual(len(self.hub.commits), 3)

    def test_retry_exhaustion_and_upload_lock(self):
        self.hub.faults = ["before"] * 4
        staging, descriptor = self.export()
        with self.assertRaises(auth.HFError):
            self.publisher().publish(staging, descriptor)
        self.assertEqual(len(self.hub.commits), 0)
        self.assertNotIn("Upload complete", self.stdout.getvalue())
        with hf.publication_lock(self.run):
            with self.assertRaises(auth.HFError):
                with hf.publication_lock(self.run):
                    self.fail("duplicate uploader acquired publication lock")

    def test_credentials_are_explicit_private_and_isolated(self):
        token = self.work / "token with space"
        token.write_text(self.secret + "\n")
        token.chmod(0o600)
        self.args.hf_token_file = token
        with patch.dict(os.environ, {"HF_TOKEN": "wrong", "MY_HF": self.secret}):
            self.assertEqual(auth.resolve_token(self.args), (self.secret, "file"))
            self.args.hf_token_env = "MY_HF"
            clean = auth.clean_environment(os.environ, self.args)
            self.assertNotIn("HF_TOKEN", clean)
            self.assertNotIn("MY_HF", clean)
        token.chmod(0o644)
        with self.assertRaises(auth.HFError):
            auth.resolve_token(self.args)
        token.chmod(0o600)
        link = self.work / "link"
        link.symlink_to(token)
        self.args.hf_token_file = link
        with self.assertRaises(auth.HFError):
            auth.resolve_token(self.args)

        source = self.work / "source"
        (source / ".secrets").mkdir(parents=True)
        (source / "scripts").mkdir()
        unsafe = source / "scripts/token"
        unsafe.write_text(self.secret)
        unsafe.chmod(0o600)
        with patch.object(auth, "__file__", str(source / "scripts/difficulty_hf_auth.py")):
            with self.assertRaises(auth.HFError):
                auth.read_token(source / ".secrets/../scripts/token")
            alias = self.work / "source-alias"
            alias.symlink_to(source / "scripts", target_is_directory=True)
            with self.assertRaises(auth.HFError):
                auth.read_token(alias / "token")

    def test_invalid_credentials_never_fall_back_or_echo(self):
        self.args.hf_token_env = "TEST_HF"
        with patch.dict(os.environ, {"TEST_HF": "", "HF_TOKEN": self.secret}):
            with self.assertRaises(auth.HFError):
                auth.resolve_token(self.args)
        self.log.emit("error", self.secret + "\x1b[31m https://host/object?signature=private", "ERROR")
        self.assertNotIn(self.secret, self.stdout.getvalue())
        self.assertNotIn("signature=private", self.stdout.getvalue())
        self.assertNotIn("\x1b", self.stdout.getvalue())

    def test_heartbeat_and_log_failure(self):
        with self.log.activity("test", "Waiting for SDK"):
            time.sleep(0.05)
        self.assertIn("heartbeat", (self.run / "hf_upload/events.jsonl").read_text())
        with patch.object(Path, "open", side_effect=OSError("disk full")):
            self.log.emit("test", "Still visible")
        self.assertIn("Cannot write upload logs", self.stdout.getvalue())
        self.assertIn("Still visible", self.stdout.getvalue())

    def test_upload_cli_dry_run_needs_no_gpu_sdk_or_token(self):
        command = [sys.executable, str(ROOT / "scripts/difficulty_eval.py"), "--phase", "upload", "--run-id", "test-run",
                   "--work-dir", str(self.work), "--results_to_hf", "--hf-dry-run", "--hf-token-file", "/does/not/exist"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dry run: no upload performed", result.stdout)
        self.assertFalse((self.run / "source").exists())
        self.assertFalse((self.run / "cuda-profile.json").exists())

    def test_upload_does_not_create_missing_run(self):
        self.args.run_id = "absent"
        with self.assertRaises(evaluation.EvaluationError):
            evaluation.DifficultyEvaluation(self.args).execute()
        self.assertFalse((self.work / "runs/difficulty_trials/absent").exists())

    def test_outcomes_preserve_evaluation_failure(self):
        self.args.phase = "collect"
        self.args.resume = True
        with patch.dict(os.environ, {"HF_TOKEN": self.secret}), \
             patch.object(hf.Publisher, "preflight"), \
             patch.object(evaluation.DifficultyEvaluation, "execute_evaluation", return_value=2), \
             patch.object(hf.Publisher, "publish", side_effect=auth.HFError("network_error")):
            self.assertEqual(evaluation.DifficultyEvaluation(self.args).execute(), 2)
        with patch.dict(os.environ, {"HF_TOKEN": self.secret}), \
             patch.object(hf.Publisher, "preflight"), \
             patch.object(evaluation.DifficultyEvaluation, "execute_evaluation", return_value=0), \
             patch.object(hf.Publisher, "publish", side_effect=auth.HFError("network_error")):
            self.assertEqual(evaluation.DifficultyEvaluation(self.args).execute(), 3)

    def test_validation_and_recovery_paths(self):
        bad = (["--hf-token-file", "a", "--hf-token-env", "B"], ["--hf-exp-date", "20260930"],
               ["--phase", "run", "--hf-dry-run"], ["--hf-repo-id", "../repo"])
        for extra in bad:
            with self.subTest(extra=extra), self.assertRaises((SystemExit, auth.HFError)):
                evaluation.parse_args(["--run-id", "test", "--results_to_hf", *extra])
        self.args.hf_token_file = Path("/a path/token")
        command = hf.recovery_command(self.args, self.work)
        self.assertIn("'/a path/token'", command)
        self.assertNotIn(self.secret, command)

    def test_partial_snapshot_resumes_before_new_local_results(self):
        staging, descriptor = self.export()
        self.hub.faults = [None, "forbidden"]
        pub = self.publisher()
        with self.assertRaises(auth.HFError):
            pub.publish(staging, descriptor)
        pub.state("failed", error_code="permission_denied")
        self.rows[1]["status"] = "unsolved"
        self.write_rows()
        # A retry first finishes the exact frozen snapshot reserved remotely.
        self.assertEqual(self.export()[1], descriptor)
        pub.publish(staging, descriptor)
        new_staging, newer = self.export()
        self.assertNotEqual(newer["snapshot_sha256"], descriptor["snapshot_sha256"])
        self.publisher().publish(new_staging, newer)

    def test_owned_sdk_worker_errors_and_cancellation(self):
        # Spawn an actual worker, using an inert SDK with deliberately unsafe errors.
        sdk = self.work / "fake_sdk"
        sdk.mkdir()
        (sdk / "huggingface_hub.py").write_text('''
import time
class CommitOperationAdd: pass
class HfApi:
    def __init__(self, **kwargs): pass
    def auth_check(self, *args, **kwargs):
        raise TimeoutError("hf_FAKE_TEST_SECRET_0123456789 https://host?signature=hidden")
    def repo_info(self, *args, **kwargs):
        time.sleep(60)
''')
        sys.path.insert(0, str(sdk))
        before = {p.pid for p in multiprocessing.active_children()}
        try:
            hub = hf.Hub(self.secret, self.args.hf_repo_id, self.run)
            with self.assertRaises(auth.HFError) as caught:
                hub.call("auth")
            self.assertEqual(caught.exception.code, "network_error")
            self.assertNotIn(self.secret, str(caught.exception))
            def stop():
                raise auth.HFError("resource_limit")
            hub.guard = stop
            with self.assertRaisesRegex(auth.HFError, "resource_limit"):
                hub.call("head")
            self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)
        finally:
            sys.path.remove(str(sdk))

    def test_docker_launcher_credential_boundary_and_offline_paths(self):
        fakebin = self.work / "bin"
        fakebin.mkdir()
        docker = fakebin / "docker"
        docker.write_text(f'#!{sys.executable}\n' + '''
import hashlib, json, os, pathlib, sys
args = sys.argv[1:]
if args[0] == 'info':
    print('[]')
elif args[0] == 'create':
    launch = next(arg.split('src=',1)[1].split(',dst=',1)[0] for arg in args if 'dst=/run/topogym-launch' in arg)
    folder = pathlib.Path(launch)
    token = folder / 'hf-token'
    pathlib.Path(os.environ['FAKE_DOCKER_REPORT']).write_text(json.dumps(dict(
        argv=args, launch=launch, inner_args=(folder/'args').read_bytes().decode().split('\\0')[:-1],
        hf_env_leaked=any(k in os.environ for k in ('HF_TOKEN','TEST_HF')),
        token_hash=hashlib.sha256(token.read_bytes()).hexdigest() if token.exists() else None,
        host_file=(folder/'hf-host-token-file').read_text() if (folder/'hf-host-token-file').exists() else None)))
    print('fake-container')
''')
        docker.chmod(0o755)
        report = self.work / "docker-report.json"
        token = self.work / "private token"
        token.write_text(self.secret)
        token.chmod(0o600)
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(self.work / "docker.sock"))
        try:
            env = dict(os.environ, PATH=str(fakebin)+os.pathsep+os.environ["PATH"],
                       DOCKER_HOST="unix://"+str(self.work / "docker.sock"),
                       FAKE_DOCKER_REPORT=str(report), HF_TOKEN=self.secret, TEST_HF=self.secret)
            base = ["bash", str(ROOT / "bash_scripts/run_difficulty_trials.sh"), "--controller-image", "sha256:"+"a"*64,
                    "--work-dir", str(self.work), "--phase", "upload", "--run-id", "test-run", "--results_to_hf"]
            for options in (["--hf-token-file", str(token)], ["--hf-token-env", "TEST_HF"],
                            ["--hf-dry-run", "--hf-token-file", "/absent"]):
                # Only the explicitly selected custom variable needs to be stripped.
                case_env = dict(env)
                if "TEST_HF" not in options:
                    case_env.pop("TEST_HF")
                result = subprocess.run(base+options, env=case_env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                data = hf.json_file(report)
                self.assertFalse(data["hf_env_leaked"])
                self.assertNotIn("--gpus", data["argv"])
                self.assertFalse(any("dst=/var/lib/topogym/codex" in v for v in data["argv"]))
                self.assertNotIn(self.secret, report.read_text()+result.stdout+result.stderr)
                self.assertFalse(Path(data["launch"]).exists())
                if "--hf-dry-run" in options:
                    self.assertIsNone(data["token_hash"])
                else:
                    self.assertEqual(data["token_hash"], hashlib.sha256(self.secret.encode()).hexdigest())
                    self.assertIn("/run/topogym-launch/hf-token", data["inner_args"])
            archive=self.work/'sealed.tar.gz'; archive.write_text('launcher fixture; verifier is tested separately')
            Path(str(archive)+'.sha256').write_text('fixture'); (self.work/'MANIFEST.md').write_text('fixture')
            spec=self.work/'assignment.json'; spec.write_text('{}')
            for command,options in (
                ('assign',['--spec',str(spec)]),
                ('verify',['--archive',str(archive),'--assignment',str(spec)]),
                ('import',['--archive',str(archive)]),
                ('export',['--run-id','test-run']),
                ('upload',['--archive',str(archive),'--hf-token-env','TEST_HF'])):
                base=['bash',str(ROOT/'bash_scripts/run_difficulty_trials.sh'),'helper',command,
                      '--controller-image','sha256:'+'a'*64,'--work-dir',str(self.work)]
                result=subprocess.run(base+options,env=env,capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                data=hf.json_file(report)
                self.assertNotIn('--gpus',data['argv'])
                self.assertEqual(data['inner_args'][:2],['helper',command])
                self.assertNotIn('--release-lock',data['inner_args'])
                self.assertEqual(data['argv'][data['argv'].index('--user')+1],
                                 '0:0' if command=='export' else f'{os.getuid()}:{os.getgid()}')
                if command!='export':
                    self.assertFalse(any('dst=/var/lib/topogym/codex' in v or 'dst=/var/run/docker.sock' in v for v in data['argv']))
                if '--archive' in options:
                    mounts=[v for v in data['argv'] if 'dst=/run/topogym-archive/' in v]
                    self.assertEqual(len(mounts),3)
                    self.assertTrue(all(v.endswith(',readonly') for v in mounts))
                self.assertFalse(Path(data['launch']).exists())
                if command=='upload':
                    self.assertFalse(data['hf_env_leaked'])
                    self.assertEqual(data['token_hash'],hashlib.sha256(self.secret.encode()).hexdigest())
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
