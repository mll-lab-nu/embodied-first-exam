"""RCB -> EFE Robot MCP adapter: the unified tools on top of the task's own eai-standard/2.x client.

The client is the task's `/opt/tools/rcb_client.py` (a 2.1 variant, 2.2 or 2.4); its keyword arguments differ between
versions, so every call passes only the arguments its signature takes. Conventions (D129): the robot base frame at the
start of the call (+X forward, +Y left, +Z up), metres and radians, quaternions wxyz, gripper 0 = open .. 1 = closed;
the manifest says how the suite's own frame, quaternion order and gripper scale map onto them."""
from __future__ import annotations
import inspect, json, math, os, sys, threading, time
import numpy as np

import geom
from geom import Frame, q_from, q_to, canon_q, q_angle
import workspace

TOOLS_DIR = os.environ.get("EFE_MCP_TOOLS_DIR", "/opt/tools")


class ToolError(Exception):
    def __init__(self, msg: str, category: str = "invalid"):
        super().__init__(msg)
        self.category = category


def _f(x, nd=4):
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_f(v, nd) for v in np.asarray(x, dtype=np.float64).tolist()]
    if x is None:
        return None
    return round(float(x), nd)


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, bytes):
        return f"<{len(o)} bytes>"
    return o


class RcbAdapter:
    def __init__(self, manifest: dict):
        self.m = manifest
        self.r = None
        self.rc = None
        self.spec = None
        self.last_cmd: dict[str, np.ndarray] = {}
        self.n = 0
        self.lock = threading.Lock()
        self.connect_error = None

    # ------------------------------------------------------------------ connection and client calls
    def connect(self):
        if self.r is not None:
            return
        if TOOLS_DIR not in sys.path:
            sys.path.insert(0, TOOLS_DIR)
        import rcb_client
        self.rc = rcb_client
        self.r = rcb_client.Robot()
        self.spec = self.r.spec()

    def _call(self, fn, *a, **kw):
        params = inspect.signature(fn).parameters
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            kw = {k: v for k, v in kw.items() if k in params}
        return fn(*a, **kw)

    def _episode_over(self, e) -> dict:
        return {"episode_over": True, "reason": str(e)}

    def obs(self, cams, seconds=0.0, depth=False, video="none"):
        params = inspect.signature(self.r.get_obs).parameters
        kw = {"cameras": list(cams), "seconds": float(seconds), "video": video}
        if depth:
            if "depth" in params:
                kw["depth"] = True
            else:
                kw["include_depth"] = True
        return self._call(self.r.get_obs, **kw)

    def submit(self, typ, A, dt, interpolate="linear", cams=None, video="none", note=None, tool="?"):
        A = np.asarray(A, dtype=np.float64)
        if A.ndim == 1:
            A = A[None, :]
        if not np.all(np.isfinite(A)):
            raise ToolError("a row contains NaN or inf")
        if note is None:
            note = f"efe-mcp:{tool}#{self.n}" if self.m.get("control", {}).get("trace_note", True) else ""
        cams = list(cams if cams is not None else self.action_cams())
        return self._call(self.r.submit, typ, A, dt=None if dt is None else float(dt), interpolate=interpolate,
                          cameras=cams, video=video, note=note)

    # ------------------------------------------------------------------ manifest helpers
    def cams_all(self):
        cams = self.m.get("cameras")
        if not cams and self.spec:
            c = self.spec.get("cameras")
            cams = list(c.keys()) if isinstance(c, dict) else [x["name"] if isinstance(x, dict) else x for x in (c or [])]
        return list(cams or [])

    def default_cams(self):
        return list(self.m.get("default_cameras") or (self.spec or {}).get("default_cameras") or self.cams_all()[:2])

    def action_cams(self):
        return list(self.m.get("action_cameras") or self.default_cams())

    def state_cams(self):
        return list(self.m.get("state_cameras") or self.default_cams()[:1])

    def control_dt(self) -> float:
        s = self.spec or {}
        for k in ("control_dt",):
            if s.get(k):
                return float(s[k])
        if s.get("control_hz"):
            return 1.0 / float(s["control_hz"])
        return float(self.m.get("control", {}).get("control_dt", 0.02))

    def step_dt(self, want: float | None = None) -> float:
        """A dt that is a whole number of control steps, at most 0.5 s."""
        base = self.control_dt()
        want = float(want if want is not None else self.m.get("control", {}).get("dt", base))
        k = max(1, int(round(want / base)))
        while k * base > 0.5 + 1e-9 and k > 1:
            k -= 1
        return k * base

    def max_chunk_s(self) -> float:
        return float(self.m.get("control", {}).get("max_chunk_s") or (self.spec or {}).get("max_chunk_s") or 10.0)

    def layout(self, typ):
        at = (self.spec or {}).get("action_types", {}).get(typ, {})
        return at.get("layout") or []

    def type_dim(self, typ) -> int:
        t = self.m.get("types", {}).get(typ, {})
        if t.get("dim"):
            return int(t["dim"])
        at = (self.spec or {}).get("action_types", {}).get(typ)
        if not at:
            raise ToolError(f"the robot has no action type {typ!r}")
        return int(at.get("dim") or len(at.get("layout") or []))

    def proprio_layout(self, meta=None):
        if meta and isinstance(meta.get("proprio"), dict) and meta["proprio"].get("layout"):
            return list(meta["proprio"]["layout"])
        return list((self.spec or {}).get("proprio_layout") or [])

    def ref(self, ref, now, meta=None):
        """Values a manifest reference picks out of the proprio row `now`."""
        if ref is None:
            return None
        now = np.asarray(now, dtype=np.float64)
        if "cols" in ref:
            a, b = ref["cols"]
            return now[a:b]
        if "col" in ref:
            return now[ref["col"]:ref["col"] + 1]
        if "group" in ref:
            g = (self.spec or {}).get("proprio_groups", {}).get(ref["group"])
            if g is None:
                raise ToolError(f"proprio group {ref['group']!r} not in the spec", "internal")
            first, n = int(g[0]), int(g[1])
            off = int(ref.get("offset", 0))
            k = int(ref.get("n", n - off))
            return now[first + off:first + off + k]
        if "names" in ref:
            lay = self.proprio_layout(meta)
            return now[[lay.index(x) for x in ref["names"]]]
        raise ToolError(f"bad manifest reference {ref}", "internal")

    # ------------------------------------------------------------------ frames and state
    def base_frame(self, now, meta=None) -> Frame:
        b = self.m.get("frame", {}).get("base") or {"fixed": [0, 0, 0, 1, 0, 0, 0]}
        if "fixed" in b:
            v = b["fixed"]
            return Frame(v[:3], v[3:7])
        pos = self.ref(b["pos"], now, meta) if "pos" in b else np.zeros(3)
        if len(pos) == 2:
            pos = np.array([pos[0], pos[1], float(b.get("z", 0.0))])
        if "yaw" in b:
            q = geom.yaw_q(float(self.ref(b["yaw"], now, meta)[0]))
        elif "quat" in b:
            q = q_from(self.ref(b["quat"], now, meta), b.get("quat_order", self.quat_order()))
        else:
            q = np.array([1.0, 0, 0, 0])
        if b.get("level", True) and "quat" in b:   # the base frame keeps +Z up: only the heading of a tilted body
            q = geom.yaw_q(geom.q_yaw(q))
        return Frame(pos, q)

    def quat_order(self):
        return self.m.get("frame", {}).get("quat", "wxyz")

    def g_to_suite(self, g, spec_g):
        o, c = float(spec_g.get("open", 0.0)), float(spec_g.get("closed", 1.0))
        g = min(1.0, max(0.0, float(g)))
        if spec_g.get("binary"):
            g = 1.0 if g >= 0.5 else 0.0
        return o + g * (c - o)

    def g_from_suite(self, v, spec_g):
        o, c = float(spec_g.get("open", 0.0)), float(spec_g.get("closed", 1.0))
        if abs(c - o) < 1e-12:
            return None
        return float(min(1.0, max(0.0, (float(v) - o) / (c - o))))

    def part_state(self, name, now, F, meta=None) -> dict:
        P = self.m["parts"][name]
        st = P.get("state", {})
        out = {}
        if st.get("joints"):
            out["joint_positions"] = _f(self.ref(st["joints"], now, meta))
        if st.get("gripper"):
            v = self.ref(st["gripper"], now, meta)
            g = self.g_from_suite(v[0], {**P.get("gripper", {}), **st["gripper"]})
            out["gripper"] = None if g is None else round(g, 3)
        if st.get("gripper_opening_m"):
            out["gripper_opening_m"] = _f(self.ref(st["gripper_opening_m"], now, meta)[0])
        if st.get("ee_pose"):
            v = self.ref(st["ee_pose"], now, meta)
            p, q = F.from_parent(v[:3], q_from(v[3:7], st["ee_pose"].get("quat", self.quat_order())))
            out["ee"] = {"position": _f(p), "quaternion_wxyz": _f(canon_q(q))}
        return out

    def ee_suite(self, name, now, meta=None):
        """The part's end-effector pose in the suite frame (p, wxyz q), from proprio."""
        st = self.m["parts"][name].get("state", {})
        if not st.get("ee_pose"):
            return None
        v = self.ref(st["ee_pose"], now, meta)
        return np.asarray(v[:3], dtype=np.float64), q_from(v[3:7], st["ee_pose"].get("quat", self.quat_order()))

    def robot_state(self, now, meta=None, F=None) -> dict:
        F = F or self.base_frame(now, meta)
        out = {"parts": {n: self.part_state(n, now, F, meta) for n in self.m["parts"]}}
        b = self.m.get("frame", {}).get("base") or {}
        if "fixed" not in b and b:
            yaw = geom.q_yaw(F.q)
            out["base_odometry"] = {"x": _f(F.p[0]), "y": _f(F.p[1]), "yaw": _f(yaw),
                                    "frame": self.m.get("frame", {}).get("suite", "suite")}
        return out

    # ------------------------------------------------------------------ result packaging
    def meta_now(self, res):
        p = res.meta.get("proprio") or {}
        now = p.get("now")
        if now is None and getattr(res, "proprio", None) is not None and len(res.proprio):
            now = res.proprio[-1]
        return np.asarray(now if now is not None else [], dtype=np.float64)

    def cam_meta(self, res, cam, F):
        cams = res.meta.get("cameras") or {}
        c = cams.get(cam) if isinstance(cams, dict) else None
        out = {}
        if not c:
            return out
        if c.get("intrinsic_cv") is not None:
            out["K"] = _f(c["intrinsic_cv"], 3)
        if c.get("extrinsic_cv") is not None:
            E = np.asarray(c["extrinsic_cv"], dtype=np.float64).reshape(3, 4)        # suite frame -> camera (OpenCV)
            T_cam_suite = np.eye(4); T_cam_suite[:3, :] = E
            T_suite_cam = np.linalg.inv(T_cam_suite)
            T_base_suite = np.eye(4); T_base_suite[:3, :3] = F.R.T; T_base_suite[:3, 3] = -F.R.T @ F.p
            out["T_base_cam_cv"] = _f(T_base_suite @ T_suite_cam, 4)
            out["extrinsic_note"] = "4x4 camera pose in the robot base frame, OpenCV camera axes (x right, y down, z forward)"
        return out

    def package(self, res, F, w: workspace.Writer, cams, depth=False, inline=None, video=False) -> tuple[dict, list]:
        """Files for the response's frames, the camera calibration, the state; and inline thumbnails."""
        images, extras = {}, []
        for cam in cams:
            entry = {}
            img = res.last.get(cam) if hasattr(res, "last") else None
            if img is not None:
                entry["image"] = w.jpeg(cam, img)
                entry["size"] = [int(np.asarray(img).shape[1]), int(np.asarray(img).shape[0])]
                if inline and cam in inline:
                    extras.append(workspace.thumbnail(img))
            d = None
            if depth:
                d = (getattr(res, "last_depth", {}) or {}).get(cam)
                if d is None and cam in (getattr(res, "depth", {}) or {}):
                    d = np.asarray(res.depth[cam])
                    d = d[-1] if d.ndim == 3 else d
            if d is not None:
                entry["depth"] = w.depth(cam, d)
            if video and cam in (getattr(res, "video", {}) or {}):
                entry["video"] = w.video(cam, res.video[cam])
            entry.update(self.cam_meta(res, cam, F))
            if entry:
                images[cam] = entry
        w.prune()
        return images, extras

    def common_meta(self, res) -> dict:
        m = res.meta
        out = {"time_left_s": _f(m.get("time_left_s"), 1), "sim_time_s": _f(m.get("sim_time_s"), 3)}
        if m.get("done"):
            out["done"] = True
            out["reason"] = m.get("reason")
        for k in ("messages", "operator", "result", "outcome", "steps_left"):
            if m.get(k) not in (None, [], {}):
                out[k] = _jsonable(m[k])
        return out

    # ------------------------------------------------------------------ tools
    def describe_robot(self, **_):
        self.connect()
        s = self.spec
        res = self.obs(self.state_cams())
        now = self.meta_now(res)
        F = self.base_frame(now, res.meta)
        parts = {}
        for name, P in self.m["parts"].items():
            d = {"kind": P.get("kind", "arm")}
            j = P.get("joints")
            if j:
                lay = self.layout(j["type"])
                names = j.get("names") or (lay[j["cols"][0]:j["cols"][1]] if lay else None)
                d["joints"] = {"count": j["cols"][1] - j["cols"][0], "names": names}
                lim = self.limits(j["type"], j["cols"])
                if lim:
                    d["joints"]["limits"] = lim
            if P.get("gripper"):
                d["gripper"] = {"range": "0 = open, 1 = closed", **({"binary": True} if P["gripper"].get("binary") else {})}
            ee = P.get("ee") or {}
            if ee:
                d["end_effector"] = {"point": ee.get("point", ""), "control": ee.get("mode_text", ee.get("mode", "planner")),
                                     "orientation": "quaternion_wxyz"}
            if P.get("ee_delta"):
                d["end_effector_delta"] = {"point": P["ee_delta"].get("point", ""),
                                           "max_step_m": P["ee_delta"].get("pos_scale"), "note": P["ee_delta"].get("note", "")}
            if P.get("note"):
                d["note"] = P["note"]
            parts[name] = d
        out = {"robot": self.m.get("robot"), "protocol": s.get("protocol"),
               "conventions": {"frame": "robot base at the start of each call: +X forward, +Y left, +Z up",
                               "units": "m, rad, s", "quaternion": "wxyz", "gripper": "0 = open, 1 = closed"},
               "base_frame": self.m.get("frame", {}).get("base_text", ""),
               "parts": parts, "cameras": self.camera_info(), "default_cameras": self.default_cams(),
               "control_dt_s": _f(self.control_dt(), 4), "spaces": self.spaces(),
               "action_types_native": self.native_types(),
               "state_now": self.robot_state(now, res.meta, F), "time_left_s": _f(res.meta.get("time_left_s"), 1)}
        if self.m.get("base"):
            out["base"] = {"move": "move_robot {target: base, dx, dy, dyaw}", **{k: v for k, v in self.m["base"].items()
                                                                                  if k in ("max_v", "max_w", "note")}}
        if self.m.get("locomotion"):
            L = self.m["locomotion"]
            out["locomotion"] = {k: v for k, v in L.items() if k in ("limits", "note", "height")}
        if self.m.get("signals"):
            out["signals"] = sorted(self.m["signals"])
        if self.m.get("notes"):
            out["notes"] = self.m["notes"]
        w = workspace.Writer()
        out["spec_file"] = w.json("spec", _jsonable(s))
        return out, []

    def limits(self, typ, cols):
        at = (self.spec or {}).get("action_types", {}).get(typ, {})
        lo, hi = at.get("lower"), at.get("upper")
        if lo is None and isinstance(at.get("limits"), dict):
            lo, hi = at["limits"].get("lower"), at["limits"].get("upper")
        if lo is None or hi is None:
            return None
        try:
            a, b = cols
            return [[None if x is None else _f(x), None if y is None else _f(y)] for x, y in zip(lo[a:b], hi[a:b])]
        except Exception:
            return None

    def camera_info(self):
        c = (self.spec or {}).get("cameras")
        out = {}
        for cam in self.cams_all():
            info = c.get(cam) if isinstance(c, dict) else None
            d = {}
            if isinstance(info, dict):
                for k in ("width", "height", "mount", "moves", "fovy", "resolution", "description"):
                    if k in info:
                        d[k] = info[k]
            out[cam] = d
        return out

    def native_types(self):
        out = {}
        for k, v in ((self.spec or {}).get("action_types") or {}).items():
            if k == "not_yet" or not isinstance(v, dict):
                continue
            out[k] = {"dim": v.get("dim"), "layout": v.get("layout"), "units": v.get("units")}
        return out

    def spaces(self):
        sp = ["native"]
        parts = self.m["parts"].values()
        if any(P.get("joints") for P in parts):
            sp.append("joint")
        if any(P.get("ee") or P.get("ik") for P in parts):
            sp.append("ee")
        if any(P.get("ee_delta") for P in parts):
            sp.append("ee_delta")
        if self.m.get("locomotion"):
            sp.append("whole_body")
        return sp

    def observe(self, cameras=None, depth=False, seconds=0.0, save_to=None, inline_cameras=None, **_):
        self.connect()
        cams = list(cameras or self.default_cams())
        bad = [c for c in cams + list(inline_cameras or []) if c not in self.cams_all()]
        if bad:
            raise ToolError(f"unknown cameras {bad}; cameras: {self.cams_all()}")
        cams = list(dict.fromkeys(cams + [c for c in (inline_cameras or []) if c not in cams]))
        seconds = float(seconds or 0)
        try:
            res = self.obs(cams, seconds=seconds, depth=depth, video="mp4" if seconds > 0 else "none")
        except self.rc.EpisodeOver as e:
            return self._episode_over(e), []
        now = self.meta_now(res)
        F = self.base_frame(now, res.meta)
        w = workspace.Writer(save_to)
        images, extras = self.package(res, F, w, cams, depth=depth, inline=inline_cameras, video=seconds > 0)
        out = {"cameras": images, **self.robot_state(now, res.meta, F), **self.common_meta(res)}
        return out, extras

    # -- building rows
    def hold_row(self, typ, now, meta=None) -> np.ndarray:
        T = self.m.get("types", {}).get(typ, {})
        dim = self.type_dim(typ)
        row = None
        for src in T.get("hold", ["ref", "last", "initial", "measured"]):
            if src == "ref" and T.get("hold_ref"):
                row = np.array(self.ref(T["hold_ref"], now, meta), dtype=np.float64)
            elif src == "last" and typ in self.last_cmd:
                row = self.last_cmd[typ].copy()
            elif src == "initial" and T.get("initial"):
                row = np.array(T["initial"], dtype=np.float64)
            elif src == "measured":
                row = self.measured_row(typ, now, meta)
            if row is not None:
                break
        if row is None or len(row) != dim:
            raise ToolError(f"cannot hold action type {typ}: no command in force is known", "internal")
        for c in T.get("zero_cols", []):
            row[c] = 0.0
        return row

    def measured_row(self, typ, now, meta=None):
        T = self.m.get("types", {}).get(typ, {})
        dim = self.type_dim(typ)
        row = np.array(T.get("initial") or [0.0] * dim, dtype=np.float64)
        F = self.base_frame(now, meta)
        filled = False
        for name, P in self.m["parts"].items():
            st = P.get("state", {})
            j = P.get("joints")
            if j and j["type"] == typ and st.get("joints"):
                a, b = j["cols"]
                row[a:b] = self.ref(st["joints"], now, meta)[: b - a]
                filled = True
            g = P.get("gripper")
            if g and g.get("type", typ) == typ and st.get("gripper") and "col" in g:
                v = self.ref(st["gripper"], now, meta)[0]
                gu = self.g_from_suite(v, {**g, **st["gripper"]})
                row[g["col"]] = self.g_to_suite(gu if gu is not None else 0.0, g)
                filled = True
            ee = P.get("ee")
            if ee and ee["type"] == typ:
                pq = self.ee_suite(name, now, meta)
                if pq is not None:
                    a = ee["cols"][0]
                    row[a:a + 3] = pq[0]
                    row[a + 3:a + 7] = q_to(pq[1], ee.get("quat", self.quat_order()))
                    filled = True
                if "gripper_col" in ee and st.get("gripper"):
                    v = self.ref(st["gripper"], now, meta)[0]
                    gu = self.g_from_suite(v, {**P.get("gripper", {}), **st["gripper"]})
                    row[ee["gripper_col"]] = self.g_to_suite(gu if gu is not None else 0.0, P.get("gripper", {}))
        return row if filled or T.get("initial") else None

    def run_rows(self, typ, rows, dt, interpolate="linear", tool="?", max_rows=None):
        """Submit rows in chunks of at most max_chunk_s (and max_rows); returns (last result, executed rows, metas)."""
        rows = np.asarray(rows, dtype=np.float64)
        T = self.m.get("types", {}).get(typ, {})
        per = max(1, int(math.floor(self.max_chunk_s() / dt + 1e-9))) if dt else len(rows)
        max_rows = max_rows or T.get("max_rows")
        if max_rows:
            per = min(per, int(max_rows))
        res, done_rows, metas = None, 0, []
        for i in range(0, len(rows), per):
            chunk = rows[i:i + per]
            res = self.submit(typ, chunk, dt, interpolate, tool=tool)
            metas.append(res.meta)
            done_rows += int(res.meta.get("executed_rows", len(chunk)) or 0)
            self.last_cmd[typ] = chunk[-1].copy()
            for c in T.get("zero_cols_after", []):
                self.last_cmd[typ][c] = 0.0
            if res.meta.get("done") or res.meta.get("stopped"):
                break
        return res, done_rows, metas

    @staticmethod
    def failures(metas) -> list:
        out = []
        for m in metas:
            plan = m.get("plan")
            if isinstance(plan, list):
                for p in plan:
                    if isinstance(p, dict) and (p.get("ok") is False or p.get("status") in ("failed", "fail")):
                        out.append({"category": "no_trajectory", "detail": _jsonable(p)})
            elif isinstance(plan, dict) and plan.get("ok") is False:
                out.append({"category": "no_trajectory", "detail": _jsonable(plan)})
            if m.get("n_clipped") or m.get("clipped"):
                out.append({"category": "limit", "detail": f"{m.get('n_clipped') or len(m.get('clipped') or [])} values clipped to the limits"})
            for r in m.get("results") or []:
                if isinstance(r, dict) and r.get("ok") is False:
                    out.append({"category": "blocked", "detail": _jsonable(r)})
                elif isinstance(r, dict) and isinstance(r.get("result"), dict) and r["result"].get("ik"):
                    out.append({"category": "out_of_reach", "detail": _jsonable(r["result"]["ik"])})
            if m.get("blocked"):
                out.append({"category": "collision", "detail": _jsonable(m.get("error") or m.get("blocked"))})
            if m.get("stopped"):
                out.append({"category": "stopped", "detail": str(m.get("stopped"))})
        return out[:8]

    def finish(self, tool, res, F, metas, executed, extra=None, inline=None, goals_check=None):
        w = workspace.Writer()
        cams = self.action_cams()
        images, extras = self.package(res, F, w, [c for c in cams if c in getattr(res, "last", {})] or [],
                                      inline=inline)
        now = self.meta_now(res)
        st = self.robot_state(now, res.meta, F)
        out = {"moved": executed > 0, "executed_rows": executed}
        if goals_check:
            out["reached"] = goals_check(now, res.meta)
        fl = self.failures(metas)
        if extra:
            out.update(extra)
        if out.get("reached") and not all(g.get("ok") for g in out["reached"]):
            if not fl:
                fl = [{"category": "not_reached", "detail": "the goal was not reached within the tolerance"}]
        out["errors"] = fl
        out["failure"] = {"category": fl[0]["category"]} if fl and (not out.get("reached") or
                                                                      not all(g.get("ok") for g in out["reached"])) else None
        out.update(st)
        out["frames"] = images
        out.update(self.common_meta(res))
        return out, extras

    # -- move_robot
    def move_robot(self, goals, duration_s=None, collision_aware=False, inline_cameras=None, **_):
        self.connect()
        self.n += 1
        parts = self.m["parts"]
        for g in goals:
            t = g.get("target")
            if t == "base":
                if not self.m.get("base"):
                    raise ToolError("this robot has no mobile base (targets: " + ", ".join(parts) + ")")
                if any(k in g for k in ("position", "quaternion_wxyz", "joint_positions", "gripper")):
                    raise ToolError("a base goal takes dx, dy, dyaw only")
            elif t not in parts:
                raise ToolError(f"unknown target {t!r}; targets: {', '.join(list(parts) + (['base'] if self.m.get('base') else []))}")
            elif any(k in g for k in ("dx", "dy", "dyaw")):
                raise ToolError("dx, dy, dyaw are for target base only")
        if len({g['target'] for g in goals}) != len(goals):
            raise ToolError("one goal per target")
        try:
            res0 = self.obs(self.state_cams())
        except self.rc.EpisodeOver as e:
            return self._episode_over(e), []
        now0 = self.meta_now(res0)
        F = self.base_frame(now0, res0.meta)
        notes = []
        if collision_aware:
            if self.m.get("control", {}).get("collision_aware"):
                notes.append("collision checking: " + self.m["control"]["collision_aware"])
            else:
                notes.append("this robot's controller does not plan around obstacles: collision_aware was ignored")
        metas, executed, res = [], 0, res0
        try:
            base_goals = [g for g in goals if g["target"] == "base"]
            part_goals = [g for g in goals if g["target"] != "base"]
            for g in base_goals:
                res, n, ms = self.move_base(g, duration_s, F, now0, res0.meta)
                metas += ms; executed += n
                if res.meta.get("done"):
                    break
            if part_goals and not res.meta.get("done"):
                if base_goals:      # the base moved: re-read the state (the goals stay in the frame of the call's start)
                    res0b = self.obs(self.state_cams()); now0 = self.meta_now(res0b)
                res, n, ms = self.move_parts(part_goals, duration_s, F, now0, res0.meta)
                metas += ms; executed += n
        except self.rc.EpisodeOver as e:
            return self._episode_over(e), []

        def check(now, meta):
            Fn = self.base_frame(now, meta)
            out = []
            for g in goals:
                r = {"target": g["target"]}
                if g["target"] == "base":
                    d = self.base_disp(F, Fn)
                    r.update(d)
                    r["ok"] = abs(d["dx"] - g.get("dx", 0)) < 0.05 and abs(d["dy"] - g.get("dy", 0)) < 0.05 and \
                        abs(geom_wrap(d["dyaw"] - g.get("dyaw", 0))) < 0.1
                    out.append(r); continue
                ok = True
                P = parts[g["target"]]
                tol = self.m.get("control", {}).get("tolerance", {})
                if "position" in g or "quaternion_wxyz" in g:
                    pq = self.ee_suite(g["target"], now, meta)
                    if pq is None:
                        r["note"] = "no end-effector pose in this robot's state"
                    else:
                        p, q = F.from_parent(pq[0], pq[1])
                        if "position" in g:
                            r["position_error_m"] = _f(np.linalg.norm(p - np.asarray(g["position"])))
                            ok &= r["position_error_m"] <= tol.get("pos_m", 0.01)
                        if "quaternion_wxyz" in g:
                            r["rotation_error_rad"] = _f(q_angle(q, q_from(g["quaternion_wxyz"])))
                            ok &= r["rotation_error_rad"] <= tol.get("rot_rad", 0.05)
                if "joint_positions" in g and P.get("state", {}).get("joints"):
                    jp = self.ref(P["state"]["joints"], now, meta)
                    err = np.abs(np.asarray(jp[:len(g["joint_positions"])]) - np.asarray(g["joint_positions"]))
                    r["joint_error_max"] = _f(float(err.max()) if len(err) else 0.0)
                    ok &= r["joint_error_max"] <= tol.get("joint", 0.03)
                if "gripper" in g and P.get("state", {}).get("gripper"):
                    v = self.ref(P["state"]["gripper"], now, meta)[0]
                    r["gripper"] = self.g_from_suite(v, {**P.get("gripper", {}), **P["state"]["gripper"]})
                r["ok"] = bool(ok)
                out.append(r)
            return out
        return self.finish("move_robot", res, F, metas, executed, extra={"notes": notes} if notes else None,
                           inline=inline_cameras, goals_check=check)

    def base_disp(self, F0, F1):
        d = F0.from_parent(F1.p)[0]
        return {"dx": _f(d[0]), "dy": _f(d[1]), "dyaw": _f(geom_wrap(geom.q_yaw(F1.q) - geom.q_yaw(F0.q)))}

    def move_base(self, g, duration_s, F, now, meta):
        B = self.m["base"]
        dx, dy, dyaw = float(g.get("dx", 0)), float(g.get("dy", 0)), float(g.get("dyaw", 0))
        typ = B["type"]
        dt = self.step_dt(B.get("dt"))
        if B.get("mode") == "pose":
            # an absolute base pose command (suite frame): x, y, yaw columns
            cols = B["cols"]
            start = self.hold_row(typ, now, meta)
            x0, y0, yaw0 = start[cols["x"]], start[cols["y"]], start[cols["yaw"]]
            tgt = F.to_parent([dx, dy, 0.0])[0]
            dist = math.hypot(dx, dy)
            T = duration_s or max(1.0, dist / B.get("max_v", 0.3), abs(dyaw) / B.get("max_w", 0.5))
            n = max(1, int(math.ceil(T / dt)))
            rows = []
            for k in range(1, n + 1):
                a = k / n
                r = start.copy()
                r[cols["x"]] = x0 + a * (tgt[0] - x0)
                r[cols["y"]] = y0 + a * (tgt[1] - y0)
                r[cols["yaw"]] = yaw0 + a * dyaw
                rows.append(r)
            res, ex, ms = self.run_rows(typ, rows, dt, tool="move_robot")
            return res, ex, ms
        # velocity mode: translate in the base frame, then turn; open loop (the result reports where the base got to)
        vmax, wmax = float(B.get("max_v", 0.3)), float(B.get("max_w", 0.5))
        cols = B["cols"]
        dist = math.hypot(dx, dy)
        T1 = max(dist / vmax, 0.0)
        T2 = abs(dyaw) / wmax
        if duration_s:
            s = (T1 + T2) / float(duration_s) if (T1 + T2) > 0 else 1.0
            if s < 1:
                T1, T2 = T1 / s, T2 / s
        rows = []
        base = self.hold_row(typ, now, meta)
        for c in cols.values():
            base[c] = 0.0
        if T1 > 0:
            n = max(1, int(round(T1 / dt)))
            vx, vy = dx / (n * dt), dy / (n * dt)
            for _ in range(n):
                r = base.copy(); r[cols["vx"]] = vx
                if "vy" in cols:
                    r[cols["vy"]] = vy
                elif abs(dy) > 1e-6:
                    raise ToolError("this base cannot move sideways (no vy): turn, then move forward")
                rows.append(r)
        if T2 > 0:
            n = max(1, int(round(T2 / dt)))
            wz = dyaw / (n * dt)
            for _ in range(n):
                r = base.copy(); r[cols["wz"]] = wz; rows.append(r)
        stop_n = max(1, int(round(float(B.get("stop_s", 0.2)) / dt)))
        rows += [base.copy() for _ in range(stop_n)]
        res, ex, ms = self.run_rows(typ, rows, dt, tool="move_robot")
        return res, ex, ms

    def move_parts(self, goals, duration_s, F, now, meta):
        parts = self.m["parts"]
        joint_goals, ee_goals, delta_goals = [], [], []
        for g in goals:
            P = parts[g["target"]]
            if "position" in g or "quaternion_wxyz" in g:
                if "joint_positions" in g:
                    raise ToolError(f"{g['target']}: give either an end-effector pose or joint positions, not both")
                if P.get("ee"):
                    ee_goals.append(g)
                elif P.get("ik"):
                    joint_goals.append(self.ik_goal(g, F, now, meta))
                elif P.get("ee_delta"):
                    delta_goals.append(g)
                else:
                    raise ToolError(f"{g['target']} takes no end-effector pose; use joint_positions")
            else:
                if "joint_positions" in g and not P.get("joints"):
                    raise ToolError(f"{g['target']} takes no joint positions")
                if "joint_positions" in g or "gripper" in g:
                    if P.get("joints") or (P.get("gripper") and "col" in P["gripper"]):
                        joint_goals.append(g)
                    elif P.get("ee"):
                        ee_goals.append(g)
                    elif P.get("ee_delta"):
                        delta_goals.append(g)
                    else:
                        raise ToolError(f"{g['target']}: nothing to move")
                else:
                    raise ToolError(f"{g['target']}: a goal needs position/quaternion_wxyz, joint_positions or gripper")
        res, executed, metas = None, 0, []
        if joint_goals:
            res, n, ms = self.move_joints(joint_goals, duration_s, now, meta)
            executed += n; metas += ms
            if res.meta.get("done"):
                return res, executed, metas
            now = self.meta_now(res)
        if ee_goals:
            res, n, ms = self.move_ee(ee_goals, duration_s, F, now, meta)
            executed += n; metas += ms
            if res.meta.get("done"):
                return res, executed, metas
            now = self.meta_now(res)
        for g in delta_goals:
            res, n, ms = self.servo_delta(g, duration_s, F, now, meta)
            executed += n; metas += ms
            if res.meta.get("done"):
                break
            now = self.meta_now(res)
        return res, executed, metas

    def ik_goal(self, g, F, now, meta):
        P = self.m["parts"][g["target"]]
        ik = P["ik"]
        pq = self.ee_suite(g["target"], now, meta)
        if pq is None:
            raise ToolError(f"{g['target']}: no end-effector pose to start from", "internal")
        p_cur, q_cur = F.from_parent(*pq)
        p = np.asarray(g.get("position", p_cur), dtype=np.float64)
        q = q_from(g.get("quaternion_wxyz", q_cur))
        ps, qs = F.to_parent(p, q)
        seed = None
        if ik.get("seed"):
            seed = self.ref(ik["seed"], now, meta)
        target = list(ps) + list(q_to(qs, ik.get("quat", self.quat_order())))
        kw = {}
        if ik.get("base_pose_ref"):
            kw["base_pose"] = [float(x) for x in self.ref(ik["base_pose_ref"], now, meta)]
        sol = self.r.ik({ik["frame"]: target}, seed=seed, **kw)
        if not sol.get("ok"):
            raise ToolError(f"{g['target']}: no joint solution for that pose ({_jsonable(sol.get('error'))})", "out_of_reach")
        q = np.asarray(sol["q"], dtype=np.float64)
        a, b = ik.get("q_cols", [0, P["joints"]["cols"][1] - P["joints"]["cols"][0]])
        out = {"target": g["target"], "joint_positions": q[a:b].tolist(), "_from_pose": True}
        if "gripper" in g:
            out["gripper"] = g["gripper"]
        return out

    def move_joints(self, goals, duration_s, now, meta):
        parts = self.m["parts"]
        types = set()
        for g in goals:
            P = parts[g["target"]]
            if "joint_positions" in g:
                types.add(P["joints"]["type"])
            if "gripper" in g:
                types.add(P["gripper"].get("type") or P["joints"]["type"])
        if len(types) != 1:
            raise ToolError(f"these goals use different action types ({sorted(types)}): send them in separate calls")
        typ = types.pop()
        S = self.hold_row(typ, now, meta)
        G = S.copy()
        grip_cols = []
        for g in goals:
            P = parts[g["target"]]
            if "joint_positions" in g:
                a, b = P["joints"]["cols"]
                jp = np.asarray(g["joint_positions"], dtype=np.float64)
                if len(jp) != b - a:
                    raise ToolError(f"{g['target']}: {b - a} joint positions expected, got {len(jp)}")
                G[a:b] = jp
            if "gripper" in g:
                G[P["gripper"]["col"]] = self.g_to_suite(g["gripper"], P["gripper"])
                grip_cols.append(P["gripper"]["col"])
        c = self.m.get("control", {})
        dt = self.step_dt(c.get("dt"))
        cont = [i for i in range(len(S)) if i not in grip_cols]
        dist = float(np.max(np.abs(G[cont] - S[cont]))) if cont else 0.0
        T = float(duration_s) if duration_s else max(float(c.get("min_move_s", 0.5)), dist / float(c.get("joint_speed", 0.5)))
        n = max(1, int(math.ceil(T / dt - 1e-9)))
        rows = []
        for k in range(1, n + 1):
            r = S + (G - S) * (k / n)
            for gc in grip_cols:
                r[gc] = G[gc]
            rows.append(r)
        settle = float(c.get("gripper_settle_s", 0.5)) if grip_cols else float(c.get("settle_s", 0.0))
        rows += [G.copy() for _ in range(int(round(settle / dt)))]
        return self.run_rows(typ, rows, dt, tool="move_robot")

    def move_ee(self, goals, duration_s, F, now, meta):
        parts = self.m["parts"]
        types = {parts[g["target"]]["ee"]["type"] for g in goals}
        if len(types) != 1:
            raise ToolError("these end-effector goals use different action types: send them in separate calls")
        typ = types.pop()
        S = self.measured_row(typ, now, meta) if self.m.get("types", {}).get(typ, {}).get("hold_measured_ee", True) \
            else self.hold_row(typ, now, meta)
        if S is None:
            S = self.hold_row(typ, now, meta)
        G = S.copy()
        qo = {}
        grip = False
        for g in goals:
            P = parts[g["target"]]
            ee = P["ee"]
            a = ee["cols"][0]
            order = ee.get("quat", self.quat_order())
            pq = self.ee_suite(g["target"], now, meta)
            p_cur, q_cur = (F.from_parent(*pq) if pq is not None else
                            F.from_parent(S[a:a + 3], q_from(S[a + 3:a + 7], order)))
            p = np.asarray(g.get("position", p_cur), dtype=np.float64)
            q = q_from(g.get("quaternion_wxyz", q_cur))
            ps, qs = F.to_parent(p, q)
            # ee rows are interpolated from the target in force, not from the measured pose
            G[a:a + 3] = ps
            qq = q_to(qs, order)
            if np.dot(qq, S[a + 3:a + 7]) < 0:
                qq = -qq
            G[a + 3:a + 7] = qq
            qo[a] = order
            if "gripper" in g:
                gc = ee.get("gripper_col")
                if gc is None:
                    raise ToolError(f"{g['target']}: its gripper is not part of the end-effector command")
                G[gc] = self.g_to_suite(g["gripper"], P.get("gripper", {}))
                grip = True
        c = self.m.get("control", {})
        mode = self.m.get("types", {}).get(typ, {}).get("ee_mode", "planner")
        dt = self.step_dt(c.get("ee_dt", c.get("dt")))
        if mode == "planner":
            rows = [G]
            if grip:
                rows.append(G.copy())
            return self.run_rows(typ, rows, dt, tool="move_robot")
        dist = max([float(np.linalg.norm(G[a:a + 3] - S[a:a + 3])) for a in qo] + [0.0])
        ang = max([q_angle(q_from(G[a + 3:a + 7], qo[a]), q_from(S[a + 3:a + 7], qo[a])) for a in qo] + [0.0])
        T = float(duration_s) if duration_s else max(float(c.get("min_move_s", 0.5)), dist / float(c.get("ee_speed", 0.15)),
                                                      ang / float(c.get("ee_ang_speed", 0.8)))
        n = max(1, int(math.ceil(T / dt - 1e-9)))
        rows = []
        for k in range(1, n + 1):
            t = k / n
            r = S + (G - S) * t
            for a, order in qo.items():
                r[a + 3:a + 7] = q_to(geom.slerp(q_from(S[a + 3:a + 7], order), q_from(G[a + 3:a + 7], order), t), order)
            rows.append(r)
        settle = float(c.get("gripper_settle_s", 0.5)) if grip else float(c.get("ee_settle_s", 0.3))
        rows += [G.copy() for _ in range(int(round(settle / dt)))]
        return self.run_rows(typ, rows, dt, tool="move_robot")

    def servo_delta(self, g, duration_s, F, now, meta):
        """Absolute end-effector goal on a robot that takes end-effector deltas only (its own delta controller):
        bounded steps towards the goal, re-measured after each step."""
        P = self.m["parts"][g["target"]]
        D = P["ee_delta"]
        typ = D["type"]
        dt = self.step_dt(D.get("dt"))
        pq = self.ee_suite(g["target"], now, meta)
        if pq is None:
            raise ToolError(f"{g['target']}: no end-effector pose in the state", "internal")
        p_cur, q_cur = F.from_parent(*pq)
        p_goal = np.asarray(g.get("position", p_cur), dtype=np.float64)
        q_goal = q_from(g.get("quaternion_wxyz", q_cur))
        ps_goal, qs_goal = F.to_parent(p_goal, q_goal)
        tol = self.m.get("control", {}).get("tolerance", {})
        budget = float(duration_s or D.get("max_servo_s", 8.0))
        k = int(D.get("rows_per_step", 5))
        t_used, executed, metas, res = 0.0, 0, [], None
        gripper_val = None if "gripper" not in g else self.g_to_suite(g["gripper"], P.get("gripper", {}))
        while True:
            pq = self.ee_suite(g["target"], now, meta)
            ep = ps_goal - pq[0]
            erot = geom.q_to_rotvec(geom.q_mul(qs_goal, geom.q_conj(pq[1])))
            pos_ok = np.linalg.norm(ep) <= tol.get("pos_m", 0.01) or "position" not in g
            rot_ok = np.linalg.norm(erot) <= tol.get("rot_rad", 0.05) or "quaternion_wxyz" not in g or not D.get("rot_cols")
            if (pos_ok and rot_ok and (gripper_val is None or executed)) or t_used >= budget:
                break
            row = self.hold_row(typ, now, meta)
            ps = float(D["pos_scale"])
            vec = ep if "position" in g else np.zeros(3)
            if D.get("frame") == "ee":
                vec = geom.q_to_mat(pq[1]).T @ vec
            step = np.clip(vec / k / ps * float(D.get("gain", 1.0)), -1, 1) * float(D.get("max_cmd", 1.0))
            a, b = D["pos_cols"]
            row[a:b] = step[: b - a] * np.asarray(D.get("pos_sign", [1, 1, 1]))[: b - a]
            if D.get("rot_cols") and "quaternion_wxyz" in g:
                rs = float(D["rot_scale"])
                rv = erot if D.get("frame") != "ee" else geom.q_to_mat(pq[1]).T @ erot
                rstep = np.clip(rv / k / rs, -1, 1) * float(D.get("max_cmd", 1.0))
                a, b = D["rot_cols"]
                row[a:b] = rstep[: b - a]
            if gripper_val is not None and D.get("gripper_col") is not None:
                row[D["gripper_col"]] = gripper_val
            res, n, ms = self.run_rows(typ, [row] * k, dt, tool="move_robot")
            executed += n; metas += ms; t_used += k * dt
            now, meta = self.meta_now(res), res.meta
            if res.meta.get("done"):
                break
        if res is None:
            res = self.obs(self.state_cams())
        return res, executed, metas

    # -- locomote
    def locomote(self, vx, vy, wz, duration_s, height=None, inline_cameras=None, **_):
        self.connect()
        self.n += 1
        L = self.m.get("locomotion")
        if not L:
            raise ToolError("this robot has no locomotion controller (use move_robot)")
        res0 = self.obs(self.state_cams())
        now = self.meta_now(res0)
        F = self.base_frame(now, res0.meta)
        typ = L["type"]
        cols = L["cols"]
        lim = L.get("limits", {})
        dt = self.step_dt(L.get("dt"))
        row = self.hold_row(typ, now, res0.meta)
        for k, v in (("vx", vx), ("vy", vy), ("wz", wz)):
            if k not in cols:
                if abs(float(v)) > 1e-9:
                    raise ToolError(f"this robot's controller takes no {k}")
                continue
            lo, hi = lim.get(k, [-1e9, 1e9])
            row[cols[k]] = min(hi, max(lo, float(v)))
        if height is not None:
            if "height" not in cols:
                raise ToolError("this robot's controller takes no height")
            lo, hi = lim.get("height", [-1e9, 1e9])
            row[cols["height"]] = min(hi, max(lo, float(height)))
        n = max(1, int(round(float(duration_s) / dt)))
        stop = row.copy()
        for k in ("vx", "vy", "wz"):
            if k in cols:
                stop[cols[k]] = 0.0
        rows = [row] * n + [stop] * max(1, int(round(float(L.get("stop_s", 0.2)) / dt)))
        try:
            res, ex, ms = self.run_rows(typ, rows, dt, tool="locomote")
        except self.rc.EpisodeOver as e:
            return self._episode_over(e), []
        self.last_cmd[typ] = stop.copy()
        Fn = self.base_frame(self.meta_now(res), res.meta)
        return self.finish("locomote", res, F, ms, ex, extra={"displacement": self.base_disp(F, Fn)}, inline=inline_cameras)

    # -- execute_trajectory
    def execute_trajectory(self, space, rows=None, native_rows=None, rows_file=None, action_type=None, dt=None,
                           interpolate="linear", inline_cameras=None, **_):
        self.connect()
        self.n += 1
        if rows_file:
            p = workspace.resolve_under_root(rows_file, must_exist=True)
            if p.suffix == ".npy":
                native_rows = np.load(p, allow_pickle=False).tolist()
            elif p.suffix == ".csv":
                native_rows = np.loadtxt(p, delimiter=",", ndmin=2).tolist()
            elif p.suffix == ".json":
                data = json.loads(p.read_text())
                if data and isinstance(data[0], list):
                    native_rows = data
                else:
                    rows = data
            else:
                raise ToolError("rows_file: .json, .npy or .csv")
        res0 = self.obs(self.state_cams())
        now = self.meta_now(res0)
        F = self.base_frame(now, res0.meta)
        try:
            if space == "native":
                if not action_type:
                    raise ToolError("space native needs action_type (describe_robot: action_types_native)")
                if not native_rows:
                    raise ToolError("space native takes native_rows (or a .npy / .csv rows_file)")
                A = np.asarray(native_rows, dtype=np.float64)
                dim = self.type_dim(action_type)
                if A.ndim != 2 or A.shape[1] != dim:
                    raise ToolError(f"{action_type}: rows of {dim} numbers expected, got shape {list(A.shape)}")
                d = self.step_dt(dt) if dt else (self.step_dt(None) if dim else self.control_dt())
                res, ex, ms = self.run_rows(action_type, A, d, interpolate, tool="execute_trajectory")
                return self.finish("execute_trajectory", res, F, ms, ex, inline=inline_cameras)
            if not rows:
                raise ToolError(f"space {space} takes rows (a list of objects naming parts)")
            if space == "joint":
                A, typ = self.rows_joint(rows, now, res0.meta)
            elif space == "ee":
                A, typ = self.rows_ee(rows, F, now, res0.meta)
            elif space == "ee_delta":
                A, typ = self.rows_delta(rows, F, now, res0.meta)
            elif space == "whole_body":
                A, typ = self.rows_whole_body(rows, now, res0.meta)
            else:
                raise ToolError(f"unknown space {space}")
            d = self.step_dt(dt) if dt else self.step_dt(None)
            res, ex, ms = self.run_rows(typ, A, d, interpolate, tool="execute_trajectory")
        except self.rc.EpisodeOver as e:
            return self._episode_over(e), []
        return self.finish("execute_trajectory", res, F, ms, ex, inline=inline_cameras)

    def _check_parts(self, row, allowed):
        for k in row:
            if k not in self.m["parts"] and k != "base":
                raise ToolError(f"unknown part {k!r}; parts: {', '.join(self.m['parts'])}")
            if allowed and k not in allowed:
                raise ToolError(f"part {k!r} cannot be used in this space")

    def rows_joint(self, rows, now, meta):
        parts = self.m["parts"]
        typs = set()
        for r in rows:
            self._check_parts(r, [n for n, P in parts.items() if P.get("joints") or (P.get("gripper") and "col" in P["gripper"])])
            for k in r:
                P = parts[k]
                typs.add((P.get("joints") or P.get("gripper"))["type"])
        if len(typs) != 1:
            raise ToolError(f"the rows mix action types {sorted(typs)}")
        typ = typs.pop()
        cur = self.hold_row(typ, now, meta)
        out = []
        for r in rows:
            cur = cur.copy()
            for k, v in r.items():
                P = parts[k]
                if "joint_positions" in v:
                    a, b = P["joints"]["cols"]
                    jp = np.asarray(v["joint_positions"], dtype=np.float64)
                    if len(jp) != b - a:
                        raise ToolError(f"{k}: {b - a} joint positions expected, got {len(jp)}")
                    cur[a:b] = jp
                if "gripper" in v:
                    cur[P["gripper"]["col"]] = self.g_to_suite(v["gripper"], P["gripper"])
            out.append(cur)
        return np.asarray(out), typ

    def rows_ee(self, rows, F, now, meta):
        parts = self.m["parts"]
        typs = set()
        for r in rows:
            self._check_parts(r, [n for n, P in parts.items() if P.get("ee")])
            for k in r:
                typs.add(parts[k]["ee"]["type"])
        if len(typs) != 1:
            raise ToolError(f"the rows mix action types {sorted(typs)}")
        typ = typs.pop()
        cur = self.measured_row(typ, now, meta)
        if cur is None:
            cur = self.hold_row(typ, now, meta)
        out = []
        for r in rows:
            cur = cur.copy()
            for k, v in r.items():
                P = parts[k]; ee = P["ee"]; a = ee["cols"][0]; order = ee.get("quat", self.quat_order())
                p_cur, q_cur = F.from_parent(cur[a:a + 3], q_from(cur[a + 3:a + 7], order))
                p = np.asarray(v.get("position", p_cur), dtype=np.float64)
                q = q_from(v.get("quaternion_wxyz", q_cur))
                ps, qs = F.to_parent(p, q)
                cur[a:a + 3] = ps
                qq = q_to(qs, order)
                if np.dot(qq, cur[a + 3:a + 7]) < 0:
                    qq = -qq
                cur[a + 3:a + 7] = qq
                if "gripper" in v:
                    if ee.get("gripper_col") is None:
                        raise ToolError(f"{k}: its gripper is not part of the end-effector command")
                    cur[ee["gripper_col"]] = self.g_to_suite(v["gripper"], P.get("gripper", {}))
            out.append(cur)
        return np.asarray(out), typ

    def rows_delta(self, rows, F, now, meta):
        parts = self.m["parts"]
        typs = set()
        for r in rows:
            self._check_parts(r, [n for n, P in parts.items() if P.get("ee_delta")])
            for k in r:
                typs.add(parts[k]["ee_delta"]["type"])
        if len(typs) != 1:
            raise ToolError(f"the rows mix action types {sorted(typs)}")
        typ = typs.pop()
        base = self.hold_row(typ, now, meta)
        out = []
        for r in rows:
            cur = base.copy()
            for k, v in r.items():
                P = parts[k]; D = P["ee_delta"]
                if "dpos" in v:
                    vec = F.vec_to_parent(v["dpos"])
                    if D.get("frame") == "ee":
                        pq = self.ee_suite(k, now, meta)
                        vec = geom.q_to_mat(pq[1]).T @ vec
                    a, b = D["pos_cols"]
                    cur[a:b] = (np.clip(vec / float(D["pos_scale"]), -1, 1) * float(D.get("max_cmd", 1.0)) *
                                np.asarray(D.get("pos_sign", [1, 1, 1])))[: b - a]
                if "drot" in v:
                    if not D.get("rot_cols"):
                        raise ToolError(f"{k} takes no rotation deltas")
                    rv = F.vec_to_parent(v["drot"])
                    a, b = D["rot_cols"]
                    cur[a:b] = (np.clip(rv / float(D["rot_scale"]), -1, 1) * float(D.get("max_cmd", 1.0)))[: b - a]
                if "gripper" in v and D.get("gripper_col") is not None:
                    cur[D["gripper_col"]] = self.g_to_suite(v["gripper"], P.get("gripper", {}))
                    base[D["gripper_col"]] = cur[D["gripper_col"]]
            out.append(cur)
        return np.asarray(out), typ

    def rows_whole_body(self, rows, now, meta):
        L = self.m.get("locomotion")
        if not L:
            raise ToolError("this robot has no whole-body controller: use space joint or native")
        typ = L["type"]
        cols = L["cols"]
        parts = self.m["parts"]
        cur = self.hold_row(typ, now, meta)
        out = []
        for r in rows:
            self._check_parts(r, None)
            cur = cur.copy()
            for k, v in r.items():
                if k == "base":
                    for key in ("vx", "vy", "wz", "height", *L.get("extra", [])):
                        if key in v:
                            if key not in cols:
                                raise ToolError(f"base: this controller takes no {key}")
                            cur[cols[key]] = float(v[key])
                    continue
                P = parts[k]
                if "joint_positions" in v:
                    if not P.get("joints") or P["joints"]["type"] != typ:
                        raise ToolError(f"{k}: joints are not part of the whole-body command")
                    a, b = P["joints"]["cols"]
                    cur[a:b] = np.asarray(v["joint_positions"], dtype=np.float64)[: b - a]
                if "gripper" in v:
                    cur[P["gripper"]["col"]] = self.g_to_suite(v["gripper"], P["gripper"])
            out.append(cur)
        return np.asarray(out), typ

    # -- wait and signal
    def wait(self, seconds=0.0, inline_cameras=None, **_):
        self.connect()
        cams = self.action_cams()
        try:
            res = self.obs(cams, seconds=float(seconds or 0), video="none")
        except self.rc.EpisodeOver as e:
            return self._episode_over(e), []
        now = self.meta_now(res)
        F = self.base_frame(now, res.meta)
        w = workspace.Writer()
        images, extras = self.package(res, F, w, cams, inline=inline_cameras)
        return {"waited_s": float(seconds or 0), "frames": images, **self.robot_state(now, res.meta, F),
                **self.common_meta(res)}, extras

    def signal(self, kind, note, category=None, **_):
        self.connect()
        S = self.m.get("signals", {})
        if kind not in S:
            if kind == "done" and not S:
                return {"recorded": True, "note": "this episode ends on success or when your time is up; nothing else "
                        "to hand in. You can end your session now."}, []
            raise ToolError(f"signal {kind!r} is not available here (available: {sorted(S) or ['done']})")
        sg = S[kind]
        if sg.get("finish"):
            import requests
            r = requests.post(self.r.base + "/finish", json={}, timeout=(5, 120))
            return {"finished": r.status_code == 200, "answer": _jsonable(r.json() if r.content else {})}, []
        typ = sg["type"]
        dim = self.type_dim(typ)
        row = [0.0] * dim
        if dim:
            if category is None:
                raise ToolError(f"signal {kind} needs a category ({sg.get('categories', '')})")
            row[0] = float(category)
        try:
            res = self.submit(typ, np.asarray([row], dtype=np.float64), self.control_dt(), "linear",
                              cams=self.state_cams(), note=note, tool="signal")
        except self.rc.EpisodeOver as e:
            return self._episode_over(e), []
        out = {"sent": kind, **self.common_meta(res)}
        m = res.meta
        if m.get("results"):
            out["results"] = _jsonable(m["results"])
        return out, []


def geom_wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
