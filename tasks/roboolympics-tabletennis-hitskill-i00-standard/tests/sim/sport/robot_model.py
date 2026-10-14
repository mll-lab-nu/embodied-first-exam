"""The robot's own model for the low-level seat (docs/benchmarks/roboolympics-modes.md §2.3, information boundary):
`robot_only.xml`, the rail base + arm + paddle cut out of the match simulator's scene (sim/scene/tt_scene.xml),
so it can never drift from the simulated arm. The low action level's /spec carries it (robot_model.robot_only_xml);
tests/test_tabletennis.py checks that its forward kinematics equal the simulator's and that it holds nothing of the
world. (The legacy seat image also installed it with MuJoCo under /opt/robot; tools/generate.py has no per-level seat
files yet.)

Kept: the compiler and physics options, the arm's defaults, its meshes, the body tree from the rail base (its two
prismatic joints base_x, base_y in the world frame of the match, as `game spec` documents; column and carriage drawn
only) through link0 to the paddle (joints, ranges, armature, damping, masses, inertias, geoms, the blade-centre site),
the robot's own contact exclusions, its self-collision pairs (the arm and paddle against its links, column and
carriage) and its 9 motors (2 base drives, 7 joint torques).
Dropped: everything that is not the robot - ball, table, net, floor, the rails drawn on the floor, target zone, lights,
textures, materials, visual settings, the ball-table and ball-paddle contact pairs - and in a duel the other robot.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENE = HERE / "sim" / "scene" / "tt_scene.xml"
ROBOT_ROOT = "base"

HEADER = """
  The robot's own model (generated from the match simulator's scene by sports/tabletennis/robot_model.py;
  do not edit): MuJoCo Menagerie Franka Panda (panda_nohand, Apache-2.0, assets/LICENSE.menagerie-franka) with the
  table-tennis paddle bolted to the flange, on an x-y rail base in the world frame of the match: the base's prismatic
  joints base_x, base_y are its position (home (0, -1.75), link0 at z = 0, facing +y). It holds the robot only:
  kinematic tree, joint ranges (the base's travel), armature and damping, masses and inertias, collision meshes,
  the paddle (blade centre = site paddle_center, face normal = the paddle body's local +x axis) and the 9 motors
  (2 base drives, 7 joint torques). Nothing of the world is in it: no ball, table, net, floor or opponent. Note: the
  base joints' value 0 lies outside base_y's range; set qpos before stepping. The joint controller that tracks your
  targets (PD + gravity/Coriolis compensation, 1 kHz) is documented in `game spec` (limits.controller).
"""


def robot_only_xml(scene: Path = SCENE) -> str:
    src = ET.parse(scene).getroot()
    out = ET.Element("mujoco", {"model": "franka_paddle_robot_only"})
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
