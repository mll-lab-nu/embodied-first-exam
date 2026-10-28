"""Local discovery/adapter tests; scripted cases do not claim autonomous capability."""
import copy
import json
from pathlib import Path
import time

import numpy as np
import pytest

from humanclaw_bench.harnesses.adaptive.bootstrap import BootstrapBridge
from humanclaw_bench.harnesses.adaptive.service import AdaptiveService
from adaptive_public_fixture import PublicInstrument, scripted_artifact


def call(service, name, arguments, *, error=False):
    result = service.call(name, arguments)
    value = json.loads(result["content"][0]["text"])
    assert bool(result["isError"]) == error, value
    return value.get("value", value)


def read_sources(service, fixture):
    for path in ("manual.md", "examples.json", "client.py"):
        call(service, "discover", {"uri": fixture.url + "/public/" + path, "question": "How do observation, advance and status work?"})


def request(service, name, arguments=None, ident=None):
    return {"request_id": ident or name, "tool": name, "arguments": arguments or {},
            "decision": {"intent": "Exercise documented interface", "expected_outcome": "Public result consistent with manual",
                "evidence": [service.binding.observation_id] if service.binding.observation_id else list(service.discovery.current.values()),
                "policy_version": service.state.policy_version, "completion": "unknown"}}


def prepare(service, fixture, *, client=False, include_status=False):
    read_sources(service, fixture)
    artifact = scripted_artifact(service, client=client, include_status=include_status)
    ident = call(service, "adapter", {"action": "propose", "arguments": {"artifact": artifact}})["id"]
    report = call(service, "adapter", {"action": "validate", "arguments": {"id": ident}})
    assert report["status"] == "pass", report
    return ident, artifact


def probe(service, ident, name, arguments=None, request_id=None, *, error=False):
    return call(service, "adapter", {"action": "probe", "arguments": {"id": ident, "request": request(service, name, arguments, request_id)}}, error=error)


@pytest.fixture
def instrument(tmp_path):
    fixture = PublicInstrument()
    service = AdaptiveService(BootstrapBridge(fixture.bootstrap()), tmp_path / "adaptive", time.monotonic() + 180)
    service.lifecycle.review = lambda *args: {"status": "pass", "reason": "Scripted independent test reviewer"}
    yield service, fixture
    service.close()
    fixture.close()


@pytest.mark.parametrize("client", [False, True])
def test_empty_registry_to_registered_public_interaction(instrument, client):
    service, fixture = instrument
    assert service.binding.observation_id is None
    assert service.initial_images() == []
    assert service.adapters.catalog() == []
    assert "No target adapter" in service.initial_prompt()
    ident, artifact = prepare(service, fixture, client=client)
    assert service.adapters.catalog() == []  # Validation alone does not register.
    first = probe(service, ident, "sample")
    assert first["status"] == "completed" and fixture.position == 0
    second = probe(service, ident, "advance", {"delta": 1})
    assert second["status"] == "completed" and fixture.position == 1
    registered = call(service, "adapter", {"action": "register", "arguments": {"id": ident, "scope": ["sample", "advance"]}})
    assert registered["scope"] == ["advance", "sample"]
    tool = next(t for t in registered["catalog"] if t["id"] == "advance")
    envelope = {**request(service, "advance", {"delta": 2}, "next"), "tool_version": tool["version"]}
    assert call(service, "execute", envelope)["status"] == "completed"
    assert call(service, "execute", envelope)["status"] == "completed"
    assert fixture.position == 3 and len(fixture.actions) == 2
    assert service.broker.counts["physical_operations"] == 2
    assert service.bridge.step == 2
    assert service.adapters.artifacts[ident]["origin"] == ("public_client" if client else "generated")


def test_discovery_and_candidate_repetition_does_not_create_progress(instrument):
    service, fixture = instrument
    read_sources(service, fixture)
    known = set(service.discovery.records)
    for _ in range(3):
        read_sources(service, fixture)
    assert set(service.discovery.records) == known
    artifact = scripted_artifact(service)
    ident = service.adapters.propose(artifact)["id"]
    assert service.adapters.propose(artifact, parent=ident)["id"] == ident
    alternate = copy.deepcopy(artifact)
    alternate["source"] += "\n# Reworded attempt"
    with pytest.raises(ValueError, match="pending adapter"):
        service.adapters.propose(alternate)
    reviews = []
    service.lifecycle.review = lambda *args: reviews.append(args) or {"status": "fail", "reason": "Test failure"}
    report = service.adapters.validate(ident)
    assert service.adapters.validate(ident) == report and len(reviews) == 1
    child = service.adapters.propose(alternate, parent=ident)["id"]
    assert child != ident and service.binding.observation_id is None
    assert service.snapshot()["interface"]["pending"]["artifact"]["parent"] == ident


def test_drift_requires_corrected_child_and_new_version(instrument):
    service, fixture = instrument
    ident, _ = prepare(service, fixture)
    probe(service, ident, "sample")
    probe(service, ident, "advance", {"delta": 1})
    service.adapters.register(ident, ["sample", "advance"])
    old_version = next(t for t in service.adapters.catalog() if t["id"] == "advance")["version"]
    fixture.revision = 2
    read_sources(service, fixture)
    assert service.adapters.catalog() == [] and ident in service.adapters.invalid
    artifact = scripted_artifact(service)
    child = service.adapters.propose(artifact, parent=ident)["id"]
    assert child != ident and service.adapters.validate(child)["status"] == "pass"
    probe(service, child, "sample", request_id="sample-2")
    probe(service, child, "advance", {"delta": .1}, "advance-2")
    service.adapters.register(child, ["sample", "advance"])
    assert fixture.position == 2
    assert next(t for t in service.adapters.catalog() if t["id"] == "advance")["version"] != old_version


def test_new_execution_can_justify_a_later_binding_scope(instrument):
    service, fixture = instrument
    ident, _ = prepare(service, fixture)
    probe(service, ident, "sample")
    probe(service, ident, "advance", {"delta": 1})
    service.adapters.register(ident, ["sample", "advance"])
    expanded = scripted_artifact(service, include_status=True)
    with pytest.raises(ValueError, match="No new"):
        service.adapters.propose(expanded, parent=ident)
    tool = next(t for t in service.adapters.catalog() if t["id"] == "sample")
    call(service, "execute", {**request(service, "sample", ident="new-public-evidence"), "tool_version": tool["version"]})
    child = service.adapters.propose(expanded, parent=ident)["id"]
    assert child != ident and service.binding.observation_id in service.adapters.artifacts[child]["evidence"]


def test_uncertain_dispatch_reconciles_without_duplicate_actuation(instrument):
    service, fixture = instrument
    ident, _ = prepare(service, fixture, include_status=True)
    probe(service, ident, "sample")
    fixture.uncertain = True
    probe(service, ident, "advance", {"delta": 1}, error=True)
    assert not service.broker.settled and len(fixture.actions) == 1
    assert service.broker.receipt("advance")["status"] == "indeterminate"
    with pytest.raises(ValueError, match="settled"):
        service.adapters.register(ident, ["sample"])
    recovered = call(service, "adapter", {"action": "reconcile", "arguments": {"request_id": "advance", "operation": "status"}})
    assert recovered["status"] == "completed" and service.broker.settled
    assert call(service, "receipt", {"request_id": "advance"}) == recovered
    assert len(fixture.actions) == 1 and fixture.position == 1
    assert service.broker.counts["physical_operations"] == 1
    assert service.adapters.probes[ident]["advance"] == "advance"


def test_received_output_drift_can_repair_without_replaying_action(instrument, monkeypatch):
    service, fixture = instrument
    ident, _ = prepare(service, fixture)
    probe(service, ident, "sample")
    monkeypatch.setattr(fixture, "sample", lambda: {"new_position": fixture.position})
    result = probe(service, ident, "advance", {"delta": 1}, error=True)
    assert result["status"] == "completed" and result["result"]["binding_error"]
    assert result["result"]["raw"] == {"new_position": 1}
    assert service.broker.settled and len(fixture.actions) == 1
    assert ident in service.adapters.invalid and service.binding.observation_id is None


def test_runtime_codec_failure_can_reuse_a_compatible_checked_parent(instrument):
    service, fixture = instrument
    good, artifact = prepare(service, fixture)
    probe(service, good, "sample")
    probe(service, good, "advance", {"delta": 1})
    service.adapters.register(good, ["sample", "advance"])
    tool = next(t for t in service.adapters.catalog() if t["id"] == "sample")
    call(service, "execute", {**request(service, "sample", ident="fresh-sample"), "tool_version": tool["version"]})
    broken = copy.deepcopy(artifact)
    broken["source"] = broken["source"].replace("if x['phase'] == 'decode': return x['value']",
        "if x['phase'] == 'decode':\n        if x['value']['position_mm'] == 2: raise ValueError('codec regression')\n        return x['value']")
    bad = service.adapters.propose(broken, parent=good)["id"]
    assert service.adapters.validate(bad)["status"] == "pass"
    probe(service, bad, "advance", {"delta": 1}, "bad-child", error=True)
    assert service.broker.settled and fixture.position == 2
    reused = service.adapters.propose(artifact, parent=bad)
    assert reused["id"] == good and reused["reused"]
    service.adapters.register(good, ["sample", "advance"])
    assert service.adapters.active == good and bad in service.adapters.invalid
    assert service.binding.observation_id is None  # A fresh sample is still needed.


@pytest.mark.parametrize("units", ["mm", "m"])
def test_scientific_workspace_original_depth_geometry_and_persistence(instrument, units):
    service, fixture = instrument
    fixture.depth_units = units
    source = call(service, "discover", {"uri": fixture.url + "/public/resources.json", "question": "What are the raw depth units, invalid values and calibration?"})["id"]
    depth = call(service, "workspace", {"action": "resource", "arguments": {"source": source, "pointer": "/depth"}})
    rgb = call(service, "workspace", {"action": "resource", "arguments": {"source": source, "pointer": "/rgb"}})
    assert depth["shape"] == [2, 2] and depth["units"] == units and depth["invalid_values"] == [0]
    assert rgb["observation_id"] == depth["observation_id"] and rgb["timestamp"] == depth["timestamp"]
    dependency = call(service, "workspace", {"action": "dependency", "arguments": {"requirement": "numpy==" + np.__version__, "install": True}})
    assert dependency["origin"] == "installed_distribution"
    source_code = '''def run(x, tools):
    import numpy as np
    from pathlib import Path
    a = np.load(x['path'], allow_pickle=False).astype(float)
    valid = ~np.isin(a, x['invalid_values'])
    z = a / (1000 if x['units'] == 'mm' else 1)
    v, u = np.indices(z.shape)
    c = x['calibration']
    xyz = np.stack(((u-c['cx'])*z/c['fx'], (v-c['cy'])*z/c['fy'], z), axis=-1)
    xyz = xyz @ np.array(c['camera_to_world_rotation']).T + np.array(c['camera_to_world_translation_m'])
    Path('geometry.json').write_text(str(xyz[valid].tolist()))
    return xyz[valid].tolist()
'''
    result = call(service, "workspace", {"action": "run", "arguments": {"source": source_code, "input": depth}})
    assert result["output"] == [[1, 0, 1], [2, 0, 2], [3, 2, 4]]
    output = call(service, "workspace", {"action": "run", "arguments": {"source": "def run(x, tools):\n from pathlib import Path\n return Path('geometry.json').read_text()", "input": None}})
    assert "[3.0, 2.0, 4.0]" in output["output"]
    fixture.depth = False
    new = call(service, "discover", {"uri": fixture.url + "/public/resources.json", "question": "Is depth now absent?"})["id"]
    call(service, "workspace", {"action": "resource", "arguments": {"source": new, "pointer": "/depth"}}, error=True)


def test_generated_code_cannot_bypass_transport_or_read_private_files(instrument, tmp_path):
    service, fixture = instrument
    secret = tmp_path / "private-evaluator.txt"
    secret.write_text("private")
    for source in [f"def run(x, tools): return open({str(secret)!r}).read()",
                   f"def run(x, tools):\n import urllib.request\n return urllib.request.urlopen({(fixture.url + '/api/sample')!r}).read().decode()"]:
        call(service, "workspace", {"action": "run", "arguments": {"source": source}}, error=True)
    assert "/api/sample" not in fixture.reads


def test_unresolved_sources_or_review_cannot_register(instrument):
    service, fixture = instrument
    call(service, "discover", {"uri": fixture.url + "/private/evaluator", "question": "Unavailable source"}, error=True)
    read_sources(service, fixture)
    artifact = scripted_artifact(service)
    ident = service.adapters.propose(artifact)["id"]
    service.lifecycle.review = lambda *args: {"status": "inconclusive", "reason": "Conflicting public timing statements"}
    assert service.adapters.validate(ident)["status"] == "inconclusive"
    probe(service, ident, "sample", error=True)
    call(service, "adapter", {"action": "register", "arguments": {"id": ident, "scope": ["sample"]}}, error=True)
    assert fixture.actions == [] and service.adapters.catalog() == []


def test_prose_examples_can_receive_independent_reference_cases(instrument):
    service, fixture = instrument
    read_sources(service, fixture)
    artifact = scripted_artifact(service)
    cases = artifact.pop("cases")
    artifact["cases"] = []
    reference_cases = [{"operation": c["operation"], "phase": c["phase"], "input": service.discovery.value(c["source"], c["input_pointer"]),
                        "expected": service.discovery.value(c["source"], c["expected_pointer"]), "evidence": [c["source"]]} for c in cases]
    service.lifecycle.review = lambda *args: {"status": "pass", "reason": "Independent public examples", "reference_cases": reference_cases}
    ident = service.adapters.propose(artifact)["id"]
    report = service.adapters.validate(ident)
    assert report["status"] == "pass"
    assert len([c for c in report["checks"] if c["check"] == "independent_source_case"]) == 4


def test_mcp_discovery_initializes_session_and_reads_public_resources(instrument):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    service, _ = instrument
    methods = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            methods.append(message["method"])
            if message["method"] != "initialize":
                assert self.headers["Mcp-Session-Id"] == "public-test-session"
            if message["method"] == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}, "resources": {}}}
            elif message["method"] == "tools/list":
                result = {"tools": [{"name": "fresh-sample", "inputSchema": {"type": "object"}}]}
            elif message["method"] == "resources/read":
                result = {"contents": [{"uri": "instrument://manual", "text": "Public MCP manual"}]}
            elif message["method"] == "tools/call":
                result = {"content": [{"type": "text", "text": "sensor=3"}]}
            else:
                result = {}
            data = json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Mcp-Session-Id", "public-test-session")
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service.discovery.spec["transports"].append({"id": "public-mcp", "kind": "mcp", "root": f"http://127.0.0.1:{server.server_port}/mcp"})
    try:
        result = call(service, "discover", {"uri": "mcp://public-mcp/tools", "question": "Which public tools exist?"})
        assert "fresh-sample" in result["text"]
        result = call(service, "discover", {"uri": "mcp://public-mcp/resource?uri=instrument%3A%2F%2Fmanual", "question": "How does the public tool work?"})
        assert result["text"] == "Public MCP manual"
        result = service.discovery.mcp_access("public-mcp").call("tools/call", {"name": "fresh-sample", "arguments": {}})
        assert result["content"][0]["text"] == "sensor=3"
        assert methods.count("initialize") == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_pi_sdk_bootstraps_without_an_initial_image(tmp_path):
    from humanclaw_bench.harnesses.runtime import NativeHarness, load_harness_config
    from humanclaw_bench.harnesses.adaptive.smoke import stream_response
    fixture = PublicInstrument("client")
    services, requests = [], []
    def responder(payload, index):
        if payload.get("instructions", "").startswith("Independently review"):
            yield from stream_response(payload, index, text=json.dumps({"status": "pass", "reason": "Scripted source review"}))
            return
        requests.append(payload)
        turn = len(requests)
        service = services[0]
        if turn == 1:
            action = ("registry", {})
        elif turn <= 4:
            path = ["manual.md", "examples.json", "client.py"][turn - 2]
            action = ("discover", {"uri": fixture.url + "/public/" + path, "question": "Read the public client contract"})
            assert "adaptive__candidate" not in {t["name"] for t in payload["tools"]}
        elif turn == 5:
            action = ("adapter", {"action": "propose", "arguments": {"artifact": scripted_artifact(service, client=True)}})
        elif turn == 6:
            action = ("adapter", {"action": "validate", "arguments": {"id": service.adapters.pending}})
            schema = next(t for t in payload["tools"] if t["name"] == "adaptive__adapter")["parameters"]
            assert schema["properties"]["action"]["enum"] == ["validate", "discard"]
        elif turn in {7, 8}:
            action = ("adapter", {"action": "probe", "arguments": {"id": service.adapters.pending,
                "request": request(service, "sample" if turn == 7 else "advance", {} if turn == 7 else {"delta": 2})}})
        elif turn == 9:
            action = ("adapter", {"action": "register", "arguments": {"id": service.adapters.pending, "scope": ["sample", "advance"]}})
        elif turn == 10:
            tool = next(t for t in service.adapters.catalog() if t["id"] == "advance")
            action = ("execute", {**request(service, "advance", {"delta": 2}, "finish"), "tool_version": tool["version"]})
        else:
            action = None
        assert turn <= 11
        yield from stream_response(payload, index, call=action)
    try:
        config = load_harness_config("configs/harnesses/pi_adaptive.json")
        result = NativeHarness("pi", config, {"model": "gpt-6-astra", "max_tokens": 8192}).run(
            fixture.bootstrap(), tmp_path, responder=responder, adaptive_setup=services.append)
        assert fixture.position == 4 and len(fixture.actions) == 2
        assert result["interface"]["local_adaptation_status"] == "pass"
        assert result["model_requests"] == 12
        assert Path(result["native_directory"], "interface-trial.json").is_file()
    finally:
        fixture.close()
