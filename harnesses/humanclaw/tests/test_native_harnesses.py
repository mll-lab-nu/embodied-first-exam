"""Exercise cross-harness contracts, failure accounting and native protocols."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import re
import threading
from types import SimpleNamespace
import urllib.request

from PIL import Image
import pytest

from humanclaw_bench.agent.skills import normalize_action
from humanclaw_bench.config import load_config
from humanclaw_bench.experiments.integration import SKILLS, register_capabilities
from humanclaw_bench.experiments.recorder import TraceRecorder, event, span
from humanclaw_bench.experiments.report import read_events, summarize_run, validate_trace
from humanclaw_bench.harnesses.environment import (
    ACTION_NAMES, NATIVE_ACTION_PROTOCOL, EnvironmentBridge, protocol_identity, tool_definitions,
)
from humanclaw_bench.harnesses.native_events import NativeEvents
from humanclaw_bench.harnesses import runtime
from humanclaw_bench.harnesses.runtime import NativeHarness, child_environment, load_harness_config, native_paper_cost
from humanclaw_bench.harnesses.services import LocalServices, flattened_tools
from humanclaw_bench.harnesses.smoke import MOCK_USAGE, ScriptedResponses, run_smoke


# The two model-visible environment facts; no sit procedure (PSV has its own).
SIT_FACT = "one call moves for only about 0.5 s and may not complete sitting down"
STOP_FACT = "submits the current pose as the final pose and ends the episode; no further motion is generated"
MOTION_FACTS = {"sit": SIT_FACT, "stand": STOP_FACT}
STRATEGY_WORDS = re.compile(r"\b(again|repeat\w*|several|behind|turn\w*)\b", re.IGNORECASE)
# Opt-in: a harness config whose Codex/Pi commands run on this host (no paid API).
NATIVE_CHECK_CONFIG = os.environ.get("HUMANCLAW_NATIVE_CHECK_CONFIG")


@pytest.fixture(autouse=True)
def local_http_without_proxy(monkeypatch):
    """Never send the test session credentials through a host's HTTP proxy."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


def args(step=0, ident="move", action="Walk<forward><slow>"):
    return {"request_id": ident, "observation_id": step, "action_name": action,
            "visible_state": "The bed is visible ahead; the lane is clear."}


def bridge(execute=None, max_steps=5):
    image = Image.new("RGB", (8, 8), "blue")
    return EnvironmentBridge(image, max_steps, execute or (lambda step, decision: (image, False)), "Find the bed.")


def entries(summary):
    return {(row["kind"], row["name"]): row for row in summary["capabilities"]["entries"]}


def test_actions_are_idempotent_stale_requests_rejected_and_stop_terminal(tmp_path):
    executed = []
    def execute(step, decision):
        executed.append((step, decision))
        with span(decision.action.skill, kind="tool"):
            return Image.new("RGB", (8, 8), "green"), False
    env = bridge(execute)
    with TraceRecorder(tmp_path, {}) as recorder:
        register_capabilities("codex")
        first = env.call("walk_forward", args())
        assert env.call("walk_forward", args()) == first
        assert env.call("walk_forward", args(ident="stale"))["isError"]
        assert env.call("walk_forward", args(1, "move"))["isError"]
        assert env.call("turn", args(True, "boolean"))["isError"]
        assert not env.call("stand", args(1, "stop", "Stop/Stand"))["isError"]
        assert env.call("walk_forward", args(2, "after_stop"))["isError"]
    assert len(executed) == 2
    assert executed[0][1].planner_skill["visible_state"] == args()["visible_state"]
    assert executed[1][1].action.cond is None
    assert env.done and env.termination == "stop"
    assert validate_trace(recorder.directory)["ok"]
    counts = entries(summarize_run(recorder.directory))
    assert counts["tool", "walk_forward"]["requested"] == 5
    assert counts["tool", "walk_forward"]["executed"] == 1
    assert counts["tool", "walk_forward"]["rejected"] == 3
    assert counts["tool", "walk_forward"]["failure_rate"] == 0


def test_parallel_actions_cannot_act_on_one_stale_frame_and_partial_failure_is_terminal():
    env = bridge()
    one = env.submit("walk_forward", args(ident="one"))
    two = env.submit("walk_forward", args(ident="two"))
    env.drain()
    assert not one.result()["isError"] and two.result()["isError"]
    assert env.step == 1
    with ThreadPoolExecutor() as pool:
        with pytest.raises(RuntimeError, match="simulator thread"):
            pool.submit(env.call, "stand", args(1)).result()
    calls = []
    def fail(step, decision):
        calls.append(decision)
        raise RuntimeError("physics failed after starting the action")
    env = bridge(fail)
    request = env.submit("walk_forward", args())
    with pytest.raises(RuntimeError, match="physics failed"):
        env.drain()
    assert isinstance(request.exception(), RuntimeError)
    assert env.call("walk_forward", args())["isError"]
    assert len(calls) == 1


@pytest.mark.parametrize("name,action,expected", [
    ("walk_forward", "Walk<forward><fast>", [0.0, 0.6, 0.0]),
    ("stand", "Stop/Stand", None), ("turn", "Turn<right><999>", -120),
    ("step_climb_up", "Climb upstairs<normal>", [0.28, 0.30]),
    ("sit", "Sit down<99>", 0.85), ("step_back", "Step back<99>", [0, -0.6]),
    ("side_walk", "Side step<right><99>", -0.5),
    ("step_climb_down", "Walk downstairs<normal>", [0.2, 0.4]),
])
def test_all_harnesses_share_benchmark_action_conversion(name, action, expected):
    result = normalize_action({"action_id": SKILLS.index(name), "action_name": action})
    assert result.skill == name and result.cond == expected
    assert {tool["name"] for tool in tool_definitions()} == set(SKILLS)


def test_native_interleaving_does_not_invent_parents_or_double_count_environment(tmp_path):
    with TraceRecorder(tmp_path, {}) as recorder:
        with span("harness.session") as parent:
            native = NativeEvents("pi")
            for ident in ("a", "b"):
                native.consume({"type": "tool_execution_start", "toolCallId": ident, "toolName": "bash", "args": {}})
            native.consume({"type": "tool_execution_end", "toolCallId": "a", "isError": True})
            native.consume({"type": "tool_execution_end", "toolCallId": "b", "isError": False})
            native.consume({"type": "tool_execution_start", "toolCallId": "env", "toolName": "mcp__humanclaw__stand", "args": {}})
            with span("stand", kind="tool"):
                pass
            native.consume({"type": "tool_execution_end", "toolCallId": "env", "isError": False})
            native.close()
    rows = read_events(recorder.directory)
    starts = [row for row in rows if row["event"] == "span.start" and row["name"] == "pi.bash"]
    assert {row["parent_span_id"] for row in starts} == {parent.span_id}
    summary = summarize_run(recorder.directory)
    counts = entries(summary)
    assert counts["tool", "pi.bash"]["failure_rate"] == 0.5
    assert counts["tool", "stand"]["executed"] == 1
    assert counts["module", "pi.environment_dispatch"]["executed"] == 1
    assert counts["tool", "pi.bash"]["latency"]["p95_ms"] is not None
    assert validate_trace(recorder.directory)["ok"]


def test_provider_boundary_counts_usage_once_and_exposures_match_native_names(tmp_path):
    env = bridge()
    payload = {"model": "mock", "tools": [
        {"type": "function", "name": "bash"},
        {"type": "namespace", "name": "mcp__humanclaw", "tools": [
            {"type": "function", "name": "walk_forward"}]}]}
    provider = ScriptedResponses()
    with TraceRecorder(tmp_path, {}) as recorder:
        with LocalServices(env, responder=provider, harness="pi") as services:
            request = urllib.request.Request(services.url + "/v1/responses", data=json.dumps(payload).encode(),
                headers={"Authorization": "Bearer " + services.bearer, "Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                assert b"response.completed" in response.read()
            for _ in range(3):
                event("native.event", kind="native", name="pi", data={"type": "message_update", "usage": MOCK_USAGE})
            native = NativeEvents("pi")
            native.consume({"type": "tool_execution_start", "toolCallId": "bash", "toolName": "bash", "args": {}})
            native.consume({"type": "tool_execution_end", "toolCallId": "bash", "isError": False})
    summary = summarize_run(recorder.directory)
    assert summary["model_usage"]["tokens"]["total_tokens"]["total"] == 150
    assert summary["model_usage"]["tokens"]["cached_input_tokens"]["total"] == 20
    assert summary["cost"]["total_usd"] is None
    counts = entries(summary)
    assert counts["tool", "pi.bash"]["exposed"] == counts["tool", "pi.bash"]["executed"] == 1
    assert counts["tool", "walk_forward"]["exposed"] == 1
    assert counts["tool", "walk_forward"]["requested"] == 1
    assert counts["tool", "walk_forward"]["executed"] == 0
    assert validate_trace(recorder.directory)["ok"]


def test_mcp_transport_auth_discovery_and_main_thread_execution(tmp_path):
    owners = []
    def execute(step, decision):
        owners.append(threading.get_ident())
        return Image.new("RGB", (8, 8)), True
    env = bridge(execute)
    with TraceRecorder(tmp_path, {}):
        with LocalServices(env, responder=ScriptedResponses()) as services:
            def post(method, params=None, authorized=True):
                body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
                request = urllib.request.Request(services.url + "/mcp", data=json.dumps(body).encode(),
                    headers={"Authorization": "Bearer " + (services.bearer if authorized else "wrong")})
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.load(response)
            with pytest.raises(urllib.error.HTTPError) as error:
                post("initialize", authorized=False)
            assert error.value.code == 401
            assert post("initialize", {"protocolVersion": "2025-03-26"})["result"]["capabilities"] == {"tools": {}}
            assert len(post("tools/list")["result"]["tools"]) == 8
            with ThreadPoolExecutor() as pool:
                future = pool.submit(post, "tools/call", {"name": "stand", "arguments": args(action="Stop/Stand")})
                # Block for the queued request, not a timing-sensitive sleep.
                name, arguments, completion = env.pending.get(timeout=5)
                env.pending.put((name, arguments, completion))
                env.drain()
                assert not future.result()["result"]["isError"]
            assert owners == [threading.get_ident()]


def served_tools(harness):
    """List the environment tools exactly as the loopback MCP endpoint serves them."""
    with LocalServices(bridge(), responder=ScriptedResponses(), harness=harness) as services:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        request = urllib.request.Request(services.url + "/mcp", data=json.dumps(body).encode(),
                                         headers={"Authorization": "Bearer " + services.bearer})
        with urllib.request.urlopen(request, timeout=5) as response:
            return {tool["name"]: tool for tool in json.load(response)["result"]["tools"]}


def action_name_text(tool, schema="inputSchema"):
    """Return the action_name property description of an MCP or provider tool."""
    return tool[schema]["properties"]["action_name"]["description"]


@pytest.mark.parametrize("harness", ["codex", "pi"])
def test_served_sit_and_stop_tools_state_motion_facts_without_strategy(harness):
    tools = served_tools(harness)
    assert tools == {tool["name"]: tool for tool in tool_definitions()}
    for name, fact in MOTION_FACTS.items():
        for text in (tools[name]["description"], action_name_text(tools[name])):
            assert fact in text
            assert STRATEGY_WORDS.search(text) is None
    assert ACTION_NAMES[SKILLS.index("sit")] == f"Sit down<height> (height clamped to 0.15–0.85 metres; {SIT_FACT})"
    assert ACTION_NAMES[SKILLS.index("stand")] == f"Stop/Stand ({STOP_FACT})"
    assert max(len(tool["description"]) for tool in tools.values()) <= 512


def test_sit_duration_fact_is_one_paper_motion_chunk():
    profile = load_config("paper_fullval_v1")
    manifest = json.loads(profile.path_value("motion", "weights_manifest").read_text())
    # Each Sit plays one generated chunk: n_future frames at the physics frame rate.
    assert manifest["base"]["architecture"]["n_future"] / profile.section("physics")["fps"] == 0.5


def test_native_action_protocol_is_recorded_with_the_session_prompt(tmp_path):
    env = bridge()
    with TraceRecorder(tmp_path, {}) as recorder:
        env.initial_prompt()
    rows = [row for row in read_events(recorder.directory) if row["event"] == "environment.protocol"]
    assert [row["data"] for row in rows] == [protocol_identity()]
    assert rows[0]["data"]["protocol"] == NATIVE_ACTION_PROTOCOL == "native-actions-v2"
    assert validate_trace(recorder.directory)["ok"]
    assert summarize_run(recorder.directory)["capabilities"]["entries"] == []


def delivered_definitions(directory):
    """Collect the benchmark tool definitions native clients sent to the model."""
    found = defaultdict(list)
    for row in read_events(directory):
        if row["event"] == "capability.exposed" and row["name"] in SKILLS:
            found[row["name"]].append(row["data"]["definition"])
    return found


@pytest.mark.skipif(not NATIVE_CHECK_CONFIG, reason="set HUMANCLAW_NATIVE_CHECK_CONFIG to run real Codex/Pi")
@pytest.mark.parametrize("harness", ["codex", "pi"])
def test_real_native_clients_deliver_sit_and_stop_facts_to_the_model(harness, tmp_path):
    result = run_smoke(harness, NATIVE_CHECK_CONFIG, tmp_path)
    # Not result["passed"]: its native shell check needs a host sandbox (Codex needs bwrap).
    assert result["error"] is None and result["trace_valid"], result
    directory = Path(result["experiment_dir"])
    served = {tool["name"]: tool for tool in tool_definitions()}
    delivered = delivered_definitions(directory)
    assert set(delivered) == set(SKILLS)
    for name in MOTION_FACTS:
        for definition in delivered[name]:
            assert definition["description"] == served[name]["description"]
            assert action_name_text(definition, "parameters") == action_name_text(served[name])
    protocols = [row["data"] for row in read_events(directory) if row["event"] == "environment.protocol"]
    assert protocols == [protocol_identity()]


def test_native_child_environment_and_config_do_not_inherit_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "private-azure-value")
    monkeypatch.setenv("UNEXPECTED_PROVIDER_SECRET", "private-other-value")
    monkeypatch.setenv("CODEX_HOME", "/private/personal-config")
    child = child_environment(tmp_path)
    assert child["HOME"] == str(tmp_path)
    assert not any("private-" in value for value in child.values())
    assert "CODEX_HOME" not in child
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"api_key": "not-allowed"}))
    with pytest.raises(ValueError, match="api_key_env"):
        load_harness_config(path)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True, "180"])
def test_startup_timeout_rejects_invalid_values(tmp_path, timeout):
    path = tmp_path / "native.json"
    path.write_text(json.dumps({"startup_timeout_seconds": timeout}))
    with pytest.raises(ValueError, match="startup_timeout_seconds must be positive and finite"):
        load_harness_config(path)


def test_slow_native_discovery_can_finish_before_configured_startup_deadline(tmp_path, monkeypatch):
    path = tmp_path / "native.json"
    path.write_text(json.dumps({"startup_timeout_seconds": 180}))
    harness = NativeHarness("pi", load_harness_config(path), {"model": "mock"})
    clock = [100.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    services = SimpleNamespace(tools_listed=threading.Event())

    def poll(_bridge, deadline):
        clock[0] = 145.0  # A cold process exceeds the previous 30-second limit.
        if clock[0] >= deadline:
            raise TimeoutError("Native harness episode timeout")
        services.tools_listed.set()

    harness._wait_for_tools(SimpleNamespace(poll=poll), services, None, 500)
    assert services.tools_listed.is_set()


@pytest.mark.parametrize("episode_deadline,expected", [
    (500, "pi environment-tool discovery timed out after 180s"),
    (120, "Native harness episode timeout"),
])
def test_discovery_timeout_is_distinct_and_cannot_extend_episode_budget(monkeypatch, episode_deadline, expected):
    harness = NativeHarness("pi", {"startup_timeout_seconds": 180}, {"model": "mock"})
    clock = [100.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    services = SimpleNamespace(tools_listed=threading.Event())

    def poll(_bridge, deadline):
        assert deadline == min(episode_deadline, 280)
        clock[0] = deadline
        raise TimeoutError("Native harness episode timeout")

    with pytest.raises(TimeoutError, match=expected):
        harness._wait_for_tools(SimpleNamespace(poll=poll), services, None, episode_deadline)


def test_flatten_responses_tools_preserves_namespaces():
    assert list(flattened_tools([{"type": "namespace", "name": "env", "tools": [
        {"type": "function", "name": "move"}]}])) == [("env", {"type": "function", "name": "move"})]


def test_incomplete_native_operations_are_not_reported_as_resolved_failures(tmp_path):
    with TraceRecorder(tmp_path, {}) as recorder:
        native = NativeEvents("pi")
        native.consume({"type": "tool_execution_start", "toolCallId": "unfinished", "toolName": "bash"})
        native.close()
    entry = entries(summarize_run(recorder.directory))["tool", "pi.bash"]
    assert entry["interrupted"] == 1
    assert entry["failed"] == 0 and entry["failure_rate"] is None


def test_native_paper_usage_keeps_missing_provider_usage_unknown():
    summary = native_paper_cost([MOCK_USAGE, {}], 2)
    assert summary["vlm_calls"] == 2
    assert summary["input_tokens"] is None
    assert summary["visible_output_tokens_per_step"] is None
    assert summary["token_source"] == "provider_partial"


def test_http_retry_unknown_usage_redaction_and_common_request_limits(tmp_path, monkeypatch):
    real_urlopen = urllib.request.urlopen
    upstream_requests = []
    class Response(io.BytesIO):
        headers = {"Content-Type": "application/json"}
    def upstream(request, **kwargs):
        if request.full_url != "https://upstream.invalid/responses":
            return real_urlopen(request, **kwargs)
        assert request.get_header("Api-key") == "private-provider-credential"
        upstream_requests.append(json.loads(request.data))
        if len(upstream_requests) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "rate limited", {}, io.BytesIO(b'{"error":"rate limited"}'))
        return Response(json.dumps({"id": "response", "output": [], "usage": MOCK_USAGE, "status": "completed"}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", upstream)
    with TraceRecorder(tmp_path, {}) as recorder:
        with LocalServices(bridge(), upstream_url="https://upstream.invalid/responses",
                           api_key="private-provider-credential", model_options={
                               "model": "mock", "max_tokens": 4096, "send_temperature": False}) as services:
            request = urllib.request.Request(services.url + "/v1/responses",
                data=json.dumps({"model": "mock", "max_output_tokens": 9999, "temperature": 0.7}).encode(),
                headers={"Authorization": "Bearer " + services.bearer})
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            assert error.value.code == 429
            with urllib.request.urlopen(request) as response:
                assert b"response.completed" in response.read()
    assert len(upstream_requests) == 2
    assert all(row["max_output_tokens"] == 4096 and "temperature" not in row for row in upstream_requests)
    summary = summarize_run(recorder.directory)
    assert summary["model_usage"]["leaf_model_calls"] == 2
    assert summary["model_usage"]["status_counts"] == {"failed": 1, "completed": 1}
    assert summary["model_usage"]["tokens"]["total_tokens"]["total"] is None
    assert summary["model_usage"]["tokens"]["total_tokens"]["known_subtotal"] == 150
    assert "private-provider-credential" not in (recorder.directory / "events.jsonl").read_text()
    assert validate_trace(recorder.directory)["ok"]


def test_magpie_responses_forwards_bearer_images_and_tool_continuation(tmp_path, monkeypatch):
    real_urlopen = urllib.request.urlopen
    requests = []

    class Response(io.BytesIO):
        headers = {"Content-Type": "text/event-stream"}

    def upstream(request, **kwargs):
        if request.full_url != "http://magpie.invalid/v1/responses":
            return real_urlopen(request, **kwargs)
        assert request.get_header("Authorization") == "Bearer private-gateway-key"
        assert request.get_header("Api-key") is None
        requests.append(json.loads(request.data))
        output = ([{"type": "function_call", "name": "mcp__humanclaw__stand", "call_id": "call_1",
                    "arguments": json.dumps(args(action="Stop/Stand"))}] if len(requests) == 1 else [])
        result = {"type": "response.completed", "response": {
            "id": "resp_test", "status": "completed", "output": output, "usage": MOCK_USAGE}}
        return Response(b"data: " + json.dumps(result).encode() + b"\n\ndata: [DONE]\n\n")

    monkeypatch.setattr(urllib.request, "urlopen", upstream)
    with TraceRecorder(tmp_path, {}) as recorder:
        with LocalServices(bridge(), upstream_url="http://magpie.invalid/v1/responses",
                           api_key="private-gateway-key", azure=False, model_options={
                               "model": "codex/gpt-6-astra", "max_tokens": 4096,
                               "send_max_tokens": False, "send_temperature": False}) as services:
            inputs = [[{"role": "user", "content": [{"type": "input_image", "image_url": "data:image/png;base64,aW1hZ2U="}]}],
                      [{"type": "function_call_output", "call_id": "call_1", "output": "result"}]]
            for content in inputs:
                request = urllib.request.Request(services.url + "/v1/responses", data=json.dumps({
                    "model": "codex/gpt-6-astra", "input": content, "max_output_tokens": 100,
                    "temperature": 0.7, "stream": True, "reasoning": {"effort": "medium"}}).encode(),
                    headers={"Authorization": "Bearer " + services.bearer})
                with urllib.request.urlopen(request) as response:
                    assert b"response.completed" in response.read()
            assert services.usage == [MOCK_USAGE, MOCK_USAGE]
            assert "call_1" in services.requested_calls
    assert [item["input"] for item in requests] == inputs
    assert all("max_output_tokens" not in item and "temperature" not in item for item in requests)
    assert all(item["reasoning"] == {"effort": "medium"} and item["stream"] for item in requests)
    assert "private-gateway-key" not in (recorder.directory / "events.jsonl").read_text()
