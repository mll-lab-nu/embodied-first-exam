"""Real native processes, synthetic model and robot. No billable API requests."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

from humanclaw_bench.experiments.recorder import TraceRecorder, span
from humanclaw_bench.harnesses.services import flattened_tools
from .backend import MockBackend
from .protocol import ToolService
from .service import MeteredService
from .adapters import run_bare, run_native
from .report import summarize


class ScriptedModel:
    """Return deterministic model replies for real native transport checks."""
    def __init__(self):
        """Initialize the synthetic model request history."""
        self.requests = []

    def __call__(self, endpoint, payload):
        """Return move, finish and completion messages in the requested wire format."""
        self.requests.append(payload)
        index = len(self.requests)
        response = {"id": f"resp_{index}", "object": "response", "created_at": int(time.time()),
                    "model": payload["model"], "status": "in_progress", "output": [], "usage": None}
        events = [{"type": "response.created", "response": dict(response)},
                  {"type": "response.in_progress", "response": dict(response)}]
        if index <= 2:
            target = "move" if index == 1 else "done"
            selected = next(((ns, tool) for ns, tool in flattened_tools(payload["tools"])
                             if tool.get("name") == target or tool.get("name", "").endswith("__" + target)), None)
            if selected is None:
                raise ValueError("Common mock tools were not exposed to the native model")
            ns, tool = selected
            arguments = {"request_id": f"operation-{index}", "observation_id": index-1}
            arguments.update({"delta": 2} if index == 1 else {"success": True})
            encoded = json.dumps(arguments)
            item = {"type": "function_call", "id": f"fc_{index}", "call_id": f"call_{index}",
                    "name": tool["name"], "arguments": "", "status": "in_progress"}
            if ns:
                item["namespace"] = ns
            events.append({"type": "response.output_item.added", "output_index": 0, "item": dict(item)})
            events.append({"type": "response.function_call_arguments.delta", "item_id": item["id"], "output_index": 0, "delta": encoded})
            events.append({"type": "response.function_call_arguments.done", "item_id": item["id"], "output_index": 0, "arguments": encoded})
            item.update(arguments=encoded, status="completed")
        else:
            item = {"type": "message", "id": f"msg_{index}", "role": "assistant", "status": "in_progress", "content": []}
            events.append({"type": "response.output_item.added", "output_index": 0, "item": dict(item)})
            part = {"type": "output_text", "text": "", "annotations": []}
            events.append({"type": "response.content_part.added", "item_id": item["id"], "output_index": 0, "content_index": 0, "part": dict(part)})
            text = "Synthetic framework check complete."
            events.append({"type": "response.output_text.delta", "item_id": item["id"], "output_index": 0, "content_index": 0, "delta": text})
            events.append({"type": "response.output_text.done", "item_id": item["id"], "output_index": 0, "content_index": 0, "text": text})
            part["text"] = text
            events.append({"type": "response.content_part.done", "item_id": item["id"], "output_index": 0, "content_index": 0, "part": part})
            item.update(status="completed", content=[part])
        events.append({"type": "response.output_item.done", "output_index": 0, "item": item})
        response.update(status="completed", output=[item], usage={"input_tokens": 100, "output_tokens": 10,
            "total_tokens": 110, "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}})
        events.append({"type": "response.completed", "response": response})
        if payload.get("stream"):
            return b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events), "text/event-stream"
        return json.dumps(response).encode(), "application/json"


def smoke(harness, config, output, *, require_isolation=False):
    """Verify native tool execution, images and history without paid requests."""
    with TraceRecorder(output, {"harness": harness, "benchmark": "synthetic-libero-protocol", "synthetic": True}) as recorder:
        bridge = ToolService(MockBackend(), recorder.run_id, recorder.directory)
        model = ScriptedModel()
        with span("episode.decision"):
            with MeteredService(bridge, upstream_url="http://unused", api_key="unused", responder=model) as meter:
                if harness == "bare":
                    result = run_bare(bridge, meter, config)
                else:
                    result = run_native(harness, bridge, meter, config, require_isolation=require_isolation)
        checks = {"robot_moved_once": bridge.backend.control_steps == 1,
                  "robot_reached_target": bridge.backend.success(), "agent_done": bridge.termination == "agent_done",
                  "initial_image_sent": "input_image" in json.dumps(model.requests[0]),
                  "ordinary_history_retained": "call_1" in json.dumps(model.requests[1])}
        recorder.write_json("checks.json", checks)
        bridge.shutdown()
        if not all(checks.values()):
            raise AssertionError(checks)
        recorder.finish(outcome={"benchmark_success": None, "synthetic_checks": checks,
                                 "infrastructure_error": False, "paid_model_requests": 0})
    report = summarize(recorder.directory)
    result = {"passed": True, "harness": harness, "directory": str(recorder.directory),
              "model_requests": report["model_requests"], "paid_model_requests": 0}
    print(json.dumps(result))
    return result


def main():
    """Run a selected synthetic transport check from the command line."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--harness", choices=["bare", "codex", "pi"], required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--require-isolation", action="store_true")
    a = p.parse_args()
    smoke(a.harness, json.loads(Path(a.config).read_text()), a.output, require_isolation=a.require_isolation)


if __name__ == "__main__":
    main()
