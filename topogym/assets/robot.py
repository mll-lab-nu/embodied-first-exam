"""Shared robot asset selection and original-scale Panda / Robotiq assembly."""

from copy import deepcopy
import hashlib
from importlib.util import find_spec
import math
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
# A named task reference, not a scaled or shortened physical gripper. At a
# near-closed parallel grasp the pad centre remains ~102.9 mm beyond `hand`.
ROBOTIQ_HAND_REFERENCE_Z = 0.0518


def asset_root(explicit=None):
    """Resolve an installed/external asset directory without writing to the package."""
    if explicit is not None:
        root = Path(str(explicit)).expanduser().resolve()
    elif os.environ.get("TOPOGYM_ASSET_ROOT"):
        root = Path(os.environ["TOPOGYM_ASSET_ROOT"]).expanduser().resolve()
    else:
        root = ROOT / "assets"
    if not root.is_dir():
        raise FileNotFoundError("Robot assets unavailable; set asset_root or TOPOGYM_ASSET_ROOT")
    return root


def robot_cache_dir():
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home()/".cache")))
    return base / "topogym" / "robots"


def tool_model(cfg):
    return str(cfg.robot.get("tool_model", "panda"))


def robot_asset(cfg):
    frozen = cfg.robot.get("frozen_asset")
    if frozen:
        path = Path(str(frozen))
        if not path.is_absolute() or not path.is_file():
            raise ValueError("Frozen assembled robot asset must be an existing absolute path")
        return str(path)
    if str(cfg.robot.name) == "aloha":
        return str(build_tabletop_aloha(float(cfg.robot.get("base_riser_height_m", 0.)),
                                       assets=cfg.robot.get("asset_root")))
    if tool_model(cfg) == "panda":
        return str(cfg.robot.asset)
    if tool_model(cfg) != "robotiq_2f85":
        raise ValueError(f"Unknown tool: {tool_model(cfg)}")
    source = Path(str(cfg.robot.asset))
    if not source.is_absolute():
        spec = find_spec("genesis")
        if spec is None or spec.origin is None:
            raise FileNotFoundError("The Genesis robot asset package is not installed")
        source = Path(spec.origin).parent / "assets" / source
    return str(build_robotiq_panda(source, assets=cfg.robot.get("asset_root")))


def build_tabletop_aloha(base_riser_height_m=0., *, assets=None):
    """Keep the upstream dual arm model, placing both mounting faces at z=0.

    The source's 20 mm lift belongs to its separate extrusion/table scene.
    TopoGym supplies its own table, room and cameras. Mesh scales, joint names,
    limits, inertias, contacts and finger equalities remain those of ALOHA 2.
    """
    if not math.isfinite(base_riser_height_m) or base_riser_height_m < 0:
        raise ValueError("ALOHA base riser must be finite and nonnegative")
    folder = asset_root(assets) / "robots/aloha"
    sources = [folder / name for name in
               ("aloha.xml", "joint_position_actuators.xml", "keyframe_ctrl.xml")]
    key = hashlib.sha256(b"".join(p.read_bytes() for p in sources)
                         + Path(__file__).read_bytes()
                         + f"riser={base_riser_height_m:.12g};source={folder}".encode()).hexdigest()[:16]
    target = robot_cache_dir() / f"aloha_tabletop_{key}.xml"
    if target.exists():
        return target
    model = ET.parse(sources[0]).getroot()
    model.find("compiler").set("meshdir", str(folder / "assets"))
    for include in list(model.findall("include")):
        for node in ET.parse(folder / include.get("file")).getroot():
            model.append(deepcopy(node))
        model.remove(include)
    world = model.find("worldbody")
    for node in list(world):
        if node.tag == "body":
            pos = [float(v) for v in node.get("pos").split()]
            pos[2] += base_riser_height_m-0.02
            node.set("pos", " ".join(str(v) for v in pos))
        else:
            world.remove(node)
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(model)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".xml", delete=False) as stream:
        temp = Path(stream.name)
    try:
        ET.ElementTree(model).write(temp, encoding="unicode")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def build_robotiq_panda(source, *, assets=None):
    source = Path(source)
    robotiq = asset_root(assets) / "robots/robotiq_2f85"
    key = hashlib.sha256(
        source.read_bytes()
        + (robotiq / "2f85.xml").read_bytes()
        + str((source.resolve(), robotiq)).encode()
        + Path(__file__).read_bytes()
    ).hexdigest()[:16]
    target = robot_cache_dir() / f"panda_robotiq_{key}.xml"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    panda = ET.parse(source).getroot()
    grip = ET.parse(robotiq / "2f85.xml").getroot()
    # Absolute assets preserve both packages' millimetre/metre scale settings.
    for tree, folder in ((panda, source.parent / "assets"), (grip, robotiq / "assets")):
        for mesh in tree.findall("asset/mesh"):
            mesh.set("name", mesh.get("name", Path(mesh.get("file")).stem))
            mesh.set("file", str((folder / mesh.get("file")).resolve()))
    aliases = {
        "right_pad": "left_finger",
        "left_pad": "right_finger",
        "right_driver_joint": "finger_joint1",
        "left_driver_joint": "finger_joint2",
    }
    # Namespace the incoming model, including inherited MJCF default classes.
    names = {
        value: aliases.get(value, "r85_" + value)
        for node in grip.iter()
        for attr, value in node.attrib.items()
        if attr == "name" or (attr == "class" and node.tag == "default")
    }
    names.update(aliases)
    for node in grip.iter():
        for attr, value in list(node.attrib.items()):
            if (
                attr
                in (
                    "name",
                    "class",
                    "childclass",
                    "mesh",
                    "material",
                    "joint",
                    "joint1",
                    "joint2",
                    "body1",
                    "body2",
                    "tendon",
                )
                and value in names
            ):
                node.set(attr, names[value])
    grip.find(".//body[@name='r85_base']").set("quat", "1 0 0 0")
    for node in grip.find("default"):
        panda.find("default").append(deepcopy(node))
    for node in grip.find("asset"):
        panda.find("asset").append(deepcopy(node))
    old = panda.find(".//body[@name='hand']")
    old.set("name", "tool_mount")
    for child in list(old):
        old.remove(child)
    old.append(deepcopy(grip.find("worldbody/body")))
    ET.SubElement(old, "body", name="hand", pos=f"0 0 {ROBOTIQ_HAND_REFERENCE_Z}")
    for tag in ("tendon", "equality", "keyframe"):
        node = panda.find(tag)
        if node is not None:
            panda.remove(node)
    for tag in ("tendon", "equality"):
        panda.append(deepcopy(grip.find(tag)))
    contact = panda.find("contact")
    if contact is None:
        contact = ET.SubElement(panda, "contact")
    for node in grip.find("contact"):
        contact.append(deepcopy(node))
    actuator = panda.find("actuator")
    for node in list(actuator):
        if node.get("tendon") is not None:
            actuator.remove(node)
    for node in grip.find("actuator"):
        actuator.append(deepcopy(node))
    panda.set("model", "panda_robotiq_2f85")
    panda.find("compiler").set("meshdir", "")
    ET.indent(panda)
    # Multiple episode workers may compose the same tool on a cold cache.
    with tempfile.NamedTemporaryFile(
        dir=target.parent, suffix=".xml", delete=False
    ) as stream:
        temp = Path(stream.name)
    try:
        ET.ElementTree(panda).write(temp, encoding="unicode")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target
