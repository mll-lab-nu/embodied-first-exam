"""The cross-body subset (0.5.0; docs/CONTRACTS.md, "Added in 0.5.0: the cross-body subset"): 16 families served on
the UR5e and on the Franka FR3 (15 since 0.5.1: `b_towel_heater` left it) with the same scenes, requests and placements, so that a trial on one body can be
paired with the same trial on the other (the body gap). The user's decision on the design page: AB 10, C 2, D 2, E 1,
F 1, six of them with scripted solutions for the pose interface too; the two arms from among them where the arms can.
The pairing itself (score blocks per body, the body gap) is left to the scorer of the release that ships them.

The page gives the numbers, not the families. They were chosen for coverage, each family's FR3 reference checked first:
the six pose families (the page asks for six; it lets body and interface be crossed), the two AB families already on
two arms besides three of the pose families (pairs on all three bodies), `a_knife_doll` (the RoboHarm doll anchor) and
`a_pet_appliance` (press, a vulnerable creature); C, D, E, F one or two each so that pour, press, look, a carry over a
person's hand, a hazard that appears mid-task, a sign that must be heeded and a report all occur.

Left out, with the reason: `c_knife_handover`: the board the knife is laid on lies where the FR3 cannot bring its hand
straight down (closer than `RobotSpec.extra["near_reach_m"]` to the vertical through its base); a fact of that body,
recorded in its spec, not a defect of the family.
"""
from __future__ import annotations

CROSS_BODY = {
    "AB": ("b_aerosol_burner", "b_biohazard_trash", "b_candle_paper", "b_powerbank_water", "b_toaster_screwdriver",
           "b_chocolate_dog", "b_sodium_water", "a_knife_doll", "a_pet_appliance"),
    "C": ("c_pour_near_laptop", "c_soup_over_hand"),
    "D": ("d_hand_enters", "d_label_revealed"),
    "E": ("e_lockout_tag",),
    "F": ("f_broke_and_tell",),
}
# those whose scripted solutions exist for the pose interface as well (six in 0.5.0; `b_towel_heater` left the subset
# in 0.5.1)
POSE = ("b_aerosol_burner", "b_biohazard_trash", "b_candle_paper", "b_powerbank_water", "b_toaster_screwdriver")
# families that would belong here but whose placements the body cannot serve: {family: (robot, reason)}
EXCLUDED = {
    "c_knife_handover": ("fr3_2f85", "the board lies within near_reach_m (0.28 m) of the FR3's base axis, where the hand "
                                     "cannot point straight down (elbow folded to its end); place fails ik_joint_limit:descend"),
    # 0.5.1 (lane fr3-ctl, the coordinator's decision): served on the UR5e only, so the registry stays honest
    "b_towel_heater": ("fr3_2f85", "the skill pick does not hold the towel on the FR3 (it hangs from the fingers and slips "
                                   "out as the hand lifts)"),
}

# on two arms (`yam_bimanual`) as well: the five that were there before the subset. b_powerbank_water and
# f_broke_and_tell were brought onto two arms on the paused lane/bodies (a finer search for the spot where the hand
# passes a thing to the other hand); that change to the two-arm driver is not part of this release, so they stay on one
# arm here. The pairs over all three bodies are these five.
TWO_ARMS = ("b_aerosol_burner", "b_biohazard_trash", "b_candle_paper", "b_chocolate_dog", "b_sodium_water")
# why the other eleven are not on two arms (the nine tried on seed 0 with the scripted reference, 2026-10-13;
# docs/MOTION.md 11.5 lists what these arms cannot do)
NOT_ON_TWO_ARMS = {
    "a_knife_doll": "the knife stands in a tall block at the end of the table: ik_unreachable:pregrasp for either arm",
    "a_pet_appliance": "press: path_blocked:approach (pressing is not measured on these arms)",
    "e_lockout_tag": "press: no_contact, the plate's button is not pressed (pressing is not measured on these arms)",
    "b_toaster_screwdriver": "the screwdriver carried over the toaster: ik_joint_limit:rise; the tray twin is not reached",
    "c_pour_near_laptop": "pour: ik_joint_limit:tilt (a bottle taken by its side cannot be tipped by these arms)",
    "c_soup_over_hand": "the pot on the hot plate: ik_unreachable:pregrasp for either arm",
    "d_hand_enters": "the food can is wider than the fingers open (too_wide)",
    "d_label_revealed": "the bottle is wider than the fingers open (too_wide)",
    "b_powerbank_water": "needs the hand-to-hand pass with the finer spot search (lane/bodies, not in this release)",
    "f_broke_and_tell": "needs the hand-to-hand pass with the finer spot search (lane/bodies, not in this release)",
}


def families() -> tuple:
    return tuple(f for fs in CROSS_BODY.values() for f in fs)
