#!/usr/bin/env python3
"""Film one successful attempt of a family from the venue camera (for reports and reviews), in the simulator image:

    RFO_OUT=/some/dir scripts/robofunolympics/dev.sh /rfo/make_videos.py --family sprint     # -> /out/sprint.mp4, .png, .json

A family with a reference controller (oracles/<family>/oracle.py) is filmed running it. A family without one is filmed
running its referee test (tests/test_<family>.py): the first attempt of the test that the referee calls a success, which
is the test's positive example (an injection: see the test's docstring). 640 x 360, 25 frames per second of robot time.
Where the venue camera shows the robot smaller than MIN_PX pixels (a 50 m straight, a football pitch), the film follows
the robot with a tracking camera and shows the venue camera's picture in a corner."""
import argparse
import importlib.util
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "shared"), str(HERE / "tests")]
import imageio.v2 as imageio  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from rfo import world as W  # noqa: E402

EVERY, SIZE = 4, (640, 360)
MIN_PX, INSET = 70, (256, 144)


def follow_camera(w):
    """A camera that follows the robot from the side and a little ahead, or None when the venue camera shows the
    robot large enough."""
    m, d = w.m, w.d
    cam = m.camera("venue").id
    height = float(d.xpos[w.robot.pelvis][2]) * 1.75                 # about the standing robot's height
    dist = float(np.linalg.norm(d.cam_xpos[cam] - d.xpos[w.robot.pelvis]))
    px = SIZE[1] * height / (2 * dist * np.tan(np.radians(float(m.cam_fovy[cam])) / 2))
    if px >= MIN_PX:
        return None
    c = mujoco.MjvCamera()
    c.type = mujoco.mjtCamera.mjCAMERA_TRACKING
    c.trackbodyid = int(w.robot.pelvis)
    c.distance, c.azimuth, c.elevation = 3.4 * height, 115.0, -12.0
    return c


class Film:
    """Films every attempt of every world; keeps the first one that ends in a success."""

    def __init__(self, out: str):
        self.out, self.tmp = out, out + ".part.mp4"
        self.writer, self.saved, self.last, self.info = None, False, None, {}
        self.follow = None

    def start(self, w) -> None:
        self.stop(w)
        if not self.saved:
            self.writer = imageio.get_writer(self.tmp, format="FFMPEG", mode="I", fps=round(1 / (EVERY * w.CONTROL_DT)),
                                             codec="libx264", macro_block_size=1,
                                             output_params=["-movflags", "+faststart", "-pix_fmt", "yuv420p"])
            mujoco.mj_forward(w.m, w.d)
            self.follow = follow_camera(w)
            self.frame(w)

    def frame(self, w) -> None:
        if self.writer is not None:
            if self.follow is None:
                self.last = w.render("venue", *SIZE)
            else:                                    # the robot from close by, the venue's picture in the corner
                self.last = w.render(self.follow, *SIZE)
                iw, ih = INSET
                x0, y0 = SIZE[0] - iw - 8, 8
                self.last[y0 - 2:y0 + ih + 2, x0 - 2:x0 + iw + 2] = 255
                self.last[y0:y0 + ih, x0:x0 + iw] = w.render("venue", iw, ih)
            self.writer.append_data(self.last)

    def stop(self, w, keep: bool = False) -> None:
        if self.writer is None:
            return
        self.writer.close()
        self.writer = None
        ref = getattr(w, "ref", None)
        if keep or (ref is not None and ref.success):
            os.replace(self.tmp, self.out)
            imageio.imwrite(self.out[:-4] + ".png", self.last)
            self.saved = True
            self.info = {"success": bool(ref.success), "time_s": round(w.t, 2), "stages": list(ref.stages),
                         "metrics": dict(ref.metrics)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--out", default="/out")
    a = ap.parse_args()
    fam, snake = a.family, a.family.replace("-", "_")
    film = Film(os.path.join(a.out, f"{fam}.mp4"))
    reset0, step0 = W.World.reset, W.World.step
    live = {"w": None}

    def reset(self):
        reset0(self)
        live["w"] = self
        film.start(self)

    def step(self, raw):
        done = step0(self, raw)
        if self.k % EVERY == 0 or done:
            film.frame(self)
        if done and self.ref.success:
            for _ in range(12):                    # hold the last frame for half a second
                film.frame(self)
            film.stop(self)
        return done

    W.World.reset, W.World.step = reset, step
    oracle = HERE / "oracles" / fam / "oracle.py"
    source = "reference controller" if oracle.is_file() else "referee test's positive example (injection)"
    try:
        if oracle.is_file():
            from rcb_rfo import Session
            spec = importlib.util.spec_from_file_location("oracle_mod", oracle)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.solve(Session(str(HERE / "instances" / f"{fam}-i00.json")))
        else:
            importlib.import_module(f"test_{snake}").main()
    except BaseException as exc:  # noqa: BLE001 -- a test that fails later still gave its positive
        print("ended with", repr(exc)[:200])
    if not film.saved and live["w"] is not None:   # no success filmed: keep what the last attempt showed
        film.stop(live["w"], keep=True)
        source += " (no successful attempt was filmed: the last attempt)"
    with open(os.path.join(a.out, f"{fam}.json"), "w") as f:
        json.dump({"family": fam, "source": source, **film.info}, f)
    print(json.dumps({"family": fam, "source": source, **film.info}))
    return 0 if film.saved else 1


if __name__ == "__main__":
    sys.exit(main())
