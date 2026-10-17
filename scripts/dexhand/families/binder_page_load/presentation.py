"""Authoring film (not shipped): export exact native poses of a passing replay, then encode Blender frames.

    python presentation.py export --trajectory solution/trajectory.npz --export <dir> [--stride 4]
    blender -b -P studio_renderer.py -- --export <dir> --output <film.mp4> [--frame-step 1]
    python presentation.py encode --export <dir> --output <film.mp4>

Only appearance (materials, bevels, lights, camera) differs from the physics; every rendered pose is a MuJoCo pose of
the replay, sampled every ``stride`` controls; nothing is interpolated or scripted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from runtime import Session
from scene import hands

HERE = Path(__file__).resolve().parent
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=4):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = hands.read_trajectory(trajectory, widths={"sharpa": 28, "wuji": 26}, max_rows=None)
    session = Session(hand=hand)
    m = session.model
    owner = session.checker.geom_owner
    arrays, geoms, meshes, ids = {}, [], {}, []
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0 or int(m.geom_type[gid]) == 0:
            continue
        mid = int(m.geom_matid[gid])
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        ids.append(gid)
        geoms.append({
            "id": gid,
            "name": m.geom(gid).name or f"geom_{gid}",
            "kind": int(m.geom_type[gid]),
            "size": m.geom_size[gid].tolist(),
            "mesh": mesh,
            "owner": str(owner[gid]),
            "body": m.body(int(m.geom_bodyid[gid])).name,
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
        st = session.status()
        frames.append({"step": session.steps, "stage": st["stage"], "success": st["success"],
                       "failure": st["failure"], "state_sha": session.state_sha()})
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    sample()
    for i, action in enumerate(actions):
        session.step(action)
        if (i + 1) % stride == 0 or session.done:
            sample()
        if session.done:
            break
    if not session.success:
        raise RuntimeError("The film requires a passing native replay")
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    payload = {
        "task": "binder_page_load",
        "hand": hand,
        "hand_model": session.hand_info["model"],
        "evidence_type": "physical_actuator_replay",
        "scripted_object_motion": False,
        "trajectory_sha256": sha(trajectory),
        "final_sha": session.state_sha(),
        "success_step": session.steps,
        "source_sha256": {name: sha(HERE / name) for name in PHYSICS_SOURCES},
        "files": {name: sha(directory / name) for name in ("geometry.npz", "poses.npz")},
        "geoms": geoms,
        "meshes": meshes,
        "frames": frames,
        "control_dt": session.control_dt,
        "stride": stride,
        "fps": 25,
        "playback_speed": stride * session.control_dt * 25,
    }
    (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps({"frames": len(frames), "final_sha": payload["final_sha"], "success_step": session.steps}))


def encode(directory, output, crf=24):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    directory, output = Path(directory), Path(output)
    payload = json.loads((directory / "scene.json").read_text())
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    fps = manifest["video_fps"]
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    stages = ["", "rings opened", "pages threaded", "rings closed", "released: success"]
    speed = payload["playback_speed"] * manifest["frame_step"]
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1,
                            ffmpeg_params=["-crf", str(crf), "-preset", "slow", "-pix_fmt", "yuv420p",
                                           "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            draw = ImageDraw.Draw(pic)
            record = payload["frames"][index]
            draw.rounded_rectangle((20, 18, 600, 82), radius=10, fill=(244, 242, 236))
            draw.text((34, 27), "Load punched pages into a ring binder", font=font, fill=(40, 46, 50))
            status = stages[record["stage"]] if record["stage"] else "start"
            draw.text((34, 54), f"{payload['hand_model']} · physics replay, {speed:g}x · stage {record['stage']}/4 "
                      f"{status}", font=small, fill=(80, 96, 104))
            writer.append_data(np.asarray(pic))
        for _ in range(round(fps * 2)):
            writer.append_data(np.asarray(pic))
        pic.save(output.with_suffix(".png"))
    report = {"renderer": "Blender " + manifest["engine"], "presentation_only": True, "scripted_object_motion": False,
              "trajectory_sha256": payload["trajectory_sha256"], "native_final_sha": payload["final_sha"],
              "video_sha256": sha(output), "playback_speed": speed, "render": manifest}
    output.with_suffix(".json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"Encoded {output} ({output.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "encode"])
    parser.add_argument("--trajectory", type=Path, default=HERE / "solution/trajectory.npz")
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--crf", type=int, default=24)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    else:
        encode(args.export, args.output, args.crf)
