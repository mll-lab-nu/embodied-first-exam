"""environment/sim/live_video.py of RoboLab (YAMLab's is the same file) without a simulator: frames per slot, thinning
past MAX_FRAMES, a restarted service regrouping the frames on disk, truncate() after a resume (the rolled-back call's
frames and the dumped end state go), meta.json pacing an encode without last.json, and a failing frame source stopping
the video only. numpy only (a stand-in for Pillow when it is missing; the encode itself needs imageio and is not run)."""
import json, os, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.dont_write_bytecode = True
try:
    import PIL.Image  # noqa: F401
except ImportError:
    class _Img:
        def __init__(self, a): self.a = a
        def save(self, fp, format=None, **kw): fp.write(b"\xff\xd8stand-in\xff\xd9")
    img = types.ModuleType("PIL.Image"); img.fromarray = lambda a, *x, **k: _Img(a)
    pil = types.ModuleType("PIL"); pil.Image = img; sys.modules["PIL"] = pil; sys.modules["PIL.Image"] = img
import numpy as np
bad = 0
def check(ok, what):
    global bad
    bad += not ok; print("ok  " if ok else "FAIL", what)
for bench in ("robolab", "yamlab"):
    sys.path.insert(0, os.path.join(ROOT, "scripts", bench, "template/standard/environment/sim"))
    import live_video as LV
    sys.path.pop(0); del sys.modules["live_video"]
    td = tempfile.mkdtemp(); n = [0]; vd = os.path.join(td, "live_video")
    def frame():
        n[0] += 1; return np.zeros((8, 8, 3), np.uint8)
    steps = lambda: sorted(int(f[:-4]) for f in os.listdir(vd) if f[:-4].isdigit())  # noqa: E731
    V = LV.LiveVideo(td, ctrl_hz=15, frame=frame, max_frames=50)
    for s in range(400): V.offer(s)
    check(V.every == 12 and len(V.kept) == 34 and steps() == list(range(0, 400, 12)), f"{bench}: thinned to one frame per 12 steps ({V.every}, {len(V.kept)})")
    meta = json.load(open(os.path.join(vd, "meta.json")))
    check(meta["base"] == 3 and meta["ctrl_hz"] == 15, f"{bench}: meta.json records the base slot ({meta})")
    V.last(399)
    V2 = LV.LiveVideo(td, ctrl_hz=15, frame=frame, max_frames=50); c = n[0]
    check(V2.every == 12 and len(V2.kept) == 34, f"{bench}: a restarted service regroups the frames on disk")
    V2.truncate(200)
    check(max(steps()) <= 200 and not os.path.exists(os.path.join(vd, "last.jpg")) and not os.path.exists(os.path.join(vd, "last.json")),
          f"{bench}: truncate after a resume drops the rolled-back frames and the dumped end state")
    for s in range(201): V2.offer(s)
    check(n[0] == c, f"{bench}: the resume's journal replay re-takes no frame on disk")
    for s in range(201, 300): V2.offer(s)
    check(max(steps()) >= 288 and V2.error is None, f"{bench}: the episode goes on filming after the resume")
    def broken():
        raise RuntimeError("camera gone")
    V3 = LV.LiveVideo(tempfile.mkdtemp(), 15, frame=broken); V3.offer(0); V3.offer(3)
    check(V3.error and "camera gone" in V3.error, f"{bench}: a failing frame stops the video, offer() never raises")
print("live video:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
