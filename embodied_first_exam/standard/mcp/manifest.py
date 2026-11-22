"""Per-suite manifests (manifests/<suite>.json) resolved into one task's manifest.json, and a static check.

    python3 manifest.py check manifests/<suite>.json [--task <base or task dir name> ...]
    python3 manifest.py resolve manifests/<suite>.json <task name>      # prints the task's manifest.json

A suite manifest may hold `variants`: [{"match": "<fnmatch glob on the task's base name>", "patch": {...}}, ...]; every
matching variant is deep-merged in order (a dict merges key by key, anything else replaces, null deletes the key).
`match` may also be a list of globs. The resolved manifest has no `variants`. A task whose resolved manifest has
`unsupported` (the reason) gets no MCP-only variant."""
from __future__ import annotations
import copy, fnmatch, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
FORMAT = "efe-mcp-manifest/0"
REF_KEYS = ({"cols"}, {"col"}, {"group"}, {"names"})


def deep_merge(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return copy.deepcopy(b)
    out = copy.deepcopy(a)
    for k, v in b.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def base_name(task: str) -> str:
    for suf in ("-standard-mcp-shell", "-standard-mcp", "-standard", "-privileged", "-realtime"):
        if task.endswith(suf):
            return task[: -len(suf)]
    return task


def resolve(suite: dict, task: str) -> dict:
    base = base_name(task)
    m = {k: v for k, v in suite.items() if k != "variants"}
    for v in suite.get("variants") or []:
        globs = v["match"] if isinstance(v["match"], list) else [v["match"]]
        if any(fnmatch.fnmatchcase(base, g) for g in globs):
            m = deep_merge(m, v.get("patch") or {})
    m["task"] = base
    return m


def _ref_ok(ref) -> str | None:
    if not isinstance(ref, dict):
        return "a reference must be an object"
    if not any(k in ref for k in ("cols", "col", "group", "names")):
        return f"reference {ref}: needs cols, col, group or names"
    if "cols" in ref and not (isinstance(ref["cols"], list) and len(ref["cols"]) == 2 and ref["cols"][0] < ref["cols"][1]):
        return f"reference {ref}: cols = [first, end)"
    return None


def check(m: dict) -> list[str]:
    """Problems of a resolved manifest that can be found without the robot (the server re-checks against /spec)."""
    errs = []
    if m.get("manifest") != FORMAT:
        errs.append(f"manifest must be {FORMAT!r}")
    kind = m.get("kind", "rcb")
    if kind != "rcb":
        try:
            import suites
            suites.tools_for(m)
        except Exception as e:      # an unknown kind, or a manifest its kind cannot list tools for
            errs.append(f"kind {kind!r}: {e}")
        return errs
    for k in ("suite", "robot"):
        if not m.get(k):
            errs.append(f"missing {k}")
    types = m.get("types") or {}
    for n, T in types.items():
        if "dim" in T and not (isinstance(T["dim"], int) and T["dim"] >= 0):
            errs.append(f"types.{n}.dim: a whole number")
        if T.get("initial") is not None and T.get("dim") and len(T["initial"]) != T["dim"]:
            errs.append(f"types.{n}.initial: {T['dim']} values expected")
    fr = m.get("frame") or {}
    if fr.get("quat", "wxyz") not in ("wxyz", "xyzw"):
        errs.append("frame.quat: wxyz or xyzw")
    b = fr.get("base")
    if b is not None:
        if "fixed" in b:
            if len(b["fixed"]) != 7:
                errs.append("frame.base.fixed: x y z qw qx qy qz")
        else:
            for k in ("pos", "yaw", "quat"):
                if k in b and _ref_ok(b[k]):
                    errs.append(f"frame.base.{k}: {_ref_ok(b[k])}")
    for name, P in (m.get("parts") or {}).items():
        where = f"parts.{name}"
        for sec in ("joints", "ee", "ee_delta", "gripper", "ik", "kin", "joint_delta"):
            if sec in P and not isinstance(P[sec], dict):
                errs.append(f"{where}.{sec}: an object")
        j = P.get("joints")
        if j:
            if "type" not in j or "cols" not in j or len(j["cols"]) != 2 or j["cols"][0] >= j["cols"][1]:
                errs.append(f"{where}.joints: type and cols [first, end)")
            elif types.get(j["type"], {}).get("dim") and j["cols"][1] > types[j["type"]]["dim"]:
                errs.append(f"{where}.joints.cols beyond types.{j['type']}.dim")
        g = P.get("gripper")
        if g and "col" in g and not (g.get("type") or (j or {}).get("type")):
            errs.append(f"{where}.gripper: type (or the joints' type)")
        e = P.get("ee")
        if e:
            if "type" not in e or "cols" not in e or e["cols"][1] - e["cols"][0] != 7:
                errs.append(f"{where}.ee: type and cols spanning x y z + quaternion (7)")
            if e.get("quat", fr.get("quat", "wxyz")) not in ("wxyz", "xyzw"):
                errs.append(f"{where}.ee.quat: wxyz or xyzw")
        d = P.get("ee_delta")
        if d:
            for k in ("type", "pos_cols", "pos_scale"):
                if k not in d:
                    errs.append(f"{where}.ee_delta.{k} missing")
            if d.get("rot_cols") and "rot_scale" not in d:
                errs.append(f"{where}.ee_delta.rot_scale missing")
        ik = P.get("ik")
        if ik and ("frame" not in ik or not j):
            errs.append(f"{where}.ik: frame, and joints to send the solution to")
        jd = P.get("joint_delta")
        if jd:
            if j:
                errs.append(f"{where}: joints or joint_delta, not both")
            if "type" not in jd or len(jd.get("cols") or []) != 2 or jd["cols"][0] >= jd["cols"][1]:
                errs.append(f"{where}.joint_delta: type and cols [first, end)")
            if not (P.get("state") or {}).get("joints"):
                errs.append(f"{where}.joint_delta: needs state.joints (the measured angles the changes add to)")
        K = P.get("kin")
        if K:
            js = K.get("joints") or []
            if not js or any(x.get("type", "revolute") not in ("revolute", "prismatic") or len(x.get("axis") or []) != 3
                             or len(x.get("point") or []) != 3 for x in js):
                errs.append(f"{where}.kin.joints: each a revolute or prismatic joint with axis and point")
            t = K.get("tcp") or {}
            if len(t.get("position") or []) != 3 or len(t.get("quaternion_wxyz") or []) != 4:
                errs.append(f"{where}.kin.tcp: position and quaternion_wxyz")
            if _ref_ok(K.get("state")) or len((K.get("state") or {}).get("names") or js) != len(js):
                errs.append(f"{where}.kin.state: a reference to the {len(js)} joint values")
            sol = sum(1 for x in js if x.get("solve"))
            to = j or jd
            if not to or to["cols"][1] - to["cols"][0] != sol:
                errs.append(f"{where}.kin: {sol} solved joints, and joints or joint_delta with as many columns")
            if not (K.get("spec_arm") or (P.get("state") or {}).get("ee_pose")):
                errs.append(f"{where}.kin: a check against the robot (state.ee_pose or spec_arm)")
        for k, ref in (P.get("state") or {}).items():
            if k not in ("joints", "gripper", "gripper_opening_m", "ee_pose"):
                errs.append(f"{where}.state.{k}: unknown (joints, gripper, gripper_opening_m, ee_pose)")
            elif _ref_ok(ref):
                errs.append(f"{where}.state.{k}: {_ref_ok(ref)}")
        if (e or d or ik) and not (P.get("state") or {}).get("ee_pose") and not e:
            errs.append(f"{where}: an end-effector command needs state.ee_pose (the measured pose)")
        if not any(P.get(k) for k in ("joints", "joint_delta", "gripper", "ee", "ee_delta", "ik")):
            errs.append(f"{where}: no command (joints, joint_delta, gripper, ee, ee_delta or ik)")
    B = m.get("base")
    if B:
        if B.get("mode", "velocity") == "pose":
            need = {"x", "y", "yaw"}
        else:
            need = {"vx", "wz"}
        if "type" not in B or not need <= set(B.get("cols") or {}):
            errs.append(f"base: type and cols {sorted(need)}")
        if not (fr.get("base") or {}).get("pos") and "fixed" in (fr.get("base") or {"fixed": 0}):
            errs.append("base: a mobile base needs frame.base from proprio (pos + yaw or quat), not fixed")
    L = m.get("locomotion")
    if L and ("type" not in L or not L.get("cols")):
        errs.append("locomotion: type and cols")
    for k, s in (m.get("signals") or {}).items():
        if not (s.get("finish") or s.get("type")):
            errs.append(f"signals.{k}: type (an action type) or finish")
    for k in ("cameras", "default_cameras", "action_cameras", "state_cameras"):
        if k in m and not isinstance(m[k], list):
            errs.append(f"{k}: a list")
    cams = m.get("cameras") or []
    for k in ("default_cameras", "action_cameras", "state_cameras"):
        bad = [c for c in m.get(k) or [] if cams and c not in cams]
        if bad:
            errs.append(f"{k}: {bad} not in cameras")
    cp = m.get("camera_poses")
    if cp is not None:      # spec camera pose keys -> the frame each is in (rcb_adapter.spec_cam_pose)
        fr = cp.get("frames") if isinstance(cp, dict) else None
        if not isinstance(fr, dict) or not fr or any(v not in ("suite", "base", "tcp") for v in fr.values()):
            errs.append("camera_poses.frames: {spec key: \"suite\" | \"base\" | \"tcp\"}")
        if isinstance(cp, dict) and cp.get("axes", "opencv") not in ("opencv", "opengl"):
            errs.append("camera_poses.axes: \"opencv\" or \"opengl\"")
        tp = (cp.get("tcp_part") if isinstance(cp, dict) else None) or {}
        for c, p in tp.items():
            if cams and c not in cams:
                errs.append(f"camera_poses.tcp_part: camera {c!r} not in cameras")
            if p not in (m.get("parts") or {}):
                errs.append(f"camera_poses.tcp_part: {c!r} -> {p!r} is not a part")
            elif not ((m["parts"][p].get("state") or {}).get("ee_pose") or m["parts"][p].get("kin")):
                errs.append(f"camera_poses.tcp_part: part {p!r} has no hand pose (state.ee_pose or kin)")
    try:
        sys.path.insert(0, str(HERE))
        import schema
        tools = schema.tools_for(m)
        names = [t["name"] for t in tools]
        for t in tools:
            try:
                import jsonschema
                jsonschema.Draft202012Validator.check_schema(t["inputSchema"])
            except ImportError:
                pass
        if "describe_robot" not in names:
            errs.append("no describe_robot tool")
    except Exception as ex:   # noqa: BLE001
        errs.append(f"tools_for failed: {type(ex).__name__}: {ex}")
    return errs


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("manifest"); c.add_argument("--task", action="append", default=[])
    r = sub.add_parser("resolve"); r.add_argument("manifest"); r.add_argument("task")
    a = ap.parse_args(argv)
    suite = json.loads(pathlib.Path(a.manifest).read_text())
    if a.cmd == "resolve":
        print(json.dumps(resolve(suite, a.task), indent=1))
        return 0
    tasks = a.task or [suite.get("suite", "x") + "-example"]
    bad = 0
    for t in tasks:
        m = resolve(suite, t)
        if m.get("unsupported"):        # no MCP-only variant of this task (generate.py skips it; the reason is shown)
            print("none " + base_name(t) + "  (no MCP-only variant: " + str(m["unsupported"])[:160] + ")")
            continue
        errs = check(m)
        tl = []
        if not errs:
            import schema
            tl = [x["name"] for x in schema.tools_for(m)]
        print(("FAIL " if errs else "ok   ") + base_name(t) + ("" if errs else "  tools: " + ", ".join(tl)))
        for e in errs:
            print("     - " + e)
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
