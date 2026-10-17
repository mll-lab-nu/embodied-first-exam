"""Export exact native poses of a physical coffee_stir replay, render them in the T11 kitchen look, encode the film.

    python tools/presentation.py export --trajectory solution/trajectory.npz --export <export-dir> --stride 4
    python tools/presentation.py verify --trajectory solution/trajectory.npz --export <export-dir>
    BLENDER=.../blender python tools/presentation.py render --export <export-dir> --output <film>.mp4

Only presentation surfaces, cameras and lighting differ from the native replay; no hand, mug or spoon motion is
synthesized or interpolated (every rendered pose is a recorded MuJoCo pose of the passing replay).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
FAMILY = HERE.parent
sys.path.insert(0, str(FAMILY))

import numpy as np  # noqa: E402

from replay import load_actions  # noqa: E402
from runtime import Session  # noqa: E402

BLENDER = os.environ.get("BLENDER", "blender")  # Blender 4.5.3 LTS (authoring films only)
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=4, fps=25):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sources = {name: sha(FAMILY / name) for name in PHYSICS_SOURCES}
    session = Session(hand="sharpa")
    m = session.model
    # Every visible robot mesh: the Marvin stand, both arms and both hands (visual geoms only).
    from scene import arm_rig
    robot = set(arm_rig.robot_body_ids(m)) | set(arm_rig.hand_body_ids(m, "left")) | set(
        arm_rig.hand_body_ids(m, "right"))
    hand_geoms = [
        g for g in range(m.ngeom)
        if int(m.geom_bodyid[g]) in robot and m.geom_group[g] <= 2 and m.geom_rgba[g, 3] > 0
        and int(m.geom_type[g]) == 7 and m.geom_contype[g] == 0
    ]
    arrays, geoms, meshes = {}, [], {}
    for gid in hand_geoms:
        mesh = int(m.geom_dataid[gid])
        mid = int(m.geom_matid[gid])
        geoms.append({"id": gid, "name": m.geom(gid).name or f"geom_{gid}", "mesh": mesh,
                      "material": m.material(mid).name if mid >= 0 else "",
                      "rgba": [round(float(x), 4) for x in m.geom_rgba[gid]],
                      "robot_link": int(m.geom_bodyid[gid]) in arm_rig.robot_body_ids(m)})
        if str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va: va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa: fa + fn].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    for name in ("cup.obj", "spoon.obj"):
        (directory / name).write_bytes((FAMILY / "assets" / name).read_bytes())
    actions = load_actions(trajectory)
    ids = np.asarray(hand_geoms, dtype=int)
    bodies = [m.body("cup").id, m.body("spoon").id]
    frames, hand_pos, hand_rot, body_pos, body_rot = [], [], [], [], []

    def sample(phase):
        f = session.features()
        frames.append({"step": session.steps, "time_s": float(session.data.time), "phase": phase,
                       "state_sha": session.state_sha(),
                       "features": {k: f[k] for k in ("stage", "revolutions", "bowl_submerged", "success", "failure",
                                                      "rest_hold_steps", "hand_spoon_contacts")}})
        hand_pos.append(session.data.geom_xpos[ids].copy())
        hand_rot.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())
        body_pos.append(session.data.xpos[bodies].copy())
        body_rot.append(session.data.xmat[bodies].reshape(-1, 3, 3).copy())

    try:
        sample("initial")
        for i, action in enumerate(actions):
            session.step(action)
            if (i + 1) % stride == 0 or session.done:
                sample("replay")
            if session.done:
                break  # the episode ends at the first success (or failure); later rows are not executed
        if not session.success:
            raise RuntimeError("Presentation requires a passing complete native replay")
        np.savez_compressed(directory / "poses.npz", hand_positions=np.asarray(hand_pos),
                            hand_rotations=np.asarray(hand_rot), body_positions=np.asarray(body_pos),
                            body_rotations=np.asarray(body_rot))
        if sources != {name: sha(FAMILY / name) for name in PHYSICS_SOURCES}:
            raise RuntimeError("Physics sources changed during export")
        files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob("*"))
                 if p.is_file() and p.name not in ("scene.json",)}
        result = {
            "schema_version": 1,
            "task": "coffee_stir",
            "hand": session.hand,
            "evidence_type": "physical_actuator_replay",
            "scripted_object_motion": False,
            "trajectory_sha256": sha(trajectory),
            "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "initial_sha": session.initial_sha,
            "final_sha": session.state_sha(),
            "verdict": {k: session.status()[k] for k in ("success", "reason", "steps", "stage", "revolutions")},
            "source_sha256": sources,
            "files": files,
            "hand_geoms": geoms,
            "meshes": meshes,
            "frames": frames,
            "control_dt": session.control_dt,
            "stride": stride,
            "fps": fps,
            "playback_speed": stride * session.control_dt * fps,
        }
        (directory / "scene.json").write_text(json.dumps(result, indent=1) + "\n")
    finally:
        session.close()
    print(json.dumps({"frames": len(frames), "final_sha": result["final_sha"], "verdict": result["verdict"],
                      "playback_speed": result["playback_speed"]}))


def checked_bundle(directory):
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    return payload


def verify(trajectory, directory):
    """Replay again and require every exported pose to equal the native pose bit for bit."""
    payload = checked_bundle(directory)
    if sha(trajectory) != payload["trajectory_sha256"]:
        raise ValueError("Trajectory differs from the exported source")
    poses = np.load(Path(directory) / "poses.npz", allow_pickle=False)
    session = Session(hand="sharpa")
    m = session.model
    ids = [g["id"] for g in payload["hand_geoms"]]
    bodies = [m.body("cup").id, m.body("spoon").id]
    index = 0

    def compare():
        nonlocal index
        record = payload["frames"][index]
        assert record["step"] == session.steps and record["state_sha"] == session.state_sha()
        assert np.array_equal(poses["hand_positions"][index], session.data.geom_xpos[ids])
        assert np.array_equal(poses["body_positions"][index], session.data.xpos[bodies])
        assert np.array_equal(poses["body_rotations"][index], session.data.xmat[bodies].reshape(-1, 3, 3))
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


def encode(directory, output, crf=21):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    payload = checked_bundle(directory)
    directory, output = Path(directory), Path(output)
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    fps = manifest["video_fps"]
    speed = round(payload["stride"] * payload["control_dt"] * manifest["frame_step"] * fps, 3)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1,
                            ffmpeg_params=["-crf", str(crf), "-preset", "slow", "-pix_fmt", "yuv420p",
                                           "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            draw = ImageDraw.Draw(pic)
            f = payload["frames"][index]["features"]
            status = ("PASS: spoon laid down" if f["success"] else
                      f"stirring {min(f['revolutions'], 6.0):.1f} / 6 turns" if f["stage"] < 2 else "6 / 6 turns, laying the spoon down")
            draw.rounded_rectangle((20, 18, 640, 88), radius=10, fill=(30, 33, 30))
            draw.text((34, 26), "Mix coffee and milk  ·  Marvin arm + Sharpa Wave", font=font, fill=(242, 238, 228))
            draw.text((34, 56), f"physics replay, {speed:g}x  ·  {status}  ·  coffee not simulated", font=small,
                      fill=(214, 196, 160))
            writer.append_data(np.asarray(pic))
        for _ in range(round(fps * 2)):
            writer.append_data(np.asarray(pic))
        pic.save(output.with_suffix(".png"))
    report = {
        "renderer": "Blender " + manifest["blender_version"] + " " + manifest["engine"],
        "presentation_only": True,
        "scripted_object_motion": False,
        "trajectory_sha256": payload["trajectory_sha256"],
        "native_final_sha": payload["final_sha"],
        "native_verdict": payload["verdict"],
        "pose_manifest_sha256": sha(directory / "scene.json"),
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
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--still", type=int, nargs="*")
    parser.add_argument("--crf", type=int, default=21)
    parser.add_argument("--device", choices=["GPU", "CPU"], default="GPU")
    parser.add_argument("--percent", type=int, default=100)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "verify":
        verify(args.trajectory, args.export)
    elif args.command == "encode":
        encode(args.export, args.output, args.crf)
    else:
        command = [BLENDER, "-b", "-t", "8", "--python-exit-code", "1", "-P", str(HERE / "studio_renderer.py"), "--",
                   "--export", str(args.export), "--output", str(args.output), "--samples", str(args.samples),
                   "--frame-step", str(args.frame_step), "--device", args.device, "--percent", str(args.percent)]
        if args.still:
            command += ["--still", *map(str, args.still)]
        with args.output.with_suffix(".render.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        if not args.still:
            encode(args.export, args.output, args.crf)
