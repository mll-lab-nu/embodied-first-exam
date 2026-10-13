"""Public nominal Go2 model builder. Caller supplies the public asset directory."""

from pathlib import Path
import xml.etree.ElementTree as ET


def xml(asset_directory, poles=()):
    path = Path(asset_directory)
    root = ET.parse(path / "go2.xml").getroot()
    root.find("compiler").set("meshdir", str(path / "assets"))
    option = root.find("option")
    option.set("timestep", "0.002")
    option.set("integrator", "implicitfast")
    # Preserve native Menagerie collisions and inertia, with explicit servo conventions.
    for joint in root.findall(".//default/joint"):
        if "damping" in joint.attrib:
            joint.set("damping", "0.05")
            joint.set("frictionloss", "0.0")
    for motor in root.findall(".//default/motor"):
        if "45.43" in motor.get("ctrlrange", ""):
            motor.set("ctrlrange", "-35.55 35.55")
    asset = root.find("asset")
    ET.SubElement(
        asset,
        "texture",
        type="skybox",
        builtin="gradient",
        rgb1="0.75 0.82 0.88",
        rgb2="0.95 0.96 0.97",
        width="128",
        height="768",
    )
    ET.SubElement(asset, "material", name="arena", rgba="0.66 0.65 0.61 1", reflectance="0.04")
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth="640", offheight="480")
    ET.SubElement(visual, "quality", shadowsize="1024", offsamples="0")
    ET.SubElement(visual, "headlight", ambient="0.4 0.4 0.4", diffuse="0.65 0.65 0.65", specular="0.1 0.1 0.1")
    world = root.find("worldbody")
    ET.SubElement(world, "light", pos="0 -3 6", dir="0 0 -1", directional="true", castshadow="true")
    ET.SubElement(
        world,
        "geom",
        name="floor",
        type="plane",
        size="0 0 0.05",
        material="arena",
        condim="3",
        friction="0.8 0.02 0.01",
    )
    for k, (x, y) in enumerate(poles):
        ET.SubElement(
            world,
            "geom",
            name=f"pole{k}",
            type="cylinder",
            pos=f"{x} {y} 0.36",
            size="0.045 0.36",
            rgba="0.94 0.43 0.08 1",
            condim="3",
        )
    return ET.tostring(root, encoding="unicode")
