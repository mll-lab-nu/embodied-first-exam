"""Offline integration checks using real native processes and scripted Responses.

This is a protocol/framework check, not a HumanCLAW benchmark score or GPU test.
"""

from __future__ import annotations

import json
from pathlib import Path
import time

from PIL import Image

from humanclaw_bench.experiments.integration import register_capabilities
from humanclaw_bench.experiments.recorder import TraceRecorder, span
from humanclaw_bench.experiments.replay import replay_run
from humanclaw_bench.experiments.report import summarize_run, validate_trace
from .environment import EnvironmentBridge
from .runtime import NativeHarness, load_harness_config
from .services import flattened_tools
from .pi_adaptive import adaptive_enabled


MOCK_USAGE = {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
              "input_tokens_details": {"cached_tokens": 20},
              "output_tokens_details": {"reasoning_tokens": 10}}


class ScriptedResponses:
    """Emit deterministic Responses events for real native harness checks."""
    def __init__(self, native_tool=False):
        """Retain observed requests and optionally exercise a native shell tool."""
        self.requests = []
        self.native_tool = native_tool

    def __call__(self, payload, index):
        """Stream scripted tool calls and a final message with synthetic usage."""
        self.requests.append(payload)
        response = {"id": f"resp_mock_{index}", "object": "response", "created_at": int(time.time()),
                    "model": payload["model"], "status": "in_progress", "output": [], "usage": None}
        yield {"type": "response.created", "response": dict(response)}
        yield {"type": "response.in_progress", "response": dict(response)}
        phase = index - int(self.native_tool)
        if phase <= 2:
            skill = "walk_forward" if phase == 1 else "stand"
            tools = list(flattened_tools(payload.get("tools", [])))
            if phase == 0:
                selected = next(((ns, tool) for ns, tool in tools if tool.get("name") in {"bash", "exec_command"}), None)
            else:
                selected = next(((namespace, tool) for namespace, tool in tools
                                 if (namespace == "mcp__humanclaw" and tool.get("name") == skill)
                                 or str(tool.get("name", "")).endswith("__" + skill)), None)
            tool = selected[1] if selected else None
            if tool is None:
                raise ValueError(f"Native request did not expose the {skill} MCP action")
            arguments = json.dumps({"request_id": f"mock_action_{phase}", "observation_id": phase - 1,
                "action_name": "Walk<forward><slow>" if phase == 1 else "Stop/Stand",
                "visible_state": "The synthetic target is visible ahead; the lane is clear."})
            if phase == 0:
                arguments = json.dumps({"command" if tool["name"] == "bash" else "cmd": "printf humanclaw-native-check"})
            elif "assessment" in tool.get("parameters", {}).get("properties", {}):
                arguments = json.dumps({**json.loads(arguments), "assessment": {
                    "phase": "approach" if phase == 1 else "finish", "target_visibility": "visible",
                    "target_anchor": "synthetic target ahead", "target_confidence": "high",
                    "alignment": "aligned", "support": "unknown", "clearance": "clear",
                    "remaining_gap": "visible" if phase == 1 else "none_visible", "progress": "advanced",
                    "evidence": "The synthetic target is ahead and the lane is clear.",
                    "finish_intent": "continue" if phase == 1 else "complete", "recovery_feasible": True}})
            item = {"type": "function_call", "id": f"fc_mock_{index}", "call_id": f"call_mock_{index}",
                    "name": tool["name"], "arguments": "", "status": "in_progress"}
            if selected[0]:
                item["namespace"] = selected[0]
            yield {"type": "response.output_item.added", "output_index": 0, "item": dict(item)}
            yield {"type": "response.function_call_arguments.delta", "item_id": item["id"],
                   "output_index": 0, "delta": arguments}
            item.update(arguments=arguments, status="completed")
            yield {"type": "response.function_call_arguments.done", "item_id": item["id"],
                   "output_index": 0, "arguments": arguments}
        else:
            item = {"type": "message", "id": f"msg_mock_{index}", "role": "assistant",
                    "status": "in_progress", "content": []}
            yield {"type": "response.output_item.added", "output_index": 0, "item": dict(item)}
            part = {"type": "output_text", "text": "", "annotations": []}
            yield {"type": "response.content_part.added", "item_id": item["id"], "output_index": 0,
                   "content_index": 0, "part": dict(part)}
            text = "Synthetic protocol check completed after walking and stopping."
            yield {"type": "response.output_text.delta", "item_id": item["id"], "output_index": 0,
                   "content_index": 0, "delta": text}
            yield {"type": "response.output_text.done", "item_id": item["id"], "output_index": 0,
                   "content_index": 0, "text": text}
            part["text"] = text
            yield {"type": "response.content_part.done", "item_id": item["id"], "output_index": 0,
                   "content_index": 0, "part": part}
            item.update(status="completed", content=[part])
        yield {"type": "response.output_item.done", "output_index": 0, "item": item}
        response.update(status="completed", output=[item], usage=MOCK_USAGE)
        yield {"type": "response.completed", "response": response}


def run_smoke(harness: str, harness_config: str | Path, output: str | Path):
    """Run the native process locally and export validated synthetic evidence."""
    config = load_harness_config(harness_config)
    config["timeout_seconds"] = min(float(config.get("timeout_seconds", 120)), 120)
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = {"model": "gpt-6-astra", "max_tokens": 4096}
    if harness == "pi" and adaptive_enabled(config):
        from .adaptive.smoke import run_adaptive_smoke
        return run_adaptive_smoke(config, output)
    provider = ScriptedResponses()
    expected_requests = 4
    states = [{"step": -1, "position": 0.0}]
    image = Image.new("RGB", (64, 64), "navy")
    recorder = TraceRecorder(output, {"benchmark": "HumanCLAW-mock", "harness": harness,
        "episode_id": "synthetic-walk-stop", "synthetic": True, "harness_config": config,
        "model_config": model, "cost_note": "scripted usage only; no paid API calls"})

    def execute(step, decision):
        """Advance deterministic mock state through the shared trace boundaries."""
        with span("decision", kind="step", step=step, input=decision.raw_plan):
            with span(decision.action.skill, kind="tool", input=decision.action.to_json(),
                      attributes={"request_id": decision.raw_plan["request_id"], "interface": "mcp"}):
                distance = 0
                if decision.action.skill != "stand":
                    with span("motion.generate", input=decision.action.to_json()) as motion:
                        distance = decision.action.cond[1]
                        motion.set_output({"synthetic_distance": distance})
                with span("environment.step", kind="environment") as env:
                    state = {"step": step, "position": states[-1]["position"] + distance,
                             "action": decision.action.to_json()}
                    states.append(state)
                    next_image = Image.new("RGB", (64, 64), (50 + step * 50, 100, 150))
                    env.set_output({"synthetic_state": state, "image": next_image})
                with span("history.update") as history:
                    history.set_output(decision.raw_plan)
                return next_image, decision.action.skill == "stand"

    bridge = EnvironmentBridge(image, 3, execute, "Approach the synthetic target and stop.")
    result = {}
    error = None
    with recorder:
        register_capabilities(harness)
        try:
            result = NativeHarness(harness, config, model).run(bridge, output, responder=provider)
            expected = states[0]["position"]
            differences = []
            for row in states[1:]:
                if row["action"]["skill"] == "walk_forward":
                    expected += row["action"]["cond"][1]
                if abs(expected - row["position"]) > 1e-9:
                    differences.append(row["step"])
            recorder.write_json("mock_trajectory.json", {"states": states,
                "replay": {"matches": not differences, "different_steps": differences},
                "scope": "synthetic scalar state; not Habitat physics replay"})
            checks = {"two_actions": bridge.step == 2, "stopped": bridge.termination == "stop",
                      "four_model_requests": len(provider.requests) == expected_requests,
                      "replay_matches": not differences,
                      "eight_environment_tools_exposed": all(name in result["tools_exposed"] for name in (
                          "walk_forward", "stand", "turn", "step_climb_up", "sit", "step_back", "side_walk", "step_climb_down")),
                      "initial_image_sent": "input_image" in json.dumps(provider.requests[0]),
                      "tool_result_image_sent": len(provider.requests) > 2 and len(_images(provider.requests[2])) >= 2}
            recorder.write_json("mock_checks.json", checks)
            if not all(checks.values()):
                raise AssertionError(f"Native integration checks failed: {checks}")
            recorder.finish(outcome={"task_success": None, "infrastructure_error": False,
                                    "steps": bridge.step, "termination_reason": bridge.termination})
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            recorder.finish(status="failed", error=exc, outcome={"task_success": None,
                "infrastructure_error": True, "steps": bridge.step, "termination_reason": "error"})
    validation = validate_trace(recorder.directory)
    summary = summarize_run(recorder.directory, write=True)
    native_tool = "codex.exec_command" if harness == "codex" else "pi.bash"
    native_entry = next((row for row in summary["capabilities"]["entries"] if row["name"] == native_tool), {})
    native_recorded = native_entry.get("executed") == 1 and native_entry.get("exposed", 0) >= 1
    usage_counted_once = summary["model_usage"]["tokens"]["total_tokens"]["total"] == expected_requests * MOCK_USAGE["total_tokens"]
    replay_run(recorder.directory, mode="log", output_dir=output / f"{recorder.run_id}-log-replay")
    result = {**result, "passed": error is None and validation["ok"] and native_recorded and usage_counted_once, "error": error,
            "native_tool_recorded": native_recorded,
            "usage_counted_once": usage_counted_once,
            "trace_valid": validation["ok"], "experiment_dir": str(recorder.directory),
            "synthetic": True, "paid_api_calls": 0}
    (output / f"{recorder.run_id}-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def _images(value):
    """Collect distinct data-URL images to verify fresh visual feedback."""
    if isinstance(value, str):
        return {value} if value.startswith("data:image/") else set()
    if isinstance(value, dict):
        return set().union(*(_images(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_images(item) for item in value))
    return set()
