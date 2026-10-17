"""Authoring film: export exact native poses of a successful replay, render them in Blender, encode an mp4.

Presentation only: every pose comes from a fresh actuator replay of the trajectory (no interpolation, no scripted
object motion); the export is re-checked against a second replay with `verify`.

    python presentation.py export --trajectory solution/trajectory.npz --export out/jar-export [--hand sharpa]
    python presentation.py verify --trajectory solution/trajectory.npz --export out/jar-export
    python presentation.py render --export out/jar-export --output out/jar.mp4     # Blender 4.5.3, Cycles OptiX
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
from scene import arm_rig

HERE = Path(__file__).resolve().parent
BLENDER = os.environ.get("BLENDER", "blender")
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=2):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    owner = session.checker.owner
    left_hand = set(arm_rig.hand_body_ids(m, "left"))
    arrays, geoms, meshes, ids = {}, [], {}, []
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        name = m.geom(gid).name or f"geom_{gid}"
        if name.startswith(("r_wuji_", "l_wuji_")) and "_collision" in name:
            continue  # the Wuji vendor's translucent collision proxies; its visual meshes are kept
        mid = int(m.geom_matid[gid])
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        ids.append(gid)
        geoms.append({
            "id": gid, "name": name, "kind": int(m.geom_type[gid]), "size": m.geom_size[gid].tolist(), "mesh": mesh,
            # the parked left hand is drawn like the arm (it never acts; it is kept out of the camera framing)
            "owner": "arm" if int(m.geom_bodyid[gid]) in left_hand else
            ["other", "jar", "lid", "hand", "worktop", "floor", "arm"][int(owner[gid])],
            "material": m.material(mid).name if mid >= 0 else "",
            "rgba": (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist(),
        })
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va:va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa:fa + fn].copy()
            ta, tn = int(m.mesh_texcoordadr[mesh]), int(m.mesh_texcoordnum[mesh])
            has_uv = ta >= 0 and tn > 0
            if has_uv:
                arrays[prefix + "uv"] = m.mesh_texcoord[ta:ta + tn].copy()
                arrays[prefix + "face_uv"] = m.mesh_facetexcoord[fa:fa + fn].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name, "has_uv": bool(has_uv)}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    with np.load(trajectory, allow_pickle=False) as archive:
        phases = archive["phases"].copy() if "phases" in archive.files else np.full(len(actions), "actuator replay")
    frames, positions, rotations = [], [], []

    def sample(phase):
        f = session.features()
        frames.append({"step": session.steps, "time_s": float(session.data.time), "phase": str(phase),
                       "state_sha": session.state_sha(),
                       "features": {k: f[k] for k in ("stage", "hold_steps", "turn_rad", "success", "failure",
                                                      "positions")}})
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    try:
        sample("initial state")
        for i, action in enumerate(actions):
            session.step(action)
            if (i + 1) % stride == 0 or session.done:
                sample(phases[i])
            if session.done:
                break
        if not session.success:
            raise RuntimeError("The film requires a passing native replay")
        np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
        files = {p.name: sha(p) for p in (directory / "geometry.npz", directory / "poses.npz")}
        payload = {
            "schema_version": 1, "task": "jar_lid_open", "hand": hand, "hand_model": session.hand_info["model"],
            "evidence_type": "physical_actuator_replay", "scripted_object_motion": False,
            "trajectory_sha256": sha(trajectory), "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "final_sha": session.state_sha(), "source_sha256": {n: sha(HERE / n) for n in PHYSICS_SOURCES},
            "files": files, "geoms": geoms, "meshes": meshes, "frames": frames, "control_dt": session.control_dt,
            "stride": stride, "label_texture": str((HERE / "assets/label.png").resolve()),
        }
        (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    finally:
        session.close()
    print(json.dumps({"frames": len(frames), "final_sha": payload["final_sha"], "success": True}))


def verify(trajectory, directory):
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    poses = np.load(directory / "poses.npz", allow_pickle=False)
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    ids = [g["id"] for g in payload["geoms"]]
    index = 0

    def compare():
        nonlocal index
        record = payload["frames"][index]
        assert record["step"] == session.steps and record["state_sha"] == session.state_sha()
        assert np.array_equal(poses["positions"][index], session.data.geom_xpos[ids])
        index += 1

    compare()
    for action in actions:
        session.step(action)
        if index < len(payload["frames"]) and payload["frames"][index]["step"] == session.steps:
            compare()
        if session.done:
            break
    assert index == len(payload["frames"]) and session.success and session.state_sha() == payload["final_sha"]
    print(f"Verified {index} exact native pose samples and the passing final state")


def encode(directory, output, fps, hold_s=2.0):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    directory, output = Path(directory), Path(output)
    payload = json.loads((directory / "scene.json").read_text())
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    speed = payload["stride"] * payload["control_dt"] * fps * manifest["frame_step"]
    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 19)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1, pixelformat="yuv420p",
                            ffmpeg_params=["-crf", "18", "-preset", "slow", "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            draw = ImageDraw.Draw(pic, "RGBA")
            f = payload["frames"][index]["features"]
            status = "PASS: lid set aside" if f["success"] else (
                f"stage {f['stage']}/3 | lid turn {f['turn_rad']:.2f} rad")
            draw.rounded_rectangle((20, 18, 520, 84), radius=10, fill=(250, 248, 242, 225))
            draw.text((34, 26), "Open a jam jar", font=title_font, fill=(52, 40, 36))
            draw.text((34, 56), f"{payload['hand_model']} | physics replay, {speed:g}x | {status}", font=font,
                      fill=(110, 52, 40))
            writer.append_data(np.asarray(pic))
        for _ in range(round(fps * hold_s)):
            writer.append_data(np.asarray(pic))
    pic.save(output.with_suffix(".png"))
    report = {"renderer": manifest["blender_version"], "presentation_only": True, "scripted_object_motion": False,
              "trajectory_sha256": payload["trajectory_sha256"], "native_final_sha": payload["final_sha"],
              "playback_speed": speed, "video_sha256": sha(output), "render": manifest}
    output.with_suffix(".json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"Encoded {output} ({output.stat().st_size / 1e6:.1f} MB, {speed:g}x)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "verify", "render", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "verify":
        verify(args.trajectory, args.export)
    elif args.command == "encode":
        encode(args.export, args.output, args.fps)
    else:
        command = [BLENDER, "-b", "-P", str(HERE / "studio_renderer.py"), "--", "--export", str(args.export),
                   "--output", str(args.output), "--samples", str(args.samples), "--frame-step",
                   str(args.frame_step), "--limit", str(args.limit)]
        with args.output.with_suffix(".render.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        if not args.limit:
            encode(args.export, args.output, args.fps)
