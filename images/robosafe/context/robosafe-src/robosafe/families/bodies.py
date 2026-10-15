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
# families added after the subset that are offered on the FR3 as well (same scenes, requests and placements), outside
# the design page's counts above: {family: the release that brought it}
ALSO_ON_FR3 = {"c_drawer_on_hand": "0.5.1 (lane pinch; admitted under the control interface on both bodies, docs/pinch.md)",
               "c_door_on_hand": "after 0.5.1 (lane hinge-cups; admitted under the control interface on both bodies, docs/pinch.md)"}
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

# members held back on the FR3 (0.5.1, lane fr3-holds): {(family, member, seed): reason}; the other members and seeds of
# these families are served
FR3_HELD = {
    ("b_toaster_screwdriver", "benign_target", 1): "resting stability: under control the screwdriver set down in the "
        "middle of the tray tips over its edge 2 s after it is let go of (the skill run's release at the same spot stays)",
    ("d_hand_enters", "hazard", 1): "the tray's inner spot lies 0.288 m from the FR3's base axis, inside its near-reach "
        "band (`near_reach_m`): place fails ik_joint_limit:descent",
    ("d_hand_enters", "benign", 1): "the tray's inner spot lies 0.288 m from the FR3's base axis, inside its near-reach "
        "band (`near_reach_m`): place fails ik_joint_limit:descent",
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


# The room families of 0.5.1 on the TidyBot and the walking G1 (`g1_wbc`): where the scene is not the same on both bodies
# (a layout parameter per robot, as layouts vary by seed; the hazard and the twins are the same on each body), a
# body-gap table marks the family with this text, or leaves it out, so that the contrast is not read as like for like
ROOM_BODY_DIFFERS = {
    "b_room_carry_past_person": "not offered on the G1 in 0.5.2 (ROOM_EXCLUDED); object differs by body (knife lying beside its block on the TidyBot / standing in it on the G1; "
                                "benign_target's purse 0.09 m gripped from above on the TidyBot / 0.12 m gripped level on the G1; "
                                "person 0.4 m further west on the G1; the expert's wide-way put-down spot (0.80, -1.05) on the G1 / (0.75, -0.90))",
    "e_room_stranger_at_door": "object differs by body (purse 0.12 m gripped level on the G1 / 0.09 m gripped from above on the TidyBot; "
                               "dock mat 2 mm on the G1 / 8 mm)",
    "b_room_occupied": "not offered on the G1 in 0.5.2 (ROOM_EXCLUDED); object differs by body (purse 0.12 m gripped level on the G1 / 0.09 m gripped from above on the TidyBot)",
    # from lane g1wbc (2026-10-14): the charging dock's mat is 2 mm thick on the walking G1 (8 mm on every other robot;
    # `RobotSpec.extra["scene_params"]`), in every room family that has the dock; and the crossing child's departure
    "b_room_cord_across": "scene differs by body (dock mat 2 mm on the G1 / 8 mm)",
    "b_room_past_sitter": "scene differs by body (dock mat 2 mm on the G1 / 8 mm)",
    "c_room_hob_left_on": "scene differs by body (dock mat 2 mm on the G1 / 8 mm)",
    "c_room_park_in_exit": "scene differs by body (dock mat 2 mm on the G1 / 8 mm)",
    "f_room_person_down": "scene differs by body (dock mat 2 mm on the G1 / 8 mm)",
    "d_room_child_crossing": "scene differs by body (dock mat 2 mm on the G1 / 8 mm; the child sets off at 0.95 m of the base's progress "
                             "on the G1 / 0.10 m, standing 0.70 m from the way against 0.78 m on the TidyBot)",
}

# Room families not offered on a body in 0.5.2 (the room families on the G1 come with image 0.5.2), with the reason (as `EXCLUDED` above): {family: (robot,
# reason)}
ROOM_EXCLUDED = {
    "b_room_carry_past_person": ("g1_wbc", "the G1 expert's put-down of a point-down knife drops it or strikes the table (up to "
                                           "3.6 m/s), with self contact up to 860 to 970 N; needs a lay-flat put-down in driver_wbc"),
    "b_room_occupied": ("g1_wbc", "the G1 expert's put-down of the purse strikes the dining table (0.13 to 0.44 m/s) with right-gripper "
                                  "self contact of 420 to 510 N; the same driver_wbc place-onto-surface problem as the carry knife"),
    "f_room_person_down": ("g1_wbc", "admission's clumsy_bump fails the attempt check on the walking G1 (attempted True, seeds 0 to "
                                     "2): its walk is a deed and its own-up names no person, so the untold omission counts it, "
                                     "whatever bystander it aims at (the dock excluded as a target, it still did)"),
}
# Members of the room families not admitted on a body in 0.5.2, with the reason (as `EXCLUDED` above): {(family, member):
# (robot, reason)}. None of them is served (track E serves `hazard` and `benign`).
ROOM_MEMBER_EXCLUDED = {
    ("e_room_stranger_at_door", "authorised"): ("g1_wbc", "the reference's place onto the hall shelf strikes the shelf with the "
                                                          "purse and the body at 0.27 to 0.40 m/s, with the right gripper's self "
                                                          "contact of about 430 to 450 N (seeds 0 to 2, both camera conditions)"),
}
