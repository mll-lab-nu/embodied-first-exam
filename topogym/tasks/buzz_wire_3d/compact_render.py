"""Three synchronized material/layout previews; explicitly not robot executions."""

import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation

from .physics import save
from .render import sha


def render(source, output, frames=120, fps=15):
    import genesis as gs
    from .scene import BuzzWireSceneBuilder
    from topogym.utils.franka import initialize_franka_controller

    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    report = json.loads((source / "report.json").read_text())
    if not report["passed"]:
        raise ValueError("A passing geometric route is required for the scene preview")
    output.mkdir(parents=True, exist_ok=True)
    cfg = OmegaConf.load(source / "config.yaml")
    z = float(cfg.env.frames.table_surface.origin[2])
    center = np.r_[np.asarray(cfg.task.origin_xy_m), z + 0.09]
    cfg.env.genesis.backend = "cpu"
    cfg.env.renderer.type = "rasterizer"
    cfg.env.presentation.background = "checker"
    cfg.env.cameras = OmegaConf.create(
        {
            "agentview": dict(
                res=[960, 720],
                pos=[0.9, -1.0, 1.65],
                lookat=[-0.18, 0, z + 0.10],
                up=[0, 0, 1],
                fov=46,
            ),
            "front_oblique": dict(
                res=[960, 720],
                pos=(center + [0.62, -0.65, 0.48]).tolist(),
                lookat=center.tolist(),
                up=[0, 0, 1],
                fov=42,
            ),
            "topdown": dict(
                res=[960, 720],
                pos=(center + [0, 0, 1.00]).tolist(),
                lookat=center.tolist(),
                up=[0, 1, 0],
                fov=42,
            ),
        }
    )
    OmegaConf.save(cfg, output / "render_config.yaml", resolve=True)
    gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
    task = BuzzWireSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output / "assets",
        include_robot=True,
    )
    controller = initialize_franka_controller(
        scene=task.scene,
        manifest=task.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    park_arm = [-0.5, -1.2, 0, -2.8, 0, 1.6, 0]
    robot_q = controller.robot.get_qpos().detach().cpu().numpy().copy()
    robot_q[:7] = park_arm
    controller.robot.set_qpos(robot_q, zero_velocity=True)
    # Static presentation: no pose-stepping or simulation masquerading as a task run.
    progress = 0.10
    p, q = task.reference_pose(progress)
    task.wand.set_pos(p, zero_velocity=True)
    task.wand.set_quat(q, zero_velocity=True)
    material_checks = []
    for entity in (task.base, task.wire, task.wand):
        for geom in entity.vgeoms:
            mat = getattr(geom.vmesh.trimesh.visual, "material", None)
            material_checks.append(
                dict(
                    entity=entity.name,
                    material=getattr(mat, "name", None),
                    metallic=getattr(mat, "metallicFactor", None),
                    roughness=getattr(mat, "roughnessFactor", None),
                    has_texture=getattr(mat, "baseColorTexture", None) is not None,
                )
            )
    save(output / "renderer_materials.json", material_checks)
    folders = {}
    for name in task.cameras:
        folders[name] = output / name
        folders[name].mkdir()
    for index in range(frames):
        angle = np.deg2rad(-12 + 24 * index / max(frames - 1, 1))
        offset = Rotation.from_euler("z", angle).apply([0.62, -0.65, 0.48])
        task.cameras["front_oblique"].set_pose(pos=center + offset, lookat=center)
        for name, camera in task.cameras.items():
            rgb = camera.render(rgb=True)[0]
            Image.fromarray(rgb).save(folders[name] / f"{index:04d}.jpg", quality=95)
        if index % 30 == 0:
            print(f"{report['family']} preview {index}/{frames}", flush=True)
    videos = {}
    for name, folder in folders.items():
        path = output / f"{name}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-framerate",
                str(fps),
                "-i",
                str(folder / "%04d.jpg"),
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(path),
            ],
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], check=True
        )
        videos[name] = dict(
            file=path.name,
            sha256=sha(path),
            frames=frames,
            fps=fps,
            duration_s=frames / fps,
        )
    save(
        output / "render_report.json",
        dict(
            scope="static compact scene and material presentation with unchanged full-size robot for scale",
            source_report_sha256=sha(source / "report.json"),
            family=report["family"],
            complete_robot_demo=False,
            physics_execution=False,
            tool_pose_progress=progress,
            robot_pose="parked beside toy; no grasp or action",
            robot_arm_qpos=park_arm,
            videos=videos,
            passed=True,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()
    render(args.source, args.output, frames=args.frames)
