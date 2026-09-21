"""Three synchronized close-up views of certified family motions (kinematic).

This is an explicitly labelled mechanism comparison, not a physics recording or
a complete robot demo. Uses the same exact box compounds and relative paths as
the accepted instances; fixed cameras and scale across the three panels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import imageio.v2 as imageio
import mujoco
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation

from .assembly_task import initial_poses, motions
from .geometry import CoilAssembly
from .variants import canonical, load_instance

VIEWS = {
    "motion_front": [0.02, -0.48, 0.04],
    "motion_side": [0.48, -0.13, 0.10],
    "motion_oblique": [0.30, -0.40, 0.23],
}
LABELS = {
    "eccentric_turn": "A | ECCENTRIC PIVOT 9 mm",
    "split_turn_offset": "B | TURN - OFFSET 9 mm - TURN",
    "axial_screw_turn": "C | TURN + AXIAL ADVANCE 9 mm",
}


def _numbers(v):
    return " ".join(str(float(x)) for x in v)


def render(instances, metadata, video_root):
    metadata, video_root = Path(metadata).resolve(), Path(video_root).resolve()
    metadata.mkdir(parents=True, exist_ok=False)
    systems = []
    fps, size = 20, 480
    for folder in map(Path, instances):
        result = json.loads((folder / "result.json").read_text())
        source = folder / result["candidate_directory"]
        cfg = load_instance(source / "instance.json")
        a = CoilAssembly(OmegaConf.to_container(cfg.task.template, resolve=True))
        origin = np.array([0, 0.05, -min(b.visual.bounds[0, 2] for b in a.bodies)])
        route, _ = motions(
            a,
            initial_poses(
                a,
                origin,
                Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True),
                cfg.task.initial_xy_offset_m,
            ),
        )
        # Isolate the distinguishing turn/offset and closing stages at native
        # robot-plan durations. Assembly approach and long insertion are omitted.
        route = [
            m for m in route if m.name not in ("approach_align", "assembly_insert")
        ]
        root = ET.Element("mujoco")
        ET.SubElement(root, "statistic", extent=".25", center="0 0 0")
        visual = ET.SubElement(root, "visual")
        ET.SubElement(visual, "global", offwidth=str(size), offheight=str(size))
        ET.SubElement(visual, "map", znear=".002")
        world = ET.SubElement(root, "worldbody")
        ET.SubElement(
            world, "light", pos=".1 -.4 .5", diffuse=".8 .8 .8", ambient=".35 .35 .35"
        )
        target = np.array([-0.015, 0, -0.025])
        for name, pos in VIEWS.items():
            z = np.array(pos) - target
            z /= np.linalg.norm(z)
            x = np.cross([0, 0, 1], z)
            x /= np.linalg.norm(x)
            y = np.cross(z, x)
            ET.SubElement(
                world,
                "camera",
                name=name,
                pos=_numbers(pos),
                xyaxes=_numbers(np.r_[x, y]),
                fovy="31",
            )
        for i, body in enumerate(a.bodies):
            node = ET.SubElement(world, "body", name=body.name, mocap="true")
            for low, high in body.boxes:
                ET.SubElement(
                    node,
                    "geom",
                    type="box",
                    pos=_numbers((low + high) / 2),
                    size=_numbers((high - low) / 2),
                    rgba=".68 .48 .12 1" if i == 0 else ".54 .62 .70 1",
                    contype="0",
                    conaffinity="0",
                )
        xml = ET.tostring(root, encoding="unicode")
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        systems.append(
            dict(
                model=model,
                data=data,
                renderer=mujoco.Renderer(model, height=size, width=size),
                route=route,
                family=cfg.task.derived_variant.family_id,
                instance_id=result["instance_id"],
                duration=sum(m.duration_s * 2 for m in route),
                instance_path=str(source / "instance.json"),
            )
        )
    duration = max(s["duration"] for s in systems) + 1
    outputs = {}
    writers = {}
    for name in VIEWS:
        path = video_root / name / f"2026-09-19_seed_families_v1_kinematic_{name}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(path)
        outputs[name] = path
        writers[name] = imageio.get_writer(
            path,
            fps=fps,
            codec="libx264",
            quality=8,
            macro_block_size=1,
            ffmpeg_log_level="error",
        )
    try:
        for frame in range(round(duration * fps)):
            panels = {name: [] for name in VIEWS}
            for s in systems:
                t = frame / fps
                for m in s["route"]:
                    dt = m.duration_s * 2
                    if t <= dt:
                        break
                    t -= dt
                # End holds are explicit; do not repeat the closing motion.
                u = 1.0 if frame / fps >= s["duration"] else min(1.0, t / dt)
                u = u**3 * (10 + u * (-15 + 6 * u))
                r, p = m.pose(u)
                s["data"].mocap_pos[1] = p
                s["data"].mocap_quat[1] = Rotation.from_matrix(r).as_quat()[
                    [3, 0, 1, 2]
                ]
                mujoco.mj_forward(s["model"], s["data"])
                for name in VIEWS:
                    s["renderer"].update_scene(s["data"], camera=name)
                    im = Image.fromarray(s["renderer"].render())
                    draw = ImageDraw.Draw(im)
                    draw.rectangle((0, 0, size, 52), fill=(240, 243, 246))
                    draw.text((12, 8), LABELS[s["family"]], fill=(20, 30, 40))
                    draw.text(
                        (12, 28),
                        m.name if frame / fps < s["duration"] else "END HOLD",
                        fill=(20, 30, 40),
                    )
                    draw.rectangle((0, size - 27, size, size), fill=(240, 243, 246))
                    draw.text(
                        (12, size - 20),
                        "KINEMATIC CLOSE-UP | NOT PHYSICS | fixed camera/scale",
                        fill=(20, 30, 40),
                    )
                    panels[name].append(np.asarray(im))
            for name, items in panels.items():
                joined = np.concatenate(items, axis=1)
                writers[name].append_data(joined)
                if frame in (0, 60, 120, round(duration * fps) - 1):
                    Image.fromarray(joined).save(metadata / f"{name}_{frame:03d}.png")
    finally:
        for w in writers.values():
            w.close()
        for s in systems:
            s["renderer"].close()
    report = dict(
        classification="kinematic_mechanism_excerpt",
        physics_steps=0,
        counts_as_complete_robotics_demo=False,
        scope="turn/offset and closure only; fixed local object frame; end holds for shorter routes",
        frames=round(duration * fps),
        fps=fps,
        duration_s=duration,
        instances=[
            {k: s[k] for k in ("family", "instance_id", "instance_path", "duration")}
            for s in systems
        ],
        videos={
            name: dict(
                path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            )
            for name, path in outputs.items()
        },
    )
    (metadata / "review.json").write_text(canonical(report) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", nargs=3, required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--video-root", default="demos/cast_coil")
    args = parser.parse_args()
    print(json.dumps(render(args.instances, args.metadata, args.video_root), indent=2))
