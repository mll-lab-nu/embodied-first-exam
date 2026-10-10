"""The tooling's replay CLI without Isaac: _load_traj, the video frame cap, and filming that fails at every stage
(writer cannot open, a frame fails mid-run, the encoder fails at close) never voiding the replay's result.
The real Session's video methods run on an object built without __init__ (no simulator), with a fake imageio writer."""
import argparse, contextlib, io, json, os, sys, tempfile, types
import numpy as np
sys.dont_write_bytecode = True
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))); bad = 0
def check(ok, what):
    global bad
    print("ok  " if ok else "FAIL", what); bad += not ok

class Writer:
    def __init__(self, mode): self.mode, self.n, self.closed = mode, 0, False
    def append_data(self, f):
        if self.mode == "frame3" and self.n == 3: raise BrokenPipeError("ffmpeg died")
        self.n += 1
    def close(self):
        self.closed = True
        if self.mode == "close": raise RuntimeError("encode failed")
FAKE = {"mode": "ok", "writer": None, "pngs": []}
def get_writer(path, **kw):
    if FAKE["mode"] == "open": raise OSError("cannot open writer")
    FAKE["writer"] = Writer(FAKE["mode"]); return FAKE["writer"]
v2 = types.ModuleType("imageio.v2"); v2.get_writer = get_writer; v2.imwrite = lambda p, img: FAKE["pngs"].append(p)
pkg = types.ModuleType("imageio"); pkg.v2 = v2; sys.modules["imageio"] = pkg; sys.modules["imageio.v2"] = v2

for bench, mod, dim in (("robolab", "rcb_robolab", 8), ("yamlab", "rcb_yamlab", 14)):
    sys.path.insert(0, os.path.join(ROOT, "scripts", bench, "shared"))
    M = __import__(mod)
    sys.path.pop(0)
    # ---- _load_traj
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "t.npz"); A = np.ones((5, dim), np.float32)
        np.savez(p, actions=A, task="fam", junk=np.array([{"a": 1}], dtype=object), meta=json.dumps({"x": 1}))
        t = M._load_traj(p)
        check(t["task"] == "fam" and np.array_equal(t["actions"], A) and "junk" not in t and "meta" in t, f"{bench} _load_traj skips an extra object entry")
        np.savez(p, actions=np.array([[{"a": 1}]], dtype=object), task="fam")
        try: M._load_traj(p); check(False, f"{bench} _load_traj object actions must raise")
        except ValueError: check(True, f"{bench} _load_traj object actions raises ValueError")
    # ---- the frame cap
    hz = M.CONTROL_HZ; real = max(1, hz // 15)
    check(M._video_every(100, 15) == real and M._video_every(M.MAX_VIDEO_FRAMES * real, 15) == real, f"{bench} video: real time up to {M.MAX_VIDEO_FRAMES * real} steps")
    e = M._video_every(100_000, 15); check(e > real and -(-100_000 // e) <= M.MAX_VIDEO_FRAMES, f"{bench} video: 100k steps -> every {e} ({-(-100_000 // e)} frames)")
    # ---- the real Session's video methods on a fake simulator
    class S(M.Session):
        def __init__(self): self._video = None; self.n_steps = 0; self.fail_frame = False
        def _video_frame(self):
            if self.fail_frame: raise RuntimeError("render failed")
            return np.zeros((4, 4, 3), np.uint8)
    for mode, want in (("ok", True), ("frame3", False), ("close", False)):
        FAKE.update(mode=mode, pngs=[]); s = S(); s.start_video("/nonexistent-dir-is-fine/v.mp4".replace("/nonexistent-dir-is-fine", tempfile.gettempdir()), fps=15, every=1)
        for i in range(10):
            s.n_steps += 1; s._video_add()                 # what step() does after env.step
        out = s.stop_video()
        check((out is not None) == want and s._video is None and FAKE["writer"].closed and (len(FAKE["pngs"]) == 1) == want,
              f"{bench} Session video, writer mode {mode}: stop_video() -> {out!r}, no exception")
    FAKE.update(mode="ok"); s = S(); s.start_video(os.path.join(tempfile.gettempdir(), "v.mp4")); s.fail_frame = True; s.n_steps += 1; s._video_add(); s._video_add()
    check(s._video["error"] is not None and s.stop_video() is None, f"{bench} Session video: a render failure stops the filming only")
    # ---- cmd_replay with a fake Session: the result line whatever the video does
    class Fake:
        instance_sha = "ii"; instance_matches = True; instance_exact = True
        def __init__(self, task, instance=None, strict=False, depth=False): self._video = None; self.n = 0; self._resets = 0; self.calls = []
        def reset(self): self.n = 0; self._resets += 1
        def start_video(self, path, fps=15, every=None):
            self.calls.append(("start", every))
            if FAKE["mode"] == "open": raise OSError("cannot open writer")
            self._video = {"every": every}
        def step(self, row): self.n += 1; return False
        def status(self): return {"success": True, "state_sha": "aa", "sim_steps": self.n}
        def replay(self, acts):
            self.reset()
            for a in acts: self.step(a)
            return self.status()
        def stop_video(self):
            self.calls.append(("stop",)); self._video = None
            if FAKE["mode"] == "stop_raises": raise RuntimeError("boom")
            return None if FAKE["mode"] == "stop_none" else "v.mp4"
        def close(self): pass
    M.Session = Fake
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "t.npz"); np.savez(p, actions=np.zeros((30, dim), np.float32), task="fam")
        for mode, video, want_ok in (("ok", True, True), ("open", True, False), ("stop_raises", True, False), ("stop_none", True, False), ("ok", False, None)):
            FAKE["mode"] = mode; buf = io.StringIO()
            a = argparse.Namespace(traj=p, task="fam", instance="x", strict=False, repeat=1, video=os.path.join(td, "v.mp4") if video else None, fps=15)
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()): M.cmd_replay(a)
                out = json.loads([l for l in buf.getvalue().splitlines() if l.startswith("{")][-1])
                check(out["replays"][0]["success"] is True and out["replays"][0]["sim_steps"] == 30 and out["video_ok"] is want_ok and out["n_actions"] == 30,
                      f"{bench} cmd_replay video mode {mode if video else 'none'}: result printed, video_ok {out['video_ok']}")
            except BaseException as exc:
                check(False, f"{bench} cmd_replay video mode {mode}: raised {exc!r}")
print("tooling units:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
