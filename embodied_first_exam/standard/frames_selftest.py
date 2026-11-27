#!/usr/bin/env python3
"""The per-call image budget and the response build of the shared layers (PROTOCOL §3 "Images per call"), on
toy simulators (numpy only, no image, a few seconds):

  - rcb1.frames_part() gives the header and bytes of array_part(np.stack(...)) (dtype promotion, empty, shape errors),
    rcb1.size() the length of encode() before it is built, and encode() empties the frame lists it writes;
  - the shared layer (rcb_limited): under the servers' tick pattern a Recorder captures exactly frames_per_call() at its stride;
    check_frames accepts a call at the budget and refuses one image over it; Recorder(max_images=...) stops filming at
    the budget, keeps the last frame and counts the rest in `skipped`; depth is kept as it is sent (uint16 mm,
    float16), never more bytes than an RGB frame, and compressed only while it fits in the room the rest of the
    response leaves (same zlib bytes; compression stops once its output passes it, and the depth is dropped);
  - the sidecar layer (every distinct rcb_service.py, the abc-sim copy included): the real capture count under the service's
    pattern; a call at the budget is accepted, one image over refused, at the real stride;
  - the realtime layer (rcb_realtime): /observe never waits (seconds > 0: 400); an answer built but not sent counts against
    max_frames_per_call, at most MAX_UNSENT_BODIES such answers wait, and a submit or an /observe now is never refused
    for its images (answered without them, meta frames_skipped); with the simulator thread's recorder an /observe is a
    read of its ring, at most MAX_UNSENT_BODIES with images at a time.
"""
import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
STD = ROOT / "embodied_first_exam/standard"
sys.path.insert(0, str(STD))
import rcb1  # noqa: E402
import rcb_limited as L  # noqa: E402

fails: list[str] = []


def check(cond, what):
    if not cond:
        fails.append(what)
        print("FAIL", what)


def refused(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


# ---------------------------------------------------------------- rcb1
rng = np.random.default_rng(0)
for arrays in ([rng.integers(0, 255, (4, 5, 3), dtype=np.uint8) for _ in range(6)],
               [rng.random((3, 2)).astype(np.float16) for _ in range(3)],
               [np.zeros((2, 2), np.float16), np.ones((2, 2), np.float32)]):
    ref = rcb1.array_part("frames/c", np.stack(arrays))
    lazy = rcb1.frames_part("frames/c", list(arrays))
    meta = {"n": 1}
    body = rcb1.encode(meta, [lazy])
    check(len(lazy[2]) == len(ref[2]) and lazy[3] == ref[3], f"frames_part header {lazy[3]} != {ref[3]}")
    check(bytes(body) == rcb1.encode(meta, [ref]), f"frames_part bytes differ ({ref[3]})")
    check(rcb1.size(meta, [ref]) == len(body), "rcb1.size != len(encode)")
    check(lazy[2].arrays == [], "encode() did not empty the frame list")
for arrays in ([np.zeros((0, 4, 3), np.uint8) for _ in range(3)],                     # zero-size frames
               [np.arange(6, dtype=">u2").reshape(2, 3) for _ in range(2)],              # big-endian: native, as np.stack
               [np.arange(6, dtype=">f4").reshape(2, 3), np.ones((2, 3), "<f4")]):
    ref = rcb1.array_part("frames/c", np.stack(arrays))
    lazy = rcb1.frames_part("frames/c", list(arrays))
    check(lazy[3] == ref[3] and bytes(rcb1.encode({}, [lazy])) == rcb1.encode({}, [ref]),
          f"frames_part differs from np.stack for {[str(a.dtype) for a in arrays]} {arrays[0].shape}")
check(rcb1.frames_part("f", [], empty=np.zeros((0, 1, 1, 3), np.uint8))[3]["shape"] == [0, 1, 1, 3], "empty frames_part")
check(refused(lambda: rcb1.frames_part("f", [])) and refused(lambda: rcb1.frames_part("f", [np.zeros(2), np.zeros(3)])),
      "frames_part: no arrays / unequal shapes must raise as np.stack does")


# ---------------------------------------------------------------- shared layer: count at the stride, the budget, max_images
def grab(cams, want):
    return ({c: np.full((6, 8, 3), 7, np.uint8) for c in cams},
            {c: np.full((6, 8), 1.25, np.float32) for c in cams} if want else {})


def recorder(cams, every, depth="none", max_images=None):
    k = [0]
    rec = L.Recorder(cams, every, grab, lambda: np.zeros(3, np.float32), lambda cs: {c: np.eye(3, 4) for c in cs},
                     lambda: k[0], depth=depth, clock_hz=50, max_images=max_images)
    return rec, k


def run_call(rec, k, steps):
    rec.tick(force=True)                 # the servers' pattern: the forced first frame, a tick per control step, the
    for _ in range(steps):               # forced last frame after the last step
        k[0] += 1
        rec.tick()
    rec.tick(force=True, last=True)
    return len(rec.steps)


for steps in (0, 1, 2, 9, 10, 11, 49, 50, 51, 150, 1501):
    for every in (1, 2, 3, 7, 25):
        rec, k = recorder(["a"], every)
        n = run_call(rec, k, steps)
        check(n == L.frames_per_call(steps, every), f"shared: {n} captures != frames_per_call({steps}, {every})")
        for per_frame, depth in ((1, "none"), (2, "frames")):
            for budget in (2, 3, 10, 2 * L.frames_per_call(steps, every) * per_frame,
                           L.frames_per_call(steps, every) * per_frame - 1):
                if budget < 2 * per_frame:
                    continue
                rec, k = recorder(["a"], every, depth=depth, max_images=budget)
                n = run_call(rec, k, steps)
                check(n + rec.skipped == L.frames_per_call(steps, every) and n * per_frame <= max(budget, 2 * per_frame)
                      and rec.steps[-1] == steps,
                      f"shared max_images {budget}: {n} taken + {rec.skipped} skipped, last step {rec.steps[-1]} of {steps}")
# fps 24 at 50 Hz is a stride of 2 (25 frames a second): 30 s = 1500 steps -> 752 frames, not 24 x 30 + 2 = 722
every = max(1, round(50 / 24))
per_cam = L.frames_per_call(1500, every)
check(per_cam == 752, f"frames_per_call(1500, 2) = {per_cam}")
budget = 2 * per_cam * 2
check(L.check_frames(2, per_cam, True, budget) == budget, "check_frames refused a call at the budget")
check(refused(lambda: L.check_frames(2, per_cam, True, budget - 1)), "check_frames accepted a call one image over")
rec, k = recorder(["a", "b"], 1, depth="frames", max_images=40)
run_call(rec, k, 100)
check(len(rec.steps) * 4 <= 40 and rec.steps[-1] == 100 and rec.skipped > 0,
      f"max_images: {len(rec.steps)} frames x 4 images, last step {rec.steps[-1]}, skipped {rec.skipped}")
rec, k = recorder(["a"], 1, depth="frames")
run_call(rec, k, 3)
rec2, k2 = recorder(["a"], 1, depth="legacy")
run_call(rec2, k2, 3)
check(rec.depth["a"][0].dtype == np.uint16 and rec2.depth["a"][0].dtype == np.float16
      and rec.depth["a"][0].nbytes <= rec.frames["a"][0].nbytes, "shared depth is not kept as it is sent")
n = len(rec.steps)
parts = rec.parts("frames", 10)
check(rec.frames["a"] == [] and rec.depth["a"] == [], "shared parts() kept its frame lists")
body = L.encode_response({}, parts)
_, got = rcb1.decode(bytes(body))
check(got["frames/a"]["data"].shape == (n, 6, 8, 3), f"shared frames/a shape {got['frames/a']['data'].shape}, {n} frames")


# per-frame depth is compressed only while it fits, with the bytes of zlib.compress of the stacked frames
import zlib  # noqa: E402
for content in ("ramp", "random"):
    z = (np.linspace(0.3, 2.0, 6 * 8, dtype=np.float32).reshape(6, 8) if content == "ramp"
         else rng.uniform(0.3, 2.0, (6, 8)).astype(np.float32))
    mm = [L.depth_mm(z + 0.001 * i) for i in range(5)]
    ref = zlib.compress(np.stack(mm).tobytes(), 1)
    part = L.depth_frames_part("depth_frames/a", list(mm))
    check(isinstance(part[2], L.Deflate) and len(part[2]) >= len(ref), "depth_frames_part: not lazy, or no upper bound")
    parts = [part, rcb1.array_part("proprio", np.zeros((5, 3), np.float32))]
    _, got = rcb1.decode(bytes(L.encode_response({}, parts)), arrays=False)
    check(got["depth_frames/a"]["data"] == ref, f"lazy depth bytes differ ({content})")
    small = L.depth_frames_part("depth_frames/a", list(mm))
    parts = [small, rcb1.array_part("proprio", np.zeros((5, 3), np.float32))]
    meta, got = rcb1.decode(bytes(L.encode_response({}, parts, max_bytes=100)), arrays=False)
    check("depth_frames/a" not in got and small[2].frames == [] and "degraded" in meta and len(parts) == 1,
          "a dropped depth part was compressed or kept")
    # the rest fits but the compressed depth does not: compression stops at the room left, the depth is dropped
    rest = rcb1.size({}, [("depth_frames/a", "bytes", b"", {"codec": "zlib", "dtype": "uint16", "shape": [5, 6, 8],
                                                                  "unit": "mm"}),
                    rcb1.array_part("proprio", np.zeros((5, 3), np.float32))])
    for limit in (rest, rest + len(ref) // 2, rest + len(ref) - 1):
        part = L.depth_frames_part("depth_frames/a", list(mm))
        parts = [part, rcb1.array_part("proprio", np.zeros((5, 3), np.float32))]
        meta, got = rcb1.decode(bytes(L.encode_response({}, parts, max_bytes=limit)), arrays=False)
        check("depth_frames/a" not in got and part[2].frames == [] and "depth_frames" in meta.get("degraded", ""),
              f"depth over the room left was kept ({content}, limit {limit})")
    check(L.Deflate(list(mm)).compress(len(ref) - 1) is None and L.Deflate(list(mm)).compress(len(ref)) == ref,
          f"Deflate.compress(limit) ({content})")


# ---------------------------------------------------------------- the sidecar and the realtime layers
class Toy:
    raw_dim = 2
    control_dt = 0.02
    max_control_steps = 10_000
    proprio_layout = ["x"]
    cameras = ["a", "b"]
    depth_cameras = ["a"]

    def __init__(self):
        self.x = 0.0

    def spec(self):
        return {"cameras": {}, "action_types": {"joints": {"dim": 2}}}

    def interpolable(self, t):
        return True

    def images(self, cams, depth):
        return ({c: np.zeros((4, 4, 3), np.uint8) for c in cams},
                {c: np.ones((4, 4), np.float32) for c in cams if depth and c in self.depth_cameras})

    def proprio(self):
        return np.array([self.x], np.float32)

    def clip(self, t, rows):
        return rows, []

    def to_sim(self, t, row):
        return np.asarray(row, float)

    def command(self, t):
        return np.zeros(2)

    def hold(self):
        return "joints", np.zeros(2)

    def step(self, row):
        self.x += float(row[0])
        return False, False, {}

    def reset(self):
        self.x = 0.0

    def state_sha(self):
        return hashlib.sha256(np.array([self.x]).tobytes()).hexdigest()[:12]

    def save_trajectory(self, rows, path, meta):
        np.savez(path, actions=rows)

    def render_video(self, rows, path):
        open(path, "wb").write(b"mp4")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


copies: dict[str, Path] = {}
for p in sorted([ROOT / "embodied_first_exam/standard/sidecar/rcb_service.py",
                 *(ROOT / "images").glob("*/tools/**/rcb_service.py")]):
    copies.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), p)
for h, path in copies.items():
    S = load(path, f"rcb_service_{h[:8]}")
    tag = path.relative_to(ROOT)
    d = tempfile.mkdtemp()
    try:
        svc = S.Service(Toy(), data=d, max_frames_per_call=1000)
        # 2 cameras + depth on one: 3 images a frame; fps 24 at 50 Hz films every 2 steps
        rec = S.Recorder(svc.sim, ["a", "b"], 24, True, "frames")
        steps = (1000 // 3 - 2) * rec.every                  # 333 frames x 3 = 999 images: at the budget
        svc._frame_budget(rec, steps)
        check(refused(lambda: svc._frame_budget(rec, steps + 2 * rec.every)), f"{tag}: one frame over the budget passed")
        for n_steps in (0, 1, rec.every - 1, rec.every, rec.every + 1, 5 * rec.every, steps):
            r = S.Recorder(svc.sim, ["a", "b"], 24, True, "frames")
            r.start()                                        # the service's pattern: start, a step per control step,
            for _ in range(n_steps):                         # finish
                r.step()
            r.finish()
            real = n_steps // r.every + 1 + (1 if n_steps % r.every else 0)   # a frame at a stride step ends the call
            check(len(r.prop) == real and r.images_per_call(n_steps) // 3 in (real, real + 1),
                  f"{tag}: {n_steps} steps: {len(r.prop)} frames captured (real {real}), images_per_call "
                  f"{r.images_per_call(n_steps)} (an upper bound: one frame high when the call ends on a stride step)")
        rec.start()
        for _ in range(steps):
            rec.step()
        rec.finish()
        code, _, body = S.Service._reply_rcb1({}, rec.parts())
        _, got = rcb1.decode(bytes(body))
        check(got["frames/a"]["data"].shape[0] == len(rec.prop) and got["depth/a"]["data"].dtype == np.float16,
              f"{tag}: the response's frames")
    finally:
        shutil.rmtree(d)

# the realtime layer on one sidecar copy: /observe never waits; what an answer holds until it is
# sent still counts against max_frames_per_call and MAX_UNSENT_BODIES
path = next(iter(copies.values()))
sys.modules["rcb_service"] = load(path, "rcb_service")
R = load(STD / "realtime/rcb_realtime.py", "rcb_realtime")


class ToyNoRec(Toy):
    record_frames = "delivered"                              # no recorder: /observe answers now on the simulator thread


d = tempfile.mkdtemp()
try:
    svc = R.RealtimeService(ToyNoRec(), data=d, max_frames_per_call=300, slowdown=1.0)
    svc.start()
    check(not svc.recording and svc.cameras is None, "realtime: record_frames = 'delivered' still records")
    view = (["a", "b"], 25, "frames", False)                 # 2 images a frame
    check(R.RealtimeService._check_observe(svc, {"last_s": 1.0})["seconds"] == 0.0, "realtime: last_s check")
    try:
        svc._check_observe({"seconds": 2.0})
        check(False, "realtime: observe seconds > 0 was accepted")
    except R.Refused as exc:
        check(exc.code == 400 and "never waits" in exc.body.get("error", ""), f"realtime: seconds refusal {exc.code} {exc.body}")
    j = R._Job("POST", "/observe")                           # the present: answered at once, its images in flight
    svc._rt_observe({"seconds": 0.0, "last_s": 0.0, "view": view}, j)   # (an upper bound: 2 a camera)
    check(j.images == 4 and svc.unsent_images == 4 and svc.unsent_bodies == 1 and j.reply[1]["last_s"] == 0.0,
          f"realtime: an immediate answer's images {j.images} / {svc.unsent_images}")
    svc._reply_rcb1(j.reply[1], j.reply[2].parts())
    svc._sent(j)
    check(svc.unsent_images == 0 and svc.unsent_bodies == 0, "realtime: _sent did not release")
    svc.unsent_bodies = R.MAX_UNSENT_BODIES
    j = R._Job("POST", "/observe")                           # the present is never refused: answered without frames
    svc._rt_observe({"seconds": 0.0, "last_s": 0.0, "view": view}, j)
    check(j.reply[1].get("frames_skipped") == 1 and j.images == 0 and not j.reply[2].cams,
          f"realtime: an observe now with MAX_UNSENT_BODIES answers waiting: {j.reply[1].get('frames_skipped')}, {j.images}")
    svc.unsent_bodies = 0

    # a submit is never refused for its images: past the budget (or with MAX_UNSENT_BODIES answers unsent) it is
    # answered without its last frames (meta frames_skipped)
    def submit(view):
        job = R._Job("POST", "/submit")
        svc._rt_submit({"type": "joints", "actions": np.zeros((1, 2)), "dt": 0.02, "k": 1, "interpolate": "hold",
                        "at": None, "view": view, "note": ""}, job)
        return job
    full = (["a", "b"], 25, "frames", True)                  # its last frames: 2 + 1 depth = 3 images
    svc.unsent_images = 299
    j = submit(full)
    check(j.reply[1].get("frames_skipped") == 1 and j.images == 0 and not j.reply[2].cams,
          f"realtime: a submit past the budget: {j.reply[1].get('frames_skipped')} skipped, {j.images} images")
    j = R._Job("POST", "/observe")
    svc._rt_observe({"seconds": 0.0, "last_s": 0.0, "view": full}, j)
    check(j.reply[1].get("frames_skipped") == 1 and j.images == 0 and not j.reply[2].cams,
          f"realtime: an observe now past the budget: {j.reply[1].get('frames_skipped')} skipped, {j.images} images")
    svc.unsent_images = 0
    j = submit(full)
    check("frames_skipped" not in j.reply[1] and j.images == 3 and j.reply[1]["duration_s"] == 0.02,
          f"realtime: a submit within the budget lost its frames ({j.images} images) {j.reply[1]}")
    svc._sent(j)
    svc.unsent_bodies = R.MAX_UNSENT_BODIES
    j = submit(full)
    check(j.reply[1].get("frames_skipped") == 1 and j.images == 0, "realtime: a submit with the unsent answers full kept its frames")
    svc.unsent_bodies = 0
finally:
    shutil.rmtree(d)

# the realtime layer with the recorder on the simulator's thread (an adapter without render hooks): /observe is a pure read of the
# ring on the HTTP thread; at most MAX_UNSENT_BODIES such answers with images are built at a time (the rest: none)
d = tempfile.mkdtemp()
try:
    svc = R.RealtimeService(Toy(), data=d, max_frames_per_call=300, slowdown=1.0)
    svc.start()
    check(svc.recording and isinstance(svc.cameras, R._ThreadCameras) and len(svc.cameras.ring) == 1,
          "realtime: the simulator thread's recorder did not take the start frame")
    out = svc.front("POST", "/observe", 2, lambda n: b"{}")
    _, got = rcb1.decode(bytes(out[3]))
    check(out[0] == "reply" and out[1] == 200 and "last/a" in got, f"realtime: a recorded observe: {out[:3]}")
    taken = [svc._obs_slots.acquire(blocking=False) for _ in range(R.MAX_UNSENT_BODIES)]
    out = svc.front("POST", "/observe", 2, lambda n: b"{}")
    m, got = rcb1.decode(bytes(out[3]))
    check(m.get("frames_skipped") == 1 and "last/a" not in got, f"realtime: observe with every slot taken: {m}")
    for t in taken:
        svc._obs_slots.release()
finally:
    shutil.rmtree(d)

if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print(f"ok per-call image budget: rcb1 frames_part/size, shared-layer stride count + max_images + depth as sent, "
      f"{len(copies)} distinct rcb_service.py (at the budget / one over), realtime unsent answers in flight, submit / observe now never refused, the thread recorder's reads")
