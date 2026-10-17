"""Robot-omitted meta view of the unchanged binder and seven-panel punched sheets."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ORIGINAL = REPO / "scripts/scene_expansion/tasks/binder_pages"

import mujoco
import numpy as np


def read_only_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


hardware = read_only_module("t37_original_hardware", ORIGINAL / "scene.py")
paper = read_only_module("t37_original_panels", ORIGINAL / "paper.py")


def dump(path, value):
    def encode(x):
        if isinstance(x, np.ndarray):
            return x.tolist()
        if isinstance(x, np.generic):
            return x.item()
        return str(x)

    Path(path).write_text(json.dumps(value, indent=2, default=encode) + "\n")


def build():
    root = ET.Element("mujoco", model="T37 Avery 05806 punched pages | analytical-only meta view")
    node, geom = hardware.node, hardware.geom
    node(root, "compiler", angle="radian", autolimits="true")
    node(
        root,
        "option",
        timestep=0.001,
        integrator="implicitfast",
        iterations=80,
        jacobian="sparse",
        cone="elliptic",
        impratio=10,
    )
    asset, world = node(root, "asset"), node(root, "worldbody")
    node(asset, "material", name="paper_stock", rgba=(0.95, 0.93, 0.86, 1), specular=0.01)
    node(root, "contact")
    visual = node(root, "visual")
    node(visual, "global", offwidth=640, offheight=480)
    node(visual, "headlight", ambient=(0.18, 0.18, 0.18), diffuse=(0.15, 0.15, 0.15))
    geom(world, "floor", "plane", (3, 3, 0.05), pos=(0, 0, -0.1), color=(0.65, 0.68, 0.67, 1))
    geom(world, "desk", "box", (0.39, 0.43, 0.022), pos=(0.59, 0.05, 0.678), color=(0.54, 0.40, 0.27, 1))
    for x in (0.25, 0.93):
        for y in (-0.31, 0.41):
            geom(
                world, f"desk_leg_{x}_{y}", "box", (0.022, 0.022, 0.39), pos=(x, y, 0.288), color=(0.25, 0.24, 0.21, 1)
            )
    node(world, "light", pos=(0.4, -0.5, 2.2), dir=(0.1, 0.3, -1), diffuse=(0.45, 0.45, 0.45))
    node(world, "light", pos=(0.8, 0.7, 1.9), dir=(-0.2, -0.4, -1), diffuse=(0.22, 0.22, 0.22))
    hardware.add_binder(root)
    topology = paper.add_pages(root, hardware.PAPER_ORIGIN, pages=2)
    # New declared ordinary initial layout: two separately supported loose sheets.
    # This is authored before compilation, never assigned as a function of progress.
    root.find(".//body[@name='page_0']").set("pos", "0.71 0.22 0.7003")
    root.find(".//body[@name='page_1']").set("pos", "0.71 -0.025 0.7003")
    xml = ET.tostring(root, encoding="unicode")
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert model.nu == 0 and model.nflex == 0 and len(topology["hole_records"]) == 6
    return model, data, xml, topology


def integration(model, data):
    result = np.empty(mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION))
    mujoco.mj_getState(model, data, result, mujoco.mjtState.mjSTATE_INTEGRATION)
    return result


def features(model, data, topology):
    gaps = [
        float(
            np.linalg.norm(data.site(f"tip_left_{i}").xpos - data.site(f"tip_right_{i}").xpos)
            - 2 * hardware.WIRE_RADIUS
        )
        for i in range(3)
    ]
    holes = []
    for row in topology["hole_records"]:
        body = data.body(row["body"])
        points = np.asarray(row["points"]) @ body.xmat.reshape(3, 3).T + body.xpos
        holes.append(
            {
                "page": row["page"],
                "hole": row["hole"],
                "center_world_m": points.mean(axis=0).tolist(),
                "normal_world": body.xmat.reshape(3, 3)[:, 2].tolist(),
                "source_boundary_vertices": 16,
            }
        )
    return {
        "ring_clear_gaps_m": gaps,
        "hole_frames": holes,
        "initial_captured_holes": 0,
        "full_task_executed": False,
        "native_warning_counts": [int(x.number) for x in data.warning],
    }


def save(folder, model, data, xml, topology):
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "model.xml").write_text(xml)
    mujoco.mj_saveModel(model, str(folder / "model.mjb"), None)
    np.savez_compressed(folder / "initial-state.npz", integration=integration(model, data))
    dump(folder / "paper-topology.json", topology)
    dump(folder / "initial-features.json", features(model, data, topology))
    dump(
        folder / "scene-summary.json",
        {
            "validation_mode": "analytical_only",
            "physics_steps": 0,
            "compiled": True,
            "robot_geometry_omitted_explicit_meta_variant": True,
            "nu": model.nu,
            "neq": model.neq,
            "nflex": model.nflex,
            "sheets": 2,
            "holes": 6,
            "sheet_dimensions_m": [paper.WIDTH, paper.HEIGHT],
            "material_thickness_m": paper.THICKNESS,
            "hole_radius_m": paper.HOLE_RADIUS,
            "wire_radius_m": hardware.WIRE_RADIUS,
            "radial_clearance_m": paper.HOLE_RADIUS - hardware.WIRE_RADIUS,
            "paper_bending_rigidity_nm": paper.D,
            "source_physics_unchanged": True,
            "initial_layout_variant": "two separately desk-supported loose sheets, no initial stack",
        },
    )
    dump(
        folder / "provenance.json",
        {
            "read_only_original_files": {
                str(ORIGINAL / n): hashlib.sha256((ORIGINAL / n).read_bytes()).hexdigest()
                for n in ("scene.py", "paper.py", "SPECIFICATION.md", "PHYSICS_LIMITS.md", "ASSET_PROVENANCE.md")
            },
            "product": "Avery05806 Standard View Mini Binder,1inch round rings,1.4inch spine,5.5x8.5inch sheets",
            "primary_refs": [
                "https://www.avery.com/products/binders/05806",
                "https://www.avery.com/help/article/mini-binders",
                "https://patents.google.com/patent/US2061676A/en",
            ],
            "manufacturer_CAD_claim": False,
            "old_hand_failures_preserved": True,
            "old_dense_flex_not_used": True,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    m, d, x, t = build()
    save(a.output.resolve(), m, d, x, t)
    print(
        json.dumps(
            {
                "compiled": True,
                "validation_mode": "analytical_only",
                "sheets": 2,
                "holes": 6,
                "nu": m.nu,
                "nflex": m.nflex,
            }
        ),
        flush=True,
    )
