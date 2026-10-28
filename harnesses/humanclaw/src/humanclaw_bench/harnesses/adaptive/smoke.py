"""Real Pi SDK protocol check using an explicitly scripted local provider."""
import json
from pathlib import Path
import time

from PIL import Image

from ..environment import EnvironmentBridge
from ..runtime import NativeHarness
from ..smoke import MOCK_USAGE
from ...experiments.recorder import TraceRecorder, span
from ...experiments.report import validate_trace
from ...experiments.integration import register_capabilities
from .bindings import HumanClawBinding
from .broker import digest
from .state import DEFAULT_POLICY


def stream_response(payload, index, call=None, text="Protocol check finished."):
    """Emit a minimal Responses stream for a scripted native SDK check."""
    response = {"id": f"resp_{index}", "object": "response", "created_at": int(time.time()),
        "model": payload["model"], "status": "in_progress", "output": [], "usage": None}
    yield {"type": "response.created", "response": dict(response)}
    if call:
        name, arguments = call
        item = {"type": "function_call", "id": f"fc_{index}", "call_id": f"call_{index}",
            "name": "adaptive__" + name, "arguments": "", "status": "in_progress"}
        yield {"type": "response.output_item.added", "output_index": 0, "item": dict(item)}
        encoded = json.dumps(arguments)
        yield {"type": "response.function_call_arguments.delta", "item_id": item["id"], "output_index": 0, "delta": encoded}
        item.update(arguments=encoded, status="completed")
        yield {"type": "response.function_call_arguments.done", "item_id": item["id"], "output_index": 0, "arguments": encoded}
    else:
        item = {"type": "message", "id": f"msg_{index}", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}
        yield {"type": "response.output_item.added", "output_index": 0, "item": item}
    yield {"type": "response.output_item.done", "output_index": 0, "item": item}
    response.update(status="completed", output=[item], usage=MOCK_USAGE)
    yield {"type": "response.completed", "response": response}


def run_adaptive_smoke(config, output):
    """Exercise real SDK discovery, execution, memory, effort and accounting."""
    output = Path(output)
    requests, executed = [], []
    def execute(step, decision):
        """Advance the explicit synthetic image fixture through trace boundaries."""
        executed.append(decision.action.skill)
        with span(decision.action.skill, kind="tool", input=decision.raw_plan, step=step):
            return Image.new("RGB", (32, 32), (80, 50 + 30 * step, 90)), decision.action.skill == "stand"
    bridge = EnvironmentBridge(Image.new("RGB", (32, 32), "navy"), 3, execute, "Approach the synthetic target and stop.")
    catalog = {t["name"]: t for t in HumanClawBinding(bridge).catalog()}
    def action(skill, step, label):
        """Build a frozen execution envelope for the known public fixture."""
        tool = catalog[skill]
        return ("execute", {"request_id": f"r{step}", "tool": tool["id"], "tool_version": tool["version"],
            "arguments": {"request_id": f"r{step}", "observation_id": step, "action_name": label, "visible_state": "Public synthetic image"},
            "decision": {"intent": "check dispatch", "expected_outcome": "new public observation", "evidence": [f"observation:{step}"],
                "policy_version": digest(DEFAULT_POLICY), "completion": "unknown" if skill == "stand" else "continue"}})
    calls = [("discover", {}), action("walk_forward", 0, "Walk<forward><slow>"),
        ("memory", {"update": {"claims": [{"text": "Changed image", "evidence": ["observation:1"], "status": "inferred"}], "feedback": "supported"}}),
        action("stand", 1, "Stop/Stand")]
    def responder(payload, index):
        """Return the next scripted tool call without making a paid model request."""
        requests.append(payload)
        assert index <= len(calls) + 1
        yield from stream_response(payload, index, calls[index - 1] if index <= len(calls) else None)
    recorder = TraceRecorder(output, {"benchmark": "HumanCLAW-mock", "harness": "pi", "synthetic": True})
    with recorder:
        register_capabilities("pi")
        result = NativeHarness("pi", config, {"model": "gpt-6-astra", "max_tokens": 4096}).run(bridge, output, responder=responder)
        recorder.finish(outcome={"task_success": None, "steps": bridge.step, "termination_reason": bridge.termination})
    checks = {"two_actions": executed == ["walk_forward", "stand"], "five_requests": len(requests) == 5,
        "effort_changes": [r["reasoning"]["effort"] for r in requests] == ["medium", "high", "high", "medium", "high"],
        "trace_valid": validate_trace(recorder.directory)["ok"]}
    value = {**result, "checks": checks, "passed": all(checks.values()), "paid_api_calls": 0,
        "scope": "Scripted provider verifies protocol, not autonomous adaptation", "experiment_dir": str(recorder.directory)}
    (output / "adaptive-smoke.json").write_text(json.dumps(value, indent=2))
    return value
