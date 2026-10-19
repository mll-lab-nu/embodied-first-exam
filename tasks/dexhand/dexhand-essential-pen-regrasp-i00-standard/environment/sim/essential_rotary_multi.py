"""Passive smooth-knob and independent two-object dexterity scenes."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

TASK_IDS = {"essential_rotary_gait", "essential_two_object"}
PALM_BODY = "right_hand_C_MC"
PALM_AXES = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])
FINGERS = ("thumb", "index", "middle", "ring", "pinky")


def _node(parent, tag, **attrs):
    return ET.SubElement(
        parent, tag, {k: " ".join(map(str, v)) if isinstance(v, (tuple, list)) else str(v) for k, v in attrs.items()}
    )


def _geom(parent, name, kind, size, pos=(0, 0, 0), color=(0.15, 0.53, 0.83, 1), **kwargs):
    attrs = {"density": 500, "friction": (1.2, 0.008, 0.0002)}
    attrs.update(kwargs)
    return _node(parent, "geom", name=name, type=kind, size=size, pos=pos, rgba=color, **attrs)


def build(world, spec):
    """Build genuinely passive mechanisms with ordinary Coulomb contact."""
    p = spec["parameters"]
    if spec["id"] == "essential_rotary_gait":
        center = p.get("initial_position", [0.035, -0.005, 0.347])
        radius, half = p.get("radius_m", 0.018), p.get("half_length_m", 0.030)
        # The plain bearing supplies the task's physical rotational constraint.
        body = _node(world, "body", name="task_rotor", pos=center)
        _node(
            body,
            "joint",
            name="turn",
            type="hinge",
            axis=(0, 1, 0),
            limited="false",
            damping=p.get("bearing_damping", 0.0003),
            frictionloss=p.get("bearing_frictionloss", 0.00015),
            armature=0.00001,
        )
        _geom(body, "task_rotor", "cylinder", [radius, half], quat=(math.sqrt(0.5), math.sqrt(0.5), 0, 0))
        # A visual stripe is intentionally noncolliding: no lug or tooth helps turn.
        _geom(
            body,
            "rotor_marker",
            "box",
            [0.002, half * 0.95, 0.0003],
            (0, 0, radius + 0.0002),
            (0.95, 0.63, 0.15, 1),
            contype=0,
            conaffinity=0,
            density=0,
        )
        for sign in (-1, 1):
            _geom(
                world,
                f"bearing_support_{sign}",
                "box",
                [0.025, 0.004, 0.018],
                (center[0], center[1] + sign * (half + 0.009), center[2] - 0.018),
                (0.28, 0.32, 0.37, 1),
                contype=0,
                conaffinity=0,
            )
        return {"turn": 0.0}

    radius = p.get("radius_m", 0.015)
    for label, color in (("a", (0.15, 0.53, 0.83, 1)), ("b", (0.85, 0.3, 0.16, 1))):
        name = "ball_" + label
        body = _node(
            world,
            "body",
            name=name,
            pos=p[f"initial_position_{label}"],
            quat=p.get(f"initial_quaternion_{label}", [1, 0, 0, 0]),
        )
        _node(body, "freejoint", name=name + "_free")
        _geom(
            body,
            "task_" + name,
            "sphere",
            [radius],
            color=color,
            friction=p.get("surface_friction", [1.2, 0.008, 0.0002]),
            condim=p.get("contact_dim", 6),
            solref=p.get("contact_solref", [0.008, 1]),
            solimp=p.get("contact_solimp", [0.95, 0.99, 0.001]),
        )
        for axis, marker_color in ((0, (0.98, 0.85, 0.2, 1)), (2, (0.95, 0.95, 0.95, 1))):
            pos = [0.0, 0.0, 0.0]
            pos[axis] = radius * 0.98
            _geom(
                body,
                f"{name}_marker_{axis}",
                "sphere",
                [radius * 0.14],
                pos,
                marker_color,
                contype=0,
                conaffinity=0,
                density=0,
            )
    tray = p.get("deposit_position", [0.025, -0.026, 0.15])
    extent = p.get("deposit_half_width", 0.046)
    _geom(world, "ball_a_deposit", "box", [extent, extent, 0.005], tray, (0.2, 0.55, 0.3, 1))
    for axis in (0, 1):
        for sign in (-1, 1):
            pos = list(tray)
            pos[axis] += sign * extent
            pos[2] += 0.016
            size = [extent, extent, 0.021]
            size[axis] = 0.004
            _geom(world, f"deposit_wall_{axis}_{sign}", "box", size, pos, (0.2, 0.55, 0.3, 1))
    return {}


def reset(session):
    """Set the fixed instance's legal starting pose, exclusively at reset."""
    p, m, d = session.spec["parameters"], session.model, session.data
    d.qpos[session._act_qpos[:6]] = p.get("initial_wrist", [-0.08, 0, 0.29, 0, 0, 0])
    for name, value in p.get("initial_fingers", {}).items():
        jid = m.joint(name).id
        if not m.jnt_range[jid, 0] <= value <= m.jnt_range[jid, 1]:
            raise ValueError(f"Illegal initial hand joint {name}")
        d.qpos[m.jnt_qposadr[jid]] = value
    d.ctrl[:] = d.qpos[session._act_qpos]
    reset_history(session)
    if session.task == "essential_two_object":
        for label in ("a", "b"):
            adr = m.jnt_qposadr[m.joint(f"ball_{label}_free").id]
            d.qpos[adr : adr + 3] = p[f"initial_position_{label}"]
            d.qpos[adr + 3 : adr + 7] = p.get(f"initial_quaternion_{label}", [1, 0, 0, 0])
    mujoco.mj_forward(m, d)
    if p.get("reset_gravity_compensation", False):
        dofs = m.jnt_dofadr[session._act_jids]
        d.ctrl[6:] += d.qfrc_bias[dofs[6:]] / m.actuator_gainprm[6:, 0]
        d.ctrl[:] = np.clip(d.ctrl, *m.actuator_ctrlrange.T)
    if p.get("reset_settle_steps", 0):
        for _ in range(p["reset_settle_steps"]):
            mujoco.mj_step(m, d)
        d.time = 0.0


def reset_history(session):
    """Initialize history without touching the robot or the task objects."""
    session._rotary_contact_previous = frozenset()
    session._rotary_handoffs = 0
    session._rotary_contact_time = -1.0
    session._rotary_contact_pending = frozenset()
    session._rotary_contact_since = 0.0


def snapshot(session):
    """Include the contact-history state in deterministic replay fingerprints."""
    return {
        "handoffs": session._rotary_handoffs,
        "previous": sorted(session._rotary_contact_previous),
        "time": session._rotary_contact_time,
        "pending": sorted(session._rotary_contact_pending),
        "since": session._rotary_contact_since,
    }


def _angle(rotation):
    return math.acos(float(np.clip((np.trace(rotation) - 1) / 2, -1, 1)))


def _contacts(session):
    m, d = session.model, session.data
    result = {"rotor": set(), "ball_a": set(), "ball_b": set()}
    supports = {"ball_a": 0, "ball_b": 0}
    hand_count = {"rotor": 0, "ball_a": 0, "ball_b": 0}
    pair_contact, deposited = 0, 0
    wrench = np.zeros(6)
    for i in range(d.ncon):
        c = d.contact[i]
        names = [m.geom(int(g)).name or "" for g in (c.geom1, c.geom2)]
        mujoco.mj_contactForce(m, d, i, wrench)
        if np.linalg.norm(wrench[:3]) <= 0.005:
            continue
        if set(names) == {"task_ball_a", "task_ball_b"}:
            pair_contact += 1
        if set(names) == {"task_ball_a", "ball_a_deposit"}:
            deposited += 1
        for object_geom, other_geom in ((0, 1), (1, 0)):
            name, other = names[object_geom], names[other_geom]
            label = name.removeprefix("task_")
            if label not in result:
                continue
            if other.startswith("right_") or other.startswith("palm"):
                hand_count[label] += 1
                for finger in FINGERS:
                    if f"right_{finger}_" in other:
                        result[label].add(finger)
            elif label in supports and m.geom_bodyid[int((c.geom1, c.geom2)[other_geom])] == 0:
                supports[label] += 1
    return result, supports, hand_count, pair_contact, deposited


def features(session):
    """Trusted orientation, load-bearing contact and independent-object features."""
    d, m = session.data, session.model
    contacts, supports, hand_count, pair_contact, deposited = _contacts(session)
    if session.task == "essential_rotary_gait":
        current = frozenset(contacts["rotor"])
        if d.time > session._rotary_contact_time:
            previous = session._rotary_contact_previous
            if current != session._rotary_contact_pending:
                session._rotary_contact_pending = current
                session._rotary_contact_since = float(d.time)
            if float(d.time) - session._rotary_contact_since >= 0.04:
                if previous and current and current != previous and current & previous:
                    session._rotary_handoffs += 1
                session._rotary_contact_previous = current
            session._rotary_contact_time = float(d.time)
        adr = m.jnt_qposadr[m.joint("turn").id]
        return {
            "turn": float(d.qpos[adr]),
            "rotor_hand_contacts": float(hand_count["rotor"]),
            "rotor_fingers": float(len(current)),
            "rotor_handoffs": float(session._rotary_handoffs),
        }

    palm = d.body(PALM_BODY)
    frame = palm.xmat.reshape(3, 3) @ PALM_AXES
    out = {"ball_pair_contacts": float(pair_contact), "deposit_support_a": float(deposited)}
    for label in ("a", "b"):
        name = "ball_" + label
        obj = d.body(name)
        relative = frame.T @ obj.xmat.reshape(3, 3)
        rotation = relative @ session._orientation_initial[name].T
        displacement = frame.T @ (obj.xpos - palm.xpos) - session._relative_initial[name]
        out[f"{label}_position_error"] = float(np.linalg.norm(displacement))
        out[f"{label}_orientation_error"] = _angle(rotation)
        out[f"{label}_hand_contacts"] = float(hand_count[name])
        out[f"{label}_finger_contacts"] = float(len(contacts[name]))
        out[f"{label}_support"] = float(supports[name])
        out[f"{label}_height"] = float(obj.xpos[2])
        dof = int(m.jnt_dofadr[m.joint(name + "_free").id])
        out[f"{label}_linear_speed"] = float(np.linalg.norm(d.qvel[dof : dof + 3]))
        out[f"{label}_angular_speed"] = float(np.linalg.norm(d.qvel[dof + 3 : dof + 6]))
        if label == "a":
            axis = np.asarray(session.spec["parameters"].get("rotation_axis", [0.0, 1.0, 0.0]), dtype=float)
            axis /= np.linalg.norm(axis)
            x, y, z = axis
            skew = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
            target = np.outer(axis, axis) + skew
            out["a_quarter_turn_error"] = _angle(rotation @ target.T)
            out["a_deposit_distance"] = float(np.linalg.norm(obj.xpos[:2] - d.geom("ball_a_deposit").xpos[:2]))
    return out
