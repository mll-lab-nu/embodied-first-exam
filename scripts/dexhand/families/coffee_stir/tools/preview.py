"""Authoring preview: replay a trajectory and write a 1280x720 MuJoCo film with the verdict overlay (evidence only)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the family folder (runtime, scene, checker, replay)

os.environ.setdefault("MUJOCO_GL", "egl")
import imageio.v2 as imageio
import numpy as np

from replay import WIDTHS, load_trajectory, overlay
from runtime import Session


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--traj", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--camera", default="overview")
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--phases", help="optional .npy of per-row phase labels")
    p.add_argument("--frames", help="comma-separated control steps to save as PNG stills")
    a = p.parse_args()
    actions, hand, _ = load_trajectory(a.traj, allow_empty=False)
    s = Session(hand=hand)
    m = s.model
    for g in range(m.ngeom):
        if s.checker.hand_geom[g] and (m.geom(g).name or "").startswith("r_wuji_") and "_collision" in m.geom(g).name:
            m.geom_rgba[g, 3] = 0.0
    phases = np.load(a.phases) if a.phases else np.full(len(actions), "actuator replay")
    stills = {int(x) for x in a.frames.split(",")} if a.frames else set()
    stride = round(1 / (s.control_dt * a.fps))
    video = Path(a.video)
    video.parent.mkdir(parents=True, exist_ok=True)
    label = s.hand_info["model"]
    writer = imageio.get_writer(video, fps=a.fps, codec="libx264", quality=8, macro_block_size=16)
    writer.append_data(overlay(s.render_frame(a.camera, 1280, 720), s.features(), "initial state", label))
    for i, row in enumerate(actions):
        f = s.step(row)
        if (i + 1) % stride == 0 or s.done or (i + 1) in stills:
            frame = overlay(s.render_frame(a.camera, 1280, 720), f, str(phases[i]) if i < len(phases) else "", label)
            if (i + 1) % stride == 0 or s.done:
                writer.append_data(frame)
            if (i + 1) in stills:
                imageio.imwrite(video.with_name(f"{video.stem}_step{i + 1:04d}.png"), frame)
        if s.done:
            break
    final = overlay(s.render_frame(a.camera, 1280, 720), s.features(), "final state", label)
    for _ in range(a.fps * 2):
        writer.append_data(final)
    imageio.imwrite(video.with_name(f"{video.stem}_final.png"), final)
    writer.close()
    st = s.status()
    out = {k: st[k] for k in ("success", "reason", "steps", "stage", "hand", "failure_detail", "revolutions")}
    out.update({"state_sha": s.state_sha(), "video": str(video), "camera": a.camera, "fps": a.fps, "size": [1280, 720]})
    video.with_suffix(".json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
