"""HumanCLAW public semantics; no benchmark vocabulary leaks into the broker."""
import json
from ..environment import tool_definitions, image_content, protocol_identity
from .broker import digest


class HumanClawBinding:
    """Translate only public HumanCLAW actions, observations and lifecycle facts."""
    def __init__(self, bridge):
        """Bind the task-local runtime dependencies and initial state."""
        self.bridge = bridge

    @property
    def observation_id(self):
        """Name the currently available ego observation."""
        return f"observation:{self.bridge.step}"

    def catalog(self):
        """Describe native schemas with declared effects and source identities."""
        return [{"id": f"humanclaw.{tool['name']}", "name": tool["name"],
            "description": tool["description"], "input_schema": tool["inputSchema"],
            "version": digest(tool), "origin": "environment", "readiness": "ready",
            "effect": "terminate" if tool["name"] == "stand" else "physical",
            "requires_current_observation": True,
            "claims": {"status": "declared", "source": protocol_identity(),
                "observation_channels": ["rgb"], "success_feedback": "unsupported",
                "control_steps_per_motion": 15, "control_hz": 30,
                "reset": "unsupported", "observe_without_action": "unsupported"}}
            for tool in tool_definitions()]

    def observation(self):
        """Return the current public RGB observation without evaluator state."""
        return {"id": self.observation_id, "source": "environment", "status": "observed",
            "channels": ["rgb"], "content": [image_content(self.bridge.image)]}

    def validate_request(self, request):
        """Require matching native and broker transport identities."""
        if request["arguments"]["request_id"] != request["request_id"]:
            raise ValueError("HumanCLAW native and broker request_id must match")

    def execute(self, tool, args):
        """Dispatch one native action and retain public observations and control counts."""
        result = self.bridge.call(tool.split(".", 1)[1], args)
        if result.get("isError"):
            return result
        public = json.loads(result["content"][0]["text"])
        return {**result, "observations": [self.observation()], "done": public["done"],
            "control_steps": 0 if tool == "humanclaw.stand" else 15,
            "termination": public["termination_reason"]}
