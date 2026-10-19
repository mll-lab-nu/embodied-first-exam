"""The robot's own model for the low-level seat (docs/construction_zh.md step 3, the low level's toolkit; the
information boundary): `seat/robot_only.xml`, the base + pedestal + arm + racket cut out of the match simulator's scene
(sim/scene/bm_scene.xml), so it can never drift from the simulated robot. The low level's /spec carries it
(robot_model.robot_only_xml) and the seat has it at /opt/robot/robot_only.xml; tests/test_badminton.py checks that its
forward kinematics and dynamics equal the simulator's and that it holds nothing of the world.

    python3 sports/badminton/robot_model.py            # rewrites seat/robot_only.xml (then refresh the manifest's
                                                       # sha256: python3 -m skilleval.toolkit check ... --fix)

Kept: the compiler and physics options, the arm's defaults, its meshes, the body tree from the base (its two prismatic
joints base_x, base_y in the world frame of the match, as `game spec` documents; the platform and pedestal are drawn
only) through link0 to the racket (joints, ranges, armature, damping, masses, inertias, geoms, the head-centre site),
the robot's own contact exclusions, its self-collision pairs (the arm and racket against its links, pedestal and
platform) and its 9 motors (2 base drives, 7 joint torques).
Dropped: everything that is not the robot - the shuttle (a mocap drawing), the court, the net, the floor, the lights,
textures, materials, visual settings - and in a duel the other robot.

The base is whatever the scene's root body `base` is (today a gantry; a slower real base replaces it in the scene and
this file follows: nothing here is specific to the gantry).
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENE = HERE / "sim" / "scene" / "bm_scene.xml"
OUT = HERE / "seat" / "robot_only.xml"
ROBOT_ROOT = "base"

HEADER = """
  The robot's own model (generated from the match simulator's scene by sports/badminton/robot_model.py; do not
  edit): MuJoCo Menagerie Franka Panda (panda_nohand, Apache-2.0, assets/LICENSE.menagerie-franka) on a 1.0 m
  pedestal whose base moves in x and y (two prismatic joints base_x, base_y: its position in the world frame of the
  match, your own frame), holding a badminton racket (head centre = site racket_center, 0.56 m beyond the flange;
  string-face normal = the racket body's local +x axis). It holds the robot only: kinematic tree, joint ranges (the
  base's travel), armature and damping, masses and inertias, collision meshes, the self-collision pairs (the arm and
  racket against its own links, pedestal and platform) and the 9 motors (2 base drives, 7 joint torques). Nothing of
  the world is in it: no shuttle, court, net or opponent. Note: base_y = 0 lies outside its range; set qpos before
  stepping. The servo that follows your joint targets (1 kHz) is documented in `game spec` (limits.controller) and is
  the toolkit's servo model (lib/bm_servo.py).
"""


def robot_only_xml(scene: Path = SCENE) -> str:
    src = ET.parse(scene).getroot()
    out = ET.Element("mujoco", {"model": "franka_racket_robot_only"})
    out.append(ET.Comment(HEADER.rstrip() + "\n"))
    for tag in ("compiler", "option"):
        el = src.find(tag)
        if el is not None:
            out.append(copy.deepcopy(el))
    out.append(copy.deepcopy(src.find("default")))
    asset = ET.SubElement(out, "asset")
    for m in src.find("asset").findall("mesh"):
        asset.append(copy.deepcopy(m))
    wb = ET.SubElement(out, "worldbody")
    robot = [b for b in src.find("worldbody") if b.tag == "body" and b.get("name") == ROBOT_ROOT]
    assert len(robot) == 1, "the scene must hold exactly one robot rooted at its base"
    wb.append(copy.deepcopy(robot[0]))
    robot_bodies = {b.get("name") for b in robot[0].iter("body")}
    robot_geoms = {g.get("name") for g in robot[0].iter("geom")}
    con = ET.SubElement(out, "contact")
    for el in src.find("contact"):
        if el.tag == "exclude" and {el.get("body1"), el.get("body2")} <= robot_bodies:
            con.append(copy.deepcopy(el))
        if el.tag == "pair" and (el.get("name") or "").startswith("selfcol") and \
                {el.get("geom1"), el.get("geom2")} <= robot_geoms:     # its self-collision (sport.toml [self_collision])
            con.append(copy.deepcopy(el))
    out.append(copy.deepcopy(src.find("actuator")))
    ET.indent(out, space="  ")
    return ET.tostring(out, encoding="unicode") + "\n"


def mesh_files(scene: Path = SCENE) -> list[Path]:
    """The mesh files robot_only.xml references, plus the Menagerie licence."""
    src = ET.parse(scene).getroot()
    d = scene.parent / src.find("compiler").get("meshdir", ".")
    return [d / m.get("file") for m in src.find("asset").findall("mesh")] + [d / "LICENSE.menagerie-franka"]


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(robot_only_xml())
    print(OUT)
