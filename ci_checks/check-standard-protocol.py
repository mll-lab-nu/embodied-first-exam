#!/usr/bin/env python3
"""eai-standard/2.2 (formerly rcb-limited/2.2) conformance test, run against a LIVE sim service (docs/STANDARD_MODE.md).

    check-standard-protocol.py --url http://127.0.0.1:8000 [--task tasks/<t>-standard] [--out DIR] [--watch 0.5]
    check-standard-protocol.py --launch tasks/<t>-standard [--port 18000] [--out DIR]   # compose up the task's sidecar, test, down

It drives the service through the task's own shipped client (environment/rcb_client.py) where the protocol allows, and
through raw HTTP for the protocol-level cases (404s, 2.0/2.1 requests, malformed bodies). Checked:
  /spec     2.2 keys and nothing unknown; cameras (intrinsics, mounting), robot_spec (joints with real limits, grippers,
            controller gains, TCP), world, kinematics, depth, proprio groups; budget == the task's [agent].timeout_sec;
  never     no forbidden field anywhere (segmentation, object poses, physical parameters); nothing in `static` or the limited
            texts says where things are (positions, heights, centres, world coordinates: check-standard-texts.sh), while names,
            sizes and colours may stay (listed as INFO); response parts and meta keys from the allowed sets;
  frames    one frame axis: proprio rows = frame_step = frame_time_s = extrinsic_cv/<cam> = depth_frames/<cam> frames;
            time = step / control_hz; meta.cameras = the last frame's pose; static cameras never move;
  depth     none by default; `last` = float32 (H,W) pixel-aligned with RGB, >= 0, 0 = invalid, plausible range; `frames` =
            one map per frame whose last map equals `last` to 1 mm; the 2.1 `include_depth` form still answers;
  kinematics stateless (twice the same answer, no control step advances); FK of the measured joints = the measured TCP
            proprio; FK(parent link) . mount = each moving camera's pose; IK round trip; unreachable -> ok false; 400s;
  projection the TCP projected through intrinsics/extrinsics lands on the gripper: within a 6 cm disc around it the depth
            image has a surface at the TCP's depth (+-5 cm) (overlays in --out).
A watch of --watch seconds (default 0.5) advances physics while holding the last command, as /observe does for an agent.
Exit 1 on any FAIL. Needs numpy + requests (+ pyyaml for --launch, Pillow for the overlays)."""
from __future__ import annotations
import argparse, json, math, os, re, subprocess, sys, tempfile, time
from pathlib import Path

import numpy as np
import requests

SPEC_KEYS_REQ = {"protocol", "protocol_compat", "simulator", "robot", "task_text", "control_hz", "max_chunk_s", "max_watch_s",
                 "cameras", "default_cameras", "action_types", "proprio_layout", "proprio_groups", "static", "world", "budget",
                 "robot_spec", "kinematics", "depth"}
SPEC_KEYS_OK = SPEC_KEYS_REQ | {"physics_substeps", "physics_hz", "on_service_error", "max_call_wall_s",   # + crash recovery
                                "episode", "max_control_steps"}                                           # PROTOCOL §4.7, §4.5
CAM_KEYS_REQ = {"rgb", "depth", "mounted", "resolution", "intrinsic_cv", "mount"}
CAM_KEYS_OK = CAM_KEYS_REQ | {"calibration_in_obs", "depth_range_m"}
ROBOT_KEYS_REQ = {"name", "base", "joints", "grippers", "controller", "tcp"}
ROBOT_KEYS_OK = ROBOT_KEYS_REQ | {"description"}
JOINT_KEYS_REQ = {"name", "type", "unit", "position_limits", "velocity_limit", "effort_limit"}
JOINT_KEYS_OK = JOINT_KEYS_REQ | {"group", "note", "rated_velocity", "rated_effort", "rated_source"}
KIN_KEYS_REQ = {"endpoint", "joint_names", "frame", "quaternion_order", "links", "tcp_frames", "ee_frames", "ik_targets"}
KIN_KEYS_OK = KIN_KEYS_REQ | {"base_pose_proprio", "ik", "stateless", "note"}
WORLD_KEYS_REQ = {"frame", "up", "units", "quaternion_order", "camera_axes"}
GROUPS_REQ = ("joint_pos", "joint_vel", "gripper_opening", "tcp_pose", "joint_effort")
META_KEYS_OK = {"stopped", "step", "calls", "control_steps", "physics_steps", "sim_time_s", "time_s", "time_left_s", "proprio", "cameras",
                "done", "reason", "degraded", "chunk_id", "type", "executed_rows", "control_steps_chunk", "physics_steps_chunk",
                "clipped", "n_clipped", "plan", "rejected", "ok", "obs_id", "seconds", "control_steps_watch", "physics_steps_watch",
                "frames_skipped"}   # frames_skipped: frames a call left out at max_frames_per_call (RoboWits, RoboTangle)
META_CAM_KEYS_OK = {"intrinsic_cv", "extrinsic_cv", "cam2world_gl", "image_size"}
PART_RE = re.compile(r"^(video|frames|last|last_depth|depth_frames|depth|extrinsic_cv)/[^/]+$|^(proprio|frame_step|frame_time_s)$")
FORBIDDEN = re.compile(r"mask|segment|semantic(?!s$)|instance_?id|bbox|bounding|categor|object|\bobj_|label|mass|friction|restitution|"
                       r"inertia|density|damping|stiffness", re.I)
GAINS = re.compile(r"damping|stiffness", re.I)
POSITION_KEY = re.compile(r"(?:^|_)(?:pos|position|positions|pose|poses|origin|location|coords?|coordinates|world|translation)(?:_|$)|"
                          r"(?:^|_)cent(?:er|re)s?(?:_|$)|(?:^|_)xyz?$|(?:^|_)(?:top|surface|floor|table|plane|height|elevation)?_?z$", re.I)
WORLD_TEXT = re.compile(r"\bworld\s+[xyz]\s*=", re.I)
COORDS = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?\s*)?\)")


def world_text(s: str) -> bool:
    """A text that gives a world coordinate: a pixel-to-world formula, or a coordinate tuple with a decimal point that is
    not the robot's own pose ("robot base at (0, 0, 1.08)" stays)."""
    return bool(WORLD_TEXT.search(s)) or any("." in m.group(0) and not re.search(r"base|robot|origin", s[max(0, m.start() - 40):m.start()], re.I)
                                             for m in COORDS.finditer(s))
CONVENTIONS = {"static.floor_z": 0.0}       # BEHAVIOR: the floor is the plane z = 0 (the world frame's definition)
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])


class Report:
    def __init__(self):
        self.rows = []

    def add(self, level: str, name: str, msg: str = "") -> None:
        self.rows.append({"level": level, "check": name, "msg": msg})
        print(f"{level:4s} {name}{': ' + msg if msg else ''}", flush=True)

    def ok(self, cond: bool, name: str, msg: str = "", level_bad: str = "FAIL") -> bool:
        self.add("PASS" if cond else level_bad, name, msg)
        return bool(cond)

    @property
    def failed(self) -> int:
        return sum(r["level"] == "FAIL" for r in self.rows)


# ---------------------------------------------------------------- helpers
def forbidden(obj, path="", skip=()) -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if p in skip:
                continue
            if FORBIDDEN.search(str(k)) and not (GAINS.search(str(k)) and p.startswith("robot_spec.controller")):
                out.append(p)
            out += forbidden(v, p, skip)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += forbidden(v, f"{path}[{i}]", skip)
    return out


def static_positions(obj, path="static") -> list[str]:
    """Paths in /spec static that say WHERE something is (the same rule as rcb_limited.static_positions)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if POSITION_KEY.search(str(k)) and CONVENTIONS.get(p, object()) != v:
                out.append(p)
            else:
                out += static_positions(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += static_positions(v, f"{path}[{i}]")
    elif isinstance(obj, str) and world_text(obj):
        out.append(path)
    return out


def leaves(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list) and obj and all(isinstance(v, (dict, list)) for v in obj):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{path}[{i}]")
    else:
        yield path, obj


def mat(x, shape) -> np.ndarray | None:
    try:
        a = np.asarray(x, dtype=np.float64)
        return a if a.shape == shape and np.all(np.isfinite(a)) else None
    except Exception:  # noqa: BLE001
        return None


def rigid(T) -> bool:
    R = T[:3, :3]
    return bool(np.allclose(R @ R.T, np.eye(3), atol=1e-4) and abs(np.linalg.det(R) - 1) < 1e-4 and np.allclose(T[3], [0, 0, 0, 1], atol=1e-6))


def quat_to_R(q, order: str) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64); q = q / np.linalg.norm(q)
    w, x, y, z = (q[0], q[1], q[2], q[3]) if order == "wxyz" else (q[3], q[0], q[1], q[2])
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def pose_T(p, order: str) -> np.ndarray:
    T = np.eye(4); T[:3, :3] = quat_to_R(p[3:7], order); T[:3, 3] = p[:3]
    return T


def rot_err(Ra, Rb) -> float:
    c = (np.trace(Ra.T @ Rb) - 1) / 2
    return float(math.acos(max(-1.0, min(1.0, c))))


def pose_err(pa, pb, order) -> tuple[float, float]:
    return float(np.linalg.norm(np.asarray(pa[:3]) - np.asarray(pb[:3]))), rot_err(quat_to_R(pa[3:7], order), quat_to_R(pb[3:7], order))


def agent_timeout(path: Path) -> float:
    try:
        import tomllib                                   # Python >= 3.11
        return float(tomllib.loads(path.read_text()).get("agent", {}).get("timeout_sec", -1))
    except ImportError:                                  # 3.10 hosts: the [agent] table's timeout_sec line
        m = re.search(r"^\[agent\][^\[]*?^timeout_sec\s*=\s*([0-9.]+)", path.read_text(), re.M | re.S)
        return float(m.group(1)) if m else -1.0


def ext_to_T_world_cam(E) -> np.ndarray:
    T = np.eye(4); T[:3, :] = np.asarray(E, dtype=np.float64)
    return np.linalg.inv(T)


# ---------------------------------------------------------------- the checks
def check_spec(rep: Report, spec: dict, task: Path | None) -> None:
    if spec.get("protocol") == "rcb-limited/2.2":          # the pre-v1.0 spelling of the same protocol
        rep.add("WARN", "spec.protocol", "legacy name rcb-limited/2.2 (use eai-standard/2.2)")
    else:
        rep.ok(spec.get("protocol") == "eai-standard/2.2", "spec.protocol", str(spec.get("protocol")))
    for k in ("on_service_error", "max_call_wall_s"):     # crash recovery and the per-call bound (rcb_limited.serve adds both)
        rep.ok(k in spec, f"spec.{k}", str(spec.get(k))[:120])
    rep.ok(set(spec.get("protocol_compat") or []) >= {"rcb-limited/2.0", "rcb-limited/2.1"}, "spec.protocol_compat", str(spec.get("protocol_compat")))
    rep.ok(SPEC_KEYS_REQ <= set(spec), "spec.required_keys", f"missing {sorted(SPEC_KEYS_REQ - set(spec))}")
    rep.ok(set(spec) <= SPEC_KEYS_OK, "spec.no_unknown_keys", f"unknown {sorted(set(spec) - SPEC_KEYS_OK)}")
    bad = forbidden(spec)
    rep.ok(not bad, "spec.never_provided", f"forbidden fields {bad}" if bad else "no forbidden field")
    st = spec.get("static") or {}
    pos = static_positions(st)
    rep.ok(not pos, "spec.static_no_positions", "static says where things are: " + "; ".join(pos) if pos else
           "no position, height, centre or world coordinate in static")
    for path, v in leaves(st, "static"):
        rep.add("INFO", "spec.static (scene fact, no position)", f"{path} = {json.dumps(v)[:160]}")
    if task is not None:
        tx = subprocess.run(["bash", str(Path(__file__).resolve().parent / "check-standard-texts.sh"), str(task)], capture_output=True, text=True)
        rep.ok(tx.returncode == 0, "task.limited_texts", (tx.stdout.strip() or "no inventories, sizes or workspace parameters in the texts")[:1500])
    # cameras
    cams = spec.get("cameras") or {}
    kin = spec.get("kinematics") or {}
    for c, cam in cams.items():
        n = f"spec.cameras[{c}]"
        rep.ok(CAM_KEYS_REQ <= set(cam), f"{n}.keys", f"missing {sorted(CAM_KEYS_REQ - set(cam))}")
        rep.ok(set(cam) <= CAM_KEYS_OK, f"{n}.no_unknown_keys", f"unknown {sorted(set(cam) - CAM_KEYS_OK)}")
        rep.ok(cam.get("depth") is True, f"{n}.depth", str(cam.get("depth")))
        K = mat(cam.get("intrinsic_cv"), (3, 3))
        rep.ok(K is not None and K[0, 0] > 0 and K[1, 1] > 0 and np.allclose(K[2], [0, 0, 1]), f"{n}.intrinsic_cv", str(cam.get("intrinsic_cv")))
        W, H = (cam.get("resolution") or [0, 0])[:2]
        if K is not None and W and H:
            rep.ok(0 < K[0, 2] < W and 0 < K[1, 2] < H, f"{n}.principal_point_inside", f"c=({K[0, 2]:.1f},{K[1, 2]:.1f}) image {W}x{H}")
        m = cam.get("mount") or {}
        if m.get("type") == "static":
            E = mat(m.get("extrinsic_cv"), (3, 4)); G = mat(m.get("cam2world_gl"), (4, 4))
            ok = E is not None and G is not None and np.allclose(ext_to_T_world_cam(E) @ GL2CV, G, atol=1e-4)
            rep.ok(ok, f"{n}.mount.static", "extrinsic_cv and cam2world_gl present and consistent")
        elif m.get("type") == "link":
            T = mat(m.get("link_T_cam_cv"), (4, 4))
            rep.ok(m.get("parent_link") in (kin.get("links") or []) and T is not None and rigid(T), f"{n}.mount.link",
                   f"parent {m.get('parent_link')} in kinematics.links, link_T_cam_cv rigid")
        else:
            rep.add("FAIL", f"{n}.mount", f"type must be static|link: {m}")
    rep.ok(all(c in cams for c in spec.get("default_cameras") or [None]), "spec.default_cameras", str(spec.get("default_cameras")))
    # proprio
    lay = spec.get("proprio_layout") or []; groups = spec.get("proprio_groups") or {}
    rep.ok(len(lay) == len(set(lay)) and all(isinstance(x, str) and x for x in lay), "spec.proprio_layout.named_unique", f"{len(lay)} columns")
    rep.ok(not any(re.fullmatch(r"q_?\d+", x) for x in lay), "spec.proprio_layout.no_anonymous_columns",
           f"{[x for x in lay if re.fullmatch(r'q_?[0-9]+', x)][:5]}")
    for g in GROUPS_REQ:
        rep.ok(g in groups, f"spec.proprio_groups.{g}")
    for g, v in groups.items():
        ok = isinstance(v, list) and len(v) >= 3 and 0 <= int(v[0]) and int(v[0]) + int(v[1]) <= len(lay) and isinstance(v[2], str)
        rep.ok(ok, f"spec.proprio_groups[{g}].range", str(v)[:120])
    rs = spec.get("robot_spec") or {}
    if "tcp_pose" in groups:
        rep.ok(groups["tcp_pose"][1] == 7 * len(kin.get("tcp_frames") or []), "spec.proprio_groups.tcp_pose.size",
               f"{groups['tcp_pose'][1]} columns for tcp_frames {kin.get('tcp_frames')}")
    if "gripper_opening" in groups:
        rep.ok(groups["gripper_opening"][1] == len(rs.get("grippers") or {}), "spec.proprio_groups.gripper_opening.size",
               f"{groups['gripper_opening'][1]} columns for {len(rs.get('grippers') or {})} grippers")
    # robot_spec
    rep.ok(ROBOT_KEYS_REQ <= set(rs), "spec.robot_spec.keys", f"missing {sorted(ROBOT_KEYS_REQ - set(rs))}")
    rep.ok(set(rs) <= ROBOT_KEYS_OK, "spec.robot_spec.no_unknown_keys", f"unknown {sorted(set(rs) - ROBOT_KEYS_OK)}")
    joints = rs.get("joints") or []
    rep.ok(bool(joints), "spec.robot_spec.joints", f"{len(joints)} joints")
    lim_sets = {}
    for j in joints:
        n = f"spec.robot_spec.joints[{j.get('name')}]"
        ok = JOINT_KEYS_REQ <= set(j) and set(j) <= JOINT_KEYS_OK and j.get("type") in ("revolute", "prismatic", "continuous") \
            and j.get("unit") in ("rad", "m")
        pl = j.get("position_limits")
        if j.get("type") != "continuous":
            ok = ok and pl is not None and len(pl) == 2 and float(pl[0]) < float(pl[1])
        for k in ("velocity_limit", "effort_limit"):
            v = j.get(k)
            ok = ok and (v is None or (isinstance(v, (int, float)) and v > 0))
            if v is None:
                rep.add("WARN", f"{n}.{k}", "null (the simulator enforces none)")
        rated = [k for k in ("rated_velocity", "rated_effort") if k in j]
        ok = ok and all(isinstance(j[k], (int, float)) and j[k] > 0 for k in rated) and (not rated or bool(j.get("rated_source")))
        rep.ok(ok, n, json.dumps({k: j.get(k) for k in ("type", "unit", "position_limits", "velocity_limit", "effort_limit")}))
        if pl is not None and j.get("type") == "revolute":
            lim_sets.setdefault((round(float(pl[0]), 3), round(float(pl[1]), 3)), []).append(j.get("name"))
    for lim, names in lim_sets.items():
        if len(names) >= 3 and abs(lim[0]) >= 6.28 and abs(lim[1]) >= 6.28:
            rep.add("FAIL", "spec.robot_spec.joints.placeholder_limits", f"{len(names)} joints share {lim}: {names[:4]}...")
    jl = {j.get("name"): j.get("position_limits") for j in joints}
    alim = ((spec.get("action_types") or {}).get("joint_position") or {}).get("limits") or {}
    for name, l in alim.items():
        if name in jl and jl[name] is not None and l is not None:
            rep.ok(float(l[0]) >= float(jl[name][0]) - 1e-6 and float(l[1]) <= float(jl[name][1]) + 1e-6,
                   f"spec.action_limits_within_joint_limits[{name}]", f"action {l} joint {jl[name]}")
    for gname, g in (rs.get("grippers") or {}).items():
        ok = isinstance(g, dict) and {"joints", "opening_m", "command", "tcp_frame"} <= set(g) and len(g["opening_m"]) == 2
        rep.ok(ok, f"spec.robot_spec.grippers[{gname}]", json.dumps(g)[:200])
    ctl = rs.get("controller") or {}
    ok = {"type", "control_hz", "gains"} <= set(ctl) and abs(float(ctl.get("control_hz", 0)) - float(spec.get("control_hz", -1))) < 1e-9
    ok = ok and isinstance(ctl.get("gains"), dict) and all(isinstance(v, dict) and {"stiffness", "damping"} <= set(v) for v in ctl["gains"].values())
    rep.ok(ok, "spec.robot_spec.controller", f"type={ctl.get('type')!r} control_hz={ctl.get('control_hz')} gains for {len(ctl.get('gains') or {})} joints")
    for f, t in (rs.get("tcp") or {}).items():
        T = mat(t.get("link_T_frame"), (4, 4))
        rep.ok(bool(t.get("parent_link")) and T is not None and rigid(T) and bool(t.get("definition")), f"spec.robot_spec.tcp[{f}]")
    base = rs.get("base") or {}
    rep.ok(base.get("type") in ("fixed", "mobile") and (base.get("type") == "mobile" or mat(base.get("pose"), (7,)) is not None),
           "spec.robot_spec.base", json.dumps(base)[:160])
    # world, kinematics, depth, budget
    w = spec.get("world") or {}
    rep.ok(WORLD_KEYS_REQ <= set(w) and w.get("quaternion_order") in ("wxyz", "xyzw"), "spec.world", json.dumps(w)[:200])
    rep.ok(KIN_KEYS_REQ <= set(kin) and set(kin) <= KIN_KEYS_OK, "spec.kinematics.keys",
           f"missing {sorted(KIN_KEYS_REQ - set(kin))} unknown {sorted(set(kin) - KIN_KEYS_OK)}")
    rep.ok(kin.get("endpoint") == "/kinematics" and kin.get("frame") in ("world", "base") and kin.get("quaternion_order") == w.get("quaternion_order"),
           "spec.kinematics.frame", f"endpoint {kin.get('endpoint')} frame {kin.get('frame')} quaternion {kin.get('quaternion_order')}")
    rep.ok(all(j in lay for j in kin.get("joint_names") or [None]), "spec.kinematics.joint_names_in_proprio", str(kin.get("joint_names")))
    links = kin.get("links") or []
    rep.ok(all(f in links for f in (kin.get("tcp_frames") or []) + (kin.get("ee_frames") or []) + (kin.get("ik_targets") or [])),
           "spec.kinematics.frames_listed")
    rep.ok(all(f in (rs.get("tcp") or {}) for f in kin.get("tcp_frames") or []), "spec.kinematics.tcp_frames_in_robot_spec")
    if kin.get("frame") == "base":
        rep.ok(len(kin.get("base_pose_proprio") or []) == 7 and all(x in lay for x in kin["base_pose_proprio"]), "spec.kinematics.base_pose_proprio")
    d = spec.get("depth") or {}
    rep.ok(d.get("modes") == ["none", "last", "frames"] and d.get("unit") == "m" and d.get("invalid") == 0 and d.get("kind") == "z-depth",
           "spec.depth", json.dumps(d)[:200])
    b = (spec.get("budget") or {}).get("wall_clock_s")
    rep.ok(isinstance(b, (int, float)) and b > 0, "spec.budget.wall_clock_s", str(b))
    if task is not None and (task / "task.toml").exists():
        want = agent_timeout(task / "task.toml")
        rep.ok(b is not None and abs(float(b) - want) < 1e-6, "spec.budget_matches_task_timeout", f"spec {b} vs task.toml [agent].timeout_sec {want}")


def check_parts_and_meta(rep: Report, name: str, res, spec: dict, cams: list[str]) -> None:
    badp = [p for p in res.raw if not PART_RE.match(p)]
    rep.ok(not badp, f"{name}.part_names", f"unexpected parts {badp}" if badp else f"{len(res.raw)} parts")
    badm = sorted(set(res.meta) - META_KEYS_OK)
    rep.ok(not badm, f"{name}.meta_keys", f"unexpected meta keys {badm}" if badm else "")
    badc = sorted({k for v in (res.meta.get("cameras") or {}).values() for k in v} - META_CAM_KEYS_OK)
    rep.ok(not badc, f"{name}.meta_camera_keys", f"unexpected {badc}" if badc else "")
    bad = forbidden(res.meta, skip=())
    rep.ok(not bad, f"{name}.meta_never_provided", str(bad) if bad else "")
    lay = spec["proprio_layout"]
    N = None if res.frame_step is None else len(res.frame_step)
    rep.ok(res.proprio is not None and res.proprio.ndim == 2 and res.proprio.shape[1] == len(lay), f"{name}.proprio_shape",
           f"{None if res.proprio is None else res.proprio.shape} vs {len(lay)} named columns")
    rep.ok(res.meta.get("proprio", {}).get("layout") == lay and len(res.meta["proprio"]["now"]) == len(lay), f"{name}.meta_proprio")
    rep.ok(N is not None and N >= 1 and res.proprio is not None and res.proprio.shape[0] == N and res.frame_time_s is not None
           and len(res.frame_time_s) == N, f"{name}.one_frame_axis", f"frames {N}, proprio {None if res.proprio is None else res.proprio.shape[0]}")
    if N:
        rep.ok(np.allclose(res.frame_time_s, res.frame_step / float(spec["control_hz"]), atol=1e-9), f"{name}.frame_time_is_step_over_hz")
        rep.ok(bool(np.all(np.diff(res.frame_step) >= 0)), f"{name}.frame_step_monotonic", str(res.frame_step[:12].tolist()))
    for c in cams:
        W, H = spec["cameras"][c]["resolution"][:2]
        lst = res.last.get(c)
        rep.ok(lst is not None and lst.shape == (H, W, 3) and lst.dtype == np.uint8, f"{name}.last[{c}]",
               f"{None if lst is None else lst.shape} vs resolution {W}x{H}")
        if c in res.frames:
            rep.ok(res.frames[c].shape[0] == N, f"{name}.frames[{c}].count", f"{res.frames[c].shape[0]} vs {N}")
        e = res.extrinsic_cv.get(c)
        rep.ok(e is not None and e.shape == (N, 3, 4) and np.all(np.isfinite(e)), f"{name}.extrinsic_cv[{c}].per_frame",
               f"{None if e is None else e.shape} for {N} frames")
        mc = (res.meta.get("cameras") or {}).get(c)
        if mc is not None and e is not None and len(e):
            rep.ok(np.allclose(np.asarray(mc["extrinsic_cv"]), e[-1], atol=2e-5), f"{name}.meta_cameras_is_last_frame[{c}]")
            rep.ok(np.allclose(np.asarray(mc["intrinsic_cv"]), np.asarray(spec["cameras"][c]["intrinsic_cv"]), atol=1e-4),
                   f"{name}.meta_intrinsics_match_spec[{c}]")
        mount = spec["cameras"][c]["mount"]
        if mount.get("type") == "static" and e is not None and len(e):
            rep.ok(np.allclose(e, np.asarray(mount["extrinsic_cv"])[None], atol=2e-5), f"{name}.static_camera_fixed[{c}]")


def check_depth_map(rep: Report, name: str, d, rgb, spec: dict, c: str) -> None:
    ok = d is not None and rgb is not None and d.shape == rgb.shape[:2] and d.dtype == np.float32
    rep.ok(ok, f"{name}.pixel_aligned[{c}]", f"depth {None if d is None else (d.shape, str(d.dtype))} rgb {None if rgb is None else rgb.shape}")
    if not ok:
        return
    rep.ok(bool(np.all(np.isfinite(d)) and np.all(d >= 0)), f"{name}.finite_nonneg[{c}]")
    v = d[d > 0]
    frac = float(v.size) / d.size
    rep.ok(frac > 0.05, f"{name}.valid_fraction[{c}]", f"{frac:.3f} of the pixels have a reading", level_bad="WARN")
    if v.size:
        med = float(np.median(v)); rng = spec["cameras"][c].get("depth_range_m") or [0, 65.535]
        rep.ok(0.02 < med < 20.0 and float(v.max()) <= 65.535 + 1e-6, f"{name}.plausible_metres[{c}]",
               f"median {med:.3f} m, min {float(v.min()):.3f}, max {float(v.max()):.3f}, spec range {rng}", level_bad="WARN")


def raw_post(url, path, body, timeout=600):
    return requests.post(url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, timeout=(5, timeout))


def check_live(rep: Report, url: str, task: Path | None, client_dir: Path, out: Path, watch: float) -> None:
    sys.path.insert(0, str(client_dir))
    import rcb1  # noqa: E402
    import rcb_client  # noqa: E402
    r = rcb_client.Robot(url, timeout=1800)
    spec = r.spec()
    (out / "spec.json").write_text(json.dumps(spec, indent=1))
    check_spec(rep, spec, task)
    if not SPEC_KEYS_REQ <= set(spec):
        rep.add("FAIL", "live checks skipped", "/spec is not a 2.2 spec"); return
    hz = float(spec["control_hz"]); order = spec["world"]["quaternion_order"]; kin = spec["kinematics"]; lay = spec["proprio_layout"]
    cams = list(spec["default_cameras"])
    # /status and the 404 surface
    st0 = r.status()
    rep.ok({"step", "calls", "done", "reason"} <= set(st0), "status.keys", json.dumps(st0))
    resets = int((spec.get("budget") or {}).get("reset") or 0)   # POST /reset exists only with a reset budget (PROTOCOL §4.5)
    for m, p in (("GET", "/reset"), ("GET", "/state"), ("GET", "/success"), ("POST", "/reset"), ("GET", "/kinematics"), ("POST", "/step")):
        if (m, p) == ("POST", "/reset") and resets:
            continue                                            # never probed live: it would start a new episode
        code = requests.request(m, url + p, timeout=30).status_code
        rep.ok(code == 404, f"http.{m}{p}.404", str(code))
    # default observe: no depth
    o = r.get_obs()
    check_parts_and_meta(rep, "observe.default", o, spec, cams)
    rep.ok(not o.last_depth and not o.depth, "observe.default.no_depth", f"depth parts: {[p for p in o.raw if 'depth' in p]}")
    # 2.0-style JSON request (the old client's fields) and 2.1's include_depth
    rj = raw_post(url, "/observe", {"cameras": cams, "seconds": 0.0, "video_fps": 5, "include_depth": False, "video": "frames"})
    ok = rj.status_code == 200
    if ok:
        m, p = rcb1.decode(rj.content)
        ok = all(f"last/{c}" in p for c in cams) and "proprio" in p and not any("depth" in k for k in p)
    rep.ok(ok, "compat.2_0_request", f"HTTP {rj.status_code}")
    rj = raw_post(url, "/observe", {"cameras": cams, "seconds": 0.0, "include_depth": True, "video": "frames"})
    ok = rj.status_code == 200
    if ok:
        m, p = rcb1.decode(rj.content)
        ok = all(f"depth/{c}" in p and p[f"depth/{c}"]["dtype"] == "float16" and len(p[f"depth/{c}"]["shape"]) == 3 for c in cams)
    rep.ok(ok, "compat.2_1_include_depth", f"HTTP {rj.status_code}: depth/<cam> float16 (N,H,W)")
    for body, what in (({"depth": "sideways"}, "bad depth value"), ({"seconds": -1}, "negative seconds"), ({"video": "gif"}, "bad video")):
        code = raw_post(url, "/observe", body).status_code
        rep.ok(code == 400, f"http.observe.400[{what}]", str(code))
    dim = spec["action_types"]["joint_position"]["dim"]
    for a, what in ((np.zeros((2, dim + 1), np.float32), "wrong dim"), (np.full((2, dim), np.nan, np.float32), "NaN")):
        rb = rcb1.encode({"type": "joint_position", "dt": 1.0 / hz}, [rcb1.array_part("actions", a)])
        code = requests.post(url + "/submit", data=rb, headers={"Content-Type": "application/x-rcb1"}, timeout=60).status_code
        rep.ok(code in (400, 409), f"http.submit.400[{what}]", str(code))
    # depth last
    ol = r.get_obs(depth=True)
    check_parts_and_meta(rep, "observe.depth_last", ol, spec, cams)
    for c in cams:
        check_depth_map(rep, "depth.last", ol.last_depth.get(c), ol.last.get(c), spec, c)
    rep.ok(not ol.depth, "observe.depth_last.no_per_frame_depth")
    # a watch with per-frame depth: the frame axis
    steps_before = r.status().get("control_steps")
    ow = r.get_obs(seconds=watch, depth="frames", video="both")
    check_parts_and_meta(rep, "observe.watch_frames", ow, spec, cams)
    N = len(ow.frame_step)
    if not ow.meta.get("done"):
        rep.ok(N >= 2 and int(ow.frame_step[-1] - ow.frame_step[0]) == int(ow.meta.get("control_steps_watch", -1)) == int(round(watch * hz)),
               "watch.steps_advance", f"frame_step {ow.frame_step.tolist()} watch steps {ow.meta.get('control_steps_watch')}")
    for c in cams:
        dd = ow.depth.get(c)
        rep.ok(dd is not None and dd.shape == (N,) + ow.last[c].shape[:2], f"depth.frames[{c}].one_per_frame", f"{None if dd is None else dd.shape} for {N} frames")
        if dd is not None and c in ow.last_depth and (spec.get("depth") or {}).get("noise", "off") == "off":
            a, b = dd[-1], ow.last_depth[c]; both = (a > 0) & (b > 0)
            err = float(np.max(np.abs(a[both] - b[both]))) if both.any() else 0.0
            rep.ok(err <= 0.0006 and np.array_equal(a > 0, b > 0), f"depth.frames_last_equals_last_depth[{c}]", f"max |diff| {err * 1000:.2f} mm")
        if c in ow.frames:
            rep.ok(np.array_equal(ow.frames[c][-1], ow.last[c]), f"frames.last_is_last[{c}]")
    steps_after = r.status().get("control_steps")
    # kinematics: stateless, FK = measured, mounts, IK round trip
    now = np.asarray(ow.meta["proprio"]["now"], dtype=np.float64)
    q = np.array([now[lay.index(j)] for j in kin["joint_names"]])
    base = [float(now[lay.index(x)]) for x in kin["base_pose_proprio"]] if kin.get("frame") == "base" else None
    t0 = r.status().get("control_steps")
    f1 = r.fk(q, base_pose=base); f2 = r.fk(q, base_pose=base)
    for _ in range(5):
        r.fk(q, links=list(kin["tcp_frames"]), base_pose=base)
    rep.ok(f1 == f2 and r.status().get("control_steps") == t0, "kinematics.stateless", "same answer twice, no control step advanced")
    rep.ok(f1.get("ok") is True and set(f1.get("poses", {})) == set(kin["links"]), "kinematics.fk_all_links", f"{len(f1.get('poses', {}))} frames")
    g = spec["proprio_groups"]["tcp_pose"]
    for i, f in enumerate(kin["tcp_frames"]):
        meas = now[g[0] + 7 * i: g[0] + 7 * i + 7]
        ep, er = pose_err(f1["poses"][f], meas, order)
        rep.ok(ep < 0.002 and er < 0.02, f"kinematics.fk_matches_measured_tcp[{f}]", f"{ep * 1000:.2f} mm, {math.degrees(er):.2f} deg")
    # moving cameras: FK(parent) . link_T_cam = the camera pose of the current frame
    for c in cams:
        m = spec["cameras"][c]["mount"]
        if m.get("type") != "link":
            continue
        fk = r.fk(q, links=[m["parent_link"]], base_pose=base)["poses"][m["parent_link"]]
        T_pred = pose_T(fk, order) @ np.asarray(m["link_T_cam_cv"])
        T_meas = ext_to_T_world_cam(ow.extrinsic_cv[c][-1])
        if kin.get("frame") == "base" and base is None:
            continue
        ep = float(np.linalg.norm(T_pred[:3, 3] - T_meas[:3, 3])); er = rot_err(T_pred[:3, :3], T_meas[:3, :3])
        rep.ok(ep < 0.003 and er < 0.01, f"kinematics.camera_mount[{c}]", f"{ep * 1000:.2f} mm, {math.degrees(er):.3f} deg")
    targets = {f: f1["poses"][f] for f in (kin["ee_frames"] if set(kin["ee_frames"]) <= set(kin["ik_targets"]) else kin["ik_targets"][:1])}
    lim = {j["name"]: j.get("position_limits") for j in spec["robot_spec"]["joints"]}
    seed = q.copy()
    for i, j in enumerate(kin["joint_names"]):
        lo, hi = (lim.get(j) or [-np.inf, np.inf])
        seed[i] = float(np.clip(q[i] + 0.05, lo, hi)) if np.isfinite(lo) else q[i] + 0.05
    ik = r.ik(targets, seed=seed, base_pose=base)
    ok = ik.get("ok") is True and ik.get("q") is not None and len(ik["q"]) == len(q)
    msg = json.dumps(ik.get("error"))[:200]
    if ok:
        fk2 = r.fk(ik["q"], links=list(targets), base_pose=base)["poses"]
        errs = {f: pose_err(fk2[f], targets[f], order) for f in targets}
        ok = all(e[0] < 0.003 and e[1] < 0.03 for e in errs.values())
        msg = ", ".join(f"{f}: {e[0] * 1000:.2f} mm {math.degrees(e[1]):.2f} deg" for f, e in errs.items())
    rep.ok(ok, "kinematics.ik_round_trip", msg)
    far = {f: [p[0] + 10.0] + list(p[1:]) for f, p in targets.items()}
    ik2 = r.ik(far, seed=q, base_pose=base)
    rep.ok(ik2.get("ok") is False and "error" in ik2, "kinematics.ik_unreachable_is_not_ok", json.dumps(ik2.get("error"))[:160])
    for body, what in (({"op": "fk", "q": list(q[:-1])}, "short q"), ({"op": "fk", "q": list(q), "links": ["no_such_link"]}, "unknown link"),
                       ({"op": "teleport"}, "unknown op"), ({"op": "ik", "targets": {"no_such_frame": [0, 0, 0, 1, 0, 0, 0]}}, "unknown target")):
        code = raw_post(url, "/kinematics", body).status_code
        rep.ok(code == 400, f"http.kinematics.400[{what}]", str(code))
    rep.ok(not forbidden(f1, skip=()) and not forbidden(ik, skip=()), "kinematics.never_provided")
    # projection: the TCP projected into each camera lands on the gripper (depth there is at the TCP's distance)
    ol = r.get_obs(depth=True)
    now = np.asarray(ol.meta["proprio"]["now"], dtype=np.float64)
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        Image = None
    for c in cams:
        mc = (ol.meta.get("cameras") or {}).get(c)
        if mc is None or c not in ol.last_depth:
            continue
        K = np.asarray(mc["intrinsic_cv"]); E = np.asarray(mc["extrinsic_cv"]); d = ol.last_depth[c]; H, W = d.shape
        img = Image.fromarray(ol.last[c]) if Image else None
        for i, f in enumerate(kin["tcp_frames"]):
            p = now[g[0] + 7 * i: g[0] + 7 * i + 3]
            X = E[:, :3] @ p + E[:, 3]
            if X[2] <= 0.01:
                rep.add("INFO", f"projection[{c}][{f}]", "behind the camera"); continue
            u, v = K[0, 0] * X[0] / X[2] + K[0, 2], K[1, 1] * X[1] / X[2] + K[1, 2]
            if not (0 <= u < W and 0 <= v < H):
                rep.add("INFO", f"projection[{c}][{f}]", f"outside the image ({u:.0f},{v:.0f})"); continue
            rad = max(3, int(K[0, 0] * 0.06 / X[2]))              # a 6 cm disc around the TCP at its depth (open fingers included)
            win = d[max(0, int(v) - rad): int(v) + rad + 1, max(0, int(u) - rad): int(u) + rad + 1]
            wv = win[win > 0]
            near = wv[np.abs(wv - X[2]) < 0.05] if wv.size else wv
            if near.size:
                rep.add("PASS", f"projection[{c}][{f}]", f"pixel ({u:.0f},{v:.0f}) at {X[2]:.3f} m: {near.size} pixels within 5 cm of it")
            elif wv.size and np.all(wv < X[2] - 0.05):
                rep.add("INFO", f"projection[{c}][{f}]", f"pixel ({u:.0f},{v:.0f}): occluded (nearest {float(wv.min()):.3f} m < {X[2]:.3f} m)")
            else:
                rep.add("FAIL", f"projection[{c}][{f}]", f"pixel ({u:.0f},{v:.0f}) expects {X[2]:.3f} m, the depth window reads "
                        f"{float(np.median(wv)) if wv.size else 0:.3f} m: pose, intrinsics or depth disagree")
            if img is not None:
                dr = ImageDraw.Draw(img); s = max(4, W // 40)
                dr.line([(u - s, v), (u + s, v)], fill=(255, 0, 0), width=2); dr.line([(u, v - s), (u, v + s)], fill=(255, 0, 0), width=2)
        if img is not None:
            img.save(out / f"projection_{c.replace(':', '_').replace('/', '_')}.png")
            dv = d.copy(); vmax = float(np.percentile(dv[dv > 0], 99)) if (dv > 0).any() else 1.0
            Image.fromarray((np.clip(dv / vmax, 0, 1) * 255).astype(np.uint8)).save(out / f"depth_{c.replace(':', '_').replace('/', '_')}.png")
    st = r.status()
    rep.add("INFO", "episode", f"control steps {steps_before} -> {steps_after} (the watch); status {json.dumps(st)}")


# ---------------------------------------------------------------- launching a task's sidecar
def launch(task: Path, port: int, out: Path) -> tuple[list[str], str]:
    import yaml
    compose = task / "environment" / "docker-compose.yaml"
    proj = re.sub(r"[^a-z0-9-]", "-", f"rcbconf-{task.name[:40]}-{os.getpid()}".lower())
    ov = out / "compose.override.yaml"
    ov.write_text(yaml.safe_dump({"services": {"main": {"image": "python:3.12-slim", "command": ["sleep", "infinity"]},
                                               "sim": {"ports": [f"127.0.0.1:{port}:8000"]}}}))
    base = ["docker", "compose", "-p", proj, "-f", str(compose), "-f", str(ov)]
    subprocess.run(base + ["up", "-d", "sim"], check=True)
    return base, proj


def wait_ready(base: list[str], url: str, timeout: float = 1800) -> None:
    """Wait until the launched service answers /spec; stop at once if its container has exited (a crash at startup)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if requests.get(url + "/spec", timeout=(3, 30)).status_code == 200:
                return
        except requests.exceptions.RequestException:
            pass
        ps = subprocess.run(base + ["ps", "-a", "--format", "{{.State}}", "sim"], capture_output=True, text=True).stdout.strip()
        if ps and ps.split()[0] in ("exited", "dead"):
            raise RuntimeError(f"the sim sidecar exited during startup (state {ps!r}); see sim.log")
        time.sleep(5)
    raise RuntimeError(f"the sim sidecar did not answer within {timeout:.0f} s")


def teardown(base: list[str], proj: str, out: Path) -> None:
    with open(out / "sim.log", "w") as f:
        subprocess.run(base + ["logs", "--no-color", "sim"], stdout=f, stderr=subprocess.STDOUT)
    subprocess.run(base + ["down", "--remove-orphans", "-t", "20"])        # never -v: named volumes may be shared caches
    vols = subprocess.run(["docker", "volume", "ls", "-q", "--filter", f"name=^{proj}_"], capture_output=True, text=True).stdout.split()
    if vols:
        subprocess.run(["docker", "volume", "rm"] + vols)                    # only this project's own volumes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url"); ap.add_argument("--task", type=Path); ap.add_argument("--client", type=Path)
    ap.add_argument("--launch", type=Path, help="a standard task dir: start its sim sidecar with docker compose, test it, stop it")
    ap.add_argument("--port", type=int, default=18000); ap.add_argument("--out", type=Path)
    ap.add_argument("--watch", type=float, default=0.5); ap.add_argument("--keep", action="store_true", help="leave the launched sidecar running")
    a = ap.parse_args()
    task = a.launch or a.task
    out = a.out or Path(tempfile.mkdtemp(prefix="rcb-conformance-"))
    out.mkdir(parents=True, exist_ok=True)
    client = a.client or (task / "environment" if task else None)
    if client is None or not (client / "rcb_client.py").exists():
        ap.error("need --client DIR (with rcb_client.py + rcb1.py) or --task/--launch")
    rep = Report(); t0 = time.time(); base = None
    try:
        if a.launch:
            base, proj = launch(a.launch, a.port, out)
            url = f"http://127.0.0.1:{a.port}"
            wait_ready(base, url)
        else:
            url = a.url or ap.error("need --url or --launch")
        check_live(rep, url, task, client, out, a.watch)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc(); rep.add("FAIL", "conformance.run", repr(exc)[:300])
    finally:
        if base is not None and not a.keep:
            teardown(base, proj, out)
    (out / "report.json").write_text(json.dumps({"url": a.url, "task": str(task) if task else None, "elapsed_s": round(time.time() - t0, 1),
                                                 "failed": rep.failed, "rows": rep.rows}, indent=1))
    n = {k: sum(r["level"] == k for r in rep.rows) for k in ("PASS", "FAIL", "WARN", "INFO")}
    print(f"{'FAIL' if rep.failed else 'ok'} eai-standard/2.2 conformance: {n} (report {out / 'report.json'})")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
