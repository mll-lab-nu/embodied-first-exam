"""Authoring-only MuJoCo preview: replay rows (physics only) and render 1280x720 with a caption bar."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

VIEWS = {
    "wide": dict(lookat=(0.04, 0.0, 0.33), distance=0.62, azimuth=118, elevation=-38),
    "remote": dict(lookat=(-0.02, 0.0, 0.33), distance=0.36, azimuth=125, elevation=-42),
}


def caption(frame, lines):
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    draw.rectangle((0, 0, img.width, 34 * len(lines) + 12), fill=(20, 26, 30, 200))
    for i, (text, color) in enumerate(lines):
        draw.text((16, 8 + 34 * i), text, font=font, fill=color)
    return np.asarray(img)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--traj", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--phases")
    p.add_argument("--view", default="wide", choices=sorted(VIEWS))
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--frames", nargs="*", type=int, default=[], help="control steps to save as PNG stills")
    a = p.parse_args()
    actions, hand, _ = hands.read_trajectory(a.traj, widths={"sharpa": 58, "wuji": 54}, max_rows=6000,
                                             task="remote_battery_swap")
    phases = np.load(a.phases)["phases"] if a.phases else np.full(len(actions), "actuator replay")
    s = Session(hand=hand)
    m = s.model
    for gid in range(m.ngeom):  # hide Wuji's translucent collision meshes in previews (drawing only)
        name = m.geom(gid).name or ""
        if name.startswith("r_wuji_") and "_collision" in name:
            m.geom_rgba[gid, 3] = 0.0
    renderer = mujoco.Renderer(m, height=720, width=1280)
    cam = mujoco.MjvCamera()
    for k, v in VIEWS[a.view].items():
        setattr(cam, k, v) if k != "lookat" else cam.lookat.__setitem__(slice(None), v)
    stride = max(1, round(1 / (s.control_dt * a.fps)))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(out, fps=a.fps, codec="libx264", quality=8, macro_block_size=16)
    label = s.hand_info["model"]

    def frame(phase):
        renderer.update_scene(s.data, cam)
        f = s.features()
        state = "SUCCESS" if s.success else ("FAIL: " + s.failure if s.failure else "running")
        color = (140, 230, 150) if s.success else ((255, 140, 120) if s.failure else (240, 240, 240))
        lat = f.get("stages_latched", {})
        marks = " ".join(("[x] " if lat.get(k) else "[ ] ") + k.replace("_", " ") for k in
                         ("cover_open", "old_cell_in_tray", "new_cell_seated", "cover_closed"))
        return caption(renderer.render(), [
            (f"{label} | remote battery swap | physics replay 1x | step {s.steps} | {state}", color),
            (f"{marks} | hold {f.get('hold_steps', 0)}/50", (244, 214, 157)),
            (str(phase)[:90], (190, 205, 195)),
        ])

    writer.append_data(frame("initial state"))
    stills = {}
    for i, row in enumerate(actions):
        s.step(row)
        if (i + 1) % stride == 0 or s.done:
            img = frame(phases[i] if i < len(phases) else "")
            writer.append_data(img)
            if s.steps in a.frames or (s.done and "final" not in stills):
                stills[s.steps if s.steps in a.frames else "final"] = img
        elif s.steps in a.frames:
            stills[s.steps] = frame(phases[i])
        if s.done:
            break
    last = frame("final state (episode ended)" if s.done else "rows exhausted")
    for _ in range(a.fps * 2):
        writer.append_data(last)
    writer.close()
    stills.setdefault("final", last)
    paths = []
    for k, img in stills.items():
        path = out.with_name(f"{out.stem}_step{k}.png")
        Image.fromarray(img).save(path)
        paths.append(str(path))
    print(json.dumps({"video": str(out), "success": s.success, "failure": s.failure, "steps": s.steps,
                      "frames": paths, "detail": s.failure_detail}))
    renderer.close()


if __name__ == "__main__":
    main()
