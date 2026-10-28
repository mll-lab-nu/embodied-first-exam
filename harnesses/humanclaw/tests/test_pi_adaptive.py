import json
from pathlib import Path
import sqlite3
import socket
import time

import pytest
from PIL import Image

from humanclaw_bench.harnesses.adaptive.broker import Broker, digest
from humanclaw_bench.harnesses.adaptive.bindings import HumanClawBinding
from humanclaw_bench.harnesses.adaptive.lifecycle import Lifecycle
from humanclaw_bench.harnesses.adaptive.sandbox import run_program
from humanclaw_bench.harnesses.adaptive.service import AdaptiveService
from humanclaw_bench.harnesses.adaptive.state import TaskState, DEFAULT_POLICY
from humanclaw_bench.harnesses.environment import EnvironmentBridge
from humanclaw_bench.harnesses.pi_adaptive import resolve_profile, package_identity
from humanclaw_bench.harnesses.runtime import load_harness_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/harnesses/pi_adaptive.json"


class TextBinding:
    def __init__(self):
        self.observation_id = "text:0"
        self.calls = 0
        self.version = "v1"
        self.crash = False
        self.effect = "observe"
    def catalog(self):
        return [{"id": "fixture.inspect", "version": self.version, "readiness": "ready", "effect": self.effect,
            "requires_current_observation": True, "input_schema": {"type": "object", "properties": {"advance": {"type": "boolean"}}, "required": ["advance"], "additionalProperties": False}}]
    def execute(self, tool, arguments):
        self.calls += 1
        if self.crash:
            raise RuntimeError("Lost connection after dispatch")
        self.observation_id = f"text:{self.calls}"
        return {"observations": [{"id": self.observation_id, "channels": ["text"]}], "control_steps": int(arguments["advance"]), "isError": False}


def request(binding, ident="r1"):
    return {"request_id": ident, "tool": "fixture.inspect", "tool_version": binding.version,
        "arguments": {"advance": True}, "decision": {"intent": "inspect", "expected_outcome": "new reading",
            "evidence": [binding.observation_id], "policy_version": digest(DEFAULT_POLICY), "completion": "continue"}}


def test_durable_duplicate_conflict_lost_receipt(tmp_path):
    binding = TextBinding(); path = tmp_path / "journal.sqlite"
    broker = Broker(path, binding, time.monotonic()+30)
    req = request(binding); first = broker.execute(req)
    assert first["status"] == "completed" and first["counts"] == dict(compute=0, observations=1, physical_operations=0, control_steps=1)
    assert broker.execute(req) == first and binding.calls == 1
    with pytest.raises(ValueError, match="conflict"):
        broker.execute({**req, "arguments": {"advance": False}})
    broker.close()
    reopened = Broker(path, binding, time.monotonic()+30)
    assert reopened.execute(req) == first and binding.calls == 1


def test_uncertain_execution_blocks_replay_and_version_activation(tmp_path):
    binding = TextBinding(); binding.crash = True
    broker = Broker(tmp_path / "journal.sqlite", binding, time.monotonic()+30)
    req = request(binding)
    with pytest.raises(RuntimeError): broker.execute(req)
    assert broker.execute(req)["status"] == "indeterminate" and binding.calls == 1
    assert broker.execute(request(binding, "r2"))["status"] == "rejected"
    assert not broker.settled
    with pytest.raises(ValueError, match="settled"):
        Lifecycle(tmp_path / "candidates", broker).activate("anything")


@pytest.mark.parametrize("change", ["version", "evidence", "deadline", "effect", "schema"])
def test_admission_never_dispatches_invalid_contract(tmp_path, change):
    binding = TextBinding(); broker = Broker(tmp_path / "journal.sqlite", binding, time.monotonic()+30)
    req = request(binding)
    if change == "version": binding.version = "v2"
    if change == "evidence": req["decision"]["evidence"] = ["text:99"]
    if change == "deadline": broker.deadline = time.monotonic()-1
    if change == "effect": binding.effect = "unknown"
    if change == "schema": req["arguments"] = {"extra": 1}
    assert broker.execute(req)["status"] == "rejected" and binding.calls == 0


def test_interrupted_intent_is_not_replayed(tmp_path):
    binding = TextBinding(); broker = Broker(tmp_path / "journal.sqlite", binding, time.monotonic()+30)
    req = request(binding)
    broker.db.execute("INSERT INTO requests VALUES (?,?,?,?,NULL)", ("r1", digest(req), "running", json.dumps(req)))
    broker.db.commit(); broker.close()
    reopened = Broker(tmp_path / "journal.sqlite", binding, time.monotonic()+30)
    assert reopened.execute(req)["status"] == "indeterminate" and binding.calls == 0


def test_evidence_provenance_and_post_action_freshness(tmp_path):
    binding = TextBinding(); broker = Broker(tmp_path / "j.sqlite", binding, time.monotonic()+30)
    state = TaskState(broker, "Inspect")
    with pytest.raises(ValueError): state.update({"completion": "supported"})
    with pytest.raises(ValueError): state.update({"claims": [{"text": "truth", "status": "observed", "evidence": ["text:0"]}]})
    state.update({"claims": [{"text": "reading plausible", "status": "inferred", "evidence": ["text:0"]}], "feedback": "supported"})
    assert state.snapshot()["recommendation"]["effort"] == "medium"
    state.update({"claims": [{"text": "prediction failed", "status": "contradicted", "evidence": ["text:0"]}], "feedback": "contradicted"})
    assert state.snapshot()["recommendation"]["effort"] == "high"


def test_os_isolation_private_files_network_oracle_and_environment(tmp_path, monkeypatch):
    sentinel = tmp_path / "private-evaluator.txt"; sentinel.write_text("secret evaluator")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-test-sentinel")
    code = '''import os, socket
def run(x, tools):
    result = {"credential": os.environ.get("AZURE_OPENAI_API_KEY"), "private_read": False, "private_write": False, "network": False}
    try:
        open(x['path']).read(); result["private_read"] = True
    except OSError: pass
    try:
        open(x['path'], "w").write("tamper"); result["private_write"] = True
    except OSError: pass
    try:
        s=socket.socket(); s.settimeout(.2); s.connect(("127.0.0.1",x['port'])); result["network"] = True
    except OSError: pass
    return result
'''
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0)); listener.listen()
        assert run_program(code, {"path": str(sentinel), "port": listener.getsockname()[1]}) == {"credential": None, "private_read": False, "private_write": False, "network": False}
    assert sentinel.read_text() == "secret evaluator"


def test_generated_children_only_use_broker_and_record_parent(tmp_path):
    binding = TextBinding(); broker = Broker(tmp_path / "j.sqlite", binding, time.monotonic()+30)
    req = request(binding); req["parent_id"] = "program:test"
    got = run_program("def run(x, tools): return tools(x)", req, invoke=broker.execute)
    assert got["parent_id"] == "program:test" and binding.calls == 1
    with pytest.raises(ValueError, match="forbidden"):
        run_program("def run(x, tools): return tools(x)", req)


def test_validation_repair_activation_and_scope(tmp_path):
    broker = Broker(tmp_path / "j.sqlite", TextBinding(), time.monotonic()+60)
    lifecycle = Lifecycle(tmp_path / "candidates", broker)
    base = {"protocol": "turn-adapter-v1", "parent": None, "evidence": ["text:0"], "diagnosis": "wrong signed turn", "implementation": "def run(x, tools): return {'direction':'left','degrees':20}"}
    bad = lifecycle.propose(base)["candidate_id"]
    assert lifecycle.validate(bad)["report"]["status"] == "fail"
    with pytest.raises(ValueError): lifecycle.activate(bad)
    good = lifecycle.propose({**base, "parent": bad, "implementation": "def run(x, tools):\n a=x['angle']; return {'direction':'left' if a>=0 else 'right','degrees':max(10,min(120,abs(a)))}"})["candidate_id"]
    report = lifecycle.validate(good)
    assert report["release"]["local_eligible"] and not report["release"]["publish_eligible"]
    lifecycle.activate(good)
    assert lifecycle.compute(good, {"angle": -30})["output"] == {"direction": "right", "degrees": 30}


def test_independent_review_cannot_override_failed_contract(tmp_path):
    broker = Broker(tmp_path / "j.sqlite", TextBinding(), time.monotonic()+30)
    life = Lifecycle(tmp_path / "c", broker)
    seen = []
    life.review = lambda *args: seen.append(args) or {"status": "pass"}
    bad = life.propose({"protocol": "feedback-policy-v1", "implementation": {**DEFAULT_POLICY, "completion_requires_evidence": False}, "parent": None, "diagnosis": "skip check", "evidence": ["text:0"]})["candidate_id"]
    assert not life.validate(bad)["release"]["local_eligible"] and not seen
    good = life.propose({"protocol": "feedback-policy-v1", "implementation": DEFAULT_POLICY, "parent": bad, "diagnosis": "prediction failure", "evidence": ["text:0"]})["candidate_id"]
    assert life.validate(good)["release"]["local_eligible"] and len(seen) == 1


def test_configuration_replaces_prototype_and_rejects_reasoning_quotas():
    config = load_harness_config(CONFIG)
    assert resolve_profile(config, {"model": "gpt-6-astra"})["version"] == "pi-adaptive-v1"
    for old in ["embodied-v1", "typo"]:
        with pytest.raises(ValueError): resolve_profile({"pi_profile": old})
    for key in ("max_high_fraction", "reasoning_deadline_seconds"):
        changed = {**config, "pi_adaptive": {**config["pi_adaptive"], key: 1}}
        with pytest.raises(ValueError): resolve_profile(changed)
    assert package_identity()["profile"] == "pi-adaptive-v1"


def test_real_sdk_scripted_protocol(tmp_path):
    from humanclaw_bench.harnesses.adaptive.smoke import run_adaptive_smoke
    result = run_adaptive_smoke(load_harness_config(CONFIG), tmp_path)
    assert result["passed"], result


def test_effectful_program_parent_journal_and_direct_bypass_denied(tmp_path):
    bridge = EnvironmentBridge(Image.new("RGB", (8,8)), 4, lambda step, d: (Image.new("RGB", (8,8)), False), "walk")
    service = AdaptiveService(bridge, tmp_path / "adaptive", time.monotonic()+60)
    service.lifecycle.review = lambda *_: {"status": "pass", "reason": "test-only independent review fixture"}
    catalog = {t["id"]: t for t in service.binding.catalog()}
    child = {"request_id": "parent/1", "tool": "humanclaw.walk_forward", "tool_version": catalog["humanclaw.walk_forward"]["version"],
        "arguments": {"request_id": "parent/1", "observation_id": 0, "action_name": "Walk<forward><slow>", "visible_state": "test fixture"},
        "decision": {"intent": "walk", "expected_outcome": "new image", "evidence": ["observation:0"], "policy_version": service.state.policy_version, "completion": "continue"}}
    parent = {"request_id": "parent", "tool": "runtime.program", "tool_version": catalog["runtime.program"]["version"],
        "arguments": {"source": "def run(x, tools): return tools(x)['status']", "input": child, "allowed_tools": ["humanclaw.walk_forward"]}, "decision": dict(child["decision"])}
    result = service.call("execute", parent)
    assert not result["isError"] and bridge.step == 1
    assert service.broker.receipt("parent/1")["parent_id"] == "parent"
    assert service.broker.receipt("parent")["result"]["output"] == "completed"
    assert service.broker.counts["physical_operations"] == 1
    assert not service.call("execute", parent)["isError"] and bridge.step == 1
    assert service.broker.evidence(["observation:0", "observation:1"])[1]["execution_id"] == "parent/1"
    service.close()


def test_native_and_broker_ids_cannot_diverge(tmp_path):
    bridge = EnvironmentBridge(Image.new("RGB", (8,8)), 4, lambda *_: pytest.fail("must not dispatch"), "walk")
    binding = HumanClawBinding(bridge); broker = Broker(tmp_path / "j.sqlite", binding, time.monotonic()+30)
    tool = binding.catalog()[0]
    req = {"request_id": "outer", "tool": tool["id"], "tool_version": tool["version"],
        "arguments": {"request_id": "inner", "observation_id": 0, "action_name": "Walk<forward><slow>", "visible_state": "test"},
        "decision": {"intent": "walk", "expected_outcome": "new image", "evidence": ["observation:0"], "policy_version": "v1"}}
    assert broker.execute(req)["status"] == "rejected"


def test_sdk_blocks_preplanned_second_action_until_new_observation_turn(tmp_path):
    from humanclaw_bench.harnesses.adaptive.smoke import stream_response
    from humanclaw_bench.harnesses.runtime import NativeHarness
    executed = []
    def step(index, decision):
        executed.append(decision.action.skill)
        return Image.new("RGB", (8,8), "blue"), decision.action.skill == "stand"
    bridge = EnvironmentBridge(Image.new("RGB", (8,8)), 5, step, "Walk and stop")
    catalog = {t["id"]: t for t in HumanClawBinding(bridge).catalog()}
    def action(name, index):
        return ("execute", {"request_id": f"r{index}", "tool": name, "tool_version": catalog[name]["version"],
            "arguments": {"request_id": f"r{index}", "observation_id": index, "action_name": "Stop/Stand" if name.endswith("stand") else "Walk<forward><slow>", "visible_state": "public image"},
            "decision": {"intent": "check", "expected_outcome": "next image", "evidence": [f"observation:{index}"], "policy_version": digest(DEFAULT_POLICY), "completion": "unknown"}})
    def responder(payload, index):
        if index == 1:
            outputs = []
            response = None
            for at in range(2):
                for event in stream_response(payload, 10+at, action("humanclaw.walk_forward", at)):
                    if event["type"] == "response.created":
                        if at == 0: yield event
                    elif event["type"] == "response.completed":
                        response = event["response"]; outputs.extend(response["output"])
                    else:
                        event["output_index"] = at
                        yield event
            response["output"] = outputs
            yield {"type": "response.completed", "response": response}
        else:
            assert index <= 3
            yield from stream_response(payload, index, action("humanclaw.stand", 1) if index == 2 else None)
    result = NativeHarness("pi", load_harness_config(CONFIG), {"model": "gpt-6-astra"}).run(bridge, tmp_path, responder=responder)
    assert executed == ["walk_forward", "stand"] and result["termination_reason"] == "stop"
