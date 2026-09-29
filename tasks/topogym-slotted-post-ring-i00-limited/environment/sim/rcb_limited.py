"""rcb-limited/2.2 — the HTTP layer and the protocol helpers every sim service shares (docs/LIMITED_MODE_PROTOCOL.md).

Byte-identical in every limited task's environment/sim/ (ci_checks/check-tooling-identity.sh). A service keeps its
simulator to itself (scene, action execution, cameras, kinematic model) and hands this module plain callables:

    import rcb_limited as L
    rec = L.Recorder(cams, every, grab, proprio_row, extrinsics, clock, depth=L.depth_mode(meta), clock_hz=CTRL_HZ)
    rec.tick(force=True)            # first frame (before the chunk / watch)
    ...; rec.tick(); ...            # after every control step: a frame every `every` steps
    rec.tick(force=True, last=True) # last frame (+ its depth)
    parts = rec.parts(video, fps)   # RCB1 parts: video/ frames/ last/ extrinsic_cv/ last_depth/ depth_frames/ depth/ proprio frame_*
    L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics,
                      status=status, on_submit_error=lambda exc: finish("error"), log=log))

    grab(cams, want_depth) -> ({cam: uint8 (H,W,3)}, {cam: float32 (H,W) z-depth in metres, 0 = no reading})
    extrinsics(cams)       -> {cam: (3,4) world -> camera, OpenCV axes (x right, y down, z forward)}
    proprio_row()          -> float32 (len(spec["proprio_layout"]),)
    clock()                -> int, control steps since the episode start (the frame's step index)
    do_kinematics(req)     -> dict; `req` is parse_kinematics(body, spec["kinematics"]); it must never step physics

None of the callables may step physics. check_spec(SPEC) runs in serve(): a service whose /spec misses a 2.2 field, or
carries a field the protocol forbids (segmentation, object identities or sizes, physical parameters), does not start."""
from __future__ import annotations
import json, math, os, re, tempfile, threading, traceback, zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

import numpy as np

import rcb1

PROTOCOL = "rcb-limited/2.2"
COMPAT = ["rcb-limited/2.0", "rcb-limited/2.1"]           # requests written for these are served unchanged
MAX_BODY = 64 * 1024 * 1024
MAX_RESP = 256 * 1024 * 1024
DEPTH_MODES = ("none", "last", "frames")
DEPTH_MAX_M = 65.535                                        # uint16 millimetres; a farther surface reads 0 (no reading)
DEPTH_NOISE = os.environ.get("RCB_DEPTH_NOISE", "off").strip().lower()   # off | realsense (as rcb-limited/2.1)
_RNG = np.random.default_rng(int(os.environ.get("RCB_DEPTH_NOISE_SEED", "0")))
PROPRIO_GROUPS_REQUIRED = ("joint_pos", "joint_vel", "gripper_opening", "tcp_pose", "joint_effort")
PART_PREFIXES = ("video/", "frames/", "last/", "last_depth/", "depth_frames/", "depth/", "extrinsic_cv/")
PART_NAMES = ("proprio", "frame_step", "frame_time_s")


# ---------------------------------------------------------------- depth
def depth_mode(meta: dict) -> str:
    """The request's depth mode: "none" | "last" | "frames" (2.2 field `depth`), or "legacy" for a 2.0/2.1 request that
    sets `include_depth: true` and no `depth` (answered as 2.1 did: `depth/<cam>` float16 (N,H,W) metres)."""
    d = meta.get("depth")
    if d is None or d is False:
        return "legacy" if meta.get("include_depth") is True else "none"
    if d is True:
        return "last"
    if isinstance(d, str) and d in DEPTH_MODES:
        return d
    raise ValueError(f"depth must be one of {'|'.join(DEPTH_MODES)} (got {d!r})")


def clean_depth(z) -> np.ndarray:
    """float32 z-depth in metres: non-finite, negative and beyond-range pixels read 0 (no reading); the optional
    RCB_DEPTH_NOISE=realsense model (sigma = 2 mm + 2.5 mm * z^2, 1 % dropouts) is applied here, after rendering, so it
    never touches physics."""
    z = np.asarray(z, dtype=np.float32).copy()
    if z.ndim == 3 and z.shape[-1] == 1:
        z = z[..., 0]
    bad = ~np.isfinite(z) | (z <= 0) | (z > DEPTH_MAX_M)
    z[bad] = 0.0
    if DEPTH_NOISE == "realsense":
        valid = z > 0
        z = z + _RNG.normal(0.0, 1.0, z.shape).astype(np.float32) * (0.002 + 0.0025 * z * z)
        z[_RNG.random(z.shape) < 0.01] = 0.0
        z[~valid] = 0.0
        z[(z < 0) | (z > DEPTH_MAX_M)] = 0.0
    return z.astype(np.float32)


def depth_frames_part(name: str, stack: np.ndarray) -> tuple[str, str, bytes, dict]:
    """(N,H,W) metres -> an RCB1 "bytes" part: zlib of C-order uint16 millimetres (0 = no reading). Clients that do not
    know it keep the raw bytes and ignore it; rcb_client decodes it back to float32 metres."""
    mm = np.rint(np.asarray(stack, dtype=np.float64) * 1000.0)
    mm[(mm < 0) | (mm > 65535)] = 0
    a = np.ascontiguousarray(mm.astype("<u2"))
    return (name, "bytes", zlib.compress(a.tobytes(), 1), {"codec": "zlib", "dtype": "uint16", "shape": list(a.shape), "unit": "mm"})


def encode_mp4(frames: np.ndarray, fps: int) -> bytes:
    """H.264 mp4 (yuv420p, faststart) of uint8 (N,H,W,3) frames: the same encoding every 2.0 service used."""
    import imageio.v2 as imageio
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        path = tf.name
    try:
        with imageio.get_writer(path, format="FFMPEG", mode="I", fps=fps, codec="libx264", macro_block_size=1,
                                output_params=["-movflags", "+faststart", "-pix_fmt", "yuv420p"]) as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f))
        return open(path, "rb").read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ---------------------------------------------------------------- recording what the cameras see during one call
class Recorder:
    """Frames of the requested cameras every `every` clock ticks, plus forced first/last frames; for every frame the
    proprio row, the clock (step index), each camera's extrinsics and, if asked, its depth. All arrays share one frame
    axis N: frames/<cam>, the mp4's frames, proprio, frame_step, frame_time_s, extrinsic_cv/<cam>, depth_frames/<cam>."""

    def __init__(self, cameras, every: int, grab: Callable, proprio_row: Callable, extrinsics: Callable, clock: Callable,
                 depth: str = "none", clock_hz: float = 1.0):
        if depth not in DEPTH_MODES + ("legacy",):
            raise ValueError(f"bad depth mode {depth!r}")
        self.cams = list(cameras); self.every = max(1, int(every)); self.mode = depth; self.hz = float(clock_hz)
        self._grab, self._prop, self._ext, self._clock = grab, proprio_row, extrinsics, clock
        self.frames: dict = {c: [] for c in self.cams}; self.depth: dict = {c: [] for c in self.cams}
        self.ext: dict = {c: [] for c in self.cams}; self.last_depth: dict = {}
        self.prop: list = []; self.steps: list = []; self.n = 0; self.missing = 0

    def tick(self, force: bool = False, last: bool = False) -> None:
        if force or last or self.n % self.every == 0:
            self._capture(last)
        self.n += 1

    def _capture(self, last: bool) -> None:
        want = self.mode in ("frames", "legacy") or (last and self.mode == "last")
        rgb, dep = self._grab(self.cams, want)
        ext = self._ext(self.cams)
        for c in self.cams:
            img = rgb.get(c)
            if img is not None:
                img = np.ascontiguousarray(np.asarray(img)[..., :3].astype(np.uint8))
            else:                  # a camera that failed to render: a black frame (sized in parts()) keeps one frame axis
                self.missing += 1
            self.frames[c].append(img)
            e = ext.get(c)
            self.ext[c].append(np.full((3, 4), np.nan) if e is None else np.asarray(e, dtype=np.float64).reshape(3, 4))
            if want:
                d = dep.get(c)
                if d is None:
                    d = np.zeros(img.shape[:2] if img is not None else (1, 1), np.float32)
                else:
                    d = clean_depth(d)
                if img is not None and d.shape != img.shape[:2]:
                    raise RuntimeError(f"depth of {c} is {d.shape}, its RGB {img.shape[:2]}: they must be pixel-aligned")
                if self.mode in ("frames", "legacy"):
                    self.depth[c].append(d)
                if last or self.mode == "frames":
                    self.last_depth[c] = d
        self.prop.append(np.asarray(self._prop(), dtype=np.float32).reshape(-1))
        self.steps.append(int(self._clock()))

    def parts(self, video: str, fps: int) -> list:
        if self.mode == "last" and not self.last_depth and self.prop:   # no last=True tick: the state has not moved since
            _, dep = self._grab(self.cams, True)
            self.last_depth = {c: clean_depth(dep[c]) for c in self.cams if c in dep}
        out = []
        for c in self.cams:
            good = [f for f in self.frames[c] if f is not None]
            hw = good[-1].shape[:2] if good else (1, 1)
            if len(good) < len(self.frames[c]):
                self.frames[c] = [f if f is not None else np.zeros(hw + (3,), np.uint8) for f in self.frames[c]]
                self.depth[c] = [d if d.shape == hw else np.zeros(hw, np.float32) for d in self.depth[c]]
                if c in self.last_depth and self.last_depth[c].shape != hw:
                    self.last_depth[c] = np.zeros(hw, np.float32)
            fr = np.stack(self.frames[c]) if self.frames[c] else np.zeros((0, 1, 1, 3), np.uint8)
            if video in ("mp4", "both") and len(fr):
                out.append((f"video/{c}", "mp4", encode_mp4(fr, fps), {"fps": fps, "n": int(len(fr))}))
            if video in ("frames", "both"):
                out.append(rcb1.array_part(f"frames/{c}", fr))
            if len(fr):
                out.append(rcb1.array_part(f"last/{c}", fr[-1]))
            out.append(rcb1.array_part(f"extrinsic_cv/{c}", np.stack(self.ext[c]) if self.ext[c] else np.zeros((0, 3, 4))))
            if self.mode in ("last", "frames") and c in self.last_depth:
                out.append(rcb1.array_part(f"last_depth/{c}", self.last_depth[c]))
            if self.mode == "frames" and self.depth[c]:
                out.append(depth_frames_part(f"depth_frames/{c}", np.stack(self.depth[c])))
            if self.mode == "legacy" and self.depth[c]:
                out.append(rcb1.array_part(f"depth/{c}", np.stack(self.depth[c]).astype(np.float16)))
        out.append(rcb1.array_part("proprio", np.stack(self.prop) if self.prop else np.zeros((0, 0), np.float32)))
        st = np.asarray(self.steps, dtype=np.int64)
        out.append(rcb1.array_part("frame_step", st))
        out.append(rcb1.array_part("frame_time_s", st.astype(np.float64) / self.hz))
        return out


def encode_response(meta: dict, parts: list, max_bytes: int = MAX_RESP) -> bytes:
    """The RCB1 body; over `max_bytes` the per-frame depth goes first, then the raw frames (mp4, last frames, last
    depth, proprio and the per-frame arrays always stay), and meta["degraded"] says what was dropped."""
    body = rcb1.encode(meta, parts)
    dropped = []
    for prefixes in (("depth_frames/", "depth/"), ("frames/",)):
        if len(body) <= max_bytes:
            break
        keep = [p for p in parts if not p[0].startswith(prefixes)]
        if len(keep) < len(parts):
            parts = keep; dropped += [x.rstrip("/") for x in prefixes]
            body = rcb1.encode({**meta, "degraded": f"response over {max_bytes} bytes: {', '.join(dropped)} dropped"}, parts)
    return body


# ---------------------------------------------------------------- kinematics
def _vec(x, n: int, what: str) -> list:
    a = np.asarray(x, dtype=np.float64).reshape(-1) if x is not None else None
    if a is None or a.size != n or not np.all(np.isfinite(a)):
        raise ValueError(f"{what} must be {n} finite numbers")
    return a.tolist()


def _pose(x, what: str) -> list:
    p = _vec(x, 7, what)
    nq = math.sqrt(sum(v * v for v in p[3:]))
    if nq < 1e-6:
        raise ValueError(f"{what}: quaternion has zero norm")
    return p[:3] + [v / nq for v in p[3:]]


def parse_kinematics(body: dict, kin: dict) -> dict:
    """Validate a /kinematics request against spec["kinematics"] (ValueError -> 400). Returns
    {"op": "fk", "q", "links", "base_pose"} or {"op": "ik", "targets": {frame: pose7}, "seed", "base_pose", "tol_pos_m",
    "tol_rot_rad", "max_iters"}; poses are x y z + a unit quaternion in the spec's order; q follows kin["joint_names"]."""
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    op = body.get("op"); n = len(kin["joint_names"])
    base = None
    if body.get("base_pose") is not None:
        if kin.get("frame") != "base":
            raise ValueError("base_pose is only accepted by a mobile robot (spec kinematics.frame == 'base')")
        base = _pose(body["base_pose"], "base_pose")
    if op == "fk":
        links = body.get("links") or list(kin["links"])
        if not isinstance(links, list) or any(l not in kin["links"] for l in links):
            raise ValueError(f"links must be a list of names from spec kinematics.links: {kin['links']}")
        return {"op": "fk", "q": _vec(body.get("q"), n, "q"), "links": links, "base_pose": base}
    if op == "ik":
        tg = body.get("targets")
        if not isinstance(tg, dict) or not tg or any(k not in kin["ik_targets"] for k in tg):
            raise ValueError(f"targets must map frames from spec kinematics.ik_targets {kin['ik_targets']} to poses")
        ik = kin.get("ik", {})
        seed = None if body.get("seed") is None else _vec(body["seed"], n, "seed")
        tol_p = float(body.get("tol_pos_m", ik.get("tol_pos_m", 0.005)))
        tol_r = float(body.get("tol_rot_rad", ik.get("tol_rot_rad", 0.05)))
        it = int(body.get("max_iters", ik.get("max_iters", 200)))
        if not (1e-5 <= tol_p <= 0.5 and 1e-4 <= tol_r <= 3.2 and 1 <= it <= 5000):
            raise ValueError("tol_pos_m in [1e-5, 0.5], tol_rot_rad in [1e-4, 3.2], max_iters in [1, 5000]")
        return {"op": "ik", "targets": {k: _pose(v, f"targets[{k}]") for k, v in tg.items()}, "seed": seed, "base_pose": base,
                "tol_pos_m": tol_p, "tol_rot_rad": tol_r, "max_iters": it}
    raise ValueError("op must be 'fk' or 'ik'")


def fk_response(poses: dict, frame: str) -> dict:
    return {"ok": True, "op": "fk", "frame": frame, "poses": {k: [float(v) for v in np.asarray(p, dtype=np.float64).reshape(7)] for k, p in poses.items()}}


def ik_response(q, ok: bool, errors: dict, frame: str, note: str | None = None) -> dict:
    """errors: {frame: (position error m, rotation error rad)} of the returned q (None / non-finite -> null: no solution)."""
    fin = lambda v: float(v) if v is not None and math.isfinite(float(v)) else None  # noqa: E731
    out = {"ok": bool(ok), "op": "ik", "frame": frame, "q": None if q is None else [float(v) for v in np.asarray(q).reshape(-1)],
           "error": {k: {"pos_m": fin(e[0]), "rot_rad": fin(e[1])} for k, e in errors.items()}}
    if note:
        out["note"] = note
    return out


def quat_angle(q1, q2) -> float:
    """Rotation angle (rad) between two unit quaternions of the same order."""
    d = abs(float(np.dot(np.asarray(q1, dtype=np.float64), np.asarray(q2, dtype=np.float64))))
    return 2.0 * math.acos(min(1.0, d))


# ---------------------------------------------------------------- /spec self-check
FORBIDDEN_KEY = re.compile(r"mask|segment|semantic(?!s$)|instance_?id|bbox|bounding|categor|object|\bobj_|label|mass|friction|"
                           r"restitution|inertia|density|damping|stiffness", re.I)
GAIN_PATHS = ("robot_spec.controller",)      # joint drive gains (stiffness, damping) are the robot's own, and allowed there
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


def static_positions(obj: Any, path: str = "static") -> list[str]:
    """Paths in /spec static that say WHERE something is (keys naming positions, heights, centres; texts with world
    coordinates). Names, inventories, sizes and colours may stay in static; positions never (docs § Never provided)."""
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


SPEC_REQUIRED = ("protocol", "protocol_compat", "simulator", "robot", "task_text", "control_hz", "cameras", "default_cameras",
                 "action_types", "proprio_layout", "proprio_groups", "static", "world", "budget", "robot_spec", "kinematics", "depth")


def forbidden_keys(obj: Any, path: str = "", skip: tuple = ()) -> list[str]:
    """Key paths that name something the protocol never provides (key paths in `skip` are not searched)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if p in skip:
                continue
            if FORBIDDEN_KEY.search(str(k)) and not (re.search(r"damping|stiffness", str(k), re.I) and p.startswith(GAIN_PATHS)):
                out.append(p)
            out += forbidden_keys(v, p, skip)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += forbidden_keys(v, f"{path}[{i}]", skip)
    return out


def check_spec(spec: dict) -> None:
    """Raise if /spec is not a complete 2.2 spec or names anything forbidden (run at startup, before binding :8000)."""
    miss = [k for k in SPEC_REQUIRED if k not in spec]
    if miss:
        raise RuntimeError(f"/spec misses {miss}")
    if spec["protocol"] != PROTOCOL:
        raise RuntimeError(f"/spec protocol {spec['protocol']!r} != {PROTOCOL}")
    bad = forbidden_keys(spec, skip=())
    if bad:
        raise RuntimeError(f"/spec names forbidden fields: {bad}")
    pos = static_positions(spec["static"])
    if pos:
        raise RuntimeError(f"/spec static says where things are (never provided): {pos}")
    lay = spec["proprio_layout"]
    if len(set(lay)) != len(lay):
        raise RuntimeError("proprio_layout names are not unique")
    for g in PROPRIO_GROUPS_REQUIRED:
        if g not in spec["proprio_groups"]:
            raise RuntimeError(f"proprio_groups misses {g}")
    for g, (first, n, _meaning) in spec["proprio_groups"].items():
        if not (0 <= first and first + n <= len(lay)):
            raise RuntimeError(f"proprio group {g} [{first}, +{n}) outside the {len(lay)} columns")
    kin = spec["kinematics"]
    for k in ("endpoint", "joint_names", "frame", "quaternion_order", "links", "tcp_frames", "ee_frames", "ik_targets"):
        if k not in kin:
            raise RuntimeError(f"kinematics misses {k}")
    if any(j not in lay for j in kin["joint_names"]):
        raise RuntimeError("kinematics.joint_names must be proprio_layout columns (the measured joint positions)")
    if any(f not in kin["links"] for f in list(kin["tcp_frames"]) + list(kin["ee_frames"]) + list(kin["ik_targets"])):
        raise RuntimeError("kinematics tcp_frames / ee_frames / ik_targets must be listed in kinematics.links")
    if spec["proprio_groups"]["tcp_pose"][1] != 7 * len(kin["tcp_frames"]):
        raise RuntimeError("proprio group tcp_pose must hold 7 columns per kinematics.tcp_frames entry")
    for c, cam in spec["cameras"].items():
        for k in ("rgb", "depth", "mounted", "resolution", "intrinsic_cv", "mount"):
            if k not in cam:
                raise RuntimeError(f"cameras.{c} misses {k}")
        if cam["mount"].get("type") not in ("static", "link"):
            raise RuntimeError(f"cameras.{c}.mount.type must be static|link")
    if any(c not in spec["cameras"] for c in spec["default_cameras"]):
        raise RuntimeError("default_cameras must be cameras")


# ---------------------------------------------------------------- the HTTP layer
class Service:
    """What a sim service hands to serve(): spec (dict), lock, state (the service's E dict: done, reason, exiting, error),
    submit(meta, actions) and observe(meta) -> (meta_out, rcb1 parts), kinematics(req) -> dict, status() -> dict,
    on_submit_error(exc) (ends the episode), log(event dict)."""

    def __init__(self, *, spec: dict, lock, state: dict, submit: Callable, observe: Callable, kinematics: Callable,
                 status: Callable, on_submit_error: Callable, log: Callable, max_resp: int = MAX_RESP):
        self.spec, self.lock, self.state, self.submit, self.observe = spec, lock, state, submit, observe
        self.kinematics, self.status, self.on_submit_error, self.log, self.max_resp = kinematics, status, on_submit_error, log, max_resp
        self.kin_calls = 0


def make_handler(svc: Service):
    class H(BaseHTTPRequestHandler):
        def _json(self, code: int, obj: dict) -> None:
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)

        def _rcb1(self, meta: dict, parts: list) -> None:
            body = encode_response(meta, parts, svc.max_resp)
            self.send_response(200); self.send_header("Content-Type", "application/x-rcb1"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                raise ValueError("bad Content-Length")
            if n > MAX_BODY:
                raise ValueError("request too large")
            raw = self.rfile.read(n) if n else b""
            if raw[:4] == rcb1.MAGIC:
                return rcb1.decode(raw)
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object or an RCB1 frame")
            return body, {}

        def do_GET(self):
            if self.path == "/spec":
                return self._json(200, svc.spec)
            if self.path == "/status":
                return self._json(200, svc.status())
            return self._json(404, {"error": "no such endpoint"})

        def do_POST(self):
            if self.path not in ("/submit", "/observe", "/kinematics"):
                return self._json(404, {"error": "no such endpoint"})
            try:
                meta, parts = self._body()
            except Exception as exc:  # noqa: BLE001
                return self._json(413 if "too large" in str(exc) else 400, {"error": str(exc)[:200]})
            E = svc.state
            if self.path == "/kinematics":          # stateless: never steps physics, never waits for the episode lock
                try:
                    req = parse_kinematics(meta, svc.spec["kinematics"])
                    out = svc.kinematics(req); svc.kin_calls += 1
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)[:300]})
                except Exception as exc:  # noqa: BLE001
                    traceback.print_exc(); return self._json(500, {"error": "kinematics error", "detail": repr(exc)[:200]})
                return self._json(200, out)
            with svc.lock:
                if E.get("exiting"):
                    return self._json(409, {"error": "episode finished", "reason": E.get("reason")})
                if self.path == "/submit":
                    if E.get("done"):
                        return self._json(409, {"error": "episode finished", "reason": E.get("reason")})
                    A = np.asarray(parts["actions"]["data"] if "actions" in parts else meta.get("actions", []), dtype=np.float64)
                    try:
                        out, blobs = svc.submit(meta, A)
                    except ValueError as exc:
                        return self._json(400, {"error": str(exc)})
                    except Exception as exc:  # noqa: BLE001
                        traceback.print_exc(); E["error"] = repr(exc); svc.log({"ev": "error", "error": repr(exc)}); svc.on_submit_error(exc)
                        return self._json(500, {"error": "simulator error", "detail": repr(exc)[:200]})
                else:
                    try:
                        out, blobs = svc.observe(meta)
                    except ValueError as exc:
                        return self._json(400, {"error": str(exc)})
                    except Exception as exc:  # noqa: BLE001
                        traceback.print_exc(); return self._json(500, {"error": "simulator error", "detail": repr(exc)[:200]})
            return self._rcb1(out, blobs)
    return H


def serve(svc: Service, port: int = 8000) -> None:
    """Check the spec, then serve forever (one request at a time, as every 2.x service)."""
    check_spec(svc.spec)
    HTTPServer(("0.0.0.0", port), make_handler(svc)).serve_forever()
