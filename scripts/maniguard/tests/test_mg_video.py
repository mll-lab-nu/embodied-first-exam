"""ManiGuard tooling: the video never changes a replay's result, and its memory is bounded (no Isaac: a stub Session)."""
import io, json, os, subprocess, sys, tempfile, contextlib
import numpy as np
REPO = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.join(REPO, "scripts/maniguard/shared"))
import rcb_maniguard as M

class Fake(M.Session):
    """The real video / replay-CLI code on a counter instead of a simulator."""
    fail_frame_at = None          # _video_frame raises from this step on
    def __init__(self, task, instance=None, strict=False, **kw):
        self.task = task; self.steps = 0; self.done = False; self.reason = None
        self._video = None; self.video_info = {}; self._resets = 0
        self.instance_sha = "abc"; self.instance_matches = True; self.instance_exact = True
    def camera_names(self): return ["cam_left", "wrist"]
    def _video_frame(self):
        if Fake.fail_frame_at is not None and self.steps >= Fake.fail_frame_at:
            raise RuntimeError("camera broke")
        f = np.zeros((256, 512, 3), np.uint8); f[:, : (self.steps % 512)] = 200
        return f
    def step(self, a):
        self.steps += 1
        if self.steps >= 40: self.done = True; self.reason = "success"
        # the tooling's own hook, copied from _after_step
        if self._video is not None and (self.steps % self._video["every"] == 0 or self.done):
            self._video_grab()
        return self.done
    def status(self): return {"success": self.done, "task_success": self.done, "sim_steps": self.steps, "reason": self.reason, "state_sha": f"s{self.steps}"}
    def state_sha(self): return f"s{self.steps}"
    def close(self): pass

def run_cli(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        old = sys.argv; sys.argv = ["rcb_maniguard.py"] + args
        try: M.main()
        finally: sys.argv = old
    return json.loads([l for l in buf.getvalue().splitlines() if l.startswith("{")][-1])

M.Session = Fake
M._slog = lambda *a, **k: None
td = tempfile.mkdtemp()
traj = os.path.join(td, "t.npz")
np.savez(traj, actions=np.zeros((100, 8), np.float32), task="fam/task_0001", extra=np.array([{"a": 1}], dtype=object))   # an extra pickled entry
base = ["replay", "--task", "fam/task_0001", "--instance", td, "--traj", traj]
ref = run_cli(base)
assert ref["replays"][0]["success"] and ref["replays"][0]["sim_steps"] == 40 and ref["video"] is None, ref
print("ok replay without video (and an extra object entry in the npz is ignored):", ref["replays"][0])

# 1. a good video: same verdict, file complete, last frame written
v = os.path.join(td, "ok", "replay.mp4")
r = run_cli(base + ["--video", v])
assert r["replays"] == ref["replays"] and r["video"] == v and os.path.getsize(v) > 0 and r["video_every"] == 1 and r["video_error"] is None, r
assert os.path.isfile(os.path.join(td, "ok", "replay.last.png")) and not os.path.exists(os.path.join(td, "ok", "replay.part.mp4"))
n = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", v], capture_output=True, text=True).stdout.strip()
assert int(n.split(",")[0]) == 41, n      # the start frame + one per step
print("ok filmed replay: same verdict, playable mp4 with", n, "frames")

# 2. the camera fails mid-episode: same verdict, no video, the error reported
Fake.fail_frame_at = 10
v2 = os.path.join(td, "cam", "replay.mp4")
r = run_cli(base + ["--video", v2])
assert r["replays"] == ref["replays"] and r["video"] is None and "camera broke" in r["video_error"] and not os.path.exists(v2) and "error" not in r, r
print("ok camera failure while filming: verdict unchanged, video_error =", r["video_error"])
Fake.fail_frame_at = 0                     # fails at the very first frame (start_video)
r = run_cli(base + ["--video", v2])
assert r["replays"] == ref["replays"] and r["video"] is None and "error" not in r, r
Fake.fail_frame_at = None

# 3. the encoder / the file system fails at the end: same verdict, no half-written file under the final name
blocker = os.path.join(td, "blocker"); open(blocker, "w").write("x")
v3 = os.path.join(blocker, "sub", "replay.mp4")      # its parent cannot be created
r = run_cli(base + ["--video", v3])
assert r["replays"] == ref["replays"] and r["video"] is None and r["video_error"], r
print("ok unwritable video path: verdict unchanged, video_error =", r["video_error"][:60])
import imageio.v2 as iio
real = iio.get_writer
class Boom:
    def __init__(self, *a, **k): self.n = 0
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def append_data(self, f):
        self.n += 1
        if self.n > 5: raise BrokenPipeError("ffmpeg died")
iio.get_writer = Boom
v4 = os.path.join(td, "enc", "replay.mp4")
r = run_cli(base + ["--video", v4])
iio.get_writer = real
assert r["replays"] == ref["replays"] and r["video"] is None and "ffmpeg died" in r["video_error"] and not os.path.exists(v4), r
print("ok encoder failure: verdict unchanged, nothing under the final name")

# 4. bounded memory: 20,000 filmed steps keep at most VIDEO_MAX_FRAMES frames, evenly thinned
s = Fake("x"); s.start_video(os.path.join(td, "long.mp4"))
peak = 0
for i in range(20000):
    s.steps += 1
    if s.steps % s._video["every"] == 0: s._video_grab()          # _after_step's rule
    peak = max(peak, len(s._video["frames"]))
assert peak <= M.VIDEO_MAX_FRAMES + 1 and s._video["every"] == 8, (peak, s._video["every"])
size = sum(len(f) for f in s._video["frames"])
print(f"ok 20,000 filmed steps: at most {peak} frames kept, stride {s._video['every']}, {size / 1e6:.1f} MB of JPEG in memory")
s._video["frames"] = s._video["frames"][:50]; p = s.stop_video()
assert p and s.video_info["every"] == 8, s.video_info

# 5. render_video (what the agent calls) reports the stride and still returns the status
s = Fake("x"); out = s.render_video(np.zeros((60, 8), np.float32), os.path.join(td, "rv.mp4"))
assert out["success"] and out["video"] == os.path.join(td, "rv.mp4") and out["video_every"] == 1 and out["video_error"] is None, out
Fake.fail_frame_at = 5; s = Fake("x"); out = s.render_video(np.zeros((60, 8), np.float32), os.path.join(td, "rv2.mp4")); Fake.fail_frame_at = None
assert out["success"] and out["video"] is None and out["video_error"], out
print("ok render_video: status + video / video_every / video_error")
print("all video tests passed")
