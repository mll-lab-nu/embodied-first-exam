"""Replay video of a privileged trajectory (PROTOCOL §4: every graded trial leaves a replay video).

    python /tests/render_video.py --task lack --traj /app/output/trajectory.npz --out /logs/verifier/replay.mp4

Evidence for people only, never the verdict: the grader (grade.py) runs this in its own process next to the two verdict
replays and ignores its result. It replays the rows exactly as the grader does (rcb_ikea.Session.step: the joint-speed
clamp, 4 physics steps, the scene's mechanism), then holds the last row for the grader's settle time, and renders
MuJoCo's free camera on the work surface (tests/video_view.json: the standard twin's rig centre, front and scale; from the
front, 25 degrees to the side, 35 degrees above; no shadows) with CPU software rendering (OSMesa; the verifier has no
GPU) at 512 x 288. At most MAX_FRAMES frames, evenly spaced over the episode, played at 25 fps (a
time-lapse for long episodes; replay.json says the simulated seconds per frame). Writes <out> (H.264 mp4),
<out without .mp4>.last.png and <out without .mp4>.json (frames, stride, the end state hash = the verdict replays').
"""
from __future__ import annotations
import argparse, json, os, sys, time

os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
os.environ.setdefault("LP_NUM_THREADS", "2")      # llvmpipe: leave the CPUs to the verdict replays
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import mujoco  # noqa: E402
import rcb_ikea as R  # noqa: E402

MAX_FRAMES = 750
W, H, FPS = 512, 288, 25


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--traj", required=True)
    ap.add_argument("--scene-dir", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t0 = time.time()
    import imageio.v2 as imageio
    s = R.Session(a.task, a.scene_dir)
    ctrl = R.load_trajectory(a.traj, s.nu, s.timestep)
    hold = int(round(R.SETTLE_S / s.control_dt))
    n = len(ctrl) + hold
    stride = max(1, -(-n // MAX_FRAMES))
    m = s.model
    m.vis.global_.offwidth, m.vis.global_.offheight = max(W, m.vis.global_.offwidth), max(H, m.vis.global_.offheight)
    r = mujoco.Renderer(m, height=H, width=W)
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    view = json.load(open(os.path.join(HERE, "video_view.json")))
    fx, fy = view["front"]
    cam.lookat[:] = view["center"]
    cam.distance = 1.8 * float(view["scale"])
    cam.azimuth = float(np.degrees(np.arctan2(-fy, -fx))) + 25.0     # looking back at the centre from the front side
    cam.elevation = -35.0
    r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
    base = os.path.splitext(a.out)[0]
    tmp = base + ".part.mp4"
    w = imageio.get_writer(tmp, fps=FPS, codec="libx264", quality=7, macro_block_size=8, ffmpeg_log_level="error")
    frames, frame = 0, None

    def shot():
        nonlocal frames, frame
        r.update_scene(s.data, camera=cam)
        frame = r.render()
        w.append_data(frame)
        frames += 1

    shot()
    for i, row in enumerate(np.asarray(ctrl, dtype=np.float64)):
        s.step(row)
        if (i + 1) % stride == 0:
            shot()
    end_sha = s.state_sha()
    last = s.rows[-1] if s.rows else s.hold_action()
    for k in range(hold):
        s.data.ctrl[:] = s.applied(last)
        s.S.step(R.SUBSTEPS)
        if (len(ctrl) + k + 1) % stride == 0:
            shot()
    shot()
    w.close()
    os.replace(tmp, a.out)
    imageio.imwrite(base + ".last.png", frame)
    with open(base + ".json", "w") as f:
        json.dump({"task": a.task, "frames": frames, "fps": FPS, "rows": len(ctrl), "settle_rows": hold, "stride_rows": stride,
                   "sim_s_per_frame": stride * s.control_dt, "size": [W, H], "renderer": os.environ.get("MUJOCO_GL"),
                   "end_state_sha": end_sha, "wall_s": round(time.time() - t0, 1)}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
