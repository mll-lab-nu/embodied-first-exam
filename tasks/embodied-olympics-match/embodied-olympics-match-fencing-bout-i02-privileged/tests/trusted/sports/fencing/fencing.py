"""The scene of robot epee fencing (fencing-7, the phrase-level sport): the piste and two Unitree G1 humanoids of the
robot library, each holding an epee on its right wrist mount, for the cameras. The phrases themselves were measured in
the fencing-6 world (this file's World and Phrase referee up to revision fencing-6, with NVIDIA's SONIC policy on the
robots: docs/screening/fencing/phrase/) and are replayed from phrases/table.json (phrases.py); the cameras draw the
joint positions kept from them (phrases/frames.npz) in this scene, which is the scene they were measured in.

World (metres): piste surface z = 0, long axis x, centre line x = 0, on-guard lines x = +-2, rear limits x = +-7,
lateral limits y = +-0.75 (t.18-t.19). Fencer A stands at x < 0 facing +x, fencer B at x > 0 facing -x (both
right-handed). Each seat sees everything in its OWN frame: x' = s x, y' = s y, z' = z with s = +1 for A and -1 for B,
so in its own frame every fencer stands at x' < 0 and faces +x'.
"""
from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
_ROOT = HERE.parent                      # sim/ in a task (bodies/ next to sport/); sports/ in a checkout
sys.path.insert(0, str(_ROOT if (_ROOT / "bodies").is_dir() else _ROOT.parent))
from bodies import load_body  # noqa: E402

CONTROL_DT, SUBSTEPS, PHYS_DT = 0.01, 10, 0.001
SEATS = ("A", "B")
SIGN = {"A": 1.0, "B": -1.0}
OTHER = {"A": "B", "B": "A"}
# ---- piste (t.18, t.19)
PISTE_HALF, ON_GUARD, PISTE_HALF_W = 7.0, 2.0, 0.75
# ---- the fencer
BODY, HAND, WALKER = "unitree_g1", "epee", "falcon_legs"
SETTLE_STEPS = 100             # after the referee places the robots: 1 s standing on guard (frozen fencing time)
FALL_Z, FALL_TILT = 0.45, 1.0  # pelvis height (m), pelvis tilt (rad): down
ARM_PARTS = ("shoulder", "elbow", "wrist", "hand", "mount")   # arm on arm is close quarters (t.24), not corps-a-corps
# ---- the apparatus
F_TOUCH = 7.35                 # N: 750 g on the point
T_TOUCH_SAMPLES = 3            # >= 2 ms: three consecutive 1 ms samples above F_TOUCH
DOUBLE_MS = 45                 # lockout: a touch by the other within 45 ms is a double (40-50 ms, Appendix B)
ACCENT = {"A": (0.1, 0.35, 0.85, 1), "B": (0.85, 0.15, 0.12, 1)}
RED, BLUE, YELLOW = (0.85, 0.15, 0.12, 1), (0.1, 0.35, 0.85, 1), (1.0, 0.85, 0.1, 1)
TINT = {"own": (0.9, 0.45, 0.4, 1), "opponent": (0.35, 0.5, 0.95, 1)}     # the robots' shells in a seat's images
REVISION = "fencing-7"

WORLD_XML = f"""<mujoco model="piste"><compiler angle="radian" autolimits="true"/>
<option timestep="{PHYS_DT}" integrator="implicitfast"/>
<visual><global offwidth="1280" offheight="720"/></visual>
<worldbody><light pos="0 0 4" dir="0 0 -1"/><light directional="true" pos="0 -6 4" dir="0 1 -0.6" diffuse="0.5 0.5 0.5"/>
<geom name="floor" type="plane" size="10 4 0.1" conaffinity="5" rgba="0.55 0.55 0.6 1"/>
<geom name="piste" type="box" size="{PISTE_HALF} {PISTE_HALF_W} 0.0005" pos="0 0 0.0005" contype="0" conaffinity="0"
 rgba="0.35 0.38 0.45 1"/>
<geom name="centre_line" type="box" size="0.01 {PISTE_HALF_W} 0.0006" pos="0 0 0.0006" contype="0" conaffinity="0" rgba="1 1 1 1"/>
<geom name="guard_A" type="box" size="0.01 {PISTE_HALF_W} 0.0006" pos="{-ON_GUARD} 0 0.0006" contype="0" conaffinity="0" rgba="1 1 1 1"/>
<geom name="guard_B" type="box" size="0.01 {PISTE_HALF_W} 0.0006" pos="{ON_GUARD} 0 0.0006" contype="0" conaffinity="0" rgba="1 1 1 1"/>
<geom name="rear_A" type="box" size="0.01 {PISTE_HALF_W} 0.0006" pos="{-PISTE_HALF} 0 0.0006" contype="0" conaffinity="0" rgba="1 0.2 0.2 1"/>
<geom name="rear_B" type="box" size="0.01 {PISTE_HALF_W} 0.0006" pos="{PISTE_HALF} 0 0.0006" contype="0" conaffinity="0" rgba="1 0.2 0.2 1"/>
</worldbody></mujoco>"""


def scene_xml(view: str | None = None) -> str:
    """the piste and both fencers (the library's mount: the robot, its epee, its self-collision pairs). view: the seat
    whose camera images it draws (its robot red, the opponent blue, the points yellow; the physics is the same)"""
    B = load_body(BODY)
    root = ET.fromstring(WORLD_XML)
    for s in SEATS:
        acc = ACCENT[s] if view is None else (RED if s == view else BLUE)
        B.mount(root, f"{s}_", (-SIGN[s] * ON_GUARD, 0.0, 0.0), 0.0 if s == "A" else math.pi, hand=HAND, accent=acc)
    if view is not None:                  # the images only: own robot light red, the opponent light blue, points yellow
        for body in root.find("worldbody").iter("body"):
            nm = body.get("name") or ""
            if nm[:2] not in ("A_", "B_") or nm.endswith("hand"):
                continue
            tint = TINT["own" if nm[0] == view else "opponent"]
            for g in body.findall("geom"):
                if g.get("contype", None) == "0" or g.get("class", "").endswith("visual") or g.get("group") in ("1", "2"):
                    g.attrib.pop("material", None)
                    g.set("rgba", " ".join(str(c) for c in tint))
        for g in root.iter("geom"):
            if (g.get("name") or "").endswith("hand_tip"):
                g.set("rgba", " ".join(str(c) for c in YELLOW))
    return ET.tostring(root, encoding="unicode")
