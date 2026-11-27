#!/usr/bin/env python3
"""The sidecar service's first-attempt record (docs/protocol/standard_mode.md "Evidence and grading"; PROTOCOL
§4), on a toy simulator (numpy only, no image, a few seconds), for every distinct rcb_service.py in
embodied_first_exam/benchmarks/ (the copies are byte-identical; a copy without the record is reported, not failed):

  - one attempt that reaches the goal and is finished (POST /finish): first_success = success = 1, no first-episode files;
  - fail (the task's rule), reset, the goal reached and finished: success 1, first_success 0 ("failed"),
    trajectory.first.npz holds episode 1's rows, replay.first.mp4 is rendered after the graded video;
  - abandon (reset mid-episode), reset, fail: first_reason "reset";
  - one attempt that times out: first_success 0 ("timeout");
  - a first-episode video that fails to render: the verdict and the graded video are unchanged (evidence only).

and, for every distinct copy (also humanclaw's and abc-sim's realtime base), the eai-standard/3.0 rules: /observe
seconds > 0 is a 400 that names the hold chunk; a /submit answers duration_s and planned_duration_s; the recorder keeps
the submit's frames and /observe last_s = n returns them (frame_step, proprio rows); a hold chunk (no rows, "hold",
seconds) runs round(seconds / control_dt) control steps and is answered as a submit; rows with seconds, or no rows
without "hold", are a 400; a reset empties the recorder; /spec states the protocol and timing.recorder; seconds, last_s, dt
and video_fps must be JSON numbers (true, "0.1": 400); a step's info["blocked"] stops a hold chunk as it stops a chunk
with rows; record_frames = "delivered" with two cameras sent in turn: /observe last_s keeps frames/<cam>, proprio and
frame_step on one frame axis; resets_left is 0 after /finish (in /status and in the 409
bodies), a /finish body over 64 MiB is a 413, and the first episode's first_success is its own end judgement.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "embodied_first_exam/standard"))   # rcb1.py
fails: list[str] = []


def check(cond, what):
    if not cond:
        fails.append(what)
        print("FAIL", what)


class Toy:
    """x moves by row[0]; x >= 1 is a success; row[1] > 0 ends the episode by the task's rule ("failed")."""
    raw_dim = 2
    control_dt = 0.01
    max_control_steps = 50
    proprio_layout = ["x"]
    cameras = ["c"]
    depth_cameras: list = []
    broken_first_video = False

    def __init__(self):
        self.reset()

    def spec(self):
        return {"cameras": {}, "action_types": {"joints": {"dim": 2}}}

    def interpolable(self, t):
        return True

    def images(self, cams, depth):
        return {c: np.zeros((2, 2, 3), np.uint8) for c in cams}, {}

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
        self.x += row[0]
        self.n += 1
        if self.x >= 1:
            return True, True, {}
        if row[1] > 0:
            return True, False, {}
        return False, False, {}

    def reset(self):
        self.x, self.n = 0.0, 0

    def state_sha(self):
        return hashlib.sha256(np.array([self.x, self.n]).tobytes()).hexdigest()[:12]

    def save_trajectory(self, rows, path, meta):
        np.savez(path, actions=rows, **{k: str(v) for k, v in meta.items()})

    def render_video(self, rows, path):
        if self.broken_first_video and "first" in os.path.basename(path):
            raise RuntimeError("no GL")
        with open(path, "wb") as f:
            f.write(b"mp4 %d" % len(rows))


def run(S, plan, budget=5, broken=False):
    d = tempfile.mkdtemp()
    try:
        sim = Toy()
        sim.broken_first_video = broken
        svc = S.Service(sim, data=d, reset_budget=budget)
        svc.start()
        for item in plan:
            if item == "reset":
                svc._reset({"cameras": []}, {})
                continue
            if item == "finish":
                svc._agent_finish()
                continue
            for r in item:
                if svc.done:
                    break
                svc._step("joints", np.array(r, float))
            svc._checkpoint("submit")
        svc.stopping = True
        svc.poll()
        fin = json.load(open(os.path.join(d, "final.json")))
        files = {f: open(os.path.join(d, f), "rb").read() for f in os.listdir(d) if f.startswith(("replay", "trajectory."))}
        first = os.path.join(d, "trajectory.first.npz")
        fin["_first_rows"] = np.load(first)["actions"].tolist() if os.path.exists(first) else None
        return fin, files
    finally:
        shutil.rmtree(d)


def test(path: Path) -> None:
    spec = importlib.util.spec_from_file_location(f"rcb_service_{hashlib.sha1(str(path).encode()).hexdigest()[:8]}", path)
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    tag = path.relative_to(ROOT)
    check({"first_success", "first_reason", "first_n_actions", "first_video"} <= S.RESERVED, f"{tag}: first_* not RESERVED")

    fin, files = run(S, [[[0.5, 0], [0.6, 0]], "finish"])
    check(fin["success"] and fin["first_success"] is True and fin["first_reason"] == "finished" and fin["resets"] == 0,
          f"{tag}: one success: {fin}")
    check("first_video" not in fin and "trajectory.first.npz" not in files and "replay.first.mp4" not in files,
          f"{tag}: one success left first-episode files: {sorted(files)}")

    fin, files = run(S, [[[0.2, 0], [0.1, 1]], "reset", [[0.5, 0], [0.6, 0]], "finish"])
    check(fin["success"] and fin["first_success"] is False and fin["first_reason"] == "failed" and fin["resets"] == 1,
          f"{tag}: fail, reset, success: {fin}")
    check(fin["first_n_actions"] == 2 and fin["_first_rows"] == [[0.2, 0.0], [0.1, 1.0]] and fin["n_actions"] == 2,
          f"{tag}: fail, reset, success: first rows {fin.get('_first_rows')} / {fin.get('first_n_actions')}")
    check(fin["first_video"] is True and files.get("replay.first.mp4") == b"mp4 2" and files.get("replay.mp4") == b"mp4 2"
          and fin["video"] is True and fin["video_pending"] is False, f"{tag}: fail, reset, success: videos {sorted(files)} {fin}")

    fin, files = run(S, [[[0.2, 0], [0.1, 0], [0.1, 0]], "reset", [[0.1, 1]]])
    check(not fin["success"] and fin["first_success"] is False and fin["first_reason"] == "reset"
          and fin["first_n_actions"] == 3 and fin["reason"] == "failed", f"{tag}: abandon, reset, fail: {fin}")

    fin, files = run(S, [[[0.1, 0]]])
    check(not fin["success"] and fin["first_success"] is False and fin["first_reason"] == "timeout"
          and "trajectory.first.npz" not in files, f"{tag}: timeout: {fin}")

    good, _ = run(S, [[[0.2, 0], [0.1, 1]], "reset", [[0.5, 0], [0.6, 0]], "finish"])
    fin, files = run(S, [[[0.2, 0], [0.1, 1]], "reset", [[0.5, 0], [0.6, 0]], "finish"], broken=True)
    same = {k: fin.get(k) for k in ("success", "live_success", "reason", "n_actions", "video", "graded_by")}
    check(same == {k: good.get(k) for k in same} and fin["first_video"] is False and "replay.first.mp4" not in files
          and files.get("replay.mp4") == b"mp4 2" and fin["video_pending"] is False,
          f"{tag}: a failed first video changed the verdict: {fin}")


def test_v3(path: Path) -> None:
    """The eai-standard/3.0 rules (module docstring) on one copy, through Service.handle (the HTTP surface)."""
    import rcb1
    spec = importlib.util.spec_from_file_location(f"rcb_service_v3_{hashlib.sha1(str(path).encode()).hexdigest()[:8]}", path)
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    tag = path.relative_to(ROOT)
    d = tempfile.mkdtemp()
    try:
        svc = S.Service(Toy(), data=d, reset_budget=1)
        svc.start()

        def post(path_, obj):
            code, ctype, body = svc.handle("POST", path_, json.dumps(obj).encode())
            if ctype == "application/json":
                return code, json.loads(body), {}
            m, p = rcb1.decode(body)
            return code, m, p

        sp = svc.spec
        check(sp.get("protocol") == "eai-standard/3.0" and sp["timing"]["recorder"]["cameras"] == ["c"]
              and sp["timing"]["recorder"]["fps"] == 10.0 and sp["timing"]["recorder"]["records"] == "during /submit"
              and sp["timing"]["recorder"]["depth"] == [] and "max_watch_s" not in sp,
              f"{tag}: /spec standard / timing.recorder: {sp.get('timing')}")
        code, m, _ = post("/observe", {"seconds": 1.0})
        check(code == 400 and "hold chunk" in m.get("error", ""), f"{tag}: observe seconds > 0: {code} {m}")
        code, m, p = post("/observe", {"last_s": 1.0})
        check(code == 200 and m["last_s"] == 0.0 and m["frame_step"] == 0, f"{tag}: last_s before any submit: {code} {m}")
        mp4 = importlib.util.find_spec("imageio") is not None      # (the video encoder; frames without it)
        code, m, p = post("/submit", {"type": "joints", "dt": 0.02, "actions": [[0.01, 0]] * 10, "video": "frames"})
        check(code == 200 and m["duration_s"] == 0.2 and m["planned_duration_s"] == 0.2 and m["control_steps_chunk"] == 20
              and m.get("frame_step") == 20, f"{tag}: submit duration, frame_step: {code} {m}")
        code, m, p = post("/observe", {"last_s": 0.1, "video": "frames"})
        steps = p.get("frame_step", {}).get("data")
        check(code == 200 and m["frame_step"] == 20 and m["last_s"] == 0.1 and steps is not None
              and list(steps) == [10, 20] and p["frames/c"]["data"].shape[0] == 2 and p["proprio"]["data"].shape[0] == 2
              and m["control_steps"] == 20, f"{tag}: last_s after a submit: {code} {m} {steps}")
        code, m, _ = post("/submit", {"type": "joints", "dt": 0.02, "actions": [[0.01, 0]], "seconds": 0})
        check(code == 400 and "no rows" in m.get("error", ""), f"{tag}: rows with seconds 0: {code} {m}")
        code, m, p = post("/observe", {"last_s": 99, "video_fps": 30, "video": "mp4" if mp4 else "frames"})
        check(code == 200 and list(p["frame_step"]["data"]) == [0, 10, 20] and ("video/c" in p) == mp4,
              f"{tag}: last_s capped at the ring: {code} {m}")
        code, m, p = post("/submit", {"type": "joints", "interpolate": "hold", "seconds": 0.1,
                                      "video": "mp4" if mp4 else "frames"})
        check(code == 200 and m.get("hold") is True and m["control_steps_chunk"] == 10 and m["duration_s"] == 0.1
              and m["executed_rows"] == 0 and m["control_steps"] == 30 and ("video/c" in p) == mp4
              and m.get("frame_step") == 30, f"{tag}: hold chunk: {code} {m}")
        code, m, _ = post("/submit", {"type": "joints", "interpolate": "hold", "seconds": sp["max_chunk_s"] + 1})
        check(code == 400 and "max_chunk_s" in m.get("error", ""), f"{tag}: hold past max_chunk_s: {code} {m}")
        code, m, _ = post("/submit", {"type": "joints", "interpolate": "hold", "seconds": 0.1, "actions": [[0, 0]]})
        check(code == 400 and "no rows" in m.get("error", ""), f"{tag}: rows with seconds: {code} {m}")
        code, m, _ = post("/submit", {"type": "joints", "seconds": 0.1})
        check(code == 400 and "hold chunk" in m.get("error", ""), f"{tag}: no rows without hold: {code} {m}")
        code, m, _ = post("/submit", {"type": "joints", "interpolate": "hold", "seconds": 1e9})
        check(code == 400, f"{tag}: hold chunk too long: {code} {m}")
        code, m, _ = post("/observe", {"last_s": 0.05, "include_depth": True})
        check(code == 400, f"{tag}: last_s with depth: {code} {m}")
        code, m, _ = post("/reset", {"cameras": []})
        check(code == 200 and m.get("frame_step") == 0, f"{tag}: reset (3.0: frame_step on an answer with images): {code} {m}")
        code, m, p = post("/observe", {"last_s": 1.0})
        check(code == 200 and m["last_s"] == 0.0 and m["frame_step"] == 0, f"{tag}: last_s after a reset: {code} {m}")
    finally:
        shutil.rmtree(d)
    test_v3_more(S, tag)


class Toy2(Toy):
    """Toy with two cameras; with record_frames "delivered" the recorder keeps only what a submit rendered."""
    cameras = ["a", "b"]
    record_frames = "delivered"
    max_control_steps = 1000


class Blocky(Toy):
    """Toy whose step() reports the robot blocked from the 4th step of the episode on."""
    def step(self, row):
        out = super().step(row)
        return out[0], out[1], ({"blocked": True} if self.n >= 4 else {})


def test_v3_more(S, tag) -> None:
    """The fixes of the 3.0 review on one copy (module docstring, the last sentences)."""
    import rcb1

    def poster(svc):
        def post(path_, obj, raw=None, length=None):
            body = raw if raw is not None else json.dumps(obj).encode()
            code, ctype, out = svc.handle("POST", path_, body, content_length=length)
            if ctype == "application/json":
                return code, json.loads(out), {}
            m, p = rcb1.decode(out)
            return code, m, p
        return post

    d = tempfile.mkdtemp()
    try:                                         # strict numbers, a blocked hold chunk
        svc = S.Service(Blocky(), data=d)
        svc.start()
        post = poster(svc)
        for bad in ({"type": "joints", "interpolate": "hold", "seconds": True},
                    {"type": "joints", "interpolate": "hold", "seconds": "0.1"},
                    {"type": "joints", "actions": [[0, 0]], "dt": "0.01"},
                    {"type": "joints", "actions": [[0, 0]], "video_fps": True}):
            code, m, _ = post("/submit", bad)
            check(code == 400, f"{tag}: {bad} is not a 400: {code} {m}")
        for bad in ({"seconds": True}, {"last_s": "1"}, {"video_fps": "10"}, {"video_fps": 0.5}):
            code, m, _ = post("/observe", bad)
            check(code == 400, f"{tag}: observe {bad} is not a 400: {code} {m}")
        check(svc.status()["control_steps"] == 0, f"{tag}: a refused request ran steps")
        code, m, _ = post("/submit", {"type": "joints", "interpolate": "hold", "seconds": 0.1, "video": "none"})
        check(code == 200 and m["control_steps_chunk"] == 4 and m["duration_s"] == 0.04 and m["planned_duration_s"] == 0.1,
              f"{tag}: a hold chunk did not stop where the robot is blocked: {code} {m}")
    finally:
        shutil.rmtree(d)

    d = tempfile.mkdtemp()
    try:                                         # record_frames "delivered", two cameras asked for in turn
        svc = S.Service(Toy2(), data=d)
        svc.start()
        post = poster(svc)
        for cam in ("a", "b"):
            code, m, _ = post("/submit", {"type": "joints", "actions": [[0.001, 0]] * 10, "cameras": [cam],
                                          "video": "frames", "video_fps": 10})
            check(code == 200, f"{tag}: delivered submit {cam}: {code} {m}")
        code, m, p = post("/observe", {"last_s": 3, "cameras": ["a", "b"], "video": "frames"})
        n = {k: int(v["data"].shape[0]) for k, v in p.items() if k.startswith(("frames/", "proprio", "frame_step"))}
        check(code == 200 and set(n.values()) == {1} and list(p["frame_step"]["data"]) == [10] and m["last_s"] == 0
              and m["frame_step"] == 10, f"{tag}: delivered, one frame holds both cameras (step 10): {n} {m}")
        code, m, _ = post("/submit", {"type": "joints", "actions": [[0.001, 0]] * 10, "cameras": ["a", "b"],
                                      "video": "frames", "video_fps": 10})
        code, m, p = post("/observe", {"last_s": 3, "cameras": ["a", "b"], "video": "frames"})
        n = {k: int(v["data"].shape[0]) for k, v in p.items() if k.startswith(("frames/", "proprio", "frame_step"))}
        check(code == 200 and len(set(n.values())) == 1 and n["proprio"] == 3 and m["frame_step"] == 30
              and list(p["frame_step"]["data"]) == [10, 20, 30],
              f"{tag}: delivered: frames, proprio and frame_step on different frame axes: {n} {m.get('frame_step')}")
        code, m, p = post("/observe", {"last_s": 3, "cameras": ["a"], "video": "frames"})
        n = {k: int(v["data"].shape[0]) for k, v in p.items() if k.startswith(("frames/", "proprio", "frame_step"))}
        check(code == 200 and len(set(n.values())) == 1 and list(p["frame_step"]["data"]) == [0, 10, 20, 30],
              f"{tag}: delivered, camera a alone: {n} {p.get('frame_step', {}).get('data')}")
    finally:
        shutil.rmtree(d)

    d = tempfile.mkdtemp()
    try:                                         # resets_left after /finish, a /finish body over the limit
        svc = S.Service(Toy(), data=d, reset_budget=1)
        svc.start()
        post = poster(svc)
        code, m, _ = post("/finish", None, raw=b"", length=S.MAX_BODY + 1)
        check(code == 413 and not svc.done, f"{tag}: /finish with a body over 64 MiB: {code} {m}")
        code, m, _ = post("/finish", {})
        check(code == 200 and m["resets_left"] == 0, f"{tag}: /finish answer resets_left: {m}")
        st = svc.status()
        check(st["resets_left"] == 0 and st["reason"] == "finished", f"{tag}: /status resets_left after /finish: {st}")
        for path_ in ("/submit", "/reset"):
            code, m, _ = post(path_, {"type": "joints", "actions": [[0, 0]]} if path_ == "/submit" else {})
            check(code == 409 and m.get("resets_left", 0) == 0, f"{tag}: {path_} after /finish: {code} {m}")
    finally:
        shutil.rmtree(d)

    d = tempfile.mkdtemp()
    try:                                         # the first episode's own end judgement
        svc = S.Service(Toy(), data=d, reset_budget=1, step_limit=3)
        svc.start()
        post = poster(svc)
        code, m, _ = post("/submit", {"type": "joints", "actions": [[0.5, 0], [0.6, 0], [0.0, 0]], "video": "none"})
        check(code == 200 and m["reason"] == "step_limit" and m["resets_left"] == 1, f"{tag}: step limit: {code} {m}")
        code, m, _ = post("/reset", {"cameras": []})
        check(code == 200, f"{tag}: reset after the step limit: {code} {m}")
        post("/submit", {"type": "joints", "actions": [[0.1, 0]], "video": "none"})
        svc.stopping = True
        svc.poll()
        fin = json.load(open(os.path.join(d, "final.json")))
        if "first_success" in S.RESERVED:
            check(fin.get("first_success") is True and fin.get("first_reason") == "step_limit" and fin["success"] is False,
                  f"{tag}: first episode (a success at the step limit, then a reset): {fin}")
    finally:
        shutil.rmtree(d)


def main() -> None:
    v3: dict[str, Path] = {}
    for p in sorted(list((ROOT / "embodied_first_exam/benchmarks").glob("**/rcb_service.py"))
                    + list((ROOT / "images").glob("*/tools/**/rcb_service.py"))):
        if "class Service" in p.read_text():
            v3.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), p)
    for p in v3.values():
        test_v3(p)
    copies: dict[str, list[Path]] = {}
    for p in sorted(list((ROOT / "embodied_first_exam/benchmarks").glob("**/rcb_service.py"))
                    + list((ROOT / "images").glob("*/tools/**/rcb_service.py"))):
        copies.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), []).append(p)
    tested = 0
    for h, paths in copies.items():
        if "def _first_episode" not in paths[0].read_text():   # every copy is the same code (check-tooling-identity.sh)
            check(False, f"{len(paths)} copy(ies) without the first-attempt record ({h[:10]}): "
                  + ", ".join(str(p.relative_to(ROOT)) for p in paths))
            continue
        test(paths[0])
        tested += len(paths)
    check(tested > 0, "no rcb_service.py copy with the first-attempt record")
    if fails:
        print(f"{len(fails)} failure(s)")
        sys.exit(1)
    print(f"ok first-attempt record: {tested} rcb_service.py copies ({sum(1 for ps in copies.values())} distinct): one "
          "success, fail-reset-success, abandon-reset-fail, timeout, a failed first video; eai-standard/3.0 rules on "
          f"{len(v3)} distinct copies: observe seconds refused, last_s from the recorder, hold chunk, duration_s")


if __name__ == "__main__":
    main()
