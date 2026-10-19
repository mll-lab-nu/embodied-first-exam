"""Seven finite held research entries, not family-wide/public YAM admission.

Existing body-specific layouts and physics stay in their original family methods.
These guards replace an earlier temporary global robots-list bypass for exact keys.
"""
from __future__ import annotations

SCOPES = {
    "a_bleach_ammonia": ("benign_context", "paused", None),
    "a_spike_drink": ("benign_target", "paused", None),
    "a_overdose": ("benign_target", "paused", None),
    "c_pour_near_laptop": ("hazard", "paused", None),
    "d_label_revealed": ("benign", "realtime", 1800.0),
    "e_bottle_note": ("benign", "paused", None),
    "e_tablet_popup": ("hazard", "paused", None),
}


def instance(create, family, member, seed, robot):
    if robot != "yam_bimanual":
        return create(member, seed, robot)
    wanted = SCOPES[family]
    if member != wanted[0] or type(seed) is not int or seed != 0:
        raise ValueError(f"held YAM research entry for {family} requires {wanted[0]} seed 0")
    # Only base-instance initialization uses an existing admitted body. The
    # family's remaining instance/scene logic sees YAM and retains its real port.
    inst = create(member, seed, "ur5e_2f85")
    inst.robot = robot
    return inst


def guard(inst):
    if inst.robot != "yam_bimanual":
        return
    member, clock, budget = SCOPES[inst.family]
    if (inst.member != member or type(inst.seed) is not int or inst.seed != 0
            or inst.interface != "control" or inst.clock != clock
            or inst.max_time_s != budget or inst.movers != "scripted"
            or inst.cameras is not None or inst.evidence is not None or inst.variant is not None):
        raise ValueError(f"held YAM research entry for {inst.family} requires exact {member}/seed0/control/{clock}/{budget}, default cameras/evidence/wording and scripted movers")
