"""Behavioral tests: physical side effects, actual HTTP transport and accounting."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
import urllib.request

import pytest

from humanclaw_bench.experiments.recorder import TraceRecorder, span
from humanclaw_bench.libero.backend import MockBackend
from humanclaw_bench.libero.protocol import ToolService
from humanclaw_bench.libero.service import MeteredService
from humanclaw_bench.libero.report import summarize


@pytest.fixture
def bridge(tmp_path):
    b = ToolService(MockBackend(), "test-run", tmp_path, max_calls=5)
    yield b
    b.shutdown()


def move(bridge, rid="a", obs=0, delta=2):
    return bridge.call_tool("move", {"request_id": rid, "observation_id": obs, "delta": delta})


def test_duplicate_retransmission_does_not_execute_again(bridge):
    first = move(bridge)
    assert move(bridge) == first
    assert bridge.backend.position == 2
    assert bridge.backend.control_steps == 1
    assert move(bridge, delta=3)["error"] == "request_id_conflict"
    assert move(bridge, rid="next", obs=0)["status"] == "rejected"
    assert bridge.backend.position == 2


def test_partial_execution_is_never_retried(bridge):
    def fail(*_):
        bridge.backend.control_steps += 1
        raise RuntimeError("failure after sending actuator command")
    bridge.backend.dispatch = fail
    first = move(bridge)
    assert first["status"] == "indeterminate"
    assert first["control_steps"] == 1
    assert move(bridge) == first
    assert move(bridge, rid="next")["status"] == "rejected"
    assert bridge.backend.control_steps == 1


def test_unserializable_result_cannot_repeat_physical_execution(bridge):
    original = bridge.backend.dispatch
    def invalid_result(*args):
        original(*args)
        return {"invalid_measurement": float("nan")}
    bridge.backend.dispatch = invalid_result
    with pytest.raises(RuntimeError, match="never retry"):
        move(bridge)
    assert move(bridge)["status"] == "indeterminate"
    assert move(bridge, rid="different-id", obs=1)["status"] == "rejected"
    assert bridge.backend.position == 2
    assert bridge.backend.control_steps == 1


def test_failed_result_commit_does_not_acknowledge_uncommitted_result(bridge):
    database = bridge.db
    class FailingCommit:
        commits = 0
        def __getattr__(self, name):
            return getattr(database, name)
        def commit(self):
            self.commits += 1
            if self.commits == 2:
                raise sqlite3.OperationalError("injected result fsync failure")
            return database.commit()
    bridge.db = FailingCommit()
    with pytest.raises(RuntimeError, match="never retry"):
        move(bridge)
    assert move(bridge)["status"] == "indeterminate"
    assert move(bridge, rid="new", obs=1)["status"] == "rejected"
    assert bridge.backend.control_steps == 1


def test_journal_recovery_refuses_uncertain_command(tmp_path):
    from humanclaw_bench.libero.protocol import digest
    request = {"run_id": "r", "request_id": "a", "tool_name": "move", "arguments": {"delta": 2}, "observation_id": 0}
    b = ToolService(MockBackend(), "r", tmp_path)
    b.db.execute("INSERT INTO requests VALUES (?,?,?,NULL)", ("a", digest(request), "started"))
    b.db.commit()
    b.shutdown()
    b = ToolService(MockBackend(), "r", tmp_path)
    try:
        assert b.execute(request)["status"] == "indeterminate"
        assert b.backend.control_steps == 0
        assert move(b, rid="new")["status"] == "rejected"
    finally:
        b.shutdown()


def test_wrong_thread_cannot_move_robot(bridge):
    with ThreadPoolExecutor() as pool:
        with pytest.raises(RuntimeError, match="owner thread"):
            pool.submit(move, bridge).result()
    assert bridge.backend.control_steps == 0


def post(service, path, body, headers=None):
    request = urllib.request.Request(service.url + path, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + service.bearer, "Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.headers["Content-Type"], response.read()


def test_mcp_and_json_api_execute_identical_service(bridge):
    with MeteredService(bridge, upstream_url="http://unused", api_key="unused") as service, ThreadPoolExecutor(2) as pool:
        request = {"run_id": "test-run", "request_id": "a", "tool_name": "move", "arguments": {"delta": 2}, "observation_id": 0}
        first = pool.submit(post, service, "/tools/call", request)
        while not first.done():
            bridge.drain()
            threading.Event().wait(.005)
        assert json.loads(first.result()[1])["status"] == "completed"
        second = pool.submit(post, service, "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "move", "arguments": {"delta": 2, "request_id": "a", "observation_id": 0}}})
        while not second.done():
            bridge.drain()
            threading.Event().wait(.005)
        assert not json.loads(second.result()[1])["result"]["isError"]
        assert bridge.backend.control_steps == 1


def test_stream_nonstream_chat_and_compaction_are_metered(tmp_path):
    requests = []
    usage = {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 20},
             "output_tokens": 10, "output_tokens_details": {"reasoning_tokens": 4}}
    def responder(endpoint, payload):
        requests.append((endpoint, payload))
        response = {"id": "resp", "usage": usage, "output": []}
        if payload.get("stream"):
            return (b"data: " + json.dumps({"type": "response.completed", "response": response}).encode() + b"\n\ndata: [DONE]\n\n", "text/event-stream")
        return json.dumps(response).encode(), "application/json"
    pricing = {"version": "test-v1", "currency": "USD", "model": "test", "provider": "synthetic", "date": "2026-10-18",
               "input_per_million": 2, "cached_input_per_million": 1, "output_per_million": 10}
    with TraceRecorder(tmp_path, {"harness": "test"}, pricing) as recorder:
        b = ToolService(MockBackend(), recorder.run_id, recorder.directory)
        with span("episode.decision"):
            with MeteredService(b, upstream_url="http://unused", api_key="NEVER_LOG_THIS", responder=responder) as service:
                for path, stream in [("/v1/responses", False), ("/v1/responses", True), ("/v1/chat/completions", False), ("/v1/responses/compact", False)]:
                    content_type, raw = post(service, path, {"model": "test", "stream": stream, "input": "unchanged"})
                    assert bool("event-stream" in content_type) == stream
                with span("grasp_object", kind="tool") as parent:
                    key = service.register_context()
                    post(service, "/v1/responses", {"model": "test"}, {"X-Bench-Context": key})
                    parent_id = parent.span_id
        b.shutdown()
    report = summarize(recorder.directory)
    assert report["model_requests"] == 5
    assert report["usage_coverage"] == 1
    assert report["tokens"]["output_tokens"] == 50
    assert report["tokens"]["reasoning_tokens"] == 20
    assert report["cost_usd"] == pytest.approx(5 * ((80*2 + 20*1 + 10*10) / 1e6))
    assert report["model_calls"][-1]["parent_span_id"] == parent_id
    assert "NEVER_LOG_THIS" not in (recorder.directory / "events.jsonl").read_text()
    assert requests[0][1]["input"] == "unchanged"


def test_missing_usage_is_unknown_not_zero(tmp_path):
    def responder(*_):
        return b'{"id":"r","output":[]}', "application/json"
    with TraceRecorder(tmp_path, {"harness": "test"}) as recorder:
        b = ToolService(MockBackend(), recorder.run_id, recorder.directory)
        with MeteredService(b, upstream_url="http://unused", api_key="", responder=responder) as service:
            post(service, "/v1/responses", {"model": "test"})
        b.shutdown()
    result = summarize(recorder.directory)
    assert result["usage_coverage"] == 0
    assert result["tokens"]["total_tokens"] is None
    assert result["cost_usd"] is None


def test_loopback_gateway_bypasses_inherited_cluster_proxy(bridge, monkeypatch):
    from openai import OpenAI
    import os
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.setenv("no_proxy", "existing.internal")
    def responder(*_):
        return b'{"id":"r","object":"response","created_at":1,"output":[],"usage":{"input_tokens":2,"output_tokens":1}}', "application/json"
    with MeteredService(bridge, upstream_url="http://unused", api_key="", responder=responder) as service:
        with OpenAI(base_url=service.url+"/v1", api_key=service.bearer, max_retries=0) as client:
            response = client.responses.create(model="test", input="hello")
        assert response.id == "r"
        assert service.calls == 1
        assert "existing.internal" in os.environ["NO_PROXY"]
        assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:9"
    assert "NO_PROXY" not in os.environ
    assert os.environ["no_proxy"] == "existing.internal"


def test_schema_rejection_has_no_motion_and_is_counted(tmp_path):
    with TraceRecorder(tmp_path, {"harness": "test"}) as recorder:
        bridge = ToolService(MockBackend(), recorder.run_id, recorder.directory)
        try:
            result = move(bridge, delta="not numeric")
            assert result["status"] == "rejected"
            assert bridge.backend.control_steps == 0
        finally:
            bridge.shutdown()
    operation = summarize(recorder.directory)["operations"]["move"]
    assert operation["rejected"] == 1
    assert operation["executions"] == 0


def test_truncated_stream_is_failure_with_unknown_usage(tmp_path):
    def responder(*_):
        return b'data: {"type":"response.created","response":{"id":"r"}}\n\n', 'text/event-stream'
    with TraceRecorder(tmp_path, {"harness": "test"}) as recorder:
        b = ToolService(MockBackend(), recorder.run_id, recorder.directory)
        with MeteredService(b, upstream_url='http://unused', api_key='', responder=responder) as service:
            _, raw = post(service, '/v1/responses', {"model": "test", "stream": True})
            assert b'response.created' in raw
        b.shutdown()
    report = summarize(recorder.directory)
    assert report['model_calls'][0]['status'] == 'failed'
    assert report['usage_coverage'] == 0
    assert report['cost_usd'] is None
    assert 'stream_incomplete' in (recorder.directory / 'events.jsonl').read_text()


def test_interrupt_keeps_durable_uncertain_execution(bridge):
    from humanclaw_bench.libero.run import EpisodeDeadlineExceeded
    def interrupted(*_):
        bridge.backend.control_steps += 1
        raise EpisodeDeadlineExceeded('budget')
    bridge.backend.dispatch = interrupted
    with pytest.raises(EpisodeDeadlineExceeded):
        move(bridge)
    assert move(bridge)['status'] == 'indeterminate'
    assert bridge.backend.control_steps == 1


def test_provider_retry_is_forwarded_and_every_attempt_is_costed(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from openai import OpenAI
    received = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append(payload)
            body = ({'error': {'message': 'busy'}} if len(received) == 1 else
                {'id': 'r', 'object': 'response', 'created_at': 1, 'model': 'test', 'output': [],
                 'usage': {'input_tokens': 3, 'output_tokens': 1}})
            raw = json.dumps(body).encode()
            self.send_response(429 if len(received) == 1 else 200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('retry-after-ms', '1')
            self.end_headers()
            self.wfile.write(raw)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    try:
        with TraceRecorder(tmp_path, {'harness': 'test'}) as recorder:
            b = ToolService(MockBackend(), recorder.run_id, recorder.directory)
            with MeteredService(b, upstream_url=f'http://127.0.0.1:{provider.server_port}', api_key='not-recorded') as service:
                OpenAI(base_url=service.url + '/v1', api_key=service.bearer, max_retries=1).responses.create(model='test', input='unchanged')
            b.shutdown()
        report = summarize(recorder.directory)
        assert report['model_requests'] == 2
        assert report['usage_coverage'] == .5
        assert report['tokens']['input_tokens'] is None
        assert report['known_token_subtotals']['input_tokens'] == 3
        assert report['model_calls'][0]['status'] == 'failed'
        assert 'retry-after-ms' in (recorder.directory / 'events.jsonl').read_text()
        assert received[0] == received[1]
    finally:
        provider.shutdown()
        provider.server_close()


def test_physics_snapshot_restores_empty_mocap_shapes():
    import numpy as np
    from humanclaw_bench.libero.backend import restore_array
    mocap = np.zeros((0, 3))
    restore_array(mocap, json.loads(json.dumps(mocap.tolist())))
    assert mocap.shape == (0, 3)
    target = np.zeros((2, 3))
    restore_array(target, [[1, 2, 3], [4, 5, 6]])
    assert target.sum() == 21
    with pytest.raises(ValueError, match='incompatible'):
        restore_array(target, [1, 2])


def test_snapshot_restore_keeps_solver_inputs_after_refresh(monkeypatch):
    import random
    import sys
    from types import ModuleType, SimpleNamespace
    import numpy as np
    from humanclaw_bench.libero.backend import RoboBackend

    data = SimpleNamespace(ctrl=np.zeros(1), qacc_warmstart=np.zeros(1),
                           mocap_pos=np.zeros((0, 3)))
    seen = []
    def forward():
        seen.append(float(data.qacc_warmstart[0]))
        data.qacc_warmstart[:] = 999
    def observe(**_):
        data.ctrl[:] = 888
        return {"public": True}
    sim = SimpleNamespace(data=data, forward=forward,
                          set_state_from_flattened=lambda _: None)
    rs = SimpleNamespace(sim=sim, robots=[SimpleNamespace(controller=SimpleNamespace())],
                         _get_observations=observe)
    env = SimpleNamespace(_env=SimpleNamespace(env=rs), instruction="fixture",
                          _invalidate_sensor_consumers=lambda: None)
    module = ModuleType("roborsi.embodied.sim.libero.adapter")
    module._visible_raw_obs = lambda raw: raw
    module._to_sim_obs = lambda raw, _: raw
    monkeypatch.setitem(sys.modules, module.__name__, module)
    robot = RoboBackend.__new__(RoboBackend)
    robot.env = env
    snapshot = {"sim_state": [], "data": {"ctrl": [34.0], "qacc_warmstart": [12.0],
                    "mocap_pos": []}, "rng": {"python": random.getstate(), "numpy": np.random.get_state()}}
    robot.restore(snapshot)
    assert seen == [12.0]  # Inputs needed by forward were set before it.
    assert data.qacc_warmstart.tolist() == [12.0]
    assert data.ctrl.tolist() == [34.0]
    assert data.mocap_pos.shape == (0, 3)
    assert env._last_obs == {"public": True}
