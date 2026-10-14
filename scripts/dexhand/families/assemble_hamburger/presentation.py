"""Export and audit native hamburger poses, then encode a studio presentation."""

from __future__ import annotations

import argparse
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np

from replay import load_actions
from runtime import Session

HERE = Path(__file__).resolve().parent
BLENDER = os.environ.get("BLENDER", "blender")  # Blender 4.5.3 LTS (authoring films only)
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "replay.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=8):
    if stride < 1:
        raise ValueError("Export stride must be positive")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sources = {name: sha(HERE / name) for name in PHYSICS_SOURCES}
    session = Session()
    m = session.model
    arrays, geoms, meshes = {}, {}, {}
    ids = []
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        mid = int(m.geom_matid[gid])
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        ids.append(gid)
        geoms[gid] = {
            "id": gid,
            "name": m.geom(gid).name or f"geom_{gid}",
            "kind": int(m.geom_type[gid]),
            "size": m.geom_size[gid].tolist(),
            "mesh": mesh,
            "owner": session.owner.get(int(m.geom_bodyid[gid]), "world"),
            "material": m.material(mid).name if mid >= 0 else "",
            "rgba": (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist(),
        }
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va : va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa : fa + fn].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    actions = load_actions(trajectory)
    with np.load(trajectory, allow_pickle=False) as archive:
        phases = archive["phases"].copy() if "phases" in archive else np.full(len(actions), "actuator replay")
    frames, positions, rotations = [], [], []

    def sample(phase):
        frames.append(
            {
                "step": session.steps,
                "time_s": float(session.data.time),
                "phase": str(phase),
                "state_sha": session.state_sha(),
                "features": session.features(),
            }
        )
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    try:
        sample("initial ingredients")
        for i, action in enumerate(actions):
            session.step(action)
            if (i + 1) % stride == 0 or i == len(actions) - 1 or session.done:
                sample(phases[i])
            if session.done:
                break  # the episode ends at the first success (or failure); later rows are not executed
        if not session.success:
            raise RuntimeError("Presentation requires a passing complete native replay")
        np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
        source_dir = directory / "physics_sources"
        source_dir.mkdir(exist_ok=True)
        for name in PHYSICS_SOURCES:
            (source_dir / name).write_bytes((HERE / name).read_bytes())
        if sources != {name: sha(HERE / name) for name in PHYSICS_SOURCES}:
            raise RuntimeError("Physics sources changed during export")
        files = {
            str(p.relative_to(directory)): sha(p)
            for p in sorted(directory.rglob("*"))
            if p.is_file() and p.name != "scene.json"
        }
        result = {
            "schema_version": 1,
            "task": "assemble_hamburger",
            "evidence_type": "physical_actuator_replay",
            "scripted_object_motion": False,
            "trajectory_sha256": sha(trajectory),
            "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "initial_sha": session.initial_sha,
            "final_sha": session.state_sha(),
            "verdict": session.features(),
            "source_sha256": sources,
            "files": files,
            "geoms": list(geoms.values()),
            "meshes": meshes,
            "frames": frames,
            "control_dt": session.control_dt,
            "stride": stride,
            "fps": 25,
            "playback_speed": stride * session.control_dt * 25,
        }
        (directory / "scene.json").write_text(json.dumps(result, indent=2) + "\n")
    finally:
        session.close()
    print(
        json.dumps({"frames": len(frames), "final_sha": result["final_sha"], "success": result["verdict"]["success"]})
    )


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
    pose_positions = poses["positions"]
    pose_rotations = poses["rotations"]
    session = Session()
    ids = [g["id"] for g in payload["geoms"]]
    index = 0

    def compare():
        nonlocal index
        record = payload["frames"][index]
        assert record["step"] == session.steps and record["state_sha"] == session.state_sha()
        assert np.array_equal(pose_positions[index], session.data.geom_xpos[ids])
        assert np.array_equal(pose_rotations[index], session.data.geom_xmat[ids].reshape(-1, 3, 3))
        index += 1

    try:
        compare()
        for i, action in enumerate(load_actions(trajectory)):
            session.step(action)
            if index < len(payload["frames"]) and payload["frames"][index]["step"] == i + 1:
                compare()
            if session.done:
                break
        assert index == len(payload["frames"]) and session.state_sha() == payload["final_sha"] and session.success
    finally:
        session.close()
    print(f"Verified {index} exact native pose samples and the passing final state")


def encode(directory, output):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    payload = checked_bundle(directory)
    directory, output = Path(directory), Path(output)
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    fps = manifest["video_fps"]
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    with imageio.get_writer(
        output,
        fps=fps,
        codec="libx264",
        macro_block_size=1,
        ffmpeg_params=["-crf", "17", "-preset", "fast", "-movflags", "+faststart"],
    ) as writer:
        for index in manifest["indices"]:
            path = frame_dir / f"{index:06d}.png"
            pic = Image.open(path).convert("RGB")
            draw = ImageDraw.Draw(pic)
            record = payload["frames"][min(index, len(payload["frames"]) - 1)]
            f = record["features"]
            label = "PASS" if f["success"] else "ASSEMBLING"
            draw.rounded_rectangle((22, 20, 360, 86), radius=10, fill=(244, 241, 232))
            draw.text((36, 30), "SHARPA WAVE / BURGER ASSEMBLY", font=small, fill=(45, 52, 44))
            draw.text(
                (36, 56), f"{label}  ·  {payload['playback_speed']:g}× physics replay", font=small, fill=(91, 110, 69)
            )
            writer.append_data(np.asarray(pic))
            if index == manifest["indices"][-1]:
                pic.save(output.with_suffix(".png"))
        for _ in range(round(fps * 2)):
            writer.append_data(np.asarray(pic))
    report = {
        "renderer": "Blender " + manifest["engine"],
        "presentation_only": True,
        "scripted_object_motion": False,
        "trajectory_sha256": payload["trajectory_sha256"],
        "native_final_sha": payload["final_sha"],
        "native_verdict": payload["verdict"],
        "pose_manifest_sha256": sha(directory / "scene.json"),
        "video_sha256": sha(output),
        "render": manifest,
        "playback_speed": payload["playback_speed"],
    }
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Encoded {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "verify", "render", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--frame-step", type=int, default=2)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="cycles")
    parser.add_argument("--still", choices=["initial", "final"])
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "verify":
        verify(args.trajectory, args.export)
    elif args.command == "encode":
        encode(args.export, args.output)
    else:
        command = [
            BLENDER,
            "-b",
            "-t",
            "6",
            "-P",
            str(HERE / "studio_renderer.py"),
            "--",
            "--export",
            str(args.export),
            "--output",
            str(args.output),
            "--samples",
            str(args.samples),
            "--frame-step",
            str(args.frame_step),
            "--engine",
            args.engine,
        ]
        if args.still:
            command += ["--still", args.still]
        env = os.environ.copy()
        if args.engine == "eevee" and not env.get("__EGL_VENDOR_LIBRARY_FILENAMES"):
            library = ctypes.util.find_library("EGL_nvidia")
            if library:
                vendor = args.output.with_suffix(".egl-vendor.json").resolve()
                vendor.write_text(json.dumps({"file_format_version": "1.0.0", "ICD": {"library_path": library}}) + "\n")
                env["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(vendor)
                env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
        with args.output.with_suffix(".render.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, env=env)
        if not args.still:
            encode(args.export, args.output)
