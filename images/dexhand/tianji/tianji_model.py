"""Convert the public Tianji Marvin fixed dual-arm assets to MuJoCo.

Copied unchanged (apart from this note) from scripts/everyday_dexterity/tianji_model.py so that
images/dexhand/prepare_assets.py rebuilds the dexhand Tianji meshes from public sources only.

Geometry and joint frames come from DexForce's complete ACD asset. Its very
small mesh-density inertias are replaced by the corresponding public Genesis
Tianji link inertias. Controller gains are prototype choices; joint ranges and
force limits are retained from the source URDF. No wheel or floating base is
introduced. See the generated PROVENANCE.json for source hashes and licenses.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

import mujoco
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = REPO_ROOT / "images/everyday_dexterity/assets/tianji"
GENESIS_URL = (
    "https://huggingface.co/datasets/Genesis-Intelligence/assets/resolve/"
    "deffbe1685e5ce6aa289efdd541f762f1eb3353f/dual_arms_primitives.urdf"
)
JOINT_STEMS = (
    "SHOULDER_PITCH", "SHOULDER_ROLL", "ELBOW_PITCH", "ELBOW_YAW",
    "WRIST_PITCH", "WRIST_YAW", "WRIST_ROLL",
)
JOINT_NAMES = tuple(
    f"{stem}_{side}_J{i}" for side in ("L", "R")
    for i, stem in enumerate(JOINT_STEMS, 1)
)
END_EFFECTOR_BODIES = {"left": "left_ee", "right": "right_ee"}
END_EFFECTOR_SITES = {"left": "left_flange", "right": "right_flange"}
HOME = np.array([
    0.2303173887, -0.6985149333, 0.1181439914, -1.5353402992,
    0.0, -0.0570802685, -0.0221954653,
    -0.2303173887, -0.6985149333, -0.1181439914, -1.5353402992,
    0.0, -0.0570802685, 0.0221954653,
])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert_assets(asset_dir: Path = ASSET_DIR) -> Path:
    """Generate an arm-only XML, preserving visual material submeshes."""
    import trimesh

    asset_dir = Path(asset_dir).resolve()
    source_path = asset_dir / "robot_acd.urdf"
    source = ET.parse(source_path).getroot()
    genesis_path = asset_dir / "genesis_dual_arms_primitives.urdf"
    if not genesis_path.exists():
        urllib.request.urlretrieve(GENESIS_URL, genesis_path)
    genesis = ET.parse(genesis_path).getroot()
    genesis_links = {x.attrib["name"]: x for x in genesis.findall("link")}
    inertia_changes = []
    visual_colors: dict[str, list[float]] = {}
    converted = asset_dir / "converted_visual"
    converted.mkdir(exist_ok=True)
    collision_dir = asset_dir / "converted_collision"
    collision_dir.mkdir(exist_ok=True)
    for link in source.findall("link"):
        name = link.attrib["name"]
        for i, stem in enumerate(JOINT_STEMS, 1):
            for side in ("L", "R"):
                if name == f"{stem.lower()}_{side.lower()}_j{i}_link":
                    old = link.find("inertial")
                    assert old is not None
                    new = copy.deepcopy(genesis_links[f"Link{i}_{side}"].find("inertial"))
                    inertia_changes.append({
                        "link": name,
                        "source_mass_kg": float(old.find("mass").attrib["value"]),
                        "simulation_mass_kg": float(new.find("mass").attrib["value"]),
                        "inertia_source": f"Genesis Link{i}_{side}",
                    })
                    link.remove(old)
                    link.insert(0, new)
        for visual in list(link.findall("visual")):
            mesh = visual.find("geometry/mesh")
            if mesh is None:
                continue
            scene = trimesh.load(asset_dir / mesh.attrib["filename"], force="scene")
            link.remove(visual)
            for n, node in enumerate(scene.graph.nodes_geometry):
                transform, geom_name = scene.graph[node]
                geom = scene.geometry[geom_name].copy()
                geom.apply_transform(transform)
                basename = f"visual_{name}_{n}.stl"
                geom.export(converted / basename)
                replacement = copy.deepcopy(visual)
                replacement.find("geometry/mesh").attrib["filename"] = str(converted / basename)
                material = getattr(geom.visual, "material", None)
                color = getattr(material, "baseColorFactor", None)
                if color is None:
                    color = [225, 228, 229, 255]
                rgba = (np.asarray(color, dtype=float) / 255.0).tolist()
                material_element = ET.SubElement(replacement, "material", name=basename)
                ET.SubElement(material_element, "color", rgba=" ".join(map(str, rgba)))
                visual_colors[Path(basename).stem] = rgba
                link.append(replacement)
        for collision in list(link.findall("collision")):
            mesh = collision.find("geometry/mesh")
            if mesh is None:
                continue
            # ACD OBJ files contain multiple disconnected convex parts. MuJoCo
            # builds one convex hull per mesh, so importing the entire file
            # would fill intentional gaps and cause false self-collisions.
            combined = trimesh.load(asset_dir / mesh.attrib["filename"],
                                    force="mesh", process=False)
            parts = combined.split(only_watertight=False)
            link.remove(collision)
            for n, part in enumerate(parts):
                basename = f"collision_{name}_{n}.stl"
                part.export(collision_dir / basename)
                replacement = copy.deepcopy(collision)
                replacement.find("geometry/mesh").attrib["filename"] = str(collision_dir / basename)
                link.append(replacement)
    mj = ET.SubElement(source, "mujoco")
    ET.SubElement(mj, "compiler", discardvisual="false", fusestatic="false", strippath="false", balanceinertia="true")
    patched_urdf = asset_dir / "converted_arm_only.urdf"
    ET.indent(source)
    ET.ElementTree(source).write(patched_urdf, encoding="unicode")
    model = mujoco.MjModel.from_xml_path(str(patched_urdf))
    output_path = asset_dir / "arm_only.xml"
    mujoco.mj_saveLastXML(str(output_path), model)
    mjcf = ET.parse(output_path).getroot()
    mjcf.attrib["model"] = "Tianji Marvin M6S CCS696 fixed dual arm"
    compiler = mjcf.find("compiler")
    compiler.attrib["angle"] = "radian"
    # Keep absolute paths in the authoring asset; tasks may relocate explicitly.
    for mesh in mjcf.findall("asset/mesh"):
        path = Path(mesh.attrib["file"])
        if not path.is_absolute():
            mesh.attrib["file"] = str((asset_dir / path).resolve())
    for geom in mjcf.findall(".//geom"):
        if geom.attrib.get("mesh") in visual_colors:
            geom.attrib["rgba"] = " ".join(map(str, visual_colors[geom.attrib["mesh"]]))
        else:
            geom.attrib.update(group="3", rgba="0 0 0 0")
    # These assembly-adjacent parts overlap in the released collision asset.
    # Fixed intermediate frames prevent the shoulder mount from receiving the
    # usual parent-child collision filter; the three compact wrist joints also
    # contain adjacent housings. Retain all other self-collision pairs.
    collision_exclusions = []
    contact = ET.SubElement(mjcf, "contact")
    for side in ("l", "r"):
        for a, b in (
            ("base_link", f"shoulder_pitch_{side}_j1_link"),
            (f"wrist_pitch_{side}_j5_link", f"wrist_roll_{side}_j7_link"),
        ):
            ET.SubElement(contact, "exclude", body1=a, body2=b)
            collision_exclusions.append([a, b])
    ET.SubElement(mjcf, "option", timestep="0.002", integrator="implicitfast", gravity="0 0 -9.81")
    actuator = ET.SubElement(mjcf, "actuator")
    joint_sources = {j.attrib["name"]: j for j in source.findall("joint")}
    joint_metadata = []
    for name in JOINT_NAMES:
        limit = joint_sources[name].find("limit").attrib
        rng = [float(limit["lower"]), float(limit["upper"])]
        effort = float(limit["effort"])
        joint = mjcf.find(f".//joint[@name='{name}']")
        joint.attrib.update(damping="2", armature="0.02")
        ET.SubElement(actuator, "position", name=f"{name}_target", joint=name,
                      kp="400", kv="35", ctrllimited="true", ctrlrange=" ".join(map(str,rng)),
                      forcelimited="true", forcerange=f"{-effort} {effort}")
        joint_metadata.append({"name": name, "range_rad": rng, "force_limit_nm": effort,
                               "source_velocity_limit_rad_s": float(limit["velocity"])})
    for side, body_name in END_EFFECTOR_BODIES.items():
        body = mjcf.find(f".//body[@name='{body_name}']")
        if body is None:
            raise RuntimeError(f"MuJoCo discarded the required flange body {body_name}.")
        ET.SubElement(body, "site", name=END_EFFECTOR_SITES[side], pos="0 0 0", size="0.008", rgba="0.9 0.2 0.15 1")
    keyframe = ET.SubElement(mjcf, "keyframe")
    ET.SubElement(keyframe, "key", name="home", qpos=" ".join(map(str,HOME)), ctrl=" ".join(map(str,HOME)))
    ET.indent(mjcf)
    ET.ElementTree(mjcf).write(output_path, encoding="unicode")
    model = mujoco.MjModel.from_xml_path(str(output_path))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    metadata = {
        "geometry_source": "DexForceAI/embodichain_data robot_assets/TianjiMarvin.zip",
        "geometry_revision": "48317bd8733182f36d306cc2a7a60ae5e47ed2c9",
        "geometry_dataset_license": "Apache-2.0",
        "inertia_source": GENESIS_URL, "inertia_dataset_license": "MIT",
        "source_arm_urdf_sha256": _sha(source_path),
        "genesis_urdf_sha256": _sha(genesis_path),
        "arm_xml_sha256": _sha(output_path),
        "inertia_changes": inertia_changes,
        "inertia_caveat": "Public asset estimates; not certified manufacturer system identification.",
        "controller_caveat": "Position gains, damping, and armature are prototype simulation parameters.",
        "joint_ranges_and_torque": "Source URDF values retained.",
        "fixed_base": True, "wheel_joints": [], "hand_attached": False,
        "collision_exclusions": collision_exclusions,
        "collision_exclusion_caveat": "Only assembly-adjacent shoulder mount and wrist housing pairs are excluded.",
        "nq": model.nq, "nv": model.nv, "nu": model.nu,
        "joints": joint_metadata, "home_rad": HOME.tolist(),
        "end_effectors": {
            side: {"body": END_EFFECTOR_BODIES[side], "site": site,
                   "home_position_m": data.site(site).xpos.tolist(),
                   "home_rotation": data.site(site).xmat.reshape(3,3).tolist()}
            for side,site in END_EFFECTOR_SITES.items()
        },
    }
    (asset_dir / "PROVENANCE.json").write_text(json.dumps(metadata, indent=2)+"\n")
    return output_path


def load_xml(asset_dir: Path = ASSET_DIR) -> ET.Element:
    """Read the prepared fixed dual-arm model for scene composition."""
    return ET.parse(Path(asset_dir) / "arm_only.xml").getroot()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, default=ASSET_DIR)
    args = parser.parse_args()
    print(convert_assets(args.asset_dir))
