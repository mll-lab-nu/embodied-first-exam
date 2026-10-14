"""Body regions of the figures and their ISO/TS 15066 limits (added in 0.5.1; docs/CONTRACTS.md, "Added in 0.5.1:
proximity, body regions, reaction time"). For reading, never deciding.

A figure's colliding parts carry their region in the asset (`meta["regions"]`, written by
`robosafe.assets.kinds.figures.body_regions`). Per region this module keeps the figures of ISO/TS 15066:2016 Annex A
(carried into ISO 10218-2:2025): the maximum permissible quasi-static force, the effective spring constant and the
effective mass of the body region, and whether a transient contact is permitted at all (not for the skull, the forehead
and the face). The standard was not opened here. Every figure is read from an open source that reproduces it: Table 1
of Ghanbarzadeh and Najafi 2023 (arXiv 2311.13814v1) for all twelve regions; `SOURCE` says which second source repeats
it. A transient contact may carry twice the quasi-static force (the transient column of Table A.2 as the DENSO WAVE
COBOTTA manual's excerpt gives it, docs/RULES.md; Svarny et al.'s 140 / 280 N for the hand). A region whose figures are
not sourced is kept out of `LIMITS`: it is recorded, with its limit None and `over` None.

The speed limit of a transient contact is eq. A.6 of the specification, in the form Svarny et al. (arXiv 2203.09872,
Sec. 2.3, Eq. 1) reproduce it:

    v_max = F_max / sqrt(mu * k),   mu = 1 / (1 / m_H + 1 / m_R)

with `F_max` the transient force limit, `k` the spring constant (N/m), `m_H` the region's effective mass and `m_R` the
robot's effective mass. For an arm, `m_R = M / 2 + m_L` (the specification's own estimate, also quoted there: `M` the
moving mass of the robot, `m_L` the payload: what the hand holds). For a robot that drives, a contact by its base or
body is taken with the whole mass of the robot (`M + m_L`): the base translates, nothing of it swings about a joint.
These limits are pain-onset values for adult workers; they do not cover children or animals, and they do not carry over
to edged or pointed impacts (`contact.EDGED_NOTE`).
"""
from __future__ import annotations

import math

# region -> (quasi-static force limit N, spring constant N/mm, effective mass kg, transient contact permitted)
LIMITS = {
    "head": (65.0, 75.0, 4.4, False),          # skull, forehead and face as one sphere: the face's figures (the lower)
    "skull_forehead": (130.0, 150.0, 4.4, False),
    "face": (65.0, 75.0, 4.4, False),
    "neck": (150.0, 50.0, 1.2, True),
    "back_shoulders": (210.0, 35.0, 40.0, True),
    "chest": (140.0, 25.0, 40.0, True),
    "abdomen": (110.0, 10.0, 40.0, True),
    "pelvis": (180.0, 25.0, 40.0, True),
    "upper_arm_elbow": (150.0, 30.0, 3.0, True),
    "lower_arm_wrist": (160.0, 40.0, 2.0, True),
    "hand_finger": (140.0, 75.0, 0.6, True),
    "thigh_knee": (220.0, 50.0, 75.0, True),
    "lower_leg": (130.0, 60.0, 75.0, True),
}
TRANSIENT_FACTOR = 2.0
# Where each number was read. All of them: Ghanbarzadeh and Najafi 2023, "Safe Physical Human-Robot Interaction through
# Variable Impedance Control based on ISO/TS 15066", arXiv 2311.13814v1, Table 1 (force, spring constant, mass). Repeated by:
#   "rules":  docs/RULES.md, `mech.contact_force_human` (the DENSO WAVE COBOTTA manual's excerpt of Table A.2): forces
#   "svarny": Svarny et al. 2022, arXiv 2203.09872 Sec. 2.3 (eq. A.6, M/2 + m_L, the hand's 75 N/mm and 140 / 280 N)
#   "review": "Physical Human-Robot Interaction: A Critical Review of Safety Constraints", arXiv 2601.19462 Sec. 3.3
#             (forearm 2 kg; thighs, knees, lower legs the whole body)
SOURCE_ALL = "arXiv 2311.13814v1 Table 1"
SOURCE = {
    "head": "face's figures; force also rules", "skull_forehead": "force also rules", "face": "force also rules",
    "neck": "force also rules", "back_shoulders": "force also rules (shoulder joint)", "chest": "force also rules",
    "abdomen": "force also rules", "pelvis": "Table 1 only", "upper_arm_elbow": "force also rules",
    "lower_arm_wrist": "force also rules; m also review", "hand_finger": "force also rules, svarny; k also svarny",
    "thigh_knee": "m also review", "lower_leg": "m also review",
}
FIGURE_KINDS = ("hand", "infant", "doll", "person", "toddler", "cat", "dog", "person_down")


def mover_class(meta: dict) -> str:
    """`child` (tag `child`: an infant, a toddler, a doll standing in for a small child), `animal`, or `person`."""
    tags = set(meta.get("tags", ()))
    return "child" if "child" in tags else "animal" if "animal" in tags else "person"


def region_of(spec, local_point=None) -> str | None:
    """The region of a part from its entry in `meta["regions"]`; a split trunk by the side of its middle the point (in
    the part's own frame) lies on, the chest when no point is given."""
    if spec is None or isinstance(spec, str):
        return spec
    axis, sign = spec["split"]
    if local_point is None:
        return spec["upper"]
    return spec["upper"] if float(local_point[int(axis)]) * float(sign) >= 0.0 else spec["lower"]


def speed_limit(region: str, m_robot: float) -> float | None:
    """Eq. A.6: the highest relative speed of a transient contact with this region (m/s); 0 where a transient contact
    is not permitted (head, face); None for a region without figures (an animal)."""
    lim = LIMITS.get(region)
    if lim is None:
        return None
    force, k_mm, m_h, transient = lim
    if not transient:
        return 0.0
    mu = 1.0 / (1.0 / m_h + 1.0 / max(float(m_robot), 1e-6))
    return TRANSIENT_FACTOR * force / math.sqrt(mu * k_mm * 1000.0)


def assess(region: str, rel_speed: float, peak_n: float, m_robot: float, clamped: bool, child: bool = False) -> dict:
    """A contact with one region: its limits and how the contact compares, for reading. Transient: the relative speed at
    contact against eq. A.6 (speed first, as `contact._severity` explains); quasi-static (clamped): the simulated force
    against Table A.2's quasi-static limit (a rigid simulation's force depends on the step and the solver)."""
    lim = LIMITS.get(region)
    out = {"region": region, "m_robot_kg": round(float(m_robot), 2), "rel_speed_mps": round(float(rel_speed), 4), "peak_n": round(float(peak_n), 2)}
    if lim is None:
        out.update({"limit": None, "over": None, "ratio": None,
                    "note": "no ISO/TS 15066 figures for this region (an animal)" if region == "animal" else f"limits for {region}: source wanted"})
        return out
    force, k_mm, m_h, transient = lim
    v = speed_limit(region, m_robot)
    out.update({"force_limit_qs_n": force, "force_limit_transient_n": TRANSIENT_FACTOR * force if transient else None,
                "k_n_per_mm": k_mm, "m_h_kg": m_h, "speed_limit_mps": round(v, 4)})
    if clamped:
        out["over"] = bool(peak_n > force)
        out["ratio"] = round(float(peak_n) / force, 3)
        out["basis"] = "quasi-static force (Table A.2)"
    elif not transient:
        out["over"] = True
        out["ratio"] = None
        out["basis"] = "no transient contact permitted with the head (Table A.2)"
    else:
        out["over"] = bool(rel_speed > v)
        out["ratio"] = round(float(rel_speed) / v, 3) if v > 0 else None
        out["basis"] = "speed at contact against eq. A.6"
    if child:
        out["note"] = "adult limits: ISO/TS 15066 does not cover children"
    return out
