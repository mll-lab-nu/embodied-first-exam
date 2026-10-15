"""Authoring tool: freeze the scene sources this family builds from into ``assets/`` (run once).

* ``assets/t48_tray_glasses.xml``: the tray (original ROMANTISK perforated tray meshes) and the two glasses of the
  accepted T48 scene, verbatim from ``scripts/hand_support/tasks/T48/model.xml`` (the composed hand+scene model of
  the scene-expansion task), minus the counters/floor/lights that ``scene.py`` rebuilds.
* ``assets/sharpa_bimanual_hands.xml``: the left (mirrored Wave, mesh scale 1 -1 1) and right Sharpa Wave hands of the
  accepted ``sweep_dustpan`` rig (classes, materials, meshes, self-collision excludes and the 44 finger actuators),
  without the arm. Mesh files keep the ``${DEXHAND_ASSET_DIR}`` token that ``scene.py`` resolves.
* ``assets/manifest.json``: sha256 of every frozen file plus the sha256 of its source.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_scene(source: Path, out: Path) -> None:
    root = ET.parse(source).getroot()
    new = ET.Element("mujoco", model="T48 tray and glasses (frozen source)")
    asset = ET.SubElement(new, "asset")
    used = set()
    world = ET.SubElement(new, "worldbody")
    for body in root.find("worldbody").findall("body"):
        if body.get("name") in ("tray", "cup_0", "cup_1"):
            world.append(copy.deepcopy(body))
            used |= {g.get("mesh") for g in body.iter("geom") if g.get("mesh")}
    for mesh in root.find("asset"):
        if mesh.get("name") in used:
            asset.append(copy.deepcopy(mesh))
    ET.ElementTree(new).write(out, encoding="unicode")


def extract_hands(source: Path, out: Path) -> None:
    root = ET.parse(source).getroot()
    new = ET.Element("mujoco", model="Sharpa Wave left+right hands (from the accepted sweep_dustpan rig)")
    default = ET.SubElement(new, "default")
    for item in root.find("default"):
        if item.get("class") in ("l_hand_sharpa", "r_hand_sharpa"):
            default.append(copy.deepcopy(item))
    asset = ET.SubElement(new, "asset")
    for item in root.find("asset"):
        if (item.get("name") or "").startswith(("l_hand_", "r_hand_")):
            asset.append(copy.deepcopy(item))
    world = ET.SubElement(new, "worldbody")
    for body in root.iter("body"):
        if body.get("name") in ("l_hand_palm", "r_hand_palm"):
            world.append(copy.deepcopy(body))
    contact = ET.SubElement(new, "contact")
    for item in root.find("contact"):
        if all((item.get(k) or "").startswith(("l_hand_", "r_hand_")) for k in ("body1", "body2")):
            contact.append(copy.deepcopy(item))
    actuator = ET.SubElement(new, "actuator")
    for item in root.find("actuator"):
        if (item.get("name") or "").startswith(("l_hand_", "r_hand_")):
            actuator.append(copy.deepcopy(item))
    ET.ElementTree(new).write(out, encoding="unicode")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, required=True, help="scripts/hand_support/tasks/T48/model.xml")
    parser.add_argument("--hands", type=Path, required=True, help="families/sweep_dustpan/assets/sweep_sharpa.xml")
    args = parser.parse_args()
    assets = HERE / "assets"
    assets.mkdir(exist_ok=True)
    extract_scene(args.scene, assets / "t48_tray_glasses.xml")
    extract_hands(args.hands, assets / "sharpa_bimanual_hands.xml")
    manifest = {
        "schema_version": 1,
        "files": {name: sha(assets / name) for name in ("t48_tray_glasses.xml", "sharpa_bimanual_hands.xml")},
        "sources": {
            "t48_tray_glasses.xml": {"path": "scripts/hand_support/tasks/T48/model.xml", "sha256": sha(args.scene)},
            "sharpa_bimanual_hands.xml": {
                "path": "scripts/dexhand/families/sweep_dustpan/assets/sweep_sharpa.xml",
                "sha256": sha(args.hands),
            },
        },
    }
    (assets / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
