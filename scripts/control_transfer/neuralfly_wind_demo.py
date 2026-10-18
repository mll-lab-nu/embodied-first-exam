"""Operator-only replay of recorded wind truth; never exported to task packages."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_episode(folder):
    folder = Path(folder)
    record = json.loads((folder / "record.json").read_text())
    if record.get("revision") != "neuralfly-cpu/4" or record["dynamics"].get("dynamics_revision") != "vector-wind/1":
        raise ValueError("A vector-wind/1 private episode is required")
    with np.load(folder / "trajectory.npz", allow_pickle=False) as archive:
        state = archive["state"]
    with np.load(folder / "wind.npz", allow_pickle=False) as archive:
        times, velocity = archive["time"], archive["velocity_world"]
    if (
        state.ndim != 2
        or state.shape[1] != 18
        or len(state) == 0
        or times.shape != (len(state),)
        or velocity.shape != (len(state), 3)
        or not np.isfinite(state).all()
        or not np.isfinite(velocity).all()
        or not np.array_equal(times, state[:, 0])
        or not np.allclose(np.diff(times), 0.02, rtol=0, atol=1e-9)
        or hashlib.sha256(state.tobytes()).hexdigest() != record["state_sha256"]
    ):
        raise ValueError("Mismatched, corrupt or nonfinite private wind/state trace")
    return record, state, velocity


def render(folder, output, assets):
    # Keep evidence creation separate from the canonical agent video, including links.
    folder, output = Path(folder).resolve(), Path(output).resolve()
    if output.name == "video.mp4" or output.exists():
        raise ValueError("Use a new operator-demo filename; never overwrite an evaluation video")
    if os.environ.get("MUJOCO_GL") != "osmesa":
        raise RuntimeError("Operator replay requires MUJOCO_GL=osmesa")
    import mujoco
    from mujoco import gl_context
    from PIL import Image, ImageDraw, ImageFont
    from .control_public.fly import target
    from .neuralfly_visual import COMMIT, FILES, render_model

    if gl_context.GLContext.__module__ != "mujoco.osmesa":
        raise RuntimeError("Software OSMesa rendering is required")
    hashes = {name: digest(folder / name) for name in ("record.json", "trajectory.npz", "wind.npz")}
    record, states, winds = load_episode(folder)
    command = record["scenario"]["trajectory"]
    model = render_model(assets)
    data = mujoco.MjData(model)
    width, height, fps = 1280, 720, 10
    model.vis.global_.offwidth, model.vis.global_.offheight = width, height
    model.vis.quality.offsamples = 0
    renderer = mujoco.Renderer(model, height, width)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = np.array(command["center"]) + [0, 0, 0.1]
    camera.distance, camera.azimuth, camera.elevation = 5.6, 110, -27
    curve = [target(t, **command)[0] for t in np.linspace(0, 2 * np.pi / command["rate"], 120, endpoint=False)]
    font = ImageFont.load_default(size=19)
    title = ImageFont.load_default(size=25)
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-n",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        stdin=subprocess.PIPE,
    )
    samples = []

    def geom(kind, position, size, color, end=None):
        scene = renderer.scene
        item = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(item, kind, np.full(3, size), position, np.eye(3).ravel(), np.array(color))
        if end is not None:
            mujoco.mjv_connector(item, kind, size, position, end)
        scene.ngeom += 1

    try:
        for frame, index in enumerate(range(0, len(states), 5)):
            row, wind = states[index], winds[index]
            data.qpos[:], data.time = row[1:8], float(row[0])
            model.site_pos[0] = target(float(row[0]), **command)[0]
            mujoco.mj_forward(model, data)  # Pose-only renderer; no dynamics stepping.
            renderer.update_scene(data, camera=camera)
            renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
            for point in curve:
                geom(mujoco.mjtGeom.mjGEOM_SPHERE, point, 0.012, [0.2, 0.7, 0.65, 0.7])
            if np.linalg.norm(wind) > 1e-12:
                geom(mujoco.mjtGeom.mjGEOM_ARROW, row[1:4], 0.022, [1, 0.3, 0.12, 1], row[1:4] + 0.1 * wind)
                for offset in ([-1.2, 0, -0.7], [0, 0, -0.7], [1.2, 0, -0.7]):
                    origin = np.array(command["center"]) + offset
                    geom(mujoco.mjtGeom.mjGEOM_ARROW, origin, 0.018, [0.1, 0.75, 1, 0.8], origin + 0.1 * wind)
            image = Image.fromarray(renderer.render())
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((18, 18, 750, 170), radius=12, fill=(17, 25, 38))
            draw.text((36, 28), "RECORDED WIND  /  operator-only replay", font=title, fill=(240, 245, 255))
            draw.text(
                (36, 65),
                f"t = {row[0]:.2f} s    Speed = {np.linalg.norm(wind):.2f} m/s",
                font=font,
                fill=(115, 221, 255),
            )
            draw.text(
                (36, 95),
                f"World velocity [x,y,z]: [{wind[0]:+.2f}, {wind[1]:+.2f}, {wind[2]:+.2f}] m/s",
                font=font,
                fill=(220, 228, 240),
            )
            draw.text(
                (36, 129), "Arrows point TOWARD airflow travel; 0.10 m arrow per m/s", font=font, fill=(255, 153, 111)
            )
            draw.rectangle((0, height - 62, width, height), fill=(17, 25, 38))
            draw.text(
                (24, height - 53),
                "Synthetic vector drag, not flight-calibrated. Skydio appearance only.",
                font=font,
                fill=(220, 228, 240),
            )
            draw.text(
                (24, height - 28), "PRIVATE WIND TRUTH  |  Not coding-agent feedback", font=font, fill=(255, 153, 111)
            )
            writer.stdin.write(image.tobytes())
            samples.append(
                {"frame": frame, "state_index": index, "time_s": float(row[0]), "velocity_world_m_s": wind.tolist()}
            )
    finally:
        renderer.close()
        writer.stdin.close()
        try:
            code = writer.wait(timeout=60)
        except subprocess.TimeoutExpired:
            writer.kill()
            writer.wait()
            raise
    if code:
        raise RuntimeError("Operator video encoding failed")
    if any(digest(folder / name) != value for name, value in hashes.items()):
        raise RuntimeError("Input evidence changed during rendering")
    receipt = {
        "schema": "neuralfly-operator-wind-demo/1",
        "operator_only": True,
        "description": "Recorded world air velocity, not force or measured real-world wind. Synthetic vector-wind/1 dynamics.",
        "input_sha256": hashes,
        "video_sha256": digest(output),
        "frames": len(samples),
        "resolution": [width, height],
        "fps": fps,
        "samples": samples,
        "visual_assets": {"commit": COMMIT, "sha256": FILES},
    }
    output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    result = render(args.episode, args.output, args.assets)
    print(json.dumps({key: result[key] for key in ("frames", "resolution", "video_sha256")}))
