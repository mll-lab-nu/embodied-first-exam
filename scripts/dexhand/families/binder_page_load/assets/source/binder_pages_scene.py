"""Closed-start Avery 05806 reconstruction with native passive mechanics.

Only the fourteen Tianji joints and forty-four Sharpa joints are actuated.
The binder is free, its covers have passive hinges, and unpinned perforated
paper uses native thin contact panels and physically scaled bending hinges.
"""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

SHARED = Path(__file__).resolve().parents[3] / "everyday_dexterity"
sys.path.insert(0, str(SHARED))
from tianji_model import HOME, JOINT_NAMES, load_xml
from hand_models import merge_hand

POSITION = np.array([0.48, 0.0, 0.705])
RING_RADIUS = 0.0140
WIRE_RADIUS = 0.0013
STATIONS = np.array([-0.06985, 0.0, 0.06985])
OPEN_ANGLE = 0.60
PLATE_Z = 0.006
LEVER_Y = -0.091
LEVER_LENGTH = 0.020
PAPER_WIDTH, PAPER_HEIGHT = 0.1397, 0.2159
PAPER_THICKNESS, PAPER_RADIUS = 0.0001, 0.00015
HOLE_RADIUS, HOLE_MARGIN = 0.003175, 0.009525
PAPER_ORIGIN = np.array([0.71, 0.20, 0.7003])


def node(parent, tag, **attributes):
    return ET.SubElement(parent, tag, {k: " ".join(map(str, v))
        if isinstance(v, (tuple, list, np.ndarray)) else str(v) for k, v in attributes.items()})


def geom(parent, name, kind, size, pos=(0, 0, 0), mass=0, color=(0.75, 0.77, 0.78, 1), **kw):
    return node(parent, "geom", name=name, type=kind, size=size, pos=pos,
        mass=mass, rgba=color, friction=(0.45, 0.0001, 0.00001),
        solref=(0.003, 1), solimp=(0.97, 0.995, 0.0002), **kw)


def add_binder(root):
    world = root.find("worldbody")
    binder = node(world, "body", name="binder", pos=POSITION)
    node(binder, "freejoint", name="binder_free")
    # Back-mounted ring hardware, two real board covers and a 1.4-inch spine.
    geom(binder, "back_cover", "box", (0.0889, 0.1143, 0.0018), pos=(0.070, 0, -0.0032), mass=0.095, color=(0.87, 0.86, 0.82, 1))
    geom(binder, "back_view_film", "box", (0.087, 0.112, 0.00010), pos=(0.070, 0, -0.0051), color=(0.96, 0.96, 0.93, 1))
    spine = node(binder, "body", name="spine", pos=(-0.0189, 0, -0.0032))
    node(spine, "joint", name="spine_fold", type="hinge", axis=(0, 1, 0), range=(-2.8, 2.8), damping=0.0006, stiffness=0.001)
    geom(spine, "spine_board", "box", (0.01778, 0.1143, 0.0018), pos=(-0.01778, 0, 0), mass=0.03, color=(0.92, 0.91, 0.88, 1))
    cover = node(spine, "body", name="front_cover", pos=(-0.03556, 0, 0))
    node(cover, "joint", name="cover_fold", type="hinge", axis=(0, 1, 0), range=(-3.1, 3.1), damping=0.0006, stiffness=0.001)
    geom(cover, "front_board", "box", (0.0889, 0.1143, 0.0018), pos=(-0.0889, 0, 0), mass=0.095, color=(0.91, 0.91, 0.87, 1))
    geom(cover, "front_view_film", "box", (0.087, 0.112, 0.0001), pos=(-0.0889, 0, -0.0019), color=(0.96, 0.96, 0.93, 1))
    # Interior pockets are real contact surfaces; no retaining fixture is added.
    geom(binder, "back_pocket", "box", (0.070, 0.030, 0.00010), pos=(0.070, 0.082, -0.0013), color=(0.80, 0.86, 0.87, 0.25))
    geom(cover, "front_pocket", "box", (0.07, 0.03, 0.0001), pos=(-0.089, 0.082, 0.0019), color=(0.80, 0.86, 0.87, 0.25))
    geom(binder, "steel_backplate", "box", (0.012, 0.090, 0.0007), pos=(0, 0, 0.002), mass=0.014)
    for y in (-0.083, 0.083):
        geom(binder, "rivet_" + str(y), "cylinder", (0.0025, 0.001), pos=(0, y, 0.003), mass=0.001)
    eq, tendon = root.find("equality"), root.find("tendon")
    if eq is None:
        eq = node(root, "equality")
    if tendon is None:
        tendon = node(root, "tendon")
    for side, sign in (("left", -1), ("right", 1)):
        plate = node(binder, "body", name=side + "_ring_plate", pos=(sign * 0.008, 0, PLATE_Z))
        node(plate, "joint", name=side + "_toggle", type="hinge", axis=(0, sign, 0), range=(0, OPEN_ANGLE), damping=0.001, armature=0.000005, solreflimit=(0.002, 1))
        geom(plate, side + "_toggle_plate", "box", (0.0038, 0.083, 0.0005), pos=(-sign * 0.0038, 0, -0.0008), mass=0.005)
        for i, y in enumerate(STATIONS):
            angles = np.linspace(0, np.pi, 25)
            curve = np.c_[sign * (WIRE_RADIUS + RING_RADIUS * np.sin(angles)), np.full(len(angles), y), RING_RADIUS * (1 - np.cos(angles))]
            curve[:, 0] -= sign * 0.008
            for j, (a, b) in enumerate(zip(curve[:-1], curve[1:])):
                node(plate, "geom", name=f"ring_{side}_{i}_{j}", type="capsule", fromto=np.r_[a, b], size=(WIRE_RADIUS,), mass=0.004 / 24,
                    rgba=(0.68, 0.71, 0.73, 1), friction=(0.30, 0.0001, 0.00001), solref=(0.002, 1), solimp=(0.99, 0.999, 0.0001))
            node(plate, "site", name=f"tip_{side}_{i}", pos=curve[-1], size=0.0005, group=5)
        # The bowed spring housing is reduced to a conservative over-center
        # spatial spring. Its maximum extension is at 0.30 rad; both stops are
        # stable, with a finite energy barrier. No progress-dependent force.
        qc, rad, anchor = 0.30, 0.006, 0.006
        node(plate, "site", name=side + "_spring_moving", pos=(-sign * rad, 0, 0), size=0.0005, group=5)
        fixed = (sign * 0.008 + sign * anchor * np.cos(qc), 0, PLATE_Z - anchor * np.sin(qc))
        node(binder, "site", name=side + "_spring_fixed", pos=fixed, size=0.0005, group=5)
        spring = node(tendon, "spatial", name=side + "_housing_spring", stiffness=30000, damping=0.01, springlength=0.0095, width=0.0002, rgba=(0.55, 0.55, 0.55, 0.0))
        node(spring, "site", site=side + "_spring_fixed")
        node(spring, "site", site=side + "_spring_moving")
    node(eq, "joint", name="paired_toggle_plates", joint1="left_toggle", joint2="right_toggle", polycoef=(0, 1, 0, 0, 0), solref=(0.002, 1), solimp=(0.999, 0.9999, 0.0001))
    for end in (-1, 1):
        lever = node(binder, "body", name=f"booster_{end}", pos=(0, end * 0.091, 0.0035))
        node(lever, "joint", name=f"booster_hinge_{end}", type="hinge", axis=(-end, 0, 0), range=(0, 0.90), damping=0.0003, armature=0.000003)
        # Initial raised steel paddle; pushing its outward end down opens rings.
        geom(lever, f"booster_paddle_{end}", "box", (0.008, 0.010, 0.00065), pos=(0, end * 0.010 * np.cos(0.55), 0.010 * np.sin(0.55)),
             mass=0.004, euler=(end * 0.55, 0, 0))
        node(lever, "site", name=f"booster_tip_{end}", pos=(0, end * LEVER_LENGTH * np.cos(0.55), LEVER_LENGTH * np.sin(0.55)), size=0.0005, group=5)
        # Passive pin/link kinematics of the booster, internal to the binder.
        node(eq, "joint", name=f"booster_link_{end}", joint1=f"booster_hinge_{end}", joint2="left_toggle", polycoef=(0, 1.5, 0, 0, 0), solref=(0.002, 1), solimp=(0.999, 0.9999, 0.0001))
    return binder


def compose(pages=2):
    root = load_xml()
    root.set("model", "T37 Avery 05806 / complete Tianji arms / two Sharpa Wave hands")
    for k in root.findall("keyframe"):
        root.remove(k)
    root.find("option").attrib.update(timestep="0.001", iterations="80", cone="elliptic", impratio="10", jacobian="sparse")
    for act in root.find("actuator"):
        act.set("kp", "700")
        act.set("kv", "48")
    hands = {s: merge_hand(root, parent, s) for s, parent in (("l", "left_ee"), ("r", "right_ee"))}
    world, assets = root.find("worldbody"), root.find("asset")
    node(assets, "material", name="paper_stock", rgba=(0.95, 0.93, 0.86, 1), specular=0.01)
    geom(world, "floor", "plane", (3, 3, 0.05), pos=(0, 0, -0.1), color=(0.65, 0.68, 0.67, 1))
    geom(world, "desk", "box", (0.39, 0.43, 0.022), pos=(0.59, 0.05, 0.678), color=(0.54, 0.40, 0.27, 1))
    for x in (0.25, 0.93):
        for y in (-0.31, 0.41):
            geom(world, f"desk_leg_{x}_{y}", "box", (0.022, 0.022, 0.39), pos=(x, y, 0.288), color=(0.25, 0.24, 0.21, 1))
    node(world, "light", pos=(0.5, -1.0, 2.3), dir=(0, 0.3, -1), diffuse=(0.8, 0.8, 0.8))
    node(world, "light", pos=(0.1, 1.2, 2.0), dir=(0.3, -0.3, -1), diffuse=(0.5, 0.5, 0.5))
    visual = root.find("visual")
    if visual is None:
        visual = node(root, "visual")
    node(visual, "global", offwidth=960, offheight=720)
    node(visual, "headlight", ambient=(0.35, 0.35, 0.35))
    add_binder(root)
    from paper import add_pages
    topology = add_pages(root, PAPER_ORIGIN, pages)
    return root, hands, topology


class Scene:
    def __init__(self, pages=2):
        root, self.hands, self.paper_topology = compose(pages)
        self.xml = ET.tostring(root, encoding="unicode")
        self.model = mujoco.MjModel.from_xml_string(self.xml)
        self.data, self.forecast = mujoco.MjData(self.model), mujoco.MjData(self.model)
        self.arm_jids = np.array([self.model.joint(n).id for n in JOINT_NAMES])
        self.arm_qpos, self.arm_dofs = self.model.jnt_qposadr[self.arm_jids], self.model.jnt_dofadr[self.arm_jids]
        self.arm_acts = np.array([self.model.actuator(n + "_target").id for n in JOINT_NAMES])
        self.hand_indices = {s: h.indices(self.model) for s, h in self.hands.items()}
        self.arm_target = HOME.copy()
        self.hand_targets = {s: np.zeros(22) for s in self.hands}
        self.data.qpos[self.arm_qpos] = HOME
        mujoco.mj_forward(self.model, self.data)

    def hand_pose(self, side, kind="point"):
        targets = np.zeros(22)
        for i, name in enumerate(self.hands[side].joint_names):
            if any(f in name for f in ("middle", "ring", "pinky")):
                targets[i] = 1.15 if "MCP_FE" in name else 1.35 if "PIP" in name else 0.9 if "DIP" in name else 0.0
            if "thumb" in name:
                targets[i] = 0.55 if "FE" in name else 0.0
            if "index" in name:
                targets[i] = 0.08 if "MCP_FE" in name else 0.0
        ids = self.hand_indices[side]["joint"]
        return np.clip(targets, self.model.jnt_range[ids, 0] + 0.002, self.model.jnt_range[ids, 1] - 0.002)

    def fingertip_local(self, side, targets):
        d = self.forecast
        d.qpos[:] = self.data.qpos
        d.qpos[self.hand_indices[side]["qpos"]] = targets
        mujoco.mj_forward(self.model, d)
        palm = d.body(self.hands[side].root_body)
        tip = d.site(self.hands[side].fingertip_sites["index"])
        return palm.xmat.reshape(3, 3).T @ (tip.xpos - palm.xpos)

    def ik(self, side, position, rotation, initial=None, iterations=180):
        m, d = self.model, self.forecast
        d.qpos[:] = self.data.qpos
        off = 0 if side == "l" else 7
        qa, va, ids = self.arm_qpos[off:off+7], self.arm_dofs[off:off+7], self.arm_jids[off:off+7]
        bounds = m.jnt_range[ids]
        d.qpos[qa] = self.arm_target[off:off+7] if initial is None else initial
        bid = m.body(self.hands[side].root_body).id
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        for _ in range(iterations):
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            error = np.r_[position - d.xpos[bid], 0.20 * Rotation.from_matrix(rotation @ d.xmat[bid].reshape(3,3).T).as_rotvec()]
            if np.linalg.norm(error) < 1e-6:
                break
            mujoco.mj_jacBody(m, d, jp, jr, bid)
            jac = np.vstack([jp[:,va], 0.20 * jr[:,va]])
            change = jac.T @ np.linalg.solve(jac @ jac.T + 0.00005 * np.eye(6), error)
            d.qpos[qa] = np.clip(d.qpos[qa] + np.clip(change, -0.12, 0.12), bounds[:,0]+0.01, bounds[:,1]-0.01)
        return d.qpos[qa].copy(), float(np.linalg.norm(error))

    def initialize(self, poses):
        rng = np.random.default_rng(37)
        residuals = {}
        for s, (pos, rot) in poses.items():
            off = 0 if s == "l" else 7
            q, e = self.ik(s, pos, rot)
            lim = self.model.jnt_range[self.arm_jids[off:off+7]]
            for _ in range(8):
                if e < 0.002:
                    break
                candidate, residual = self.ik(s,pos,rot,initial=rng.uniform(lim[:,0]+0.05,lim[:,1]-0.05),iterations=240)
                if residual < e:
                    q,e = candidate,residual
            if e > 0.002:
                raise ValueError(f"{s} palm unreachable: {e}")
            self.arm_target[off:off+7] = q
            residuals[s] = e
        self.data.qpos[self.arm_qpos] = self.arm_target
        for s in self.hands:
            self.data.qpos[self.hand_indices[s]["qpos"]] = self.hand_targets[s]
        mujoco.mj_forward(self.model,self.data)
        return residuals

    def step(self):
        m,d = self.model,self.data
        bounds = m.actuator_ctrlrange[self.arm_acts]
        d.ctrl[self.arm_acts] = np.clip(self.arm_target + d.qfrc_bias[self.arm_dofs]/700,bounds[:,0],bounds[:,1])
        for s,ids in self.hand_indices.items():
            d.ctrl[ids["actuator"]] = self.hand_targets[s]
        action=d.ctrl.copy()
        mujoco.mj_step(m,d)
        return action
