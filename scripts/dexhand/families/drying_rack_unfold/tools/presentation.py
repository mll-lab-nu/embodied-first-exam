"""Export exact native drying-rack poses for the Blender PR film, then encode the rendered frames.

  python tools/presentation.py export --trajectory solution/trajectory.npz --export <dir> [--stride 4]
  blender -b -P tools/studio_renderer.py -- --export <dir> --output <film.mp4> [--samples 32] [--engine cycles]
  python tools/presentation.py encode --export <dir> --output <film.mp4>

The export replays the trajectory with the frozen runtime (every control) and stores world poses of every drawn geom
every `stride` controls; the renderer only places those geoms (no interpolation, no synthesized motion).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from replay import load_trajectory  # noqa: E402
from runtime import Session  # noqa: E402

PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=4):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    arrays, geoms, meshes, ids = {}, [], {}, []
    rack = set(session.checker.rack_bodies.tolist())
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        body = int(m.geom_bodyid[gid])
        owner = "hand" if body in session.checker.hand_bodies else "rack" if body in rack else "world"
        mid = int(m.geom_matid[gid])
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        ids.append(gid)
        geoms.append({
            "id": gid, "name": m.geom(gid).name or f"geom_{gid}", "kind": int(m.geom_type[gid]),
            "size": m.geom_size[gid].tolist(), "mesh": mesh, "owner": owner,
            "material": m.material(mid).name if mid >= 0 else "",
            "rgba": (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist(),
        })
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va: va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa: fa + fn].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    frames, positions, rotations = [], [], []

    def sample():
        f = session.features()
        frames.append({"step": session.steps, "time_s": float(session.data.time), "state_sha": session.state_sha(),
                       "stage": f["stage"], "stage_name": f["stage_name"], "success": f["success"],
                       "failure": f["failure"], "hold": f["released_hold_steps"]})
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    sample()
    for i, action in enumerate(actions):
        session.step(action)
        if (i + 1) % stride == 0 or session.done:
            sample()
        if session.done:
            break
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    result = {
        "schema_version": 1, "task": "drying_rack_unfold", "hand": hand,
        "evidence_type": "physical_actuator_replay", "scripted_object_motion": False,
        "trajectory_sha256": sha(trajectory), "final_sha": session.state_sha(), "success": session.success,
        "failure": session.failure, "source_sha256": {n: sha(HERE.parent / n) for n in PHYSICS_SOURCES},
        "geoms": geoms, "meshes": meshes, "frames": frames, "control_dt": session.control_dt, "stride": stride,
        "files": {n: sha(directory / n) for n in ("geometry.npz", "poses.npz")},
    }
    (directory / "scene.json").write_text(json.dumps(result, indent=1) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "success": result["success"], "failure": result["failure"],
                      "final_sha": result["final_sha"]}))


def encode(directory, output, fps, title, speed_note):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    directory, output = Path(directory), Path(output)
    payload = json.loads((directory / "scene.json").read_text())
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    hand = "SHARPA WAVE" if payload["hand"] == "sharpa" else "WUJI HAND 2.2"
    speed = payload["stride"] * payload["control_dt"] * fps * manifest.get("frame_step", 1)
    last = None
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1,
                            ffmpeg_params=["-crf", "23", "-preset", "slow", "-pix_fmt", "yuv420p",
                                           "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            record = payload["frames"][index]
            draw = ImageDraw.Draw(pic)
            status = ("PASS" if record["success"] else ("FAIL: " + record["failure"]) if record["failure"]
                      else ["in progress", "unfolded", "standing", "released hold"][min(record["stage"], 3)])
            draw.rounded_rectangle((20, 18, 470, 88), radius=10, fill=(244, 241, 232))
            draw.text((34, 27), title, font=font, fill=(45, 52, 44))
            draw.text((34, 56), f"{hand}  ·  {status}  ·  physics replay, {speed:g}x {speed_note}", font=small,
                      fill=(91, 110, 69))
            arr = np.asarray(pic)
            writer.append_data(arr)
            last = pic
        for _ in range(round(fps * 2)):
            writer.append_data(np.asarray(last))
    last.save(output.with_suffix(".png"))
    report = {"renderer": manifest.get("engine"), "presentation_only": True, "scripted_object_motion": False,
              "trajectory_sha256": payload["trajectory_sha256"], "native_final_sha": payload["final_sha"],
              "success": payload["success"], "video_sha256": sha(output), "playback_speed": speed,
              "frames": len(manifest["indices"]), "render": {k: v for k, v in manifest.items() if k != "indices"}}
    output.with_suffix(".json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"video": str(output), "bytes": output.stat().st_size, "speed": speed}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["export", "encode"])
    p.add_argument("--trajectory", type=Path)
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--stride", type=int, default=4)
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--title", default="UNFOLD A FOLDING SWEATER DRYER")
    p.add_argument("--speed-note", default="")
    a = p.parse_args()
    if a.command == "export":
        export(a.trajectory, a.export, a.stride)
    else:
        encode(a.export, a.output, a.fps, a.title, a.speed_note)
