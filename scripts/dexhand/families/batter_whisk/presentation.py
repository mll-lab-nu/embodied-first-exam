"""Authoring only: export exact native poses of the physical whisk episode, render them in Blender, encode the film.

    python presentation.py export --trajectory solution/trajectory.npz --export out/whisk-export --stride 3
    python presentation.py verify --trajectory solution/trajectory.npz --export out/whisk-export
    python presentation.py render --export out/whisk-export --output film.mp4        # Blender 4.5.3 + OptiX
    python presentation.py encode --export out/whisk-export --output film.mp4

No object or hand motion is synthesized: every rendered frame is a sampled native MuJoCo state of the replayed rows;
the tail after success holds the final native state while the camera moves.
"""

from __future__ import annotations

import argparse
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
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")
FPS = 25


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owner(session, gid):
    body = int(session.model.geom_bodyid[gid])
    if session.checker.is_hand[gid]:
        if session.marvin:
            from scene import _arm_rig_module

            rig = _arm_rig_module()
            if body in rig.robot_body_ids(session.model):
                return "robot"
        return "hand"
    return session.model.body(body).name if body else "world"


def export(trajectory, directory, stride=4, tail_s=3.5):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sources = {name: sha(HERE / name) for name in PHYSICS_SOURCES}
    session = Session()
    m = session.model
    arrays, geoms, meshes, ids = {}, [], {}, []
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
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
            "owner": owner(session, gid),
            "material": m.material(mid).name if mid >= 0 else "",
            "rgba": (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist(),
        })
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va:va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa:fa + fn].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    actions = load_actions(trajectory)
    frames, positions, rotations = [], [], []

    def sample(tail=False):
        st = session.status()
        frames.append({
            "step": session.steps,
            "time_s": float(session.data.time),
            "tail": tail,
            "state_sha": session.state_sha(),
            "stage": st["stage"],
            "revolutions": st["revolutions"],
            "success": st["success"],
            "reason": st["reason"],
            "whisk_com": session.checker.f["whisk_com"],
        })
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
        if not session.success:
            raise RuntimeError("Presentation requires a passing complete native replay")
        for _ in range(round(tail_s * FPS)):
            sample(tail=True)  # the final native state, held while the camera moves
        np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
        if sources != {name: sha(HERE / name) for name in PHYSICS_SOURCES}:
            raise RuntimeError("Physics sources changed during export")
        files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob("*"))
                 if p.is_file() and p.name in ("geometry.npz", "poses.npz")}
        result = {
            "schema_version": 1,
            "task": "batter_whisk",
            "evidence_type": "physical_actuator_replay",
            "scripted_object_motion": False,
            "hand": session.hand,
            "trajectory_sha256": sha(trajectory),
            "initial_sha": session.initial_sha,
            "final_sha": session.state_sha(),
            "success_step": session.steps,
            "source_sha256": sources,
            "files": files,
            "geoms": geoms,
            "meshes": meshes,
            "frames": frames,
            "control_dt": session.control_dt,
            "stride": stride,
            "fps": FPS,
            "playback_speed": stride * session.control_dt * FPS,
        }
        (directory / "scene.json").write_text(json.dumps(result, indent=1) + "\n")
    finally:
        session.close()
    print(json.dumps({"frames": len(frames), "final_sha": result["final_sha"], "success_step": session.steps}))


def checked_bundle(directory):
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    return payload


def verify(trajectory, directory):
    """Re-run the replay and check every exported pose sample bit for bit."""
    payload = checked_bundle(directory)
    if sha(trajectory) != payload["trajectory_sha256"]:
        raise ValueError("Trajectory differs from the exported source")
    poses = np.load(Path(directory) / "poses.npz", allow_pickle=False)
    session = Session()
    ids = [g["id"] for g in payload["geoms"]]
    live = [i for i, f in enumerate(payload["frames"]) if not f["tail"]]
    k = 0

    def compare():
        nonlocal k
        index = live[k]
        record = payload["frames"][index]
        assert record["step"] == session.steps and record["state_sha"] == session.state_sha()
        assert np.array_equal(poses["positions"][index], session.data.geom_xpos[ids])
        assert np.array_equal(poses["rotations"][index], session.data.geom_xmat[ids].reshape(-1, 3, 3))
        k += 1

    try:
        compare()
        for i, action in enumerate(load_actions(trajectory)):
            session.step(action)
            if k < len(live) and payload["frames"][live[k]]["step"] == i + 1:
                compare()
            if session.done:
                break
        assert k == len(live) and session.success and session.state_sha() == payload["final_sha"]
    finally:
        session.close()
    print(f"Verified {k} exact native pose samples and the passing final state")


def encode(directory, output, hand_label="Sharpa Wave"):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    payload = checked_bundle(directory)
    output = Path(output)
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 17)
    speed = payload["playback_speed"]
    with imageio.get_writer(output, fps=payload["fps"], codec="libx264", macro_block_size=1,
                            ffmpeg_params=["-crf", "21", "-preset", "slow", "-pix_fmt", "yuv420p",
                                           "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            record = payload["frames"][index]
            if record["success"]:
                label = "PASS: whisk set down"
            elif record["stage"] >= 4:
                label = "drained, setting the whisk down"
            elif record["stage"] == 3:
                label = "whisked 5 turns, lifting to drain"
            elif record["stage"] == 2:
                label = f"whisking  {min(record['revolutions'], 5.0):.1f} / 5 turns"
            elif record["stage"] == 1:
                label = "whisk picked up, into the batter"
            else:
                label = "left hand steadies the bowl, right hand picks up the whisk"
            draw = ImageDraw.Draw(pic, "RGBA")
            draw.rounded_rectangle((20, 18, 640, 88), radius=10, fill=(246, 244, 238, 225))
            draw.text((34, 27), f"Whisk batter  ·  Tianji Marvin arms + {hand_label}", font=bold, fill=(40, 46, 44))
            draw.text((34, 55), f"{label}  ·  physics replay, {speed:g}x", font=font, fill=(88, 102, 74))
            writer.append_data(np.asarray(pic))
        pic.save(output.with_suffix(".png"))
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
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Encoded {output} ({output.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "verify", "render", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--frames", default="", help="comma-separated frame indices (stills for review)")
    parser.add_argument("--device", choices=["optix", "cpu"], default="optix")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--percent", type=int, default=100)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "verify":
        verify(args.trajectory, args.export)
    elif args.command == "encode":
        encode(args.export, args.output)
    else:
        command = [BLENDER, "-b", "-t", str(args.threads), "-P", str(HERE / "studio_renderer.py"), "--", "--export",
                   str(args.export), "--output", str(args.output), "--samples", str(args.samples),
                   "--device", args.device, "--percent", str(args.percent)]
        if args.frames:
            command += ["--frames", args.frames]
        with args.output.with_suffix(".render.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        if not args.frames:
            encode(args.export, args.output)
