#!/usr/bin/env python3
"""Authoring tool: replay a trajectory with the packaged Session and record an evidence video.

Phase 1 replays every row on the CPU (exactly like the verifier: stop at the first success/failure) and keeps the
integration state every `--every-s` simulated seconds. Phase 2 restores those states and renders them with EGL while
holding a GPU lock (`--lock <file>` or `DEXHAND_GPU_LOCK`: an flock shared by the renderers on one host), so the GPU is held for seconds, not for the whole replay.
Rendering never changes the verdict, which is written to the JSON report together with the video metadata.

    PYTHONPATH=<family>:<scripts/dexhand/shared> MUJOCO_GL=egl python tools/record_evidence.py \
        --traj case.npz --out case.mp4 [--label "..."]
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

os.environ.setdefault("MUJOCO_GL", "egl")

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import hands
from runtime import ACTION_DIM, Session


def font(size):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--every-s", type=float, default=0.2, help="simulated seconds between frames")
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--cameras", default="work,overview")
    parser.add_argument("--lock", default=os.environ.get("DEXHAND_GPU_LOCK", os.devnull))
    args = parser.parse_args()
    actions, hand, _ = hands.read_trajectory(args.traj, widths=ACTION_DIM, max_rows=None, max_bytes=200_000_000)
    session = Session(hand=hand)
    every = max(1, int(round(args.every_s / session.control_dt)))
    frames = [(session.physics_state(), session.status())]
    start = time.time()
    session.reset()
    for row in actions:
        if session.checker.done:
            break
        session._advance(row)
        if session.steps % every == 0:
            frames.append((session.physics_state(), session.status()))
    final_status = session.status()
    frames.append((session.physics_state(), final_status))
    verdict = {"status": final_status, "state_sha": session.state_sha(), "features": session.features(),
               "replay_seconds": time.time() - start, "rows": int(len(actions)), "hand": hand}
    cameras = args.cameras.split(",")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    big, small = font(18), font(15)
    software = os.environ.get("MUJOCO_GL") == "osmesa"  # CPU rendering (e.g. inside eai-dexhand): no GPU lock
    with open(os.devnull if software else args.lock, "a") as lock:
        if not software:
            fcntl.flock(lock, fcntl.LOCK_EX)
        renderers = mujoco.Renderer(session.model, height=480, width=640)
        with imageio.get_writer(args.out, fps=args.fps, codec="libx264", macro_block_size=16, quality=8) as writer:
            for index, (state, status) in enumerate(frames):
                mujoco.mj_setState(session.model, session.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
                mujoco.mj_forward(session.model, session.data)
                views = []
                for camera in cameras:
                    renderers.update_scene(session.data, camera=camera)
                    renderers.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = not software
                    views.append(renderers.render().copy())
                image = Image.fromarray(np.concatenate(views, axis=1))
                draw = ImageDraw.Draw(image)
                if status["success"]:
                    verdict_text, color = "SUCCESS", (110, 230, 140)
                elif status["failed"]:
                    verdict_text, color = "FAIL: " + status["reason"], (250, 120, 110)
                elif index == len(frames) - 1:
                    verdict_text, color = "rows ended: NO SUCCESS", (250, 120, 110)
                else:
                    verdict_text, color = "in progress", (240, 220, 150)
                draw.rectangle((0, 0, image.width, 58), fill=(18, 24, 32))
                draw.text((10, 6), f"sweep_dustpan | {hand} | t = {status['time_s']:.2f} s | debris in pan "
                          f"{status['in_pan']}/6 | {verdict_text}", font=big, fill=color)
                draw.text((10, 33), (args.label + " | " if args.label else "")
                          + f"native replay, {args.every_s * args.fps:g}x", font=small, fill=(220, 226, 235))
                frame = np.asarray(image)
                writer.append_data(frame)
                if index == len(frames) - 1:
                    for _ in range(args.fps * 2):
                        writer.append_data(frame)
        renderers.close()
    verdict["video"] = {"path": str(args.out), "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
                        "frames": len(frames) + args.fps * 2, "fps": args.fps,
                        "playback_speed": args.every_s * args.fps, "cameras": cameras}
    args.out.with_suffix(".json").write_text(json.dumps(verdict, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"status": final_status, "video": str(args.out)}))
    session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
