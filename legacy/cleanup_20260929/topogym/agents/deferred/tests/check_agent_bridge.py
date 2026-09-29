"""Irreversibility, complete feedback, accounting and harness/HTTP contracts."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import subprocess
import sys
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from topogym.agent_bridge.adapters import CounterTask
from topogym.agent_bridge.budget import Budget
from topogym.agent_bridge.client import Client
from topogym.agent_bridge.openai_harness import OpenAIResponses, run
from topogym.agent_bridge.policy import compile_policy, PolicyError
from topogym.agent_bridge.server import BridgeServer
from topogym.agent_bridge.session import Session
from topogym.agent_bridge.package import export_package


def usage(i=10, o=5):
    return dict(input_tokens=i, output_tokens=o, total_tokens=i+o,
                input_tokens_details={"cached_tokens": 3}, output_tokens_details={"reasoning_tokens": 2})


class PolicyChecks(unittest.TestCase):
    def test_observation_arithmetic_and_variable_length(self):
        actions = compile_policy('a = obs["x"]\nfor i in range(3):\n    env.step({"dx": (a+i)/2}, steps=2)', {"x": 0})
        self.assertEqual(actions, [{"dx": 0}, {"dx": 0}, {"dx": .5}, {"dx": .5}, {"dx": 1}, {"dx": 1}])

    def test_simulator_python_and_resource_escape_rejected(self):
        for source in ('env.reset()', 'import os', 'env.__class__', 'while True: pass',
                       'open("x", "w")', 'env.step({"dx": "x"*999999999})',
                       'for i in range(100001):\n env.step({"dx": 0})',
                       'env.step({"dx": 1}, steps=True)', 'x = 10 ** 9999999',
                       'for i in range(0):\n import os', 'env.step({"dx": 1e999})'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                # Nonfinite JSON is validated by the Session before execution.
                result = compile_policy(source, {})
                json.dumps(result, allow_nan=False)

    def test_nested_loops_and_large_segments_have_bounds(self):
        with self.assertRaises(PolicyError):
            compile_policy('for i in range(100000):\n for j in range(100000):\n  a = 1', {})
        with self.assertRaises(ValueError):
            compile_policy('env.step({"dx": 1}, steps=1001)', {})


class BudgetChecks(unittest.TestCase):
    def test_reserve_finalize_subsets_and_idempotency(self):
        b = Budget(100)
        b.reserve("a", 10, 20)
        self.assertEqual(b.snapshot()["remaining"], 70)
        self.assertFalse(b.snapshot()["exact"])
        b.progress("a", 6)
        b.complete("a", usage())
        b.complete("a", usage())
        self.assertEqual(b.snapshot()["used"], 15)
        self.assertEqual(b.snapshot()["remaining"], 85)
        self.assertTrue(b.snapshot()["exact"])
        with self.assertRaises(ValueError):
            b.complete("a", usage(11))

    def test_pending_call_cannot_be_freed_or_oversubscribed(self):
        b = Budget(30)
        with self.assertRaises(ValueError):
            b.reserve("a", 20, 11)
        b.reserve("a", 20, 10)
        self.assertEqual(b.snapshot()["remaining"], 0)
        with self.assertRaises(ValueError):
            b.reserve("b", 0, 1)
        self.assertEqual(b.snapshot()["used"], 0)

    def test_invalid_and_manual_usage(self):
        for limit in (0, -1, True, 2_000_001):
            with self.assertRaises(ValueError):
                Budget(limit)
        b = Budget(10, "manual")
        b.estimate("a", 20, 5)
        self.assertEqual(b.snapshot()["used"], 25)
        self.assertTrue(b.snapshot()["over_budget"])
        self.assertFalse(b.snapshot()["exact"])


class SessionChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/"episode"

    def tearDown(self):
        self.temp.cleanup()

    def create(self, factory=CounterTask, **kwargs):
        return Session(factory, self.root, **{"mode": "manual", **kwargs})

    def submit(self, s, code, n=1, **kwargs):
        return s.submit(request_id=f"r{n}", expected_segment=n, code=code, **kwargs)

    def test_complete_multiview_frames_and_success_stops_segment(self):
        s = self.create()
        self.submit(s, 'env.step({"dx": 1}, steps=20)')
        m = json.loads((self.root/"segment_001/manifest.json").read_text())
        self.assertEqual(m["executed_steps"], 3)
        self.assertEqual(len(m["frames"]), 4)
        self.assertEqual(s.state, "succeeded")
        for tick, frame in enumerate(m["frames"]):
            self.assertEqual(frame["tick"], tick)
            self.assertEqual(set(frame["cameras"]), {"front", "top"})
            for data in frame["cameras"].values():
                raw = (self.root/data["path"]).read_bytes()
                self.assertEqual(data["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(s.snapshot()["success_within_budget"])
        with self.assertRaises(ValueError):
            self.submit(s, 'env.step({"dx": -1})', 2)

    def test_retry_and_stale_requests_do_not_step(self):
        s = self.create()
        code = 'env.step({"dx": 1})'
        a = self.submit(s, code)
        self.assertEqual(a, self.submit(s, code))
        self.assertEqual(s.tick, 1)
        with self.assertRaises(ValueError):
            self.submit(s, 'env.step({"dx": -1})')
        with self.assertRaises(ValueError):
            s.submit(request_id="new", expected_segment=1, code=code)
        self.assertEqual(s.tick, 1)

    def test_all_actions_prevalidated_and_no_reopen(self):
        s = self.create()
        with self.assertRaises(ValueError):
            self.submit(s, 'env.step({"dx": 1})\nenv.step({"dx": 99})')
        self.assertEqual(s.adapter.x, 0)
        self.assertEqual(s.state, "ready")
        with self.assertRaises(FileExistsError):
            self.create()
        with self.assertRaises(ValueError):
            s.finish(outcome="succeeded")

    def test_partial_physics_error_is_terminal_and_not_replayed(self):
        class Broken(CounterTask):
            def step(self, action):
                super().step(action)
                if self.x == 2:
                    raise RuntimeError("solver failed after mutation")
        s = self.create(Broken)
        code = 'env.step({"dx": 1}, steps=3)'
        result = self.submit(s, code)
        m = json.loads((self.root/result["manifest"]).read_text())
        self.assertEqual(s.adapter.x, 2)
        self.assertEqual(s.state, "failed")
        self.assertEqual((m["attempted_steps"], m["executed_steps"], len(m["frames"])), (2, 1, 2))
        self.submit(s, code)
        self.assertEqual(s.adapter.x, 2)

    def test_partial_render_failure_keeps_recorded_feedback(self):
        class Broken(CounterTask):
            def render(self):
                if self.x == 2:
                    raise RuntimeError("camera lost")
                return super().render()
        s = self.create(Broken)
        r = self.submit(s, 'env.step({"dx": 1}, steps=3)')
        self.assertEqual(r["executed_steps"], 2)
        self.assertEqual(s.state, "failed")
        self.assertTrue((self.root/"segment_001/front/000001.png").exists())

    def test_metered_action_needs_new_final_receipt_and_prompt_updates(self):
        s = self.create(mode="metered", token_limit=100)
        with self.assertRaises(ValueError):
            self.submit(s, 'env.step({"dx": 1})')
        s.usage("reserve", call_id="call", input_tokens=10, max_output_tokens=20)
        self.assertIn("你还剩 70 tokens", s.prompt())
        with self.assertRaises(ValueError):
            self.submit(s, 'env.step({"dx": 1})', call_id="call")
        s.usage("complete", call_id="call", usage=usage())
        self.assertIn("你还剩 85 tokens", s.prompt())
        self.submit(s, 'env.step({"dx": 1})', call_id="call")
        with self.assertRaises(ValueError):
            self.submit(s, 'env.step({"dx": 1})', 2, call_id="call")

    def test_budget_exhaustion_and_overrun_block_actions(self):
        s = self.create(mode="metered", token_limit=15)
        s.usage("reserve", call_id="call", input_tokens=10, max_output_tokens=5)
        s.usage("complete", call_id="call", usage=usage())
        self.assertEqual(s.state, "budget_exhausted")
        with self.assertRaises(ValueError):
            self.submit(s, 'env.step({"dx": 1})', call_id="call")

    def test_reservation_violation_records_usage_and_fails(self):
        s = self.create(mode="metered", token_limit=100)
        s.usage("reserve", call_id="call", input_tokens=10, max_output_tokens=5)
        s.usage("complete", call_id="call", usage=usage(11, 6))
        self.assertEqual(s.state, "failed")
        self.assertEqual(s.snapshot()["budget"]["used"], 17)

    def test_only_public_artifacts_are_readable(self):
        s = self.create()
        self.assertTrue(s.artifact("initial/front/000000.png").is_file())
        for path in ("../episode/session.json", "session.json", "/etc/passwd", "private_assets/config.yaml"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                s.artifact(path)

    def test_tool_freedom_does_not_publish_solutions_and_network_switch_persists(self):
        s = self.create(allow_internet=False)
        policy = s.snapshot()["tool_policy"]
        self.assertEqual(policy["local_tools"], "unrestricted")
        self.assertFalse(policy["allow_internet"])
        self.assertIn("existing solutions and demo videos", policy["forbidden_references"])
        self.assertIn("Internet research, downloads and remote tools are disabled", s.prompt())
        self.assertIn("Do not read repository", s.prompt())
        self.assertEqual(json.loads((self.root/"session.json").read_text())["tool_policy"], policy)

    def test_manual_prompt_does_not_claim_unmeasured_remaining_tokens(self):
        s = self.create()
        self.assertTrue(s.snapshot()["tool_policy"]["allow_internet"])
        self.assertIn("真实剩余 tokens 未知", s.prompt())
        self.assertNotIn("你还剩 2,000,000", s.prompt())
        s.usage("estimate", call_id="estimate", input_tokens=100, output_tokens=20)
        self.assertIn("估算剩余 1,999,880", s.prompt())
        self.assertIn("真实余额未知", s.prompt())

    def test_task_references_are_copied_and_explicitly_allowlisted(self):
        class ReferenceTask(CounterTask):
            def __init__(self, asset_dir):
                super().__init__()
                asset_dir.mkdir()
                (asset_dir/"goal.json").write_text('{"goal":3}')
                (asset_dir/"secret.json").write_text('{"answer":"private"}')
                self.public_assets = {"goal.json": asset_dir/"goal.json"}
        s = self.create(factory=ReferenceTask)
        asset = s.snapshot()["task"]["public_assets"][0]
        self.assertEqual(asset["path"], "public_assets/goal.json")
        self.assertEqual(hashlib.sha256(s.artifact(asset["path"]).read_bytes()).hexdigest(), asset["sha256"])
        (self.root/"public_assets/unlisted.json").write_text("{}")
        for name in ("private_assets/secret.json", "private_assets/goal.json", "public_assets/unlisted.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                s.artifact(name)
        self.assertEqual(s.tick, 0)

    def test_task_reference_images_are_rejected_before_render_or_step(self):
        class ReferenceImageTask(CounterTask):
            def __init__(self, asset_dir):
                super().__init__()
                self.public_assets = {"reference.png": asset_dir/"reference.png"}
            def render(self):
                raise AssertionError("Task with forbidden references must fail before rendering")
        with self.assertRaisesRegex(ValueError, "reference images are not permitted"):
            self.create(factory=ReferenceImageTask)
        self.assertFalse((self.root/"public_assets").exists())
        self.assertEqual(json.loads((self.root/"session.json").read_text())["tick"], 0)


class HTTPChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = BridgeServer(("127.0.0.1", 0), CounterTask, Path(self.temp.name)/"episode", mode="metered", token_limit=5000)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client(f"http://127.0.0.1:{self.server.server_port}")

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temp.cleanup()

    def test_http_dashboard_and_cross_origin(self):
        html = self.client.request("/", raw=True)
        self.assertIn(b"remaining", html)
        with self.assertRaises(ValueError):
            self.client.request("/artifacts/../session.json")
        request = Request(self.client.base_url+"/v1/finish", data=b"{}",
                          headers={"Content-Type": "application/json", "X-TopoGym": "1", "Origin": "https://example.com"})
        with self.assertRaises(HTTPError):
            urlopen(request)

    def test_reference_harness_with_mock_provider_and_history_inspection(self):
        class Provider:
            calls = 0
            def count(self, payload):
                return 100
            def generate(self, payload, on_progress):
                self.calls += 1
                on_progress(20)
                command = ({"action": "inspect", "frames": ["initial/manifest.json"]} if self.calls == 1 else
                           {"action": "segment", "code": 'env.step({"dx": 1}, steps=3)'})
                return dict(status="completed", id=f"resp_{self.calls}", usage=usage(100, 20),
                            output=[dict(type="message", content=[dict(type="output_text", text=json.dumps(command))])])
        provider = Provider()
        result = run(self.client, provider, model="mock", max_output_tokens=50)
        self.assertEqual(result["state"], "succeeded")
        self.assertTrue(result["success_within_budget"])
        self.assertEqual(result["budget"]["used"], 240)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(result["tick"], 3)

    def test_ambiguous_model_failure_keeps_reservation(self):
        class Provider:
            def count(self, payload):
                return 100
            def generate(self, payload, on_progress):
                raise RuntimeError("network lost")
        with self.assertRaises(RuntimeError):
            run(self.client, Provider(), model="mock", max_output_tokens=50)
        state = self.client.state()
        self.assertEqual(state["state"], "failed")
        self.assertEqual(state["budget"]["reserved"], 150)
        self.assertFalse(state["budget"]["exact"])
        self.assertEqual(state["tick"], 0)

    def test_standalone_solver_client_observes_submits_and_retries(self):
        from topogym.agent_bridge import client as client_module
        folder = Path(self.temp.name)/"solver"
        folder.mkdir()
        script = folder/"bridge_client.py"
        script.write_bytes(Path(client_module.__file__).read_bytes())

        def command(*args):
            result = subprocess.run([sys.executable, str(script), "--url", self.client.base_url, *args],
                                    cwd=folder, text=True, capture_output=True, check=True)
            return json.loads(result.stdout)

        observation = command("observe")
        self.assertEqual(observation["expected_segment"], 1)
        self.assertEqual(len(observation["images"]), 2)
        self.assertTrue(Path(observation["prompt"]).exists())
        for path in observation["images"]:
            self.assertTrue(Path(path).read_bytes().startswith(b"\x89PNG"))
        self.client.request("/v1/usage/reserve", dict(call_id="cli-call", input_tokens=10, max_output_tokens=20))
        self.client.request("/v1/usage/complete", dict(call_id="cli-call", usage=usage()))
        policy = folder/"policy.py"
        policy.write_text('env.step({"dx": 1}, steps=2)')
        result = command("submit", "policy.py", "--request-id", "seg001", "--expected-segment", "1", "--call-id", "cli-call")
        policy.write_text('env.step({"dx": -1})')
        self.assertEqual(command("retry", "--request-id", "seg001"), result)
        self.assertEqual(self.client.state()["tick"], 2)
        all_frames = command("observe", "--all-frames")
        self.assertEqual(len(all_frames["images"]), 6)
        saved = json.loads((folder/"requests/seg001.json").read_text())
        self.assertEqual(saved["code"], 'env.step({"dx": 1}, steps=2)')
        with self.assertRaises(subprocess.CalledProcessError):
            command("submit", "policy.py", "--request-id", "seg001", "--expected-segment", "1", "--call-id", "cli-call")
        self.assertEqual(self.client.state()["tick"], 2)

    def test_fresh_package_contains_only_public_inputs_and_runs_offline_brief(self):
        folder = Path(self.temp.name)/"fresh_solver"
        export_package(self.client, folder, "new_episode")
        config = json.loads((folder/"bridge_config.json").read_text())
        self.assertEqual(config["tool_policy"], self.client.state()["tool_policy"])
        result = subprocess.run([sys.executable, str(folder/"bridge_client.py"), "brief"],
                                cwd=folder, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["task"]["task_id"], "counter_smoke")
        observation = subprocess.run([sys.executable, str(folder/"bridge_client.py"), "observe"],
                                    cwd=folder, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(observation.stdout)["tool_policy"], config["tool_policy"])
        self.assertFalse((folder/"policies").exists())
        self.assertFalse((folder/"private_assets").exists())
        self.assertEqual(self.client.state()["tick"], 0)
        self.client.request("/v1/finish", dict(reason="test finished"))
        with self.assertRaises(ValueError):
            export_package(self.client, Path(self.temp.name)/"stale", "stale")

    def test_package_rejects_legacy_references_without_copying_or_downloading(self):
        from types import SimpleNamespace
        state = self.client.state()
        state["task"]["goal_reference"] = {"image": "public_assets/goal_reference.png"}
        client = SimpleNamespace(state=lambda: state)
        output = Path(self.temp.name)/"legacy_package"
        with self.assertRaisesRegex(ValueError, "reference assets"):
            export_package(client, output, "legacy")
        self.assertFalse(output.exists())


class StreamingChecks(unittest.TestCase):
    def test_terminal_usage_and_text_progress(self):
        events = [dict(type="response.output_text.delta", delta="hello"),
                  dict(type="response.completed", response=dict(status="completed", usage=usage()))]
        stream = io.BytesIO(b"".join(b"data: "+json.dumps(e).encode()+b"\n\n" for e in events))
        counts = []
        with patch("topogym.agent_bridge.openai_harness.urlopen", return_value=stream):
            result = OpenAIResponses("test").generate({}, counts.append)
        self.assertEqual(result["usage"]["total_tokens"], 15)
        self.assertEqual(counts, [5])

    def test_missing_usage_is_never_treated_as_zero(self):
        with patch("topogym.agent_bridge.openai_harness.urlopen", return_value=io.BytesIO(b"data: [DONE]\n")):
            with self.assertRaises(RuntimeError):
                OpenAIResponses("test").generate({}, lambda n: None)


if __name__ == "__main__":
    unittest.main()
