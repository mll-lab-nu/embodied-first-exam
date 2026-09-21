"""Render three synchronized views of measured finite-wrench fixture states.

This is a physical trace replay, not a robotic demonstration or a new rollout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation

from .physics import array, save
from .scene import BuzzWireSceneBuilder

CAMERAS = ("overview", "front_oblique", "topdown")


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


def physical_assets_signature(directory):
    """Include optional toy-base collision meshes, excluding visual materials."""
    directory = Path(directory)
    result = {}
    for name in ("wire.urdf", "wand.urdf", "base.urdf"):
        path = directory / name
        if name == "base.urdf" and not path.exists():
            continue
        result[name] = physics_signature(path)
        for mesh in ET.parse(path).findall(".//collision/geometry/mesh"):
            filename = mesh.attrib["filename"]
            result[f"{name}:{filename}"] = sha(path.parent / filename)
    return result


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


def render(source, output, preview=False, fps=25, diagnostic=False):
    import genesis as gs

    source, output = Path(source).resolve(), Path(output).resolve()
    report = json.loads((source / "report.json").read_text())
    if diagnostic and not report["checks"]["completed"]:
        raise ValueError("Diagnostic recording requires a complete measured case")
    if (
        not preview
        and not diagnostic
        and (not report["passed"] or report["case"] != "traverse")
    ):
        raise ValueError("A full demo requires a passing complete physical traversal")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / "source_evidence"
    evidence.mkdir()
    for name in ("report.json", "frames.json", "config.yaml", "settings.json"):
        shutil.copy2(source / name, evidence / name)
    shutil.copytree(source / "assets", evidence / "assets")
    if (source / "implementation").exists():
        shutil.copytree(source / "implementation", evidence / "implementation")
    shutil.copy2(__file__, output / "render_source.py")
    rows = select_frames(json.loads((source / "frames.json").read_text()), fps)
    cfg = OmegaConf.load(source / "config.yaml")
    cfg.env.genesis.backend = "cpu"
    cfg.env.renderer.type = "rasterizer"
    cfg.env.presentation.background = "checker"
    # Two exterior views show depth and the vertical folds; overhead resolves
    # the horizontal switchbacks and the inward spiral.
    cfg.env.cameras = OmegaConf.create(
        {
            "overview": dict(
                res=[960, 720],
                pos=[1.25, -1.45, 1.95],
                lookat=[-0.035, 0, 1.20],
                up=[0, 0, 1],
                fov=43,
            ),
            "front_oblique": dict(
                res=[960, 720],
                pos=[1.45, 1.15, 1.57],
                lookat=[-0.035, 0, 1.20],
                up=[0, 0, 1],
                fov=43,
            ),
            "topdown": dict(
                res=[960, 720],
                pos=[-0.035, 0, 2.45],
                lookat=[-0.035, 0, 1.20],
                up=[-1, 0, 0],
                fov=57,
            ),
        }
    )
    if diagnostic:
        geometry = report["geometry"]
        ratio = max(geometry["layout"]["base_size_m"][:2]) / 1.18
        center = np.r_[
            cfg.task.origin_xy_m,
            float(cfg.env.frames.table_surface.origin[2])
            + geometry["rail_bounds_m"][1][2] / 2,
        ]
        for camera in cfg.env.cameras.values():
            camera.pos = (
                center + ratio * (np.array(camera.pos) - np.array(camera.lookat))
            ).tolist()
            camera.lookat = center.tolist()
    OmegaConf.save(cfg, output / "render_config.yaml", resolve=True)
    gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
    task = BuzzWireSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output / "assets",
        constraint_timeconst=report["settings"].get("constraint_timeconst", 0.005),
    )
    for name in ("wire.urdf", "wand.urdf"):
        if physics_signature(source / "assets" / name) != physics_signature(
            output / "assets" / name
        ):
            raise ValueError("Recorded and rendered geometry differ: " + name)
    save(
        output / "physics_equivalence.json",
        dict(
            passed=True,
            scope="Exact collision geometry, mass, inertia, joints and task configuration; visual material names repaired",
        ),
    )
    selected = (
        sorted({0, len(rows) // 2, len(rows) - 1}) if preview else range(len(rows))
    )
    peaks = dict(position_m=0.0, orientation_rad=0.0)
    records = []
    start = time.monotonic()
    for name in CAMERAS:
        if not preview:
            (output / "frames" / name).mkdir(parents=True)
    for index in selected:
        row = rows[index]
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
        if peaks["position_m"] > 1e-7 or peaks["orientation_rad"] > 1e-7:
            raise ValueError(f"Rendered pose differs from physical state: {peaks}")
        task.scene.visualizer.update_visual_states(force_render=True)
        poses = {}
        for name in CAMERAS:
            camera = task.tabletop.cameras[name]
            rgb = camera.render(force_render=True)[0]
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
                source_step=row["step"],
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
        variant=report["variant"],
        classification="finite_wrench_physical_trace_replay",
        robot_present=False,
        counts_as_complete_robotics_demo=False,
        diagnostic_only=diagnostic,
        source_case=report["case"],
        source_directory=str(source),
        source_passed=report["passed"],
        source_sha256={
            n: sha(evidence / n)
            for n in ("report.json", "frames.json", "config.yaml", "settings.json")
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
        renderer="Genesis rasterizer",
        ui_overlays=False,
        scope=(
            f"Physical qualification diagnostic: {report['case']}; measured free-tool states, bounded external wrench, no robot or grasp; not a complete robot demo."
            if diagnostic
            else "One continuous bounded-wrench execution, including full route and gravity release; recorded measured poses; no robot or grasp."
        ),
    )
    save(output / "report.json", result)
    if not preview:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    render(args.source, args.output, args.preview, diagnostic=args.diagnostic)


if __name__ == "__main__":
    main()
