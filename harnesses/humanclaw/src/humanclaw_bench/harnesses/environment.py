"""Public observations and serialized, idempotent benchmark actions.

The controller runs on the simulator's owning thread. HTTP workers enqueue
requests; they never touch Habitat, its graphics context, or benchmark metrics.
"""

from __future__ import annotations

import base64
from concurrent.futures import Future
import hashlib
import io
import json
import queue
import threading
from typing import Any, Callable

from PIL import Image

from humanclaw_bench.agent.skills import ACTION_PARSER_VERSION, normalize_action
from humanclaw_bench.agent.types import PlannerResult
from humanclaw_bench.experiments.integration import SKILLS
from humanclaw_bench.experiments.recorder import event, span


# Version of the model-visible native text: tool definitions and initial prompt.
# Bump it with any change to that text. Runs that record no protocol used v1:
# no Sit-duration fact, and Stop read "finish at the current pose; no generated motion".
NATIVE_ACTION_PROTOCOL = "native-actions-v2"

# One generated motion chunk is 15 frames (n_future) played at 30 fps: 0.5 s.
ACTION_NAMES = (
    "Walk<forward><slow|normal|fast> (0.2/0.4/0.6 metres)",
    "Stop/Stand (submits the current pose as the final pose and ends the episode; "
    "no further motion is generated)",
    "Turn<left|right><degrees> (clamped to 10–120 degrees)",
    "Climb upstairs<normal>",
    "Sit down<height> (height clamped to 0.15–0.85 metres; one call moves for only "
    "about 0.5 s and may not complete sitting down)",
    "Step back<distance> (clamped to 0.10–0.60 metres)",
    "Side step<left|right><distance> (clamped to 0.10–0.50 metres)",
    "Walk downstairs<normal>",
)


def tool_definitions() -> list[dict[str, Any]]:
    """Describe the eight public benchmark actions without private evaluator state."""
    return [{
        "name": name,
        "description": f"Execute one HumanCLAW action: {ACTION_NAMES[index]}. "
        "Use the latest observation_id. Describe the CURRENT image in visible_state, "
        "including whether the task target is visible. Return includes a new image. "
        "Call actions sequentially; reuse request_id only when retrying the same action.",
        "inputSchema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "request_id": {"type": "string", "minLength": 1},
                "observation_id": {"type": "integer", "minimum": 0},
                "action_name": {"type": "string", "description": ACTION_NAMES[index]},
                "visible_state": {"type": "string", "minLength": 1},
            },
            "required": ["request_id", "observation_id", "action_name", "visible_state"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    } for index, name in enumerate(SKILLS)]


def protocol_identity() -> dict[str, str]:
    """Name the native action protocol and digest the exact tool text it serves."""
    served = json.dumps(tool_definitions(), sort_keys=True, ensure_ascii=False)
    return {"protocol": NATIVE_ACTION_PROTOCOL,
            "action_parser_version": ACTION_PARSER_VERSION,
            "tool_definitions_sha256": hashlib.sha256(served.encode("utf-8")).hexdigest()}


def image_content(image: Image.Image) -> dict[str, str]:
    """Encode an ego image as an MCP and Pi-compatible PNG content block."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return {"type": "image", "mimeType": "image/png",
            "data": base64.b64encode(buffer.getvalue()).decode("ascii")}


class EnvironmentBridge:
    """Share only the task, ego image and action outcome with native agents."""

    def __init__(self, image: Image.Image, max_steps: int,
                 execute: Callable[[int, PlannerResult], tuple[Image.Image, bool]],
                 instruction: str):
        """Bind initial observation and the owner-thread benchmark executor."""
        self.image, self.max_steps, self.execute = image, max_steps, execute
        self.instruction = instruction
        self.step = 0
        self.done = False
        self.termination = "not_started"
        self.cache: dict[str, tuple[str, dict[str, Any]]] = {}
        self.provider_requests: dict[tuple[str, str], list[str]] = {}
        self.pending: queue.Queue = queue.Queue()
        self.failure: BaseException | None = None
        self.owner = threading.get_ident()

    def initial_prompt(self) -> str:
        """Describe the task and action protocol without adding a second planner.

        Each native session requests this prompt once, so the protocol identity
        is recorded here, inside the session's trace.
        """
        event("environment.protocol", kind="environment", name="environment.protocol",
              data=protocol_identity())
        return (
            f"Perform this HumanCLAW embodied task: {self.instruction}\n"
            f"Current observation_id: 0. Maximum environment actions: {self.max_steps}.\n"
            "The attached image is the current first-person observation. Use the eight "
            "humanclaw environment tools to act. Each tool executes exactly one action "
            "and returns the next image and observation_id. Use a new request_id for "
            "each new action. Wait for its result before choosing another action. "
            "In visible_state describe the CURRENT image, whether the task target is "
            "visible and whether the near-body lane is clear. Do not claim hidden state. "
            "Use stand (Stop/Stand) when finished. When done is true, provide a short "
            "final answer and make no further environment calls."
        )

    def submit(self, name: str, arguments: dict[str, Any]) -> Future:
        """Queue a request for execution on the environment owner thread."""
        result: Future = Future()
        self.pending.put((name, arguments, result))
        return result

    def drain(self) -> None:
        """Execute queued actions in order and propagate infrastructure failures."""
        if threading.get_ident() != self.owner:
            raise RuntimeError("Environment actions must run on the simulator thread")
        while True:
            try:
                name, arguments, future = self.pending.get_nowait()
            except queue.Empty:
                return
            if future.cancelled():
                continue
            try:
                future.set_result(self.call(name, arguments))
            except BaseException as exc:
                self.failure = exc
                future.set_exception(exc)
                raise

    def close(self) -> None:
        """Fail queued requests when the episode session has closed."""
        while not self.pending.empty():
            _, _, future = self.pending.get_nowait()
            if not future.done():
                future.set_exception(RuntimeError("Episode session closed"))

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Validate freshness and idempotency before executing exactly one action."""
        if threading.get_ident() != self.owner:
            raise RuntimeError("Environment actions must run on the simulator thread")
        request_id = args.get("request_id") if isinstance(args, dict) else None
        from_provider = isinstance(request_id, str) and (name, request_id) in self.provider_requests
        event("mcp.requested" if from_provider else "tool.requested", kind="tool", name=name,
              data={"arguments": args, "interface": "mcp"}, step=self.step)
        try:
            if name not in SKILLS or not isinstance(args, dict):
                raise ValueError("Unknown action or invalid arguments")
            if set(args) != {"request_id", "observation_id", "action_name", "visible_state"}:
                raise ValueError("Expected request_id, observation_id, action_name and visible_state")
            if any(not isinstance(args[k], str) or not args[k].strip()
                   for k in ("request_id", "action_name", "visible_state")):
                raise ValueError("request_id, action_name and visible_state must be nonempty strings")
            fingerprint = json.dumps([name, args], sort_keys=True)
            if request_id in self.cache:
                previous, result = self.cache[request_id]
                if previous != fingerprint:
                    raise ValueError("request_id was already used with different arguments")
                event("tool.deduplicated", kind="tool", name=name,
                      data={"request_id": request_id}, step=self.step)
                return result
            if type(args["observation_id"]) is not int or args["observation_id"] != self.step:
                raise ValueError(f"Stale observation: current observation_id is {self.step}")
            if self.done or self.failure is not None:
                raise ValueError("Episode has ended; no further actions are allowed")

            plan = {"action_id": SKILLS.index(name), "action_name": args["action_name"],
                    "visible_state": args["visible_state"], "request_id": request_id,
                    "observation_id": self.step,
                    "native_call_ids": self.provider_requests.get((name, request_id), [])}
            with span("action.normalize", input=plan, step=self.step,
                      attributes={"action_parser_version": ACTION_PARSER_VERSION}) as normal:
                action = normalize_action(plan)
                normal.set_output(action.to_json())
        except ValueError as exc:
            event("tool.rejected", kind="tool", name=name,
                  data={"error": str(exc), "request_id": request_id, "arguments": args,
                        "action_parser_version": ACTION_PARSER_VERSION}, step=self.step)
            return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}

        decision = PlannerResult(raw_plan=plan, action=action, planner_skill=plan, verifier={})
        try:
            # The evaluator owns the sole tool execution span and metrics/physics.
            self.image, env_done = self.execute(self.step, decision)
        except BaseException as exc:
            # An uncertain partial execution is terminal, never automatically retried.
            self.failure = exc
            raise
        self.step += 1
        self.done = env_done or name == "stand" or self.step >= self.max_steps
        self.termination = ("stop" if name == "stand" else "environment_done" if env_done
                            else "max_steps" if self.done else "running")
        public = {"request_id": request_id, "observation_id": self.step,
                  "action": action.to_json(), "done": self.done,
                  "termination_reason": self.termination if self.done else None}
        result = {"isError": False, "content": [
            {"type": "text", "text": json.dumps(public)}, image_content(self.image),
        ]}
        self.cache[request_id] = fingerprint, result
        event("observation.available", kind="environment", name="environment.observation",
              data={**public, "image": self.image}, step=self.step)
        return result
