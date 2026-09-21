"""Render synchronized exterior and wrist views from measured robot states."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation

from .physics import array, save
from .render import physical_assets_signature
from .scene import BuzzWireSceneBuilder

CAMERAS = ("agentview", "front_oblique", "wrist")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def physics_signature(path):
    root = ET.parse(path).getroot()
    for link in root.findall("link"):
        for visual in link.findall("visual"):
            link.remove(visual)

    # Ignore formatting tails left by removed visual nodes.
    def node(element):
        return element.tag, sorted(element.attrib.items()), [node(c) for c in element]

    return node(root)


def select_frames(rows, fps):
    times = np.array([r["time_s"] for r in rows])
    if len(times) < 2 or times[0] != 0 or np.any(np.diff(times) <= 0):
        raise ValueError("Physical timestamps must increase from zero")
    targets = np.arange(round(times[-1] * fps) + 1) / fps
    indices = np.searchsorted(times, targets - 1e-9)
    if indices.max() >= len(rows) or not np.allclose(
        times[indices], targets, atol=1e-8, rtol=0
    ):
        raise ValueError("Requested video rate is not represented by measured states")
    return [rows[i] for i in indices]


def snapshot_robot(asset, destination):
    """Copy the exact assembled robot and its meshes with portable references."""
    import mujoco

    asset, destination = Path(asset), Path(destination)
    destination.mkdir(parents=True)
    shutil.copy2(asset, destination / "original.xml")
    tree = ET.parse(asset)
    files = {}
    for index, node in enumerate(e for e in tree.iter() if e.get("file")):
        original = Path(node.get("file"))
        if not original.is_absolute():
            original = asset.parent / original
        name = f"meshes/{index:03d}_{original.name}"
        copied = destination / name
        copied.parent.mkdir(exist_ok=True)
        shutil.copy2(original, copied)
        node.set("file", name)
        files[name] = dict(original_path=str(original), sha256=sha(copied))
    tree.write(destination / "robot.xml", encoding="utf-8", xml_declaration=True)
    original_model = mujoco.MjModel.from_xml_path(str(asset))
    portable_model = mujoco.MjModel.from_xml_path(str(destination / "robot.xml"))
    for field in (
        "body_mass",
        "body_inertia",
        "body_ipos",
        "body_iquat",
        "jnt_range",
        "geom_pos",
        "geom_quat",
        "geom_size",
        "geom_type",
        "mesh_vert",
        "mesh_face",
    ):
        np.testing.assert_array_equal(
            getattr(original_model, field), getattr(portable_model, field)
        )
    save(
        destination / "manifest.json",
        dict(
            original_xml_sha256=sha(asset),
            portable_xml_sha256=sha(destination / "robot.xml"),
            compiled_model_equivalent=True,
            files=files,
        ),
    )


def render(
    source,
    output,
    preview=False,
    fps=25,
    resume=False,
    frame_start=None,
    frame_stop=None,
):
    import genesis as gs

    source, output = Path(source).resolve(), Path(output).resolve()
    report = json.loads((source / "report.json").read_text())
    if not preview and (not report["passed"] or not report["complete"]):
        raise ValueError("A full demo requires a passing complete physical traversal")
    if preview and resume:
        raise ValueError("Only full video rendering can be resumed")
    if output.exists() and any(output.iterdir()) and not resume:
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / "source_evidence"
    evidence.mkdir(exist_ok=resume)
    if resume:
        for path in source.rglob("*"):
            if path.is_file() and (
                not (evidence / path.relative_to(source)).is_file()
                or sha(path) != sha(evidence / path.relative_to(source))
            ):
                raise ValueError("Resume source evidence differs: " + str(path))
        if (output / "report.json").exists() and json.loads(
            (output / "report.json").read_text()
        )["complete"]:
            raise ValueError("The completed render must not be overwritten")
        previous_source = output / "render_source.py"
        shutil.copy2(
            previous_source,
            output / f"render_source_previous_{sha(previous_source)[:12]}.py",
        )
    else:
        for name in ("report.json", "frames.json", "config.yaml"):
            shutil.copy2(source / name, evidence / name)
        shutil.copytree(source / "assets", evidence / "assets")
        shutil.copytree(source / "planning", evidence / "planning")
        if (source / "implementation").exists():
            shutil.copytree(source / "implementation", evidence / "implementation")
    shutil.copy2(__file__, output / "render_source.py")
    rows = select_frames(json.loads((source / "frames.json").read_text()), fps)
    chunked = frame_start is not None or frame_stop is not None
    lo = 0 if frame_start is None else frame_start
    hi = len(rows) if frame_stop is None else frame_stop
    if not 0 <= lo < hi <= len(rows) or (preview and chunked):
        raise ValueError("Invalid render frame range")
    cfg = OmegaConf.load(source / "config.yaml")
    cfg.env.genesis.backend = "cpu"
    cfg.env.renderer.type = "rasterizer"
    cfg.env.presentation.background = "checker"
    cfg.env.cameras = OmegaConf.create(
        {
            "agentview": dict(
                res=[960, 720],
                pos=[1.05, -1.30, 1.95],
                lookat=[-0.24, 0, 1.14],
                up=[0, 0, 1],
                fov=48,
            ),
            "front_oblique": dict(
                res=[960, 720],
                pos=[0.95, 1.10, 1.72],
                lookat=[-0.24, 0, 1.14],
                up=[0, 0, 1],
                fov=48,
            ),
            "wrist": dict(
                res=[960, 720],
                pos=[0, -0.5, 1.5],
                lookat=[0, 0, 1.1],
                up=[0, 0, 1],
                fov=80,
                near=0.005,
            ),
        }
    )
    if resume and OmegaConf.to_container(cfg, resolve=True) != OmegaConf.to_container(
        OmegaConf.load(output / "render_config.yaml"), resolve=True
    ):
        raise ValueError("Resume camera or scene configuration differs")
    OmegaConf.save(cfg, output / "render_config.yaml", resolve=True)
    gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
    from topogym.robot.assets import robot_asset

    plan = json.loads((source / "planning/plan.json").read_text())
    robot_path = robot_asset(cfg.robot_control)
    robot_digest = sha(robot_path)
    if robot_digest != plan["robot_asset_sha256"]:
        raise ValueError("Recorded and rendered robot assets differ")
    if resume:
        robot_manifest = json.loads((output / "robot_assets/manifest.json").read_text())
        if robot_manifest["original_xml_sha256"] != robot_digest:
            raise ValueError("Resume robot differs")
        for name, entry in robot_manifest["files"].items():
            if sha(output / "robot_assets" / name) != entry["sha256"]:
                raise ValueError("Resume robot mesh differs")
    else:
        snapshot_robot(robot_path, output / "robot_assets")
    task = BuzzWireSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output / "assets",
        include_robot=True,
    )
    from topogym.utils.franka import initialize_franka_controller

    c = initialize_franka_controller(
        scene=task.scene,
        manifest=task.tabletop.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    if physical_assets_signature(source / "assets") != physical_assets_signature(
        output / "assets"
    ):
        raise ValueError("Recorded and rendered collision/inertial assets differ")
    save(
        output / "physics_equivalence.json",
        dict(
            passed=True,
            scope="Exact collision geometry, mass, inertia, joints and task configuration",
            robot_asset_sha256=robot_digest,
        ),
    )
    selected = sorted({0, len(rows) // 2, len(rows) - 1}) if preview else range(lo, hi)
    peaks = dict(position_m=0.0, orientation_rad=0.0, robot_qpos=0.0)
    records = []
    reusable = set()
    if resume:
        for index in range(len(rows)):
            paths = [output / "frames" / n / f"{index:05d}.jpg" for n in CAMERAS]
            if all(p.is_file() for p in paths):
                try:
                    for path in paths:
                        with Image.open(path) as frame:
                            if frame.size != (960, 720) or frame.mode != "RGB":
                                raise ValueError("Resume image format differs")
                            frame.load()
                    reusable.add(index)
                except OSError:
                    pass  # An interrupted JPEG write is rendered again.
    resume_checks = {min(reusable), max(reusable)} if reusable else set()
    resume_maximum_pixel_error = 0.0
    if reusable:
        print(f"resume {len(reusable)}/{len(rows)} synchronized frames", flush=True)
    start = time.monotonic()
    for name in CAMERAS:
        if not preview:
            (output / "frames" / name).mkdir(parents=True, exist_ok=resume)
    for index in selected:
        row = rows[index]
        c.robot.set_qpos(row["robot_qpos"], zero_velocity=True)
        peaks["robot_qpos"] = max(
            peaks["robot_qpos"],
            float(np.max(abs(array(c.robot.get_qpos()) - row["robot_qpos"]))),
        )
        task.wand.set_pos(row["position_m"], zero_velocity=True)
        task.wand.set_quat(row["quaternion_wxyz"], zero_velocity=True)
        p, q = array(task.wand.get_pos()), array(task.wand.get_quat())
        recorded = Rotation.from_quat(np.array(row["quaternion_wxyz"])[[1, 2, 3, 0]])
        actual = Rotation.from_quat(q[[1, 2, 3, 0]])
        peaks["position_m"] = max(
            peaks["position_m"], float(np.linalg.norm(p - row["position_m"]))
        )
        peaks["orientation_rad"] = max(
            peaks["orientation_rad"], float((recorded * actual.inv()).magnitude())
        )
        if max(peaks.values()) > 1e-7:
            raise ValueError(f"Rendered pose differs from physical state: {peaks}")
        hand_rotation = Rotation.from_quat(c.hand_quat()[[1, 2, 3, 0]])
        camera_position = c.hand_pos() + hand_rotation.apply([0.070, 0.045, 0.015])
        task.tabletop.cameras["wrist"].set_pose(
            pos=camera_position, lookat=p, up=hand_rotation.apply([0, 1, 0])
        )
        poses = {}
        for name in CAMERAS:
            camera = task.tabletop.cameras[name]
            # All three cameras share this measured state. Refresh the scene
            # once even though replay does not advance the physics clock.
            if index not in reusable or index in resume_checks:
                rgb = camera.render(force_render=name == CAMERAS[0])[0]
                if index in resume_checks:
                    encoded = io.BytesIO()
                    Image.fromarray(rgb).save(encoded, format="JPEG", quality=95)
                    regenerated = np.array(Image.open(io.BytesIO(encoded.getvalue())))
                    previous = np.array(
                        Image.open(output / "frames" / name / f"{index:05d}.jpg")
                    )
                    difference = float(
                        np.mean(np.abs(regenerated.astype(float) - previous))
                    )
                    resume_maximum_pixel_error = max(
                        resume_maximum_pixel_error, difference
                    )
                    if difference > 0.1:
                        raise ValueError(f"Resume image differs: {name} {difference}")
                if not preview:
                    Image.fromarray(rgb).save(
                        output / "frames" / name / f"{index:05d}.jpg", quality=95
                    )
                if preview or index in (0, len(rows) // 2, len(rows) - 1):
                    Image.fromarray(rgb).save(
                        output / f"frame_{index:05d}_{name}.jpg", quality=95
                    )
            poses[name] = np.asarray(camera.transform).tolist()
        records.append(
            dict(
                frame=index,
                source_step=row["physics_step"],
                time_s=row["time_s"],
                cameras=poses,
            )
        )
        if preview or index % 50 == 0:
            print(
                f"render {index + 1}/{len(rows)} elapsed={time.monotonic() - start:.1f}s",
                flush=True,
            )
    save(output / "camera_poses.json", records)
    result = dict(
        complete=False,
        preview_only=preview,
        task_id="buzz_wire_3d",
        variant=report["instance_id"],
        classification="single_arm_physical_trace_replay",
        robot_present=True,
        counts_as_complete_robotics_demo=not preview and not chunked,
        source_directory=str(source),
        source_passed=report["passed"],
        source_sha256={
            n: sha(evidence / n) for n in ("report.json", "frames.json", "config.yaml")
        },
        fps=fps,
        cameras=list(CAMERAS),
        frame_count=len(rows),
        duration_s=len(rows) / fps,
        recording_range_s=[0.0, rows[-1]["time_s"]],
        source_physics_steps=report["physics_steps"],
        render_physics_steps=0,
        new_physics_execution=False,
        pose_replay_errors=peaks,
        resumed_frame_count=len(reusable),
        resume_pixel_comparison_maximum_mean_error=resume_maximum_pixel_error,
        renderer="Genesis rasterizer",
        ui_overlays=False,
        scope="One continuous joint-servo robot execution from pregrasp contact through complete maze, release, retreat and settle; measured full robot and ring states.",
        pregrasp_start=True,
        assisted_grasp=report["assisted_grasp"],
        passive_gripper_joints_reconstructed=False,
        wrist_camera_scope="Position fixed relative to hand; gaze tracks the measured ring center",
        partial_frame_range=[lo, hi] if chunked else None,
        rendered_frame_count=len(selected),
    )
    save(output / "report.json", result)
    if not preview and not chunked:
        for name in CAMERAS:
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-y",
                    "-v",
                    "error",
                    "-xerror",
                    "-framerate",
                    str(fps),
                    "-start_number",
                    "0",
                    "-i",
                    str(output / "frames" / name / "%05d.jpg"),
                    "-frames:v",
                    str(len(rows)),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "18",
                    "-threads",
                    "2",
                    "-filter_threads",
                    "1",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(output / f"{name}.mp4"),
                ],
                check=True,
            )
        result["complete"] = True
        result["video_sha256"] = {n: sha(output / f"{n}.mp4") for n in CAMERAS}
        save(output / "report.json", result)
    return result


def parallel_render(source, output, workers=3, resume=False, fps=25):
    """Render disjoint frame ranges of ONE measured execution, then validate coverage."""
    source, output = Path(source).resolve(), Path(output).resolve()
    physical = json.loads((source / "report.json").read_text())
    if not physical["passed"] or not physical["complete"]:
        raise ValueError(
            "Parallel rendering requires one complete passing physical run"
        )
    if not 1 <= workers <= 8:
        raise ValueError("Use between one and eight render workers")
    rows = select_frames(json.loads((source / "frames.json").read_text()), fps)
    edges = np.linspace(0, len(rows), min(workers, len(rows)) + 1, dtype=int)
    ranges = [[int(a), int(b)] for a, b in zip(edges[:-1], edges[1:])]
    settings = dict(
        source=str(source),
        fps=fps,
        ranges=ranges,
        source_sha256={
            n: sha(source / n) for n in ("report.json", "frames.json", "config.yaml")
        },
    )
    if output.exists() and any(output.iterdir()) and not resume:
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    if resume:
        if json.loads((output / "parallel_settings.json").read_text()) != settings:
            raise ValueError("Parallel resume source or frame ranges differ")
        if (output / "report.json").exists() and json.loads(
            (output / "report.json").read_text()
        )["complete"]:
            raise FileExistsError("A completed render must not be overwritten")
    save(output / "parallel_settings.json", settings)
    jobs, logs = [], []
    try:
        for index, (lo, hi) in enumerate(ranges):
            folder = output / "chunks" / f"{index:02d}"
            command = [
                sys.executable,
                "-m",
                "topogym.tasks.buzz_wire_3d.robot_render",
                "--source",
                str(source),
                "--output",
                str(folder),
                "--frame-start",
                str(lo),
                "--frame-stop",
                str(hi),
                "--fps",
                str(fps),
            ]
            if resume and folder.exists() and any(folder.iterdir()):
                command.append("--resume")
            stream = (output / f"chunk_{index:02d}.log").open("a" if resume else "w")
            logs.append(stream)
            jobs.append(
                subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
            )
        pending = set(range(len(jobs)))
        while pending:
            for index in tuple(pending):
                code = jobs[index].poll()
                if code is None:
                    continue
                if code != 0:
                    raise RuntimeError(
                        f"Render worker {index} failed ({code}); see chunk log"
                    )
                pending.remove(index)
                print(f"render chunk {index + 1}/{len(jobs)} complete", flush=True)
            if pending:
                time.sleep(0.5)
    finally:
        for job in jobs:
            if job.poll() is None:
                job.terminate()
        for job in jobs:
            try:
                job.wait(timeout=30)
            except subprocess.TimeoutExpired:
                job.kill()
                job.wait()
        for stream in logs:
            stream.close()
    records, reports, provenance = [], [], []
    first = output / "chunks/00"
    config_digest = sha(first / "render_config.yaml")
    equivalence = json.loads((first / "physics_equivalence.json").read_text())
    for index, (lo, hi) in enumerate(ranges):
        folder = output / "chunks" / f"{index:02d}"
        report = json.loads((folder / "report.json").read_text())
        poses = json.loads((folder / "camera_poses.json").read_text())
        if (
            report["source_sha256"] != settings["source_sha256"]
            or report["partial_frame_range"] != [lo, hi]
            or [r["frame"] for r in poses] != list(range(lo, hi))
            or sha(folder / "render_config.yaml") != config_digest
            or json.loads((folder / "physics_equivalence.json").read_text())
            != equivalence
        ):
            raise ValueError(
                "Render chunks differ in source, geometry, configuration or coverage"
            )
        for record in poses:
            i = record["frame"]
            if (
                record["source_step"] != rows[i]["physics_step"]
                or abs(record["time_s"] - i / fps) > 1e-8
                or set(record["cameras"]) != set(CAMERAS)
            ):
                raise ValueError("Chunk timestamp or measured source-state mismatch")
        for name in CAMERAS:
            destination = output / "frames" / name
            destination.mkdir(parents=True, exist_ok=True)
            for i in range(lo, hi):
                shutil.copy2(
                    folder / "frames" / name / f"{i:05d}.jpg",
                    destination / f"{i:05d}.jpg",
                )
        for path in folder.glob("frame_*.jpg"):
            shutil.copy2(path, output / path.name)
        records.extend(poses)
        reports.append(report)
        provenance.append(
            dict(
                frame_range=[lo, hi],
                report=report,
                camera_poses_sha256=sha(folder / "camera_poses.json"),
            )
        )
    for name in ("source_evidence", "assets", "robot_assets"):
        shutil.copytree(first / name, output / name, dirs_exist_ok=resume)
    for name in ("render_config.yaml", "physics_equivalence.json"):
        shutil.copy2(first / name, output / name)
    shutil.copy2(__file__, output / "render_source.py")
    save(output / "camera_poses.json", records)
    save(output / "render_chunks.json", provenance)
    result = dict(reports[0])
    result.update(
        complete=False,
        partial_frame_range=None,
        rendered_frame_count=len(rows),
        counts_as_complete_robotics_demo=False,
        renderer_workers=len(ranges),
        resumed_frame_count=sum(r["resumed_frame_count"] for r in reports),
        pose_replay_errors={
            k: max(r["pose_replay_errors"][k] for r in reports)
            for k in reports[0]["pose_replay_errors"]
        },
    )
    save(output / "report.json", result)
    for name in CAMERAS:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-xerror",
                "-framerate",
                str(fps),
                "-start_number",
                "0",
                "-i",
                str(output / "frames" / name / "%05d.jpg"),
                "-frames:v",
                str(len(rows)),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-threads",
                "2",
                "-filter_threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output / f"{name}.mp4"),
            ],
            check=True,
        )
    result.update(
        complete=True,
        counts_as_complete_robotics_demo=True,
        video_sha256={n: sha(output / f"{n}.mp4") for n in CAMERAS},
    )
    save(output / "report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--frame-start", type=int)
    parser.add_argument("--frame-stop", type=int)
    parser.add_argument("--fps", type=int, default=25)
    args = parser.parse_args()
    if args.workers > 1:
        if args.preview or args.frame_start is not None or args.frame_stop is not None:
            parser.error(
                "Parallel mode cannot be combined with preview or an explicit frame range"
            )
        parallel_render(args.source, args.output, args.workers, args.resume, args.fps)
    else:
        render(
            args.source,
            args.output,
            args.preview,
            fps=args.fps,
            resume=args.resume,
            frame_start=args.frame_start,
            frame_stop=args.frame_stop,
        )


if __name__ == "__main__":
    main()
