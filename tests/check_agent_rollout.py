"""Frozen variants, observation conditions, continuity, artifacts and isolation."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from topogym.agent_rollout.agents import CodexAgent
from topogym.agent_rollout.evaluate import summarize
from topogym.agent_rollout.isolation import sandbox_command
from topogym.agent_rollout.initial import audit_initial
from topogym.agent_rollout.media import probe
from topogym.agent_rollout.runtime import run_repeat, inspect_paths
from topogym.agent_rollout.suite import prepare, load_suite, load_preset, file_hash


class RolloutChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.suite = prepare(self.root / "suite", {"counter": "topogym.agent_rollout.suite:prepare_counter"}, variants=2, seed=7)
        self.preset = self.suite.parent / "counter/rollout_1.json"

    def job(self, name, decisions, **overrides):
        job = dict(public=str(self.root / name), private=str(self.root / (name+"_private")),
                   preset=str(self.preset), repeat=1, agent=dict(id="test", provider="replay", mode="rgb", decisions=decisions),
                   max_steps=10, max_total_steps=20, max_calls=8, max_segments=4, samples_per_camera=2)
        job.update(overrides)
        return job

    def test_preparation_is_deterministic_and_detects_edits(self):
        second = prepare(self.root / "suite2", {"counter": "topogym.agent_rollout.suite:prepare_counter"}, variants=2, seed=7)
        self.assertEqual(load_suite(self.suite), load_suite(second))
        a = load_preset(self.preset)
        b = load_preset(self.suite.parent / "counter/rollout_2.json")
        self.assertNotEqual(a["kwargs"], b["kwargs"])
        a["kwargs"]["start"] = 2
        self.preset.write_text(json.dumps(a))
        with self.assertRaisesRegex(ValueError, "hash"):
            load_suite(self.suite)

    def test_multisegment_video_repeat_and_information_boundary(self):
        actions = [dict(kind="segment", code="env.step({'dx': 1}, steps=2)"),
                   dict(kind="inspect", paths=["segment_0.json", "frames/segment_1/front/000002.png"]),
                   dict(kind="segment", code="env.step({'dx': 1}, steps=3)")]
        job = self.job("rgb", actions)
        result = run_repeat(job)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["segments"], 2)
        public, private = Path(job["public"]), Path(job["private"])
        self.assertFalse((public / "privileged.json").exists())
        for i in range(3):
            manifest = json.loads((public / f"segment_{i}.json").read_text())
            self.assertEqual(len(manifest["videos"]), 3)
            counts = {probe(public / v["path"])["frames"] for v in manifest["videos"].values()}
            self.assertEqual(counts, {probe(public / f"segment_{i}.mp4")["frames"]})
            self.assertFalse(any("observation" in f for f in manifest["frames"]))
        initial = json.loads((public / "segment_0.json").read_text())
        first = json.loads((public / "segment_1.json").read_text())
        second = json.loads((public / "segment_2.json").read_text())
        self.assertEqual(initial["end_tick"], 0)
        self.assertEqual(first["end_tick"], second["start_tick"])
        for camera in first["cameras"]:
            self.assertEqual(first["frames"][-1]["cameras"][camera]["sha256"],
                             second["frames"][0]["cameras"][camera]["sha256"])
        request = json.loads((private / "call_1.request.json").read_text())
        self.assertEqual(len(request["images"]), 3)
        self.assertNotIn('"start":', request["prompt"])
        self.assertNotIn('"x":', request["prompt"])
        other = self.job("privileged", actions, expected_initial=result["initial_audit"])
        other["agent"]["mode"] = "rgb_privileged"
        repeated = run_repeat(other)
        self.assertTrue(repeated["success"], repeated)
        self.assertEqual(repeated["initial_observation_sha256"], result["initial_observation_sha256"])
        self.assertEqual(repeated["ticks"], result["ticks"])
        self.assertTrue((Path(other["public"]) / "privileged.json").exists())
        self.assertFalse(repeated["usage_complete"])
        self.assertFalse(repeated["success_physics_qualified"])

    @staticmethod
    def no_video(private, public, manifest_path, index, cameras, dt, **kwargs):
        return dict(model_inputs=[])

    def test_invalid_script_does_not_step_and_total_budget_is_enforced(self):
        job = self.job("invalid", [dict(kind="segment", code="env.reset()"),
            dict(kind="segment", code="env.step({'dx': 1}, steps=3)"),
            dict(kind="segment", code="env.step({'dx': 1}, steps=2)")], max_total_steps=2)
        with patch("topogym.agent_rollout.runtime.publish_segment", self.no_video):
            result = run_repeat(job)
        self.assertEqual(result["ticks"], 2)
        self.assertEqual(result["segments"], 1)
        self.assertEqual(result["calls"], 3)
        self.assertEqual(result["status"], "limit_reached")
        self.assertFalse(result["success"])

    def test_initial_drift_fails_before_agent_or_action(self):
        with patch("topogym.agent_rollout.runtime.publish_segment", self.no_video):
            first = run_repeat(self.job("reference", []))
            audit = Path(first["initial_audit"])
            content = json.loads(audit.read_text())
            content["state_sha256"] = "wrong"
            audit.write_text(json.dumps(content))
            result = run_repeat(self.job("drift", [], expected_initial=str(audit)))
        self.assertEqual(result["status"], "pipeline_error")
        self.assertEqual(result["ticks"], 0)
        self.assertEqual(result["calls"], 0)

    def test_inspection_cannot_escape_through_paths_or_symlinks(self):
        public = self.root / "public"
        public.mkdir()
        (public / "frames").mkdir()
        secret = self.root / "secret.png"
        secret.write_text("private")
        (public / "frames/leak.png").symlink_to(secret)
        for path in ("../secret.png", "frames/leak.png", str(secret)):
            with self.assertRaises(ValueError):
                inspect_paths(public, [path])

    def test_existing_repeat_is_never_overwritten(self):
        job = self.job("once", [])
        with patch("topogym.agent_rollout.runtime.publish_segment", self.no_video):
            run_repeat(job)
            with self.assertRaises(FileExistsError):
                run_repeat(job)

    def test_rgb_tolerance_is_explicit_and_does_not_allow_scene_changes(self):
        from types import SimpleNamespace
        from PIL import Image
        with patch("topogym.agent_rollout.runtime.publish_segment", self.no_video):
            result = run_repeat(self.job("noise_reference", []))
        reference = Path(result["initial_audit"])
        data = json.loads(reference.read_text())
        path = Path(data["cameras"]["front"]["path"])
        with Image.open(path) as image:
            image = image.copy()
        old = image.getpixel((0, 0))
        image.putpixel((0, 0), (old[0]+8, old[1], old[2]))
        image.save(path)
        data["cameras"]["front"]["sha256"] = file_hash(path)
        reference.write_text(json.dumps(data))
        job = self.job("noise_trial", [], expected_initial=str(reference))
        with patch("topogym.agent_rollout.runtime.publish_segment", self.no_video):
            strict = run_repeat(job)
        self.assertEqual(strict["status"], "pipeline_error")
        preset = load_preset(self.preset)
        preset["initial_rgb_tolerance"] = dict(mean_absolute=.01, max_channel=32, changed_fraction=.001)
        initial = json.loads(reference.read_text())["state"]
        session = SimpleNamespace(root=Path(job["private"]) / "episode",
                                  adapter=SimpleNamespace(adapter=SimpleNamespace(observe=lambda: initial)))
        report = audit_initial(session, preset, Path(job["private"]), str(reference))
        self.assertFalse(report["initial_rgb_comparison"]["front"]["exact"])
        image.paste((255, 255, 255), (0, 0, 30, 30))
        image.save(path)
        data["cameras"]["front"]["sha256"] = file_hash(path)
        reference.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "RGB differs"):
            audit_initial(session, preset, Path(job["private"]), str(reference))

    def test_summary_includes_errors_in_denominator(self):
        trials = [dict(agent_id="a", input_mode="rgb", task_id="t", variant_id="rollout_1",
                       status=status, success=status == "succeeded")
                  for status in ("succeeded", "task_failed", "pipeline_error")]
        result = summarize(trials)[0]
        self.assertEqual(result["success_rate"], 1/3)
        self.assertEqual(result["pipeline_errors"], 1)
        self.assertEqual(result["any_repeat_success_rate"], 1)

    def test_failed_provider_does_not_claim_complete_usage(self):
        from types import SimpleNamespace
        def fail(*args):
            raise TimeoutError("Model connection failed")
        agent = SimpleNamespace(isolation="test", decide=fail)
        with patch("topogym.agent_rollout.runtime.publish_segment", self.no_video), \
                patch("topogym.agent_rollout.runtime.create_agent", return_value=agent):
            result = run_repeat(self.job("provider_failed", []))
        self.assertEqual(result["status"], "pipeline_error")
        self.assertFalse(result["usage_complete"])
        self.assertEqual(result["calls"], 1)
        self.assertEqual(result["ticks"], 0)

    def test_bwrap_hides_host_and_protects_inputs(self):
        public, home, output = [self.root / name for name in ("inputs", "home", "output")]
        for path in (public, home, output, public / "scratch"):
            path.mkdir()
        secret = self.root / "hidden.txt"
        secret.write_text("not for the model")
        (public / "visible.txt").write_text("pixels")
        code = ("from pathlib import Path; "
                f"assert not Path({str(secret)!r}).exists(); "
                f"assert not Path('/proc/1/root{secret}').exists(); "
                "assert Path('/workspace/visible.txt').read_text() == 'pixels'; "
                "Path('/workspace/scratch/planning.txt').write_text('allowed'); "
                "Path('/workspace/visible.txt').write_text('forbidden')")
        args, env = sandbox_command(["/usr/bin/python3", "-c", code], public, home, output)
        result = subprocess.run(args, env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Read-only file system", result.stderr)
        self.assertEqual((public / "scratch/planning.txt").read_text(), "allowed")
        self.assertEqual((public / "visible.txt").read_text(), "pixels")

    def test_codex_thread_continuity_and_usage_without_model_calls(self):
        public, private = self.root / "codex", self.root / "codex_private"
        public.mkdir()
        private.mkdir()
        (public / "scratch").mkdir()
        agent = CodexAgent(dict(model="explicit-model"), public, private)
        self.addCleanup(agent.close)
        requests = []

        def provider(args, **kwargs):
            requests.append(args)
            response = args[args.index("--output-last-message")+1]
            (agent.output / Path(response).name).write_text(json.dumps(dict(kind="stop", code="", paths=[], reason="done")))
            return subprocess.CompletedProcess(args, 0, stdout='{"type":"thread.started","thread_id":"test-thread"}\n'
                '{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":4}}\n', stderr="")

        with patch("topogym.agent_rollout.agents.subprocess.run", provider):
            for number in (1, 2):
                decision, usage = agent.decide(dict(prompt="test", images=["inputs/front.png"]), number)
                self.assertEqual(usage["input_tokens"], 12)
                self.assertEqual(decision["kind"], "stop")
        self.assertNotIn("resume", requests[0])
        self.assertIn("resume", requests[1])
        self.assertIn("test-thread", requests[1])
        self.assertIn("/workspace/inputs/front.png", requests[0])


if __name__ == "__main__":
    unittest.main()
