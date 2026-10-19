"""RoboOlympics robot resource library (bodies/README.md, "机器人资源库"): shared robots, the attachments on their
common wrist mount, the one trusted limit / servo path, and optional control libraries. Not a part of the framework
(players / sports / core / tools): a library the sports draw from; core never imports it.

    from bodies import load_body, assemble
    B = load_body("wheeled_humanoid")                      # a robot: model, joints, actuators, real limits (body.toml)
    cfg = assemble("wheeled_humanoid", "paddle", controllers=["wholebody"])   # robot + attachment + controllers
    cfg.id                                                 # "wheeled_humanoid@wh-3+paddle+wholebody#<hash>"

A sport declares in sport.toml

    [body]
    name = "wheeled_humanoid"
    hand = "paddle"
    controllers = ["wholebody"]          # optional: bodies/control/<name>.py the sport imports

tools/generate.py then copies the robot (without its fine meshes and provenance tools), the attachments, the limit
/ servo path and the declared control libraries into the task's simulator directory, with configuration.json (the
assembled configuration's id and hash). The fixed-base arms (franka_panda, franka_fr3, kuka_iiwa14: limits only, each
sport's scene carries the arm's MJCF) are declared with [arm] body instead; the limits-only legged robots (booster_t1:
the sport's scene carries the model and its walking policy; bodies/servo.py Actuators + WalkCommand) with [legs] body.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# library robots with a model, a rig and a servo (load_body); "status" in each body.toml says what they may be used for
BODIES = ("wheeled_humanoid", "unitree_g1", "unitree_h1", "galaxea_r1pro", "tianji_marvin_pro", "abb_irb1100")
ARMS = ("franka_panda", "franka_fr3", "kuka_iiwa14")          # limits-only entries (bodies/limits.py)
LEGS = ("booster_t1",)                  # limits-only legged entries (bodies/servo.py Actuators + WalkCommand; the
                                        # sport's scene carries the model and the walking policy): sport.toml [legs] body
ROBOTS = BODIES + ARMS + LEGS
CONTROLLERS = ("wholebody", "arbiter", "kinematics")            # bodies/control/: optional, a sport imports them


def _path():
    if str(HERE.parent) not in sys.path:
        sys.path.insert(0, str(HERE.parent))


def load_body(name: str):
    """A library robot (bodies/<name>/body.py load()): mount into a scene, rig, robot-only export."""
    if name not in BODIES:
        raise ValueError(f"unknown body {name!r}; one of {list(BODIES)}")
    _path()
    return importlib.import_module(f"bodies.{name}.body").load()


def planner(name: str):
    """The whole-body planner module (bodies/control/wholebody.py), the same for every body with the wheeled
    humanoid's controlled vector (and the legged ones' planar copies)."""
    if name not in BODIES:
        raise ValueError(f"unknown body {name!r}; one of {list(BODIES)}")
    _path()
    return importlib.import_module("bodies.control.wholebody")


def assemble(robot: str, attachment: str | None = None, other_attachment: str | None = None, controllers=(),
             arm: str = "right"):
    """robot + attachment(s) + declared controllers -> an assembled configuration with its own version hash
    (bodies/assembly.py)."""
    _path()
    from bodies import assembly
    return assembly.assemble(robot, attachment, other_attachment, controllers, arm)
