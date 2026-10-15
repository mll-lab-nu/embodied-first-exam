"""Authoring preview (not shipped): MuJoCo offscreen 1280x720 film of a trajectory replay with an inset ring view."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

STAGES = ["start", "rings opened", "pages placed", "rings closed", "released 1 s hold: SUCCESS"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--camera", default="overview")
    ap.add_argument("--inset", default="rings")
    ap.add_argument("--frames", default="", help="comma-separated control indices to also save as PNG")
    ap.add_argument("--render-from", type=int, default=0, help="first control rendered (physics always from reset)")
    ap.add_argument("--render-to", type=int, default=10**9, help="last control rendered; the closing hold is added "
                    "only when the episode ends inside the rendered range")
    args = ap.parse_args()
    import imageio.v2 as imageio

    actions, hand, _ = hands.read_trajectory(args.traj, widths={"sharpa": 28, "wuji": 26}, max_rows=None)
    s = Session(hand=hand)
    s.model.vis.quality.offsamples = 2
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    keep = {int(x) for x in args.frames.split(",") if x}
    out = Path(args.video)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(out, fps=args.fps, codec="libx264", quality=8, macro_block_size=16)
    stride = max(1, round(1 / (s.control_dt * args.fps)))

    def frame(st, i):
        main_img = Image.fromarray(s.render_frame(args.camera, 1280, 720))
        inset = Image.fromarray(s.render_frame(args.inset, 448, 252)).copy()
        main_img.paste(inset, (1280 - 448 - 14, 14))
        draw = ImageDraw.Draw(main_img)
        draw.rectangle((1280 - 448 - 16, 12, 1280 - 12, 12 + 254), outline=(255, 255, 255), width=2)
        label = "FAIL: " + st["failure"] if st["failure"] else STAGES[st["stage"]]
        draw.rectangle((0, 0, 760, 74), fill=(24, 30, 36))
        draw.text((14, 8), f"{s.hand_info['model']} | load punched pages into a ring binder | t={i * s.control_dt:5.2f} s",
                  font=font, fill="white")
        draw.text((14, 42), f"stage {st['stage']}/4: {label} | rings {st['toggles_rad'][1]:.2f} rad | "
                  f"threaded {sum(st['open_threaded'])}/6 linked {sum(st['linked'])}/6", font=small, fill=(240, 215, 160))
        return np.asarray(main_img)

    st = s.status()
    img = None
    if args.render_from == 0:
        img = frame(st, 0)
        writer.append_data(img)
    for i, a in enumerate(actions):
        st = s.step(a)
        if not args.render_from <= i + 1 <= args.render_to:
            if s.done or i + 1 > args.render_to:
                break
            continue
        if (i + 1) % stride == 0 or s.done:
            img = frame(st, i + 1)
            writer.append_data(img)
            if i + 1 in keep:
                Image.fromarray(img).save(out.with_name(out.stem + f"_frame{i + 1:05d}.png"))
        if s.done:
            break
    if s.done and img is not None and s.steps <= args.render_to:
        for _ in range(args.fps * 2):
            writer.append_data(img)
        Image.fromarray(img).save(out.with_name(out.stem + "_final.png"))
    writer.close()
    print(json.dumps({"video": str(out), "steps": s.steps, "success": s.success, "reason": st["reason"],
                      "state_sha": s.state_sha()}))


if __name__ == "__main__":
    main()
