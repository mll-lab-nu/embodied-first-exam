import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parent
SPECS = {
    "linearbot": {
        "xml": "bots/Linearbot/linearbot_mujoco.xml",
        "hands": ["gripper_L", "gripper_R"],
        "active": ["base_x", "base_y", "base_yaw", "joint9"]
        + [f"joint{i}_{side}" for side in ["L", "R"] for i in range(1, 7)],
    },
    "vega": {
        "xml": "bots/vega/mujoco/generated/vega_wheeled.xml",
        "hands": ["L_arm_l7", "R_arm_l7"],
        "active": ["base_x", "base_y", "base_yaw"]
        + [f"torso_j{i}" for i in range(1, 4)]
        + [f"{side}_arm_j{i}" for side in ["L", "R"] for i in range(1, 8)],
    },
}


def verify(robot):
    from control_assets import check

    return check("bots/Linearbot" if robot == "linearbot" else "bots/vega")


def build(robot):
    from control_assets import ROOT as ASSETS

    p = ASSETS / SPECS[robot]["xml"]
    root = ET.parse(p).getroot()
    compiler = root.find("compiler")
    base = p.parent / compiler.get("meshdir", "")
    compiler.set("meshdir", str(base))
    root.find("option").set("timestep", ".002")
    for b in root.iter("body"):
        b.attrib.pop("gravcomp", None)
    for name, body in zip(["left_hand", "right_hand"], SPECS[robot]["hands"]):
        parent = root.find(f".//body[@name='{body}']")
        ET.SubElement(
            parent,
            "site",
            name=name,
            pos="0 0 .08" if robot == "linearbot" else ".08 0 0",
            size=".012",
            rgba="0.1 1 .5 1",
        )
    wb = root.find("worldbody")
    for name, color in [("left_goal", "0.1 1 .5 .6"), ("right_goal", "1 .5 .1 .6")]:
        ET.SubElement(wb, "site", name=name, size=".025", rgba=color)
    ET.SubElement(wb, "site", name="base_goal", size=".05", rgba=".2 .6 1 .6")
    m = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    for i in range(m.nu):
        name = m.actuator(i).name
        jname = m.joint(m.actuator_trnid[i, 0]).name
        # Explicit benchmark caps; planar base/lift and Linearbot caps are not identified hardware values.
        cap = (
            400
            if jname in ["base_x", "base_y"]
            else 180
            if jname == "base_yaw"
            else 1500
            if jname == "joint9"
            else 700
            if "torso_j1" == jname
            else 380
            if jname.startswith("torso")
            else 150
            if ("arm_j1" in jname or "arm_j2" in jname)
            else 80
            if ("arm_j3" in jname or "arm_j4" in jname)
            else 100
            if robot == "linearbot" and jname in [f"joint{i}_{s}" for i in [1, 2, 3] for s in ["L", "R"]]
            else 30
        )
        m.actuator_forcelimited[i] = 1
        m.actuator_forcerange[i] = [-cap, cap]
    return m


class Robot:
    def __init__(self, name):
        self.name = name
        self.m = build(name)
        self.d = mujoco.MjData(self.m)
        self.names = SPECS[name]["active"]
        self.jids = np.array([self.m.joint(n).id for n in self.names])
        self.qids = self.m.jnt_qposadr[self.jids]
        self.vids = self.m.jnt_dofadr[self.jids]
        self.aids = np.array([next(i for i in range(self.m.nu) if self.m.actuator_trnid[i, 0] == j) for j in self.jids])
        self.n = len(self.names)
        self.home = np.zeros(self.m.nq)
        for side in ["L", "R"]:
            for j, v in (
                [(f"joint2_{side}", 0.9), (f"joint3_{side}", 1.2)]
                if name == "linearbot"
                else [(f"{side}_arm_j2", 0.4 if side == "L" else -0.4), (f"{side}_arm_j4", -0.8)]
            ):
                self.home[self.m.jnt_qposadr[self.m.joint(j).id]] = v
        if name == "vega":
            self.home[self.m.jnt_qposadr[self.m.joint("torso_j1").id]] = 0.25
            self.home[self.m.jnt_qposadr[self.m.joint("torso_j2").id]] = 0.5
            self.home[self.m.jnt_qposadr[self.m.joint("torso_j3").id]] = -0.25
        self.limits = self.m.jnt_range[self.jids].copy()
        self.speed = np.array([0.5, 0.5, 0.6] + [0.25 if n == "joint9" else 0.7 for n in self.names[3:]])
        self.d.qpos[:] = self.home
        mujoco.mj_forward(self.m, self.d)

    def set(self, q, v=None):
        self.d.qpos[:] = q
        self.d.qvel[:] = 0 if v is None else v
        mujoco.mj_forward(self.m, self.d)

    def poses(self):
        return np.r_[self.d.qpos[self.qids[:3]]], [
            (self.d.site(n).xpos.copy(), self.d.site(n).xmat.reshape(3, 3).copy()) for n in ["left_hand", "right_hand"]
        ]

    def feature(self, q, v, target, twist):
        self.set(q, v)
        base, hands = self.poses()
        err = np.r_[
            target[0] - base,
            *[
                np.r_[p - tp, 0.5 * sum(np.cross(tr[:, i], r[:, i]) for i in range(3))]
                for (tp, tr), (p, r) in zip(hands, target[1])
            ],
        ]
        return np.r_[q[self.qids] - self.home[self.qids], v[self.vids], err, twist].astype(np.float32), err

    def expert(self, err, twist, gain=4.0, damping=0.03):
        j = np.zeros((15, self.n))
        j[:3, :3] = np.eye(3)
        for k, name in enumerate(["left_hand", "right_hand"]):
            jp = np.zeros((3, self.m.nv))
            jr = jp.copy()
            mujoco.mj_jacSite(self.m, self.d, jp, jr, self.m.site(name).id)
            j[3 + 6 * k : 6 + 6 * k] = jp[:, self.vids]
            j[6 + 6 * k : 9 + 6 * k] = jr[:, self.vids]
        velocity = j.T @ np.linalg.solve(j @ j.T + np.eye(15) * damping**2, gain * err + twist)
        return np.clip(velocity, -self.speed, self.speed) / self.speed
