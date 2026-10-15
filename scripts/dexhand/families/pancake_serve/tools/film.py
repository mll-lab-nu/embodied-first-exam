"""Authoring only: export exact native poses of a passing replay and encode the Blender studio film.

    python tools/film.py export --trajectory solution/trajectory.npz --export <dir> [--stride 4]
    blender -b -P tools/film_blender.py -- --export <dir> --output <frames dir> [--samples 16]
    python tools/film.py encode --export <dir> --frames <frames dir> --output film.mp4

Poses are sampled from the physical replay (no interpolation, no scripted object motion); Blender only changes
materials, lighting and the camera (the T16 scene film's studio settings).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=4):
    from replay import load_trajectory
    from runtime import Session

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    owner = session.checker.body_owner.copy()
    if getattr(session, "marvin", False):  # Marvin stand and arm links render in their own colours
        from scene import _arm_rig_module

        for b in _arm_rig_module().robot_body_ids(m):
            owner[b] = "robot"
    arrays, geoms, meshes, ids = {}, [], {}, []
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        name = m.geom(gid).name or f"geom_{gid}"
        if name.startswith("r_wuji_") and "_collision" in name:
            continue
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        mid = int(m.geom_matid[gid])
        ids.append(gid)
        geoms.append({"id": gid, "name": name, "kind": int(m.geom_type[gid]), "size": m.geom_size[gid].tolist(),
                      "mesh": mesh, "owner": owner[int(m.geom_bodyid[gid])] or "world",
                      "material": m.material(mid).name if mid >= 0 else "",
                      "rgba": (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist()})
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va:va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa:fa + fn].copy()
            tn = int(m.mesh_texcoordnum[mesh])
            if tn > 0:
                ta = int(m.mesh_texcoordadr[mesh])
                arrays[prefix + "uv"] = m.mesh_texcoord[ta:ta + tn].copy()
                arrays[prefix + "faceuv"] = m.mesh_facetexcoord[fa:fa + fn].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name, "uv": tn > 0}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    frames, positions, rotations = [], [], []

    def sample():
        f = session.features()
        frames.append({"step": session.steps, "stage": f["stage"], "success": f["success"], "failure": f["failure"]})
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
    payload = {"task": "pancake_serve", "hand": hand, "hand_model": session.hand_info["model"],
               "trajectory_sha256": sha(trajectory), "final_sha": session.state_sha(), "stride": stride,
               "control_dt": session.control_dt, "geoms": geoms, "meshes": meshes, "frames": frames,
               "texture": str((HERE / "assets/pancake-browning.png").resolve())}
    payload["files"] = {name: sha(directory / name) for name in ("geometry.npz", "poses.npz")}
    (directory / "scene.json").write_text(json.dumps(payload) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "success": True, "final_sha": payload["final_sha"]}))


def encode(directory, frames_dir, output, speed_note=None):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    payload = json.loads((Path(directory) / "scene.json").read_text())
    frames_dir, output = Path(frames_dir), Path(output)
    fps = round(1 / (payload["control_dt"] * payload["stride"]), 3)  # 1x physics playback
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    stages = ["pancake on the blade", "carried over the plate", "served, turner withdrawn"]
    paths = sorted(frames_dir.glob("*.png"))
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=8,
                            ffmpeg_params=["-crf", "21", "-preset", "slow", "-pix_fmt", "yuv420p",
                                           "-movflags", "+faststart"]) as writer:
        for n, path in enumerate(paths):
            index = int(path.stem)
            record = payload["frames"][index]
            pic = Image.open(path).convert("RGB")
            draw = ImageDraw.Draw(pic)
            idle = "picking up the turner" if record["step"] <= 300 else "approach"
            status = "PASS" if record["success"] else (stages[record["stage"] - 1] if record["stage"] else idle)
            draw.rounded_rectangle((20, 18, 640, 84), radius=10, fill=(244, 241, 232))
            draw.text((34, 26), f"Serve a pancake with a spatula  ·  Tianji Marvin arm + {payload['hand_model']}",
                      font=font, fill=(45, 52, 44))
            draw.text((34, 56), f"{status}  ·  physics replay, {speed_note or '1x'}  ·  t = "
                      f"{record['step'] * payload['control_dt']:.1f} s", font=small, fill=(91, 110, 69))
            frame = np.asarray(pic)
            repeat = round(fps) if n == 0 else (round(fps * 2) if n == len(paths) - 1 else 1)
            for _ in range(repeat):
                writer.append_data(frame)
    print(f"Encoded {output} ({len(paths)} frames at {fps} fps)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--frames", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=4)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    else:
        encode(args.export, args.frames, args.output)
