"""Synthetic test of the request checks of the LabUtopia, AutoBio and DexJoCo sim services: the checking functions are taken
from server.py's own source (ast), run without a simulator. A malformed field must raise ValueError (the layer's 400)
and nothing else (anything else is a 500 that ends the episode), before anything is executed."""
import ast, itertools, math, os, sys
import numpy as np
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, "scripts/eai_standard"))
import rcb_limited as L  # the real shared layer (depth_mode)
WANT = ("checked", "number", "note_of", "video_fps", "frames_ok", "cameras_of", "parse_submit", "parse_observe")
BAD = [None, True, False, [], [1], {}, {"a": 1}, "x", "0.02", "", float("nan"), float("inf"), -float("inf"), -1, 0, 0.5, 1, 7,
       10 ** 400, -10 ** 400, 1e308, [None], [["a"]], ["cam_a"], ["nope"], "cam_a", 5, 3.7, "mp4", "hold", "frames", "none", "last"]
FIELDS = ("type", "dt", "seconds", "video_fps", "cameras", "note", "interpolate", "video", "depth", "include_depth", "actions")
bad = 0
for bench, dim, types in (("labutopia", 9, ("joint_position", "joint_position_velocity")), ("autobio", 7, ("joint_position", "done")),
                          ("dexjoco", 23, ("ee_pose", "joint_position"))):   # DexJoCo: no frame limit per call (no frames_ok)
    path = os.path.join(ROOT, "scripts", bench, "shared/standard/server.py")
    tree = ast.parse(open(path).read())
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in WANT]
    assert {f.name for f in fns} == set(WANT) - ({"frames_ok"} if bench == "dexjoco" else set()), {f.name for f in fns}
    DT = 1 / 60 if bench == "labutopia" else 0.02 if bench == "dexjoco" else 0.002
    ns = {"math": math, "np": np, "L": L, "DT": DT, "PERIOD": "1/60 s", "MAX_CHUNK_S": 10.0, "MAX_WATCH_S": 30.0,
          "MAX_FPS": 30 if bench == "labutopia" else 50, "MAX_FRAMES": 300 if bench == "labutopia" else 3000,
          "CAMS": ["cam_a", "cam_b"], "DEFAULT_CAMS": ["cam_a"], "ND": 9, "NA": 7, "ADIM": 23, "SPEC": {"action_types": {"not_yet": ["ee_pose"]}}}
    exec(compile(ast.Module(body=fns, type_ignores=[]), path, "exec"), ns)
    ps, po = ns["parse_submit"], ns["parse_observe"]
    A = np.zeros((5, dim))
    def call(fn, *a):
        try:
            return "ok", fn(*a)
        except ValueError as exc:
            return "400", str(exc)
        except BaseException as exc:  # noqa: BLE001 -- what the layer would turn into a 500 that ends the episode
            return "500", repr(exc)
    errs = []
    def expect(what, got, want):
        if got[0] != want: errs.append(f"{what}: {got} (want {want})")
    # valid requests
    for t in types:
        expect(f"valid {t}", call(ps, {"type": t}, A if t != "joint_position_velocity" else np.zeros((5, 18))), "ok")
    expect("valid full", call(ps, {"type": "joint_position", "dt": DT * 3, "interpolate": "hold", "video": "none", "video_fps": 10,
                                   "cameras": ["cam_b"], "note": "n" * 2000, "depth": "last"}, A), "ok")
    assert call(ps, {"type": "joint_position", "note": "n" * 2000}, A)[1][-1] == "n" * 500
    expect("valid null fields = defaults", call(ps, {"type": "joint_position", "dt": None, "video_fps": None, "cameras": None, "note": None}, A), "ok")
    assert call(ps, {"type": "joint_position", "dt": None}, A)[1][1] == DT
    expect("valid observe", call(po, {}), "ok"); expect("valid observe 2", call(po, {"seconds": 2, "video": "mp4", "cameras": ["cam_a", "cam_b"]}), "ok")
    assert call(po, {"seconds": None})[1][2] == 0.0
    # specific rejections
    for what, meta in (("dt null string", {"dt": "0.02"}), ("dt list", {"dt": [0.02]}), ("dt nan", {"dt": float("nan")}), ("dt inf", {"dt": float("inf")}),
                       ("dt bool", {"dt": True}), ("dt huge int", {"dt": 10 ** 400}), ("dt not a multiple", {"dt": DT * 1.5}), ("dt zero", {"dt": 0}),
                       ("dt negative", {"dt": -DT}), ("dt > 0.5", {"dt": DT * round(0.6 / DT)}), ("note int", {"note": 5}), ("note dict", {"note": {"a": 1}}),
                       ("note list", {"note": ["a"]}), ("cameras str", {"cameras": "cam_a"}), ("cameras int", {"cameras": 5}),
                       ("cameras nested", {"cameras": [["cam_a"]]}), ("cameras unknown", {"cameras": ["nope"]}), ("cameras dict", {"cameras": {"cam_a": 1}}),
                       ("video_fps 0", {"video_fps": 0}), ("video_fps -1", {"video_fps": -1}), ("video_fps str", {"video_fps": "5"}), ("video_fps nan", {"video_fps": float("nan")}),
                       ("video list", {"video": ["mp4"]}), ("video dict", {"video": {}}), ("interpolate null", {"interpolate": None}), ("interpolate dict", {"interpolate": {}}),
                       ("depth int", {"depth": 3}), ("depth str", {"depth": "all"}), ("depth list", {"depth": ["last"]})):
        expect(f"submit {what}", call(ps, {"type": "joint_position", **meta}, A), "400")
    for what, meta in (("seconds str", {"seconds": "1"}), ("seconds list", {"seconds": [1]}), ("seconds nan", {"seconds": float("nan")}), ("seconds inf", {"seconds": float("inf")}),
                       ("seconds -1", {"seconds": -1}), ("seconds 31", {"seconds": 31}), ("seconds huge", {"seconds": 10 ** 400}), ("seconds dict", {"seconds": {}}),
                       ("cameras int", {"cameras": 5}), ("video_fps 0", {"video_fps": 0}), ("video list", {"video": []}), ("depth dict", {"depth": {"a": 1}})):
        expect(f"observe {what}", call(po, meta), "400")
    for what, meta, arr in (("type null", {}, A), ("type list", {"type": ["joint_position"]}, A), ("type dict", {"type": {}}, A), ("type other", {"type": "joint_velocity" if bench == "dexjoco" else "ee_pose"}, A),
                            ("rows 1-D", {"type": "joint_position"}, np.zeros(dim)), ("rows 0-D", {"type": "joint_position"}, np.asarray(np.nan)),
                            ("rows wrong width", {"type": "joint_position"}, np.zeros((5, dim + 1))), ("rows nan", {"type": "joint_position"}, np.full((5, dim), np.nan)),
                            ("rows inf", {"type": "joint_position"}, np.full((5, dim), np.inf)), ("rows 3-D", {"type": "joint_position"}, np.zeros((2, 5, dim))),
                            ("chunk too long", {"type": "joint_position", "dt": DT * round(0.5 / DT)}, np.zeros((40, dim)))):
        expect(f"submit {what}", call(ps, meta, arr), "400")
    if bench == "autobio":   # `done` checks its fields too, before it ends the episode
        for what, meta in (("done cameras int", {"cameras": 5}), ("done note int", {"note": 5}), ("done depth dict", {"depth": {}})):
            expect(f"submit {what}", call(ps, {"type": "done", **meta}, np.asarray([])), "400")
        expect("done ignores rows and dt", call(ps, {"type": "done", "dt": "x"}, np.asarray([])), "ok")
    # fuzz: every field x every bad value, alone and in pairs: a return or a ValueError, never anything else
    n = 0
    for f, v in itertools.product(FIELDS, BAD):
        for t in types + (None,):
            for fn, args in ((ps, ({"type": t, f: v} if f != "type" else {"type": v}, A)), (po, ({f: v},))):
                r = call(fn, *args); n += 1
                if r[0] == "500": errs.append(f"fuzz {fn.__name__} {f}={v!r} type={t}: {r[1]}")
    for (f1, v1), (f2, v2) in itertools.combinations(itertools.product(FIELDS[1:], BAD[::3]), 2):
        if f1 == f2: continue
        for fn, args in ((ps, ({"type": "joint_position", f1: v1, f2: v2}, A)), (po, ({f1: v1, f2: v2},))):
            r = call(fn, *args); n += 1
            if r[0] == "500": errs.append(f"fuzz {fn.__name__} {f1}={v1!r} {f2}={v2!r}: {r[1]}")
    print(("FAIL" if errs else "ok  "), bench, f"({n} fuzzed requests)", *errs[:20], sep="\n  " if errs else " "); bad += bool(errs)
print("ALL PASS" if not bad else f"{bad} FAILED"); sys.exit(bool(bad))
