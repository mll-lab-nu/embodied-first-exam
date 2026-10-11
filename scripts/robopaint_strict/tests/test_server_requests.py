"""Synthetic test of the request checks of the RoboPaint sim service (the standard tasks' environment/sim/server.py,
byte-identical in every pair): the checking functions are taken from server.py's own source (ast) and run without a
simulator. A malformed field must raise ValueError (the layer's 400) and nothing else (anything else is a 500 that ends
the episode), before anything is executed; null fields are the defaults. One call holds at most MAX_FRAMES images
(/spec max_frames_per_call; review R3 B-M2): a request over it is a ValueError too, the largest default request is
not, a camera named several times is one camera, and an ee_pose position too far for a float distance is a ValueError
(it was an OverflowError in the middle of the chunk, a 500 that ended the episode). Needs numpy:
    python3 scripts/robopaint_strict/tests/test_server_requests.py [repo root]"""
import ast, glob, itertools, math, os, re, sys, types
import numpy as np
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, "scripts/eai_standard"))
import rcb_limited as L  # the real shared layer (depth_mode)
WANT = ("checked", "number", "note_of", "video_fps", "tip_steps", "call_steps", "frames_ok", "parse_submit", "parse_observe")
BAD = [None, True, False, [], [1], {}, {"a": 1}, "x", "0.02", "", float("nan"), float("inf"), -float("inf"), -1, 0, 0.5, 1, 7,
       10 ** 400, -10 ** 400, 1e308, [None], [["a"]], ["canvas_cam"], ["nope"], "canvas_cam", 5, 3.7, "mp4", "hold", "frames", "none", "last"]
FIELDS = ("type", "dt", "seconds", "video_fps", "cameras", "note", "interpolate", "video", "depth", "include_depth")
paths = sorted(glob.glob(os.path.join(ROOT, "tasks/robopaint-*-standard/environment/sim/server.py")))
assert paths and len({open(p, "rb").read() for p in paths}) == 1, "the RoboPaint standard tasks share one server.py"
tree = ast.parse(open(paths[0]).read())
fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in WANT]
assert {f.name for f in fns} == set(WANT), {f.name for f in fns}
SRC = open(paths[0]).read()
MAX_FRAMES, DEPTH_FRAME = (int(re.search(rf"^{k} = (\d+)", SRC, re.M).group(1)) for k in ("MAX_FRAMES", "DEPTH_FRAME"))
E = {"done": False, "tip_target": None}       # the service's episode state, as far as the checks read it
ns = {"math": math, "np": np, "L": L, "CTRL_HZ": 20, "MAX_CHUNK_S": 10.0, "MAX_WATCH_S": 30.0, "MAX_VIDEO_FPS": 1000,
      "MAX_FRAMES": MAX_FRAMES, "DEPTH_FRAME": DEPTH_FRAME, "E": E, "M": types.SimpleNamespace(MAX_TIP_SPEED=0.25),
      "S": types.SimpleNamespace(tip_pose=lambda: (np.array([0.0, 0.0, 0.2]), np.array([1.0, 0, 0, 0]))),
      "VIDEOS": ("mp4", "frames", "both", "none"), "CAMS": ["canvas_cam", "practice_cam", "scene_cam", "side_cam"],
      "SPEC": {"action_types": {"not_yet": [], "joint_position": {"dim": 7}, "ee_pose": {"dim": 7}}}}
exec(compile(ast.Module(body=fns, type_ignores=[]), paths[0], "exec"), ns)
ps, po = ns["parse_submit"], ns["parse_observe"]
A = np.zeros((5, 7)); errs = []


def call(fn, *a):
    try:
        return "ok", fn(*a)
    except ValueError as exc:
        return "400", str(exc)
    except BaseException as exc:  # noqa: BLE001 -- what the layer would turn into a 500 that ends the episode
        return "500", repr(exc)


def expect(what, got, want):
    if got[0] != want: errs.append(f"{what}: {got} (want {want})")


J = {"type": "joint_position"}
for t in ("joint_position", "ee_pose"):
    expect(f"valid {t}", call(ps, {"type": t}, A), "ok")
expect("valid full", call(ps, {**J, "dt": 0.1, "interpolate": "hold", "video": "none", "video_fps": 30, "cameras": ["scene_cam"], "note": "n" * 2000, "depth": "last"}, A), "ok")
assert call(ps, {**J, "note": "n" * 2000}, A)[1][-1] == "n" * 500
r = call(ps, {**J, "dt": None, "video_fps": None, "cameras": None, "note": None}, A)
expect("null fields are the defaults", r, "ok"); assert r[1][1] == 0.05 and r[1][4] == 5 and r[1][6] == "", r
expect("valid observe", call(po, {}), "ok"); expect("valid observe 2", call(po, {"seconds": 2, "video": "mp4", "cameras": ["canvas_cam"]}), "ok")
assert call(po, {"seconds": None, "video_fps": None})[1][1:3] == (0.0, 5)
expect("unknown camera names fall back to all cameras (unchanged)", call(ps, {**J, "cameras": ["nope"]}, A), "ok")
for what, meta in (("dt string", {"dt": "0.1"}), ("dt list", {"dt": [0.1]}), ("dt nan", {"dt": float("nan")}), ("dt inf", {"dt": float("inf")}), ("dt bool", {"dt": True}),
                   ("dt huge int", {"dt": 10 ** 400}), ("dt not a multiple", {"dt": 0.075}), ("dt zero", {"dt": 0}), ("dt negative", {"dt": -0.05}), ("dt > 0.5", {"dt": 0.55}),
                   ("note int", {"note": 5}), ("note zero", {"note": 0}), ("note dict", {"note": {"a": 1}}), ("note list", {"note": ["a"]}),
                   ("video_fps -1", {"video_fps": -1}), ("video_fps str", {"video_fps": "5"}), ("video_fps nan", {"video_fps": float("nan")}), ("video_fps huge", {"video_fps": 10 ** 400}),
                   ("video_fps 1e12", {"video_fps": 1e12}), ("video list", {"video": ["mp4"]}), ("video dict", {"video": {}}), ("interpolate dict", {"interpolate": {}}),
                   ("depth int", {"depth": 3}), ("depth str", {"depth": "all"}), ("depth list", {"depth": ["last"]})):
    expect(f"submit {what}", call(ps, {**J, **meta}, A), "400")
for what, meta in (("seconds str", {"seconds": "1"}), ("seconds list", {"seconds": [1]}), ("seconds nan", {"seconds": float("nan")}), ("seconds inf", {"seconds": float("inf")}),
                   ("seconds -1", {"seconds": -1}), ("seconds 31", {"seconds": 31}), ("seconds huge", {"seconds": 10 ** 400}), ("seconds dict", {"seconds": {}}),
                   ("video_fps -1", {"video_fps": -1}), ("video list", {"video": []}), ("depth dict", {"depth": {"a": 1}})):
    expect(f"observe {what}", call(po, meta), "400")
for what, meta, arr in (("type null", {}, A), ("type list", {"type": ["joint_position"]}, A), ("type dict", {"type": {}}, A), ("type other", {"type": "joint_velocity"}, A),
                        ("rows 1-D", J, np.zeros(7)), ("rows 0-D", J, np.asarray(np.nan)), ("rows wrong width", J, np.zeros((5, 8))), ("rows nan", J, np.full((5, 7), np.nan)),
                        ("rows 3-D", J, np.zeros((2, 5, 7))), ("chunk too long", {**J, "dt": 0.5}, np.zeros((40, 7))), ("ee_pose 401 rows", {"type": "ee_pose"}, np.zeros((401, 7)))):
    expect(f"submit {what}", call(ps, meta, arr), "400")
# ---- the call's image budget (cameras x frames; a frame with per-frame depth counts DEPTH_FRAME images)
assert (MAX_FRAMES, DEPTH_FRAME) == (640, 4), (MAX_FRAMES, DEPTH_FRAME)
assert f'"max_frames_per_call": MAX_FRAMES' in SRC, "/spec states the limit"
for p in paths:      # and every instruction states the numbers the service enforces
    text = open(os.path.join(os.path.dirname(p), "..", "..", "instruction.md")).read()
    assert f"at most {MAX_FRAMES} images" in text and f"counts {DEPTH_FRAME})" in " ".join(text.split()), p
ALL = {"seconds": 30}; ONE = ["canvas_cam"]
for what, fn, args, want in (
        ("the longest default watch, every camera (152 frames x 4 = 608 images)", po, (ALL,), "ok"),
        ("the longest watch at the full rate, one camera (602)", po, ({**ALL, "video_fps": 20, "cameras": ONE},), "ok"),
        ("the same, the camera named 5 times", po, ({**ALL, "video_fps": 20, "cameras": ONE * 5},), "ok"),
        ("the longest watch at the full rate, every camera (602 x 4)", po, ({**ALL, "video_fps": 20},), "400"),
        ("the longest watch at the full rate, two cameras (602 x 2)", po, ({**ALL, "video_fps": 20, "cameras": ["canvas_cam", "side_cam"]},), "400"),
        ("the longest default watch with per-frame depth (152 x 4 x 4)", po, ({**ALL, "depth": "frames"},), "400"),
        ("the same with include_depth", po, ({**ALL, "include_depth": True},), "400"),
        ("the longest default watch with the last frame's depth", po, ({**ALL, "depth": "last"},), "ok"),
        ("the longest default chunk, every camera (52 x 4)", ps, (J, np.zeros((200, 7))), "ok"),
        ("the longest chunk at the full rate, every camera (202 x 4)", ps, ({**J, "video_fps": 20}, np.zeros((200, 7))), "400"),
        ("the longest chunk at the full rate, three cameras (202 x 3)", ps, ({**J, "video_fps": 20, "cameras": ["canvas_cam", "scene_cam", "side_cam"]}, np.zeros((200, 7))), "ok"),
        ("ee_pose, a target 0.5 m away (41 control steps)", ps, ({"type": "ee_pose"}, np.array([[0.5, 0, 0.2, 1, 0, 0, 0]])), "ok"),
        ("ee_pose, millimetres sent as metres (x = 400: 32001 control steps)", ps, ({"type": "ee_pose", "cameras": ONE, "video_fps": 1}, np.array([[400, 0, 0.05, 1, 0, 0, 0.]])), "400"),
        ("ee_pose, x = 1e30", ps, ({"type": "ee_pose", "cameras": ONE, "video_fps": 1}, np.array([[1e30, 0, 0.05, 1, 0, 0, 0]])), "400"),
        ("ee_pose, x = 1e200 (no float distance)", ps, ({"type": "ee_pose"}, np.array([[1e200, 0, 0.05, 1, 0, 0, 0]])), "400"),
        ("ee_pose, +-1e308 in two rows", ps, ({"type": "ee_pose"}, np.array([[1e308, 0, 0, 1, 0, 0, 0], [-1e308, 0, 0, 1, 0, 0, 0]])), "400")):
    expect(what, call(fn, *args), want)
assert call(po, {**ALL, "video_fps": 20, "cameras": ONE * 5})[1][0] == ONE and call(ps, {**J, "cameras": ["side_cam", "canvas_cam", "side_cam"]}, A)[1][3] == ["side_cam", "canvas_cam"]
assert "max_frames_per_call = 640" in call(po, {**ALL, "video_fps": 20})[1] and "32001 control steps" in call(ps, {"type": "ee_pose", "cameras": ONE, "video_fps": 1}, np.array([[400, 0, 0.05, 1, 0, 0, 0.]]))[1]
E["tip_target"] = (np.array([0.5, 0.0, 0.2]), None)      # ee_pose rows start at the last commanded target, not at the measured tip
assert ns["call_steps"]("ee_pose", np.array([[0.5, 0, 0.2, 1, 0, 0, 0], [0.5, 0.25, 0.2, 1, 0, 0, 0]]), 0.05) == 1 + 20
E.update(done=True, tip_target=None)                     # after the episode an /observe is one frame, whatever it asks for
expect("a watch after the episode has ended", call(po, {**ALL, "video_fps": 20}), "ok"); E["done"] = False
n = 0   # fuzz: every field x every bad value, alone and in pairs: a return or a ValueError, never anything else
for f, v in itertools.product(FIELDS, BAD):
    for t in ("joint_position", "ee_pose", None):
        for fn, args in ((ps, ({"type": t, f: v} if f != "type" else {"type": v}, A)), (po, ({f: v},))):
            r = call(fn, *args); n += 1
            if r[0] == "500": errs.append(f"fuzz {fn.__name__} {f}={v!r} type={t}: {r[1]}")
for (f1, v1), (f2, v2) in itertools.combinations(itertools.product(FIELDS[1:], BAD[::3]), 2):
    if f1 == f2: continue
    for fn, args in ((ps, ({**J, f1: v1, f2: v2}, A)), (po, ({f1: v1, f2: v2},))):
        r = call(fn, *args); n += 1
        if r[0] == "500": errs.append(f"fuzz {fn.__name__} {f1}={v1!r} {f2}={v2!r}: {r[1]}")
for e in errs[:40]: print("FAIL", e)
print(f"{'FAIL' if errs else 'ok'} robopaint ({n} fuzzed requests, {len(paths)} identical server.py)")
sys.exit(1 if errs else 0)
