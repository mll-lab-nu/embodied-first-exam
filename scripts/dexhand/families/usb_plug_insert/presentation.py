"""Authoring only: export exact native poses of a passing replay, render them with Blender, encode the PR film.

Pattern of `assemble_hamburger/presentation.py`: every visible geom transform is sampled from a complete actuator
replay (no pose is synthesized or interpolated); `verify` repeats the physics and checks every sampled transform and
state hash; `render` runs `studio_renderer.py` inside Blender 4.5.3; `encode` adds a small caption and writes H.264.
"""

from __future__ import annotations

import argparse
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np

from replay import load_trajectory
from runtime import Session
from scene import USB

HERE = Path(__file__).resolve().parent
BLENDER = os.environ.get("BLENDER", "blender")  # Blender 4.5.3 LTS (authoring films only)
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py", "assets/usb_scene.json")
MATERIALS = {name: {"rgba": rgba, "metallic": metallic, "roughness": roughness}
             for name, rgba, metallic, roughness in USB["materials"]}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=4):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sources = {name: sha(HERE / name) for name in PHYSICS_SOURCES}
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    owner = session.checker.owner
    arrays, geoms, meshes, ids = {}, {}, {}, []
    for gid in range(m.ngeom):
        name = m.geom(gid).name or f"geom_{gid}"
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0 or (name.startswith(("r_wuji_", "l_wuji_")) and "_collision" in name):
            continue
        mid = int(m.geom_matid[gid])
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        material = m.material(mid).name if mid >= 0 else ""
        ids.append(gid)
        geoms[gid] = {
            "id": gid,
            "name": name,
            "kind": int(m.geom_type[gid]),
            "size": m.geom_size[gid].tolist(),
            "mesh": mesh,
            "owner": owner[int(m.geom_bodyid[gid])],
            "material": material,
            "rgba": (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist(),
            "pbr": MATERIALS.get(material),
        }
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
        frames.append({
            "step": session.steps,
            "time_s": float(session.data.time),
            "state_sha": session.state_sha(),
            "stage": st["stage"],
            "success": st["success"],
            "reason": st["reason"],
            "plug_pos": list(st["plug_pos"]),
            "depth_m": st["target_depth_m"],
        })
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    try:
        sample()
        for i, action in enumerate(actions):
            session.step(action)
            if (i + 1) % stride == 0 or i == len(actions) - 1 or session.done:
                sample()
            if session.done:
                break  # the episode ends at the first success; later rows are not executed
        if not session.success:
            raise RuntimeError("Presentation requires a passing complete native replay")
        np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
        if sources != {name: sha(HERE / name) for name in PHYSICS_SOURCES}:
            raise RuntimeError("Physics sources changed during export")
        files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob("*"))
                 if p.is_file() and p.name in ("geometry.npz", "poses.npz")}
        result = {
            "schema_version": 1,
            "task": "usb_plug_insert",
            "evidence_type": "physical_actuator_replay",
            "scripted_object_motion": False,
            "hand": session.hand,
            "hand_model": session.hand_info["model"],
            "trajectory_sha256": sha(trajectory),
            "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "initial_sha": session.initial_sha,
            "final_sha": session.state_sha(),
            "success_step": session.steps,
            "source_sha256": sources,
            "files": files,
            "geoms": list(geoms.values()),
            "meshes": meshes,
            "frames": frames,
            "control_dt": session.control_dt,
            "stride": stride,
            "fps": 25,
            "playback_speed": round(stride * session.control_dt * 25, 6),
        }
        (directory / "scene.json").write_text(json.dumps(result, indent=1) + "\n")
    finally:
        session.close()
    print(json.dumps({"frames": len(frames), "final_sha": result["final_sha"], "success_step": result["success_step"]}))


def checked_bundle(directory):
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    return payload


def verify(trajectory, directory):
    payload = checked_bundle(directory)
    if sha(trajectory) != payload["trajectory_sha256"]:
        raise ValueError("Trajectory differs from the exported source")
    poses = np.load(Path(directory) / "poses.npz", allow_pickle=False)
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    ids = [g["id"] for g in payload["geoms"]]
    index = 0

    def compare():
        nonlocal index
        record = payload["frames"][index]
        assert record["step"] == session.steps and record["state_sha"] == session.state_sha()
        assert np.array_equal(poses["positions"][index], session.data.geom_xpos[ids])
        assert np.array_equal(poses["rotations"][index], session.data.geom_xmat[ids].reshape(-1, 3, 3))
        index += 1

    try:
        compare()
        for i, action in enumerate(actions):
            session.step(action)
            if index < len(payload["frames"]) and payload["frames"][index]["step"] == i + 1:
                compare()
            if session.done:
                break
        assert index == len(payload["frames"]) and session.state_sha() == payload["final_sha"] and session.success
    finally:
        session.close()
    print(f"Verified {index} exact native pose samples and the passing final state")


def encode(directory, output, crf=23):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    payload = checked_bundle(directory)
    output = Path(output)
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    fps = manifest["video_fps"]
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    speed = manifest["playback_speed"]
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1,
                            ffmpeg_params=["-crf", str(crf), "-preset", "slow", "-pix_fmt", "yuv420p",
                                           "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            record = payload["frames"][index]
            draw = ImageDraw.Draw(pic)
            depth = record["depth_m"] * 1000
            inside = f"port-4 depth {depth:4.1f}/12 mm" if 0 <= depth <= 13 else "plug not in port 4"
            status = "SUCCESS: plug seated in port 4" if record["success"] else f"stage {record['stage']}/3  ·  {inside}"
            draw.rounded_rectangle((20, 18, 470, 92), radius=10, fill=(244, 242, 236))
            draw.text((34, 26), "Connect a USB cable to a hub port", font=font, fill=(36, 42, 48))
            draw.text((34, 50), f"{payload['hand_model']}  ·  physics replay, {speed:g}x", font=small, fill=(70, 86, 96))
            draw.text((34, 69), status, font=small, fill=(40, 110, 70) if record["success"] else (110, 90, 50))
            writer.append_data(np.asarray(pic))
            last = pic
        for _ in range(round(fps * 2)):
            writer.append_data(np.asarray(last))
    last.save(output.with_suffix(".png"))
    report = {
        "renderer": "Blender " + manifest["blender_version"] + " " + manifest["engine"],
        "presentation_only": True,
        "scripted_object_motion": False,
        "trajectory_sha256": payload["trajectory_sha256"],
        "native_final_sha": payload["final_sha"],
        "success_step": payload["success_step"],
        "pose_manifest_sha256": sha(Path(directory) / "scene.json"),
        "video_sha256": sha(output),
        "playback_speed": speed,
        "render": {k: v for k, v in manifest.items() if k != "measurements"},
    }
    output.with_suffix(".json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"Encoded {output} ({output.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "verify", "render", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="eevee")
    parser.add_argument("--crf", type=int, default=23)
    parser.add_argument("--only", help="comma-separated frame indices (preview stills)")
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "verify":
        verify(args.trajectory, args.export)
    elif args.command == "encode":
        encode(args.export, args.output, args.crf)
    else:
        command = [BLENDER, "-b", "-t", "6", "-P", str(HERE / "studio_renderer.py"), "--", "--export",
                   str(args.export), "--output", str(args.output), "--samples", str(args.samples),
                   "--frame-step", str(args.frame_step), "--engine", args.engine]
        if args.only:
            command += ["--only", args.only]
        env = os.environ.copy()
        if not env.get("__EGL_VENDOR_LIBRARY_FILENAMES"):
            library = ctypes.util.find_library("EGL_nvidia")
            if library:
                vendor = args.output.with_suffix(".egl-vendor.json").resolve()
                vendor.write_text(json.dumps({"file_format_version": "1.0.0", "ICD": {"library_path": library}}) + "\n")
                env["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(vendor)
                env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
        with args.output.with_suffix(".render.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, env=env)
        if not args.only:
            encode(args.export, args.output, args.crf)
