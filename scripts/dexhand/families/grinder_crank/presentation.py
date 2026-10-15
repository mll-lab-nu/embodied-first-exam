"""Authoring film tooling (not shipped): export exact native poses of a passing replay, render with Blender, encode.

    python presentation.py export --trajectory solution/trajectory.npz --export OUT [--stride 4]
    python presentation.py verify --trajectory solution/trajectory.npz --export OUT
    blender -b -P studio_renderer.py -- --export OUT --output film.mp4 [--samples 48]
    python presentation.py encode --export OUT --output film.mp4

Every sampled pose comes from `Session.step` on the recorded motor targets; nothing is interpolated or scripted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from replay import load_trajectory
from runtime import Session

HERE = Path(__file__).resolve().parent
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=4):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    owner = session.checker.body_owner
    arrays, geoms, meshes, ids = {}, [], {}, []
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        name = m.geom(gid).name or f"geom_{gid}"
        if "_wuji_" in name and "_collision" in name:
            continue
        mid = int(m.geom_matid[gid])
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        ids.append(gid)
        geoms.append({
            "id": gid,
            "name": name,
            "kind": int(m.geom_type[gid]),
            "size": m.geom_size[gid].tolist(),
            "mesh": mesh,
            "owner": owner[int(m.geom_bodyid[gid])],
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
        frames.append({"step": session.steps, "time_s": float(session.data.time), "state_sha": session.state_sha(),
                       "status": {k: st[k] for k in ("success", "failed", "reason", "stage", "crank_turns",
                                                     "released_hold_steps", "hand_contacts", "tilt_deg", "slide_m")}})
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    try:
        sample()
        for i, action in enumerate(actions):
            session.step(action)
            if (i + 1) % stride == 0 or session.done:
                sample()
            if session.done:
                break  # the episode ends at the first success (or failure); later rows are not executed
        np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
        files = {p.name: sha(p) for p in (directory / "geometry.npz", directory / "poses.npz")}
        result = {
            "schema_version": 1,
            "task": "grinder_crank",
            "evidence_type": "physical_actuator_replay",
            "scripted_object_motion": False,
            "hand": hand,
            "trajectory_sha256": sha(trajectory),
            "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "initial_sha": session.initial_sha,
            "final_sha": session.state_sha(),
            "success": bool(session.success),
            "reason": session.status()["reason"],
            "source_sha256": {name: sha(HERE / name) for name in PHYSICS_SOURCES},
            "files": files,
            "geoms": geoms,
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
    print(json.dumps({"frames": len(frames), "final_sha": result["final_sha"], "success": result["success"],
                      "reason": result["reason"]}))


def checked_bundle(directory):
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    return payload


def verify(trajectory, directory):
    """Fresh replay: every exported pose sample must equal the native state bit for bit."""
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
        for action in actions:
            session.step(action)
            if index < len(payload["frames"]) and payload["frames"][index]["step"] == session.steps:
                compare()
            if session.done:
                break
        assert index == len(payload["frames"]) and session.state_sha() == payload["final_sha"]
    finally:
        session.close()
    print(f"Verified {index} exact native pose samples; final state {payload['reason']}")


def encode(directory, output, title="Operate a manual coffee grinder"):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    payload = checked_bundle(directory)
    output = Path(output)
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    fps = manifest["video_fps"]
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    hand = {"sharpa": "Marvin arms + two Sharpa Wave hands", "wuji": "Marvin arms + two Wuji Hand 2.2"}[payload["hand"]]
    speed = payload["stride"] * payload["control_dt"] * fps
    pic = None
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1, pixelformat="yuv420p",
                            ffmpeg_params=["-crf", "21", "-preset", "slow", "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            draw = ImageDraw.Draw(pic)
            st = payload["frames"][index]["status"]
            label = "PASS" if st["success"] else ("FAIL: " + st["reason"] if st["failed"] else "IN PROGRESS")
            line1 = f"{title}  ·  {hand}"
            line2 = (f"{label}  ·  crank {max(st['crank_turns'], 0):.2f} / 2 turns  ·  "
                     f"physics replay, {speed:g}x")
            width = max(draw.textlength(line1, font=font), draw.textlength(line2, font=small)) + 28
            draw.rounded_rectangle((20, 18, 20 + width, 18 + 58), radius=8, fill=(245, 244, 237))
            draw.text((32, 25), line1, font=font, fill=(35, 45, 40))
            draw.text((32, 50), line2, font=small, fill=(61, 104, 75) if st["success"] else (90, 94, 88))
            writer.append_data(np.asarray(pic))
        for _ in range(round(fps * 2)):
            writer.append_data(np.asarray(pic))
    pic.save(output.with_suffix(".png"))
    report = {
        "renderer": manifest["engine"],
        "blender_version": manifest.get("blender_version"),
        "presentation_only": True,
        "scripted_object_motion": False,
        "hand": payload["hand"],
        "trajectory_sha256": payload["trajectory_sha256"],
        "native_final_sha": payload["final_sha"],
        "native_reason": payload["reason"],
        "pose_manifest_sha256": sha(Path(directory) / "scene.json"),
        "video_sha256": sha(output),
        "playback_speed": speed,
        "render": {k: v for k, v in manifest.items() if k != "measurements"},
    }
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Encoded {output} ({output.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "verify", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=4)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "verify":
        verify(args.trajectory, args.export)
    else:
        encode(args.export, args.output)
