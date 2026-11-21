"""Tool definitions narrowed to one robot: schema/tools.v0.json + the task's manifest (no sim contact: the tool list is
answered before the agent's first call, which starts the agent's clock)."""
from __future__ import annotations
import copy, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
DRAFT = "https://json-schema.org/draft/2020-12/schema"


def canonical() -> dict:
    return json.loads((HERE / "schema" / "tools.v0.json").read_text())


def spaces_of(m: dict) -> list:
    parts = m.get("parts", {}).values()
    sp = []
    if any(P.get("joints") for P in parts):
        sp.append("joint")
    if any(P.get("ee") or P.get("ik") for P in parts):
        sp.append("ee")
    if any(P.get("ee_delta") for P in parts):
        sp.append("ee_delta")
    if m.get("locomotion"):
        sp.append("whole_body")
    sp.append("native")
    return sp


def part_lines(m: dict) -> str:
    out = []
    for n, P in m.get("parts", {}).items():
        caps = []
        if P.get("joints"):
            j = P["joints"]
            caps.append(f"{j['cols'][1] - j['cols'][0]} joints")
        if P.get("ee") or P.get("ik"):
            caps.append("end-effector pose")
        elif P.get("ee_delta"):
            caps.append("end-effector pose (stepped by its delta controller)")
        if P.get("gripper"):
            caps.append("gripper")
        out.append(f"{n} ({P.get('kind', 'arm')}: {', '.join(caps) or 'state only'})")
    if m.get("base"):
        out.append("base (mobile: dx, dy, dyaw)")
    return "; ".join(out)


def tools_for(m: dict) -> list:
    """The tool list for the robot of manifest `m`."""
    kind = m.get("kind", "rcb")
    if kind != "rcb":
        import suites
        return suites.tools_for(m)
    tools = {t["name"]: copy.deepcopy(t) for t in canonical()["tools"]}
    parts = m.get("parts", {})
    cams = list(m.get("cameras") or [])
    has_pose = any(P.get("ee") or P.get("ik") or P.get("ee_delta") for P in parts.values())
    has_grip = any(P.get("gripper") for P in parts.values())
    has_joints = any(P.get("joints") for P in parts.values())
    targets = list(parts) + (["base"] if m.get("base") else [])
    plines = part_lines(m)

    def cam_enum(prop):
        if cams:
            prop["items"] = {"type": "string", "enum": cams}

    o = tools["observe"]["inputSchema"]["properties"]
    cam_enum(o["cameras"]); cam_enum(o["inline_cameras"])
    if cams:
        tools["observe"]["description"] += f" Cameras: {', '.join(cams)}."

    mv = tools["move_robot"]
    gi = mv["inputSchema"]["properties"]["goals"]["items"]["properties"]
    gi["target"]["enum"] = targets or ["none"]
    if not m.get("base"):
        for k in ("dx", "dy", "dyaw"):
            gi.pop(k)
    if not has_pose:
        gi.pop("position"); gi.pop("quaternion_wxyz")
    if not has_grip:
        gi.pop("gripper")
    if not has_joints:
        gi.pop("joint_positions")
    mv["description"] += f" This robot's targets: {plines}."
    cam_enum(mv["inputSchema"]["properties"]["inline_cameras"])

    sp = spaces_of(m)
    et = tools["execute_trajectory"]
    et["inputSchema"]["properties"]["space"]["enum"] = sp
    cam_enum(et["inputSchema"]["properties"]["inline_cameras"])
    et["description"] += f" This robot's parts: {plines}. Spaces: {', '.join(sp)}."

    L = m.get("locomotion")
    if L:
        lo = tools["locomote"]["inputSchema"]["properties"]
        lim = L.get("limits", {})
        for k in ("vx", "vy", "wz", "height"):
            if k not in L["cols"]:
                if k in lo:
                    lo.pop(k)
                    if k in tools["locomote"]["inputSchema"]["required"]:
                        tools["locomote"]["inputSchema"]["required"].remove(k)
                continue
            if k in lim:
                lo[k]["minimum"], lo[k]["maximum"] = lim[k]
        cam_enum(lo["inline_cameras"])
        if L.get("note"):
            tools["locomote"]["description"] += " " + L["note"]
    else:
        tools.pop("locomote")

    sg = tools["signal"]
    kinds = ["done"] + [k for k in (m.get("signals") or {}) if k != "done"]
    sg["inputSchema"]["properties"]["kind"]["enum"] = kinds
    if not any((v or {}).get("dim") for v in (m.get("signals") or {}).values()):
        sg["inputSchema"]["properties"].pop("category")
    if m.get("signals_text"):
        sg["description"] = m["signals_text"]
    cam_enum(tools["wait"]["inputSchema"]["properties"]["inline_cameras"])
    if m.get("resets"):
        cam_enum(tools["reset_episode"]["inputSchema"]["properties"]["inline_cameras"])
        if isinstance(m["resets"], dict) and m["resets"].get("note"):
            tools["reset_episode"]["description"] += " " + m["resets"]["note"]
    else:
        tools.pop("reset_episode")
    if not targets:            # no part the unified conventions reach: the robot's own action types only
        tools.pop("move_robot")
    out = []
    for t in tools.values():
        t["inputSchema"]["$schema"] = DRAFT
        out.append({"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]})
    return out


def validate_args(schema: dict, args: dict) -> None:
    """A small validator for the subset the tool schemas use (types, required, enum, bounds, additionalProperties),
    so a malformed call is refused before anything runs."""
    _check(schema, args, "arguments")


def _check(s, v, path):
    from rcb_adapter import ToolError
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
