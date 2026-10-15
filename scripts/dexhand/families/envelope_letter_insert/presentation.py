"""Authoring film (not shipped): export exact native MuJoCo geom poses of the physical replay, render them with
Blender (studio_renderer.py) and encode an mp4 with a small caption. No pose is synthesized or interpolated.

python presentation.py export --trajectory solution/trajectory.npz --export OUT/export --stride 4
BLENDER=<blender> python presentation.py render --export OUT/export --output OUT/film.mp4 --engine eevee
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np

from replay import load_trajectory
from runtime import Session

HERE = Path(__file__).resolve().parent
BLENDER = os.environ.get("BLENDER", "blender")
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=4):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    arrays, geoms, meshes, ids = {}, {}, {}, []
    from scene import _arm_rig_module

    arm_rig = _arm_rig_module()
    left_hand = arm_rig.hand_body_ids(m, "left")
    robot = arm_rig.robot_body_ids(m) | left_hand
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        name = m.geom(gid).name or f"geom_{gid}"
        bid = int(m.geom_bodyid[gid])
        owner = "robot" if bid in robot else session.owner.get(bid, "world")
        hand_like = owner == "hand" or bid in left_hand
        if hand_like and hand == "wuji" and "_collision" in name:
            continue  # vendor collision meshes are not drawn
        if hand_like and hand == "sharpa" and m.geom_group[gid] != 2:
            continue  # Sharpa: draw the visual meshes only
        if bid in left_hand:
            owner = "left_hand"
        mid = int(m.geom_matid[gid])
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        ids.append(gid)
        geoms[gid] = {
            "id": gid, "name": name, "kind": int(m.geom_type[gid]), "size": m.geom_size[gid].tolist(),
            "mesh": mesh, "owner": owner, "material": m.material(mid).name if mid >= 0 else "",
            "rgba": (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist(),
        }
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va: va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa: fa + fn].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name}
    # Letterhead UVs from scene.py's texcoords (u along the 210 mm width, v along the 99 mm depth), computed in the
    # letter body frame because MuJoCo stores the print mesh in its own principal-axis frame.
    gid = m.geom("letter_print").id
    mesh = int(m.geom_dataid[gid])
    verts = arrays[f"mesh_{mesh}_vertices"]
    d = session.data
    bid = m.body("letter").id
    world = d.geom_xpos[gid] + verts @ d.geom_xmat[gid].reshape(3, 3).T
    local = (world - d.xpos[bid]) @ d.xmat[bid].reshape(3, 3)
    hd, hw = session.config["letter"]["depth_m"] / 2, session.config["letter"]["width_m"] / 2
    arrays[f"mesh_{mesh}_uv"] = np.c_[(local[:, 1] + hw) / (2 * hw), (local[:, 0] + hd) / (2 * hd)]
    np.savez_compressed(directory / "geometry.npz", **arrays)
    frames, positions, rotations = [], [], []

    def sample():
        f = session.features()
        frames.append({"step": session.steps, "state_sha": session.state_sha(), "success": f["success"],
                       "stage": f["stage_completed"], "letter_pos": f["letter_pos"], "envelope_pos": f["envelope_pos"]})
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
        raise RuntimeError("The film requires a passing physical replay")
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    (directory / "letter.png").write_bytes((HERE / "assets/letter.png").read_bytes())
    files = {p.name: sha(p) for p in sorted(directory.iterdir()) if p.is_file() and p.name != "scene.json"}
    payload = {
        "task": "envelope_letter_insert", "hand": hand, "hand_label": session.hand_info["model"],
        "evidence_type": "physical_actuator_replay", "scripted_object_motion": False,
        "trajectory_sha256": sha(trajectory), "final_sha": session.state_sha(), "success_step": session.steps,
        "source_sha256": {n: sha(HERE / n) for n in PHYSICS_SOURCES}, "files": files,
        "geoms": list(geoms.values()), "meshes": meshes, "frames": frames, "stride": stride,
        "control_dt": session.control_dt, "fps": 25, "playback_speed": stride * session.control_dt * 25,
        "letter": session.config["letter"], "envelope": session.config["envelope"],
    }
    (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "success_step": payload["success_step"], "final_sha": payload["final_sha"]}))


def encode(directory, output):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    directory, output = Path(directory), Path(output)
    payload = json.loads((directory / "scene.json").read_text())
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    fps = manifest["video_fps"]
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    speed = payload["playback_speed"] * manifest["frame_step"]
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1,
                            ffmpeg_params=["-crf", "18", "-preset", "slow", "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            draw = ImageDraw.Draw(pic)
            record = payload["frames"][index]
            label = "SUCCESS: letter inside, released" if record["success"] else f"stage {record['stage']}/3"
            draw.rounded_rectangle((20, 18, 600, 82), radius=10, fill=(245, 243, 236))
            draw.text((34, 26), "Put a folded letter into an envelope", font=font, fill=(40, 48, 52))
            draw.text((34, 54), f"{payload['hand_label']} · physics replay, {speed:g}x · {label}", font=small,
                      fill=(80, 98, 92))
            writer.append_data(np.asarray(pic))
        for _ in range(round(fps * 2)):
            writer.append_data(np.asarray(pic))
    pic.save(output.with_suffix(".png"))
    report = {"renderer": "Blender " + manifest["engine"], "presentation_only": True, "scripted_object_motion": False,
              "trajectory_sha256": payload["trajectory_sha256"], "native_final_sha": payload["final_sha"],
              "success_step": payload["success_step"], "playback_speed": speed, "video_sha256": sha(output),
              "render": {k: v for k, v in manifest.items() if k != "measurements"}}
    output.with_suffix(".json").write_text(json.dumps(report, indent=1) + "\n")
    print("Encoded", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "render", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="eevee")
    parser.add_argument("--still", type=int, help="render only this export frame index (look test)")
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "encode":
        encode(args.export, args.output)
    else:
        command = [BLENDER, "-b", "-t", "6", "-P", str(HERE / "studio_renderer.py"), "--", "--export", str(args.export),
                   "--output", str(args.output), "--samples", str(args.samples), "--frame-step", str(args.frame_step),
                   "--engine", args.engine]
        if args.still is not None:
            command += ["--still", str(args.still)]
        with args.output.with_suffix(".render.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, env=os.environ.copy())
        if args.still is None:
            encode(args.export, args.output)
