"""Temporary effectful programs; every child operation traverses the same broker."""
import ast
import time
from .broker import digest
from .sandbox import run_program


class ProgramBinding:
    """Add a managed program entry point without exposing raw actuation."""
    def __init__(self, binding, service):
        """Retain the public binding and host admission callback."""
        self.binding, self.service = binding, service

    def __getattr__(self, name):
        """Delegate only binding contract methods to the public adapter."""
        return getattr(self.binding, name)

    def catalog(self):
        """Expose a versioned program contract alongside native tools."""
        tool = {"id": "runtime.program", "effect": "program", "origin": "generated", "readiness": "ready",
            "requires_current_observation": True,
            "description": "Run a temporary standard-library Python program in an OS sandbox. Define run(input, tools). tools(child_request) invokes one native broker envelope; child request_id must start with the parent request_id plus '/'. Declare allowed_tools. Every child needs fresh evidence and policy version. Nested programs are forbidden. The host performs independent review before dispatch. This is task-local execution, never a published skill.",
            "input_schema": {"type": "object", "properties": {"source": {"type": "string", "maxLength": 32000}, "input": {},
                "allowed_tools": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
                "required": ["source", "input", "allowed_tools"], "additionalProperties": False}}
        return [*self.binding.catalog(), {**tool, "version": digest(tool), "claims": {"status": "declared", "source": "broker-program-v1", "isolation": "OS", "physical_effects": "only_admitted_children"}}]

    def validate_request(self, request):
        """Check declared program scope or the native transport contract."""
        if request["tool"] != "runtime.program":
            validate = getattr(self.binding, "validate_request", None)
            if validate:
                validate(request)
            return
        tree = ast.parse(request["arguments"]["source"])
        if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
            raise ValueError("Program must define run(input, tools)")
        allowed = set(request["arguments"]["allowed_tools"])
        if not allowed <= {t["id"] for t in self.binding.catalog()}:
            raise ValueError("Program scope includes an unknown or nested runtime tool")

    def execute_request(self, tool, args, request):
        """Execute the program with a restricted pipe callback for each child."""
        if tool != "runtime.program":
            if hasattr(self.binding, "execute_request"):
                return self.binding.execute_request(tool, args, request)
            return self.binding.execute(tool, args)
        receipts = []
        def child(value):
            """Bind causal ancestry, scope and current policy before child dispatch."""
            if value.get("tool") not in args["allowed_tools"] or not value.get("request_id", "").startswith(request["request_id"] + "/"):
                raise ValueError("Program child is outside its declared scope or identity")
            self.service.check_execution(value)
            receipt = self.service.broker.execute({**value, "parent_id": request["request_id"]})
            self.service.ingest(receipt, value)
            receipts.append(receipt)
            return receipt  # Programs receive public sensor content, not just guessed next IDs.
        if self.service.adapters:
            output = self.service.workspace.run(args["source"], args["input"], invoke=child)
        else:
            output = run_program(args["source"], args["input"], invoke=child,
                timeout=min(60, max(.01, self.service.deadline-time.monotonic())))
        observations = [o for receipt in receipts for o in receipt.get("result", {}).get("observations", [])]
        # Children already own physical/control/observation counters.
        return {"isError": False, "output": output, "child_requests": [r["request_id"] for r in receipts],
            "evidence_references": [o["id"] for o in observations], "content": observations[-1].get("content", []) if observations else [],
            "done": self.service.bridge.done, "control_steps": 0}
