"""Live SDK, fixed reset, permissions and cumulative trial budgets. No paid API."""
import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from topogym.agent_rollout.env_sdk import Environment, EnvironmentError
from topogym.agent_rollout.profiles import profile
from topogym.agent_rollout.runtime import run_repeat
from topogym.agent_rollout.suite import prepare
from topogym.agent_rollout.token_budget import TokenBudget
from topogym.agent_rollout.tool_runtime import Trial, EnvironmentServer
from topogym.agent_rollout.agents import CodexAgent
from topogym.agent_rollout.budget_proxy import BudgetProxy
from tests.check_agent_rollout_budget import FakeOpenAI, usage


class ToolChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.suite = prepare(self.root / "suite", {"counter": "topogym.agent_rollout.suite:prepare_counter"}, seed=13)

    def job(self, name="trial", **options):
        value = dict(public=str(self.root/name), private=str(self.root/(name+"_private")),
            preset=str(self.suite.parent/"counter/rollout_1.json"), repeat=1,
            agent=dict(id="test", provider="replay", mode="simulator", interaction="tools"),
            max_steps=10, max_total_steps=30, max_segments=20, max_calls=2,
            max_api_calls=100, max_resets=2, samples_per_camera=2, worker_timeout_s=120, token_limit=0)
        value.update(options)
        return value

    def trial(self, **options):
        job = self.job(**options)
        for key in ("public", "private"):
            Path(job[key]).mkdir()
        (Path(job["public"])/"scratch").mkdir()
        trial = Trial(job)
        self.addCleanup(trial.close)
        trial.start()
        server = EnvironmentServer(trial)
        self.addCleanup(server.close)
        client = Environment(server.url, server.token)
        return trial, client, server

    def test_profiles_preserve_legacy_and_separate_reset(self):
        self.assertEqual(profile(dict(mode="rgb"))["interaction"], "segments")
        self.assertEqual(profile(dict(access_mode="simulator"))["reset_policy"], "same_preset")
        self.assertEqual(profile(dict(mode="rgb", interaction="tools", reset_policy="same_preset"))["reset_policy"], "same_preset")
        for config in (dict(mode="simulator", interaction="segments"), dict(mode="rgb", reset_policy="same_preset")):
            with self.assertRaises(ValueError):
                profile(config)

    def test_reset_preserves_initial_state_history_and_token_ledger(self):
        trial, client, _ = self.trial()
        trial.budget = TokenBudget(trial.private, trial.public, 1000)
        request, _ = trial.budget.reserve(40, 20)
        trial.budget.complete(request, dict(input_tokens=40, output_tokens=10, total_tokens=50))
        start = client.get_pose("marker")["data"]
        client.step({"dx": 1}, steps=2)
        self.assertNotEqual(client.get_pose("marker")["data"], start)
        reset = client.reset()
        self.assertEqual(reset["episode_id"], 1)
        self.assertEqual(reset["total_ticks"], 2)
        self.assertEqual(reset["token_budget"]["used"], 50)
        self.assertEqual(client.get_pose("marker")["data"], start)
        self.assertEqual(trial.records[0]["initial_state_sha256"], trial.records[1]["initial_state_sha256"])
        self.assertTrue((trial.public/"episodes/episode_0/segment_1.mp4").exists())
        while trial.status == "running":
            result = client.step({"dx": 1})
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(trial.records[0]["state"], "ready")
        with self.assertRaisesRegex(EnvironmentError, "ended"):
            client.reset()

    def test_rgb_denies_hidden_state_and_reset(self):
        trial, client, server = self.trial(agent=dict(id="rgb", provider="replay", mode="rgb", interaction="tools"))
        self.assertEqual(client.observe()["data"]["observation"], {})
        self.assertEqual(client.describe()["data"]["capabilities"]["simulator"], {})
        for fn in (client.get_state, client.list_entities, lambda: client.get_pose("marker"), client.reset):
            with self.assertRaises(EnvironmentError):
                fn()
        self.assertEqual(trial.ticks, 0)
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(server.url, data=b'{}', headers={"Authorization": "Bearer invalid"}))
        self.assertEqual(caught.exception.code, 401)
        self.assertNotIn('"position"', (trial.public/"events.jsonl").read_text())

    def test_stale_and_duplicate_requests_never_reexecute(self):
        trial, client, _ = self.trial()
        request = dict(method="step", params={"action": {"dx": 1}, "steps": 1}, request_id="one", expected_revision=0)
        first = trial.dispatch(request)
        self.assertEqual(trial.dispatch(request), first)
        self.assertEqual(trial.ticks, 1)
        client.observe()
        client.reset()
        with self.assertRaisesRegex(ValueError, "Stale"):
            trial.dispatch(dict(request, request_id="late", expected_revision=1))
        self.assertEqual(trial.ticks, 1)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            trial.dispatch(dict(request, params={"action": {"dx": -1}, "steps": 1}))

    def test_step_and_reset_budgets_are_cumulative(self):
        trial, client, _ = self.trial(max_total_steps=3, max_resets=1)
        with self.assertRaises(EnvironmentError):
            client.step({"dx": 1}, steps=4)
        self.assertEqual(trial.ticks, 0)
        client.step({"dx": -1}, steps=2)
        client.reset()
        with self.assertRaisesRegex(EnvironmentError, "reset budget"):
            client.reset()
        result = client.step({"dx": 1})
        self.assertEqual(result["status"], "limit_reached")
        self.assertEqual(result["total_ticks"], 3)
        with self.assertRaises(EnvironmentError):
            client.step({"dx": 1})

    def test_api_budget_and_wall_deadline_stop_mutations(self):
        trial, client, _ = self.trial(max_api_calls=2)
        client.observe()  # The constructor already used one describe call.
        with self.assertRaisesRegex(EnvironmentError, "API call budget"):
            client.step({"dx": 1})
        self.assertEqual(trial.status, "limit_reached")
        self.assertEqual(trial.ticks, 0)
        trial.deadline = 0
        with self.assertRaisesRegex(EnvironmentError, "wall-time"):
            client.reset()

    def test_reset_after_task_failure_and_trial_close(self):
        trial, client, _ = self.trial(max_total_steps=40)
        failed = client.step({"dx": -1}, steps=10)
        self.assertEqual(failed["episode_state"], "failed")
        self.assertEqual(failed["status"], "running")
        with self.assertRaisesRegex(EnvironmentError, "Episode ended"):
            client.step({"dx": 1})
        self.assertEqual(client.reset()["episode_state"], "ready")
        trial.close()
        trial.close()
        self.assertEqual(sum(json.loads(line)["event"] == "trial_ended"
                             for line in (trial.public/"events.jsonl").read_text().splitlines()), 1)
        with self.assertRaisesRegex(EnvironmentError, "closed"):
            client.step({"dx": 1})

    def test_rgb_reset_ablation_still_has_no_state_queries(self):
        trial, client, _ = self.trial(agent=dict(id="rgb", provider="replay", mode="rgb", interaction="tools", reset_policy="same_preset"))
        client.step({"dx": -1})
        self.assertEqual(client.reset()["episode_id"], 1)
        self.assertEqual(client.observe()["data"]["observation"], {})
        with self.assertRaises(EnvironmentError):
            client.get_state()

    def test_blocked_model_budget_disables_physical_actions(self):
        trial, client, _ = self.trial()
        trial.budget = TokenBudget(trial.private, trial.public, 100)
        trial.budget.stop("token_budget_exhausted", "Input cannot fit")
        with self.assertRaises(EnvironmentError):
            client.step({"dx": 1})
        self.assertEqual(trial.ticks, 0)
        self.assertEqual(trial.status, "token_budget_exhausted")

    def test_replay_program_exercises_the_real_sdk_and_archives_results(self):
        job = self.job()
        job["agent"]["tool_script"] = '''from topogym_env import connect
env = connect()
initial = env.get_pose("marker")["data"]
env.step({"dx": -1}, steps=2)
env.reset()
assert env.get_pose("marker")["data"] == initial
while True:
    result = env.step({"dx": 1})
    if result["status"] != "running":
        break
assert result["status"] == "succeeded"
'''
        result = run_repeat(job)
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["resets"], 1)
        self.assertFalse(result["first_episode_success"])
        self.assertFalse(result["usage_complete"])
        self.assertTrue((Path(job["public"])/"trajectory.json").exists())
        records = json.loads((Path(job["private"])/"episodes.json").read_text())
        self.assertEqual(len(records), 2)

    def test_real_codex_terminal_can_call_live_sdk_with_metered_model(self):
        trial, _, server = self.trial()
        normal = FakeOpenAI()
        generation = []
        program = "from topogym_env import connect; from pathlib import Path; e=connect(); e.get_pose('marker'); e.step({'dx':0}); e.reset(); r=e.step({'dx':0}); assert r['total_ticks']==2; Path('scratch/codex-sdk-ok').write_text('ok')"

        def fake(path, payload):
            if path.endswith("input_tokens"):
                return io.BytesIO(b'{"input_tokens":40}')
            generation.append(payload)
            if len(generation) > 1:
                return normal(path, payload)
            item = dict(type="function_call", id="fc_sdk", call_id="call_sdk", status="completed",
                name="exec_command",
                arguments=json.dumps(dict(cmd="python3 -c "+__import__('shlex').quote(program),
                    yield_time_ms=10000, max_output_tokens=2000)))
            response = dict(id="resp_sdk", object="response", status="completed", model=payload["model"],
                            output=[item], usage=usage(40, 10))
            events = [dict(type="response.created", response=dict(response, status="in_progress", output=[])),
                dict(type="response.output_item.added", output_index=0, item=dict(item, status="in_progress", arguments="")),
                dict(type="response.function_call_arguments.delta", item_id="fc_sdk", output_index=0, delta=item["arguments"]),
                dict(type="response.output_item.done", output_index=0, item=item),
                dict(type="response.completed", response=response)]
            return io.BytesIO(b''.join(b'data: '+json.dumps(dict(event, sequence_number=i)).encode()+b'\n\n'
                                      for i, event in enumerate(events)))

        original = BudgetProxy.__init__
        def local_proxy(instance, *args, **kwargs):
            original(instance, *args, **dict(kwargs, transport=fake))
        with patch.dict(os.environ, CODEX_API_KEY="fake-test-key"), patch.object(BudgetProxy, "__init__", local_proxy):
            agent = CodexAgent(dict(model="gpt-6-astra", interaction="tools", token_limit=1000,
                environment_url=server.url, environment_token=server.token, timeout_s=30), trial.public, trial.private)
            self.addCleanup(agent.close)
            trial.budget = agent.budget
            agent.decide(dict(prompt="Use the environment SDK to verify reset, then return a stop decision.", images=[]), 1)
        self.assertTrue((trial.public/"scratch/codex-sdk-ok").exists(),
                        json.dumps(dict(outputs=[item for item in generation[-1].get("input", [])
                                    if item.get("type") == "function_call_output"],
                                    tools=generation[0].get("tools"))))
        self.assertEqual(trial.ticks, 2)
        self.assertEqual(trial.resets, 1)
        self.assertEqual(agent.budget.snapshot()["used"], 100)


if __name__ == "__main__":
    unittest.main()
