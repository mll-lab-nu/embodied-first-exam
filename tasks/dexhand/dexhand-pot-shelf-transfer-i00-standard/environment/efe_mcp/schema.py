"""The tool list of one task: schema/tools.json narrowed by the task's manifest (no service contact: the list is
answered before the agent's first call, which starts the agent's clock).

An RCB task (manifest kind "rcb") lists one tool per agent-facing endpoint its service serves (manifest `tools`,
written by inject.py: spec, observe, submit and finish everywhere, reset where the task has a reset budget, kinematics
where the service offers it); a tool's `realtime_only` fields (submit's `at`) only in realtime mode
(manifest `realtime`): in standard mode the world is frozen between submits. Another kind (suites.py) lists
its own."""
from __future__ import annotations
import copy, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
DRAFT = "https://json-schema.org/draft/2020-12/schema"
ALWAYS = ("spec", "observe", "submit", "finish")      # every RCB task


def canonical() -> dict:
    return json.loads((HERE / "schema" / "tools.json").read_text())


def tool(name: str) -> dict:
    t = next(t for t in canonical()["tools"] if t["name"] == name)
    return {"name": t["name"], "description": t["description"], "inputSchema": copy.deepcopy(t["inputSchema"])}


def tools_for(m: dict) -> list:
    """The tool list for the task of manifest `m`."""
    if m.get("kind", "rcb") != "rcb":
        import suites
        return suites.tools_for(m)
    want = set(m.get("tools") or ALWAYS)
    out = []
    for t in canonical()["tools"]:
        if t["name"] not in want:
            continue
        t = copy.deepcopy(t)
        for k in t.pop("realtime_only", []) if not m.get("realtime") else []:
            t["inputSchema"]["properties"].pop(k)
        t.pop("realtime_only", None)
        t["inputSchema"]["$schema"] = DRAFT
        out.append({"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]})
    return out


def validate_args(schema: dict, args: dict) -> None:
    """A small validator for the subset the tool schemas use (types, required, enum, bounds, additionalProperties),
    so a malformed call is refused before anything runs."""
    _check(schema, args, "arguments")


def _check(s, v, path):
    from rcb_tools import ToolError
    t = s.get("type")
    if t == "object":
        if not isinstance(v, dict):
            raise ToolError(f"{path}: an object expected")
        props = s.get("properties", {})
        for r in s.get("required", []):
            if r not in v:
                raise ToolError(f"{path}: missing {r!r}")
        if s.get("additionalProperties") is False:
            extra = [k for k in v if k not in props]
            if extra:
                raise ToolError(f"{path}: unknown {extra}; allowed: {sorted(props)}")
        for k, sub in props.items():
            if k in v:
                _check(sub, v[k], f"{path}.{k}")
    elif t == "array":
        if not isinstance(v, list):
            raise ToolError(f"{path}: an array expected")
        if "minItems" in s and len(v) < s["minItems"]:
            raise ToolError(f"{path}: at least {s['minItems']} items")
        if "maxItems" in s and len(v) > s["maxItems"]:
            raise ToolError(f"{path}: at most {s['maxItems']} items")
        it = s.get("items")
        if isinstance(it, dict):
            for i, x in enumerate(v):
                _check(it, x, f"{path}[{i}]")
    elif t in ("number", "integer"):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or (t == "integer" and not float(v).is_integer()):
            raise ToolError(f"{path}: a {t} expected")
        if "minimum" in s and v < s["minimum"]:
            raise ToolError(f"{path}: at least {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            raise ToolError(f"{path}: at most {s['maximum']}")
        if "exclusiveMinimum" in s and v <= s["exclusiveMinimum"]:
            raise ToolError(f"{path}: more than {s['exclusiveMinimum']}")
    elif t == "string":
        if not isinstance(v, str):
            raise ToolError(f"{path}: a string expected")
        if "maxLength" in s and len(v) > s["maxLength"]:
            raise ToolError(f"{path}: at most {s['maxLength']} characters")
    elif t == "boolean":
        if not isinstance(v, bool):
            raise ToolError(f"{path}: true or false expected")
    if "enum" in s and v not in s["enum"]:
        raise ToolError(f"{path}: one of {s['enum']}")
