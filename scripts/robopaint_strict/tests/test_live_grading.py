"""Synthetic test of the RoboPaint standard verdict (board 0151: graded by the live episode, no grading replay). No simulator:
  1. the service's end of the episode, the functions `numbers`, `dump`, `render` and `_end_from_signal` taken from the shipped
     environment/sim/server.py (byte-identical in every standard pair) and run on a stub Session: the live sheet's score is
     the verdict (success 1 / failure 0), written to final.json before the video; the one render pass renders the recorded
     rows once; nothing is replayed (the stub counts replays); a failed video or evidence picture keeps the verdict; a live sheet that cannot be
     scored is grade_error (infra after a normal end, the agent's 0 after its own simulator error);
  2. tests/grade.py on synthetic final.json files (no final.json, unfinalized, give-ups, an old replay-rule record);
  3. environment/sim/finalize.sh with the real rcb_limited.py: a verdict with its video is kept; a verdict whose video ran out
     of time is kept (video lost); no verdict -> infrastructure.
Needs numpy and sh (Pillow is stood in for when missing): python3 scripts/robopaint_strict/tests/test_live_grading.py [repo root]"""
import ast, glob, json, math, os, shutil, subprocess, sys, tempfile, threading, time, traceback, types
import numpy as np
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, "scripts/eai_standard"))
import rcb_limited as L  # noqa: E402  the real shared layer (_write_json, final_verdict)
try:
    import PIL.Image  # noqa: F401  the service saves the live sheets with Pillow
except ImportError:      # the CI job installs numpy and requests only: a stand-in that writes the array's bytes
    _img = types.ModuleType("PIL.Image")
    _img.fromarray = lambda a: types.SimpleNamespace(save=lambda path, *x, **k: open(path, "wb").write(np.asarray(a).tobytes()))
    sys.modules["PIL"] = types.ModuleType("PIL"); sys.modules["PIL"].Image = _img; sys.modules["PIL.Image"] = _img
paths = sorted(glob.glob(os.path.join(ROOT, "tasks/robopaint-*-standard/environment/sim/server.py")))
assert paths and len({open(p, "rb").read() for p in paths}) == 1, "the RoboPaint standard tasks share one server.py"
SIM = os.path.dirname(paths[0]); TASK = os.path.dirname(os.path.dirname(SIM))
SRC = open(paths[0]).read()
WANT = ("numbers", "dump", "render", "_end_from_signal")
fns = [n for n in ast.parse(SRC).body if isinstance(n, ast.FunctionDef) and n.name in WANT]
assert {f.name for f in fns} == set(WANT), {f.name for f in fns}
assert 'M = importlib.import_module(os.path.splitext(os.path.basename(os.environ.get("RCB_TOOL")' in SRC, "the service scores with RCB_TOOL's module"
assert "RCB_TOOL: /srv/rcb_brush_strict.py" in open(os.path.join(TASK, "environment/docker-compose.yaml")).read()
errs = []; n = 0
TMP = tempfile.mkdtemp(prefix="rp_live_")


def expect(what, got, want):
    global n
    n += 1
    if got != want:
        errs.append(f"{what}: got {got!r}, want {want!r}")


class Exited(Exception):
    pass


class FakeOS(types.ModuleType):
    def __getattr__(self, k):
        return getattr(os, k)

    @staticmethod
    def _exit(code):
        raise Exited(code)


class Painter:
    def __init__(self): self.finished = 0
    def finish(self): self.finished += 1


class Stub:
    """The live Session at the end of an episode: `score` = what status() reports (the strict scorer's metrics)."""
    def __init__(self, score=None, score_raises=False, video_raises=False, canvas_raises=False):
        self.painter = Painter(); self.inst = {"target": {"success": {"de_mean": 5.5, "max_strokes": 10, "max_path_mm": 100.0}}}
        self.instance_exact = True; self.score_ = score or {}; self.score_raises = score_raises; self.video_raises = video_raises
        self.canvas_raises = canvas_raises
        self.replays = 0; self.renders = []; self.rows = np.zeros((25, 7), np.float32)
    def record_stop(self): return self.rows
    def save_trajectory(self, acts, path, meta=None): np.savez(path, actions=acts)
    def status(self):
        if self.score_raises: raise RuntimeError("scorer: truth image unreadable (stub)")
        return {**self.score_, "state_sha": "abc123", "sim_steps": 25, "loaded": True, "pen_down": False}
    def canvas(self, sheet):
        if self.canvas_raises: raise OSError("no space left on device (stub)")
        return np.zeros((8, 8, 3), np.uint8)
    def replay(self, acts): self.replays += 1; return self.status()
    def render_video(self, acts, path, every=2, fps=10):
        self.renders.append((len(acts), every, fps))
        if self.video_raises: raise RuntimeError("cannot create buffer (stub)")
        open(path, "wb").write(b"stub"); return {}


def episode(name, stub, reason=None):
    data = os.path.join(TMP, name); os.makedirs(data)
    E = {"step": 3, "calls": 4, "done": reason is not None, "reason": reason, "t0": time.time() - 5, "t_end": None,
         "episode_control_steps": 25}
    events = []
    ns = {"np": np, "json": json, "math": math, "time": time, "traceback": traceback, "sys": sys, "os": FakeOS("os"), "L": L,
          "DATA": data, "E": E, "S": stub, "LOCK": threading.Lock(), "TASK": "t", "PROTOCOL": L.PROTOCOL, "SUBSTEPS": 5,
          "M": types.SimpleNamespace(MAX_VIDEO_FRAMES=600), "log": events.append,
          "EP": types.SimpleNamespace(final_fields=lambda: {"sim_startups": 1, "resumes": 0})}
    def finish(r):
        if E["done"]: return
        E.update(done=True, reason=r, t_end=time.time())
    ns["finish"] = finish
    exec(compile(ast.Module(body=fns, type_ignores=[]), paths[0], "exec"), ns)
    order = []
    real_write = L._write_json
    try:
        L._write_json = lambda p, o: (order.append((o.get("graded_by"), o.get("video_pending"), stub.renders[:])), real_write(p, o))[1]
        ns["_end_from_signal"]()
    except Exited:
        pass
    finally:
        L._write_json = real_write
    return data, json.load(open(os.path.join(data, "final.json"))), order, events


def grade(data):
    log = data + ".verifier"; shutil.rmtree(log, ignore_errors=True)
    r = subprocess.run([sys.executable, os.path.join(TASK, "tests/grade.py")], capture_output=True, text=True,
                       env={**os.environ, "RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log})
    assert r.returncode == 0, r.stderr
    out = json.load(open(os.path.join(log, "reward.json")))
    assert open(os.path.join(log, "reward.txt")).read().strip() == str(out["success"]), out
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in out.values()), out
    assert "replay_success" not in out and "deterministic" not in out and out["replays"] == 0, out
    return out


GOOD = {"success": 1.0, "final_reward": 0.81, "image_success": 1.0, "strict_ok": 1.0, "path_mm": 50.0}
BAD = {"success": 0.0, "final_reward": 0.31, "image_success": 1.0, "strict_ok": 0.0, "path_mm": 250.0}
try:
    # 1a. a live success: the verdict first, then one render of the recorded rows, nothing replayed
    st = Stub(GOOD); data, d, order, ev = episode("success", st)
    expect("success: final.json", (d["success"], d["live_success"], d["graded_by"], d["replays"], d["finalized"], d["video_done"], d["video_pending"], d["video"]),
           (True, True, "live", 0, True, True, False, True))
    expect("success: the episode was ended (timeout) and the stroke committed", (d["reason"], st.painter.finished), ("timeout", 1))
    expect("success: the verdict is on disk before the video renders", order[0], ("live", True, []))
    expect("success: one render pass of the 25 recorded rows, no replay", (st.renders, st.replays), ([(25, 2, 10)], 0))
    expect("success: metrics from the live score", (d["metrics"]["final_reward"], d["metrics"]["strict_ok"], d["live_sha"]), (0.81, 1.0, "abc123"))
    expect("success: no replay fields", [k for k in ("replay_success", "deterministic", "live_matches_replay", "gpu_lost") if k in d], [])
    expect("success: the deliverable", os.path.exists(os.path.join(data, "trajectory.npz")), True)
    out = grade(data)
    expect("success: reward", (out["success"], out["live_success"], out["graded_by_live"], out["infra_error"], out["final_reward"], out["strict_ok"]),
           (1, 1, 1, 0, 0.81, 1.0))
    # 1b. a live failure (a process rule fails): 0, not infra
    st = Stub(BAD); data, d, _, _ = episode("failure", st)
    out = grade(data)
    expect("failure: reward", (d["success"], out["success"], out["infra_error"], out["grader_error"], out["strict_ok"]), (False, 0, 0, 0, 0.0))
    # 1c. a failed video keeps the verdict
    st = Stub(GOOD, video_raises=True); data, d, _, _ = episode("video_fail", st)
    out = grade(data)
    expect("video failure: final.json", (d["success"], d["video"], d["video_done"], "video_error" in d), (True, False, True, True))
    expect("video failure: reward", (out["success"], out["infra_error"], out["video_rendered"]), (1, 0, 0))
    # 1c'. an evidence picture that cannot be saved never touches the computed score
    st = Stub(GOOD, canvas_raises=True); data, d, _, _ = episode("canvas_fail", st)
    out = grade(data)
    expect("canvas failure: the score stands", (d["success"], "grade_error" in d, "canvas_error" in d, out["success"], out["infra_error"]),
           (True, False, True, 1, 0))
    # 1d. the live sheet cannot be scored: infra after a normal end, the agent's 0 after its own simulator error
    st = Stub(GOOD, score_raises=True); data, d, _, _ = episode("score_error", st)
    out = grade(data)
    expect("score error: reward", (d.get("grade_error"), out["success"], out["infra_error"], out["grader_error"]), (True, 0, 1, 1))
    st = Stub(GOOD, score_raises=True); data, d, _, _ = episode("score_error_sim", st, reason="error")
    out = grade(data)
    expect("score error after a sim error: reward", (out["success"], out["infra_error"], out["sim_error"]), (0, 0, 1))

    # 2. the grader on synthetic records
    def synth(name, fin):
        dd = os.path.join(TMP, name); os.makedirs(dd)
        if fin is not None:
            open(os.path.join(dd, "final.json"), "w").write(fin if isinstance(fin, str) else json.dumps(fin))
        return grade(dd)
    out = synth("none", None); expect("no final.json", (out["success"], out["infra_error"], out["missing_log"]), (0, 1, 1))
    out = synth("corrupt", '{"success": tr'); expect("unreadable", (out["success"], out["infra_error"], out["grader_error"]), (0, 1, 1))
    out = synth("unfinalized", {"graded_by": "live", "success": True, "live_success": True, "finalized": False})
    expect("unfinalized", (out["success"], out["infra_error"]), (0, 1))
    out = synth("crashed", {"finalized": True, "gave_up": True, "reason": "sim_crashed", "success": False, "infra_error": 1})
    expect("give-up after crashes between calls", (out["success"], out["infra_error"]), (0, 1))
    out = synth("crashed_on_call", {"finalized": True, "gave_up": True, "reason": "sim_crashed_on_call", "success": False})
    expect("give-up after crashes inside the agent's calls", (out["success"], out["infra_error"]), (0, 0))
    out = synth("mismatch", {"finalized": True, "gave_up": True, "reason": "instance_mismatch: instance sha a != expected b", "success": False, "infra_error": 1})
    expect("instance mismatch at the start", (out["success"], out["infra_error"], out["instance_mismatch"]), (0, 1, 1))
    out = synth("old", {"finalized": True, "replay_success": True, "deterministic": True, "live": {"success": 1.0}})
    expect("an old replay-rule record is no live verdict", (out["success"], out["infra_error"]), (0, 1))

    # 3. finalize.sh with the real rcb_limited.py (its paths pointed at copies, a short timeout)
    hook = os.path.join(TMP, "finalize.sh"); lim = os.path.join(TMP, "rcb_limited.py")
    shutil.copy(os.path.join(SIM, "rcb_limited.py"), lim); shutil.copy(os.path.join(SIM, "rcb1.py"), os.path.join(TMP, "rcb1.py"))
    open(hook, "w").write(open(os.path.join(SIM, "finalize.sh")).read().replace("/srv/rcb_limited.py", lim).replace("--timeout 2700", "--timeout 3"))
    def run_hook(name, fin):
        dd = os.path.join(TMP, "hook_" + name); os.makedirs(dd)
        if fin is not None: json.dump(fin, open(os.path.join(dd, "final.json"), "w"))
        r = subprocess.run(["sh", hook], capture_output=True, text=True, env={**os.environ, "RCB_DATA": dd, "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")},
                           timeout=60)   # the hook runs `python`: this interpreter
        return r.returncode, json.load(open(os.path.join(dd, "final.json")))
    ok_fin = {"finalized": True, "graded_by": "live", "replays": 0, "success": True, "live_success": True, "video_done": True, "video_pending": False}
    rc, fin = run_hook("done", ok_fin); expect("hook: a verdict with its video is kept as written", (rc, fin), (0, ok_fin))
    rc, fin = run_hook("video_late", {**ok_fin, "video_done": False, "video_pending": True})
    expect("hook: the video ran out of time, the verdict stands", (rc, fin["success"], fin["video_done"], fin["video_pending"], "video_error" in fin, fin.get("infra_error")),
           (0, True, True, False, True, None))
    rc, fin = run_hook("nothing", None)
    expect("hook: no verdict -> infrastructure", (rc, fin.get("infra_error"), fin.get("finalized"), fin.get("graded_by")), (0, 1, True, None))
finally:
    shutil.rmtree(TMP, ignore_errors=True)
for e in errs: print("FAIL", e)
print(f"{'FAIL' if errs else 'ok'} robopaint standard service, live verdict: {n} checks, {len(errs)} failed")
sys.exit(1 if errs else 0)
