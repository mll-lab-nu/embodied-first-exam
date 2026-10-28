#!/usr/bin/env python3
"""Real-provider task-local autonomy probes; distinct from scripted SDK tests.

Three small public text environments, independent host oracles, complete retained
traces and candidate chains. No Habitat success claim is made by these probes.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sqlite3

from PIL import Image
from humanclaw_bench.environment import load_project_environment
from humanclaw_bench.harnesses.adaptive.broker import digest
from humanclaw_bench.harnesses.environment import EnvironmentBridge
from humanclaw_bench.harnesses.runtime import NativeHarness, load_harness_config
from humanclaw_bench.experiments.recorder import TraceRecorder
from humanclaw_bench.experiments.report import validate_trace
from humanclaw_bench.experiments.integration import register_capabilities

ROOT = Path(__file__).resolve().parents[1]
TASKS = {
    "construct": "A shortest-angle numerical tool is missing. Construct and validate an angle-delta-v1 Python tool, activate it and use compute for current=350, target=10. Then finish. The tool must be constructed through candidate/validate/activate; mental calculation alone does not satisfy this tool-building task.",
    "repair": "An unvalidated turn-adapter-v1 candidate is faulty. Its source and candidate ID are in task memory. Validate it to expose the defect, then create a corrected child candidate, validate and activate the repair, use compute for angle=-35, then finish. Retain the failed candidate in the audit.",
    "policy": "Reach position 1 in this public scalar fixture. Begin with fixture.move delta=1 and predict its effect. If feedback contradicts the prediction, persist the evidence and propose a concrete feedback-policy-v1 repair; validate it through independent review and activate it. Then use the revised strategy to reach position 1 and finish. This task specifically checks evidence-driven policy revision. Movement results are text sensor readings; no images or hidden success signal exist.",
}


class FixtureBinding:
    def __init__(self, bridge):
        self.bridge = bridge
        self.position = 0
        self.attempted = False
    @property
    def observation_id(self):
        return f"fixture:{self.bridge.step}"
    def observation(self):
        return {"id": self.observation_id, "channels": ["text"], "content": [], "position": self.position}
    def catalog(self):
        tools = [
            {"id": "fixture.move", "effect": "physical", "description": "Add delta to position. The first attempted move is obstructed and sensor feedback reports the unchanged position. Subsequent moves follow delta. Public position initially 0.", "input_schema": {"type": "object", "properties": {"delta": {"type": "number", "minimum": -2, "maximum": 2}}, "required": ["delta"], "additionalProperties": False}},
            {"id": "fixture.finish", "effect": "terminate", "description": "Finish the fixture at current position. No success feedback.", "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
        ]
        return [{**tool, "version": digest(tool), "readiness": "ready", "origin": "environment", "requires_current_observation": True,
            "claims": {"status": "declared", "source": "controlled-public-fixture-v1", "success_feedback": "unsupported"}} for tool in tools]
    def execute(self, tool, arguments):
        if tool == "fixture.move":
            if self.attempted: self.position += arguments["delta"]
            self.attempted = True
        else:
            self.bridge.done = True; self.bridge.termination = "stop"
        self.bridge.step += 1
        return {"isError": False, "done": self.bridge.done, "observations": [self.observation()],
            "position": self.position, "control_steps": int(tool == "fixture.move"), "content": []}


def run(case, root):
    config = load_harness_config(ROOT / "configs/harnesses/pi_adaptive.json")
    config["timeout_seconds"] = 1200
    model = json.loads((ROOT / "configs/models/azure_gpt6_astra.json").read_text())
    bridge = EnvironmentBridge(Image.new("RGB", (1, 1)), 10, lambda *_: None, TASKS[case])
    binding = FixtureBinding(bridge)
    def setup(service):
        if case == "repair":
            source = "def run(x, tools): return {'direction': 'left', 'degrees': x['angle']}"
            ident = service.lifecycle.propose({"protocol": "turn-adapter-v1", "parent": None, "implementation": source,
                "diagnosis": "Provided faulty adapter requires independent validation", "evidence": [binding.observation_id]})["candidate_id"]
            service.state.update({"claims": [{"text": f"Unvalidated adapter candidate {ident}; source: {source}", "status": "unknown", "evidence": [binding.observation_id]}]})
    recorder = TraceRecorder(root / case, {"benchmark": "adaptive-controlled-v1", "case": case, "harness": "pi", "synthetic_environment": True, "real_provider": True})
    error, result = None, {}
    with recorder:
        register_capabilities("pi")
        try:
            result = NativeHarness("pi", config, model).run(bridge, root / case, environment_binding=binding, adaptive_setup=setup)
            recorder.finish(outcome={"steps": bridge.step, "termination_reason": bridge.termination})
        except Exception as exc:
            error = str(exc)
            recorder.finish(status="failed", error=exc)
    database = recorder.directory / "native/adaptive/journal.sqlite"
    db = sqlite3.connect(database)
    events = [(kind, json.loads(data)) for kind, data in db.execute("SELECT kind,payload FROM events ORDER BY seq")]
    db.close()
    created = [data for kind, data in events if kind == "candidate.created"]
    reports = [data for kind, data in events if kind == "validation.report"]
    activated = [data for kind, data in events if kind == "candidate.activated"]
    computed = [data for kind, data in events if kind == "compute.result"]
    checks = {"runtime_ok": error is None, "trace_valid": validate_trace(recorder.directory)["ok"],
        "candidate_created": bool(created), "validated": any(r["status"] == "pass" for r in reports), "activated": bool(activated)}
    if case == "construct":
        checks["independent_result"] = any(c["input"] == {"current": 350, "target": 10} and c["output"] == 20 for c in computed)
    elif case == "repair":
        checks["failed_parent_retained"] = any(r["status"] == "fail" for r in reports) and any(c["parent"] for c in created)
        checks["independent_result"] = any(c["input"] == {"angle": -35} and c["output"] == {"direction": "right", "degrees": 35} for c in computed)
    else:
        checks["fresh_independent_review"] = any(r["review"]["status"] == "pass" for r in reports)
        checks["prediction_error_recorded"] = any(k == "memory.updated" and d["update"].get("feedback") == "contradicted" for k, d in events)
        checks["fresh_environment_result"] = binding.position == 1 and bridge.done
        activation_index = next((i for i, (k, _) in enumerate(events) if k == "candidate.activated"), len(events))
        checks["execution_after_activation"] = any(k == "execution.started" and d["tool"] == "fixture.move" for k, d in events[activation_index:])
    report = {"case": case, "passed": all(checks.values()), "checks": checks, "error": error, "identity": result.get("identity"),
        "model_requests": result.get("model_requests"), "trace": str(recorder.directory), "synthetic_environment": True, "real_provider": True}
    (root / f"{case}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=[*TASKS, "all"], default="all")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    load_project_environment()
    reports = [run(case, args.output) for case in TASKS if args.case in (case, "all")]
    (args.output / "validation.json").write_text(json.dumps(reports, indent=2))
    raise SystemExit(0 if all(r["passed"] for r in reports) else 1)
