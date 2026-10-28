"""Minimal public entry contract for sessions without a prewritten binding."""
from __future__ import annotations

import copy
import jsonschema


BOOTSTRAP_SCHEMA = {
    "type": "object", "required": ["schema", "task", "entries", "transports"],
    "properties": {
        "schema": {"const": "bootstrap-v1"}, "task": {"type": "string", "minLength": 1},
        "entries": {"type": "array", "items": {"type": "string"}},
        "source_roots": {"type": "array", "items": {"type": "string"}},
        "internet": {"type": "boolean"},
        "search_url": {"type": "string"},
        "dependency_index": {"type": "string"},
        "transports": {"type": "array", "items": {
            "type": "object", "required": ["id", "kind", "root"], "additionalProperties": False,
            "properties": {"id": {"type": "string"}, "kind": {"enum": ["http", "mcp"]},
                           "root": {"type": "string"}, "credential_env": {"type": "string"}}}},
        "max_actions": {"type": "integer", "minimum": 1},
        "snapshot": {"type": "object"},
    }, "additionalProperties": False,
}


class BootstrapBridge:
    """Carry task bookkeeping without inventing observations or action semantics."""

    def __init__(self, spec):
        """Validate and freeze ordinary access settings before discovery starts."""
        jsonschema.validate(spec, BOOTSTRAP_SCHEMA)
        ids = [item["id"] for item in spec["transports"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate transport handle")
        self.bootstrap = copy.deepcopy(spec)
        self.instruction = spec["task"]
        self.max_steps = spec.get("max_actions", 100)
        self.step = 0
        self.done = False
        self.termination = None
        self.provider_requests = {}

    def close(self):
        """Leave public environment lifecycle decisions to the discovered adapter."""
