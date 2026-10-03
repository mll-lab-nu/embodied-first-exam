"""Public terminal requirements, derived from the selected task's effective config.

These descriptions expose goals and tolerances, never object poses, live metrics,
qualification records or solver state. Both Harbor modes use the same payload.
Importing the renderer does not import NumPy or initialize a simulator.
"""

TASK_IDS = frozenset({
    "interlocked_claws", "rope_threading", "lock_picking", "hedgehog_in_cage",
    "fiber_bundling", "horseshoe_ring", "knot_untying", "cast_coil",
    "cast_keyhole", "buzz_wire_3d", "blanket_flatten", "slotted_post_ring", "orbits",
})

PLACEMENT = {
    "interlocked_claws": ("the entire brown claw piece", "the other claw piece"),
    "hedgehog_in_cage": ("the whole hedgehog ball, including every spike", "all cage components"),
    "horseshoe_ring": ("the entire removable ring", "the horseshoes and chains"),
    "cast_keyhole": ("the entire silver keyhole piece", "the gold piece"),
    "slotted_post_ring": ("the entire removable metal ring", "the post, cord, beads and end discs"),
    "orbits": ("the entire cord and wooden handle together", "the rings, posts and fixed assembly"),
}


def mm(value):
    return f"{float(value)*1000:.6g} mm"


def _rigid_contact_failure():
    from topogym.utils.grasp import TASK_CONTACT_PENETRATION_M, GRASP_CONTACT_PENETRATION_M
    return (
        "A task piece falling more than 100 mm below the tabletop ends the episode in failure. "
        f"Finger contact with a held movable piece may penetrate at most {mm(GRASP_CONTACT_PENETRATION_M)}; "
        "holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand. "
        f"All other task contacts, including piece-piece, table, arm and gripper-housing contacts, may penetrate at most {mm(TASK_CONTACT_PENETRATION_M)}. "
        "Exceeding either limit ends the episode in failure."
    )


def render_goal(description, *, include_summary=False):
    if description["schema_version"] != 1:
        raise ValueError("Unsupported public goal description")
    text = (description["summary"] + "\n\n") if include_summary else ""
    text += "## Success requirements\n\n"
    text += "\n".join("- " + item for item in description["success_conditions"])
    text += (f"\n- Keep all final conditions satisfied together for at least {description['stable_duration_s']:g} s "
             "of simulation time. If any final condition stops holding, the confirmation interval starts again. "
             "A brief qualifying pose is not enough; let the simulation advance through the full interval.")
    if description["failure_conditions"]:
        text += "\n\n## Task failure conditions\n\n"
        text += "\n".join("- " + item for item in description["failure_conditions"])
    return text


def _threading(task):
    import numpy as np
    from topogym.assets.geometry.rope_threading import ThreadingLayout
    layout = getattr(task, "layout", None) or ThreadingLayout(**task.config["geometry"])
    rings = layout.rings()
    names = {"R1": "cyan ring (R1)", "R2": "green ring (R2)", "R3": "purple ring (R3)"}
    by_name = {ring["name"]: ring for ring in rings}
    crossings = layout.required_crossings()
    directions = []
    for name, sign in crossings:
        ring = by_name[name]
        # Identify each required exit side using another visible ring, without
        # publishing the ring's pose or normal in world coordinates.
        others = sorted((r for r in rings if r["name"] != name),
                        key=lambda r: np.linalg.norm(np.asarray(r["center_m"])-ring["center_m"]))
        for other in others:
            side = float(np.dot(np.asarray(other["center_m"])-ring["center_m"], ring["normal"]))
            if abs(side) > 1e-8:
                direction = "toward" if side*sign > 0 else "away from"
                directions.append(f"{names[name]}: cross {direction} the side containing the {names[other['name']]}")
                break
        else:
            if len(rings) == 1 and abs(ring['normal'][0]) > .5:
                arm = 'left' if ring['normal'][0]*sign < 0 else 'right'
                directions.append(f"{names[name]}: cross toward the side containing the {arm} robot base")
            else:
                raise ValueError("Threading direction has no visible ring-side reference")
    order = " then ".join(names[name] for name, _ in crossings)
    return order, "; ".join(directions)


def describe_goal(task):
    """Return JSON-safe public requirements; no scene build or live reads needed."""
    name, cfg = task.task_id, task.config
    if name not in TASK_IDS:
        raise ValueError(f"No public terminal description for {name}")
    terminal = cfg.get("terminal", {})
    rules, failures = [], []
    if name == "interlocked_claws" and getattr(task, "separation_only", False):
        summary = "Completely separate the two claw pieces and briefly hold both still."
        rules += [
            f"Leave at least {mm(cfg.get('minimum_separation_m', .01))} between the complete pieces, "
            "with a plane separating all of their geometry; a gap inside the interlock is insufficient.",
            "Keep both pieces' linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. "
            "Holding both pieces is allowed; release and transport into the green region are not required.",
        ]
        failures.append(_rigid_contact_failure())
    elif name in PLACEMENT:
        target, remainder = PLACEMENT[name]
        summary = f"Separate and place {target} inside the green dashed goal region. Keep {remainder} on the puzzle/system side."
        region = getattr(task, "goal_region", None)
        margin = getattr(region, "boundary_margin_m", .001)
        penetration = getattr(region, "penetration_tolerance_m", .001)
        rules += [
            f"Put every part of {target} inside the fixed goal volume, leaving at least {mm(margin)} inside its horizontal border. "
            "The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.",
            f"Keep the target above the tabletop (contact tolerance {mm(penetration)} below the surface) and within the goal volume's height. "
            "It need not touch the table.",
            f"Keep {remainder}, and every other remaining puzzle component, entirely on the system side of the fixed separator. "
            "Moving the whole puzzle into the goal is not completion.",
            "Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. "
            + ("Every point of the target cord must also move at most 1 mm/s. " if name == "orbits" else "")
            + "Holding the target with the gripper is allowed; release is not required.",
        ]
        if region is not None:
            rules[1] += f" The goal volume extends {mm(region.placement_height_m)} above the tabletop."
        if name == "horseshoe_ring":
            rules.append("Keep every permanent chain/eye interlock intact; free only the removable target ring.")
            failures.append("Losing any permanent chain/eye connection ends the episode in failure.")
        if name in {"slotted_post_ring", "orbits"}:
            endpoints = "both end discs" if name == "slotted_post_ring" else "both handle attachment points"
            rules.append(f"Keep the cord intact and attached to {endpoints}; each attachment residual must be at most 2 mm. "
                         "No inverted or collapsed cord volume is accepted.")
            failures.append("Broken attachments or invalid cord volume end the episode in failure.")
        else:
            failures.append(_rigid_contact_failure())
    elif name == "rope_threading" and cfg['geometry'].get('ring_shape') == 'lower_semicircle':
        summary = "Lift the rope and drape its body across the lower inside of the cyan semicircle through the open top."
        rules += [
            "The rope must cross the fixture plane over the lower supporting rim, with material extending to both sides. "
            "Touching a cut end, an endpoint-only touch, or hovering inside the open half-circle is insufficient.",
            "Use the lower central portion of the cradle, at least half the ring centreline radius below its centre.",
            f"Keep the supported rope within {mm(terminal['support_gap_m'])} of the rim; "
            f"nominal rope-to-rim overlap may not exceed {mm(terminal['support_penetration_m'])}.",
            f"At least {mm(terminal['minimum_drape_length_m']/2)} of rope must remain on either side along the material. "
            f"The points {mm(terminal['drape_span_m'])} along the rope on either side of the crossing must clear the fixture's thickness.",
            f"Keep every rope point at or below {mm(terminal['maximum_speed_m_s'])}/s. Holding is allowed; release is not required.",
            "Keep the rope intact; collapsed or inverted rope volume is not accepted.",
        ]
        failures.append("Invalid rope volume ends the episode in failure.")
    elif name == "rope_threading":
        order, directions = _threading(task)
        summary = f"Thread the rope through the {order}, in that order along the rope from material start to material end."
        rules += [
            f"Required directions along that material order: {directions}. Do not reverse the crossing directions.",
            "Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. "
            f"Keep the full rope thickness clear of the rim, with an additional {mm(terminal['aperture_margin_m'])} radial margin; "
            "the passage must clear both sides of each ring's thickness, not just its middle plane.",
            f"Keep every rope point at or below {mm(terminal['maximum_speed_m_s'])}/s. Holding is allowed; release is not required.",
            "Keep the rope intact; collapsed or inverted rope volume is not accepted.",
        ]
        if task.family_id == 'single_ring_bimanual':
            summary = "Use both hands to feed and receive the same rope end through the single cyan ring. " + summary
            rules.append(
                f"Before threading, grasp one of the terminal {mm(terminal['handoff_band_m'])} rope bands on the entry side. "
                "After the end passes through the hole, the other hand must grasp the same end band on the exit side "
                "while the feeding hand still holds it; then release the feeding hand while the receiving hand keeps its grasp. "
                f"Each grip must persist for at least {terminal['handoff_grip_duration_s']:g} s. "
                "A single-hand passage or unrelated touches by the second hand are insufficient. "
                "The transfer is invalidated if the threaded crossing is lost or reversed, and is reset when rewinding "
                "to a state before it occurred.")
        failures.append("Invalid rope volume ends the episode in failure.")
    elif name == "lock_picking":
        rotor_count = len(cfg["geometry"].get("slots", [None]*3))
        rotor_word = {2: "two", 3: "three"}[rotor_count]
        plate_word = {2: "three", 3: "four"}[rotor_count]
        summary = f"Insert the tabbed key through all {rotor_word} rotor plates and the final END plate, while respecting their slots and stops."
        if rotor_count == 2:
            summary = "Pick up the two-tab key from its rest. " + summary
            if task.family_id == "two_rotor_first_turn":
                summary += " Align the first rotor's slot with the second rotor's slot to allow insertion."
            else:
                summary += " Both rotor slots start aligned for straight insertion."
        rules += [
            f"Keep the finite-length shaft passing through the full thickness of all {plate_word} plates at once, facing the insertion direction. "
            "Reaching END with only the shaft tip is insufficient.",
            f"The rear edge of the leading tab must clear the outer face of END by at least {mm(terminal['insertion_margin_m'])}.",
            f"Normal contact with the bore wall and a small tilt are allowed when the shaft still fits through all {plate_word} bores. "
            f"The radial numerical contact tolerance is {mm(terminal['shaft_contact_tolerance_m'])}; do not push the shaft through solid plate material.",
            "Keep every tab clear of solid plate material whenever it overlaps a plate; account for the key's offset and tilt, not just its rotation about the shaft.",
            f"Keep limited-travel rotor pins within their physical slot bounds (angular tolerance {terminal['rotor_tolerance_deg']:g} degrees).",
            "You may keep holding the key. Release and zero velocity are not required; all insertion and clearance conditions must remain satisfied throughout confirmation.",
        ]
        failures += ["A limited-travel rotor exceeding its allowed bounds ends the episode in failure.",
                     "The key falling more than 100 mm below the tabletop ends the episode in failure."]
    elif name == "fiber_bundling":
        summary = "Manipulate the thick sheath to pass every fine fiber and the front sheath through the fixed copper ring; keep the rear terminal anchored."
        rules += [
            "Pass every fiber tip first, then successive material points through to its root. The actual crossing history must be observed; "
            "placing fibers on the far side or passing only the tips is not completion.",
            "All fiber points must finish beyond the exit side of the ring tube, allowing for fiber thickness. "
            "The branching face of the front sheath must also pass through and clear the tube with its full thickness. "
            "The fixed rear terminal must remain anchored and does not pass through.",
            f"Keep the angle between every pair of adjacent fiber segments at most {terminal['maximum_bend_deg']:g} degrees in the final configuration.",
            "Touch and grasp only the thick sheath with the gripper. Keep the completed passage valid through confirmation; "
            "holding is allowed, with no separate release or speed threshold.",
        ]
        failures += ["Any gripper touch of a fine fiber at any time ends the episode in failure, including a brief or zero-force touch.",
                     "A fiber link falling more than 100 mm below the tabletop ends the episode in failure."]
    elif name == "knot_untying":
        summary = "Untie and spread the rope on the tabletop until its top-down projection has no crossings or overlaps, then release it."
        rules += [
            "Remove projected crossings, overlaps, collapsed projected segments and exact foldbacks. Nonlocal rope segments must be separated "
            "by at least one rope diameter in the top-down view; merely changing over/under order is insufficient.",
            f"Keep the entire rope close to the tabletop: no point more than {mm(terminal['penetration_tolerance_m'])} below it, "
            f"and no point higher than one rope diameter plus {mm(terminal['table_clearance_m'])} above it.",
            "Keep the rope volume intact; do not invert or collapse it to bypass the knot.",
        ]
        failures.append("Invalid rope volume ends the episode in failure.")
    elif name == "cast_coil":
        assembling = cfg["objective"] == "assemble"
        summary = ("Assemble the gold and silver Cast Coil pieces into their matching interlocking configuration, then release both." if assembling else
                   "Separate the gold and silver Cast Coil pieces completely, then release both on the table.")
        if assembling and getattr(task, "geometry_resource", None):
            summary = "Assemble the gold and silver pieces into a cube with flush outer faces, then release both on the table."
        rules += [
            ("Align the pieces' matching assembly frames with relative position error below 1 mm and relative angular error below 0.02 rad." if assembling else
             "Separate the pieces' complete bounding extents by more than 10 mm along at least one axis."),
            f"The bottom of {'at least one piece' if assembling else 'each piece'} must be within {mm(terminal['table_clearance_m'])} of the tabletop. "
            "Neither piece may extend more than 1 mm below it, and each piece must overlap the tabletop horizontally.",
            "Keep both pieces' linear speeds below 1 mm/s and angular speeds below 0.02 rad/s. Merely touching or gripping them is not completion.",
        ]
        failures.append(_rigid_contact_failure())
    elif name == "buzz_wire_3d":
        summary = "Guide the metal loop along the entire wire from start to finish without touching the wire, then release the tool on the finish support."
        rules += [
            f"Start within {mm(terminal['start_route_tolerance_m'])} along the wire from its starting end and traverse continuously "
            f"until within {mm(terminal['start_route_tolerance_m'])} of its finishing end. Keep one unambiguous wire crossing inside the loop. "
            "Skipping branches or taking the loop off the route before completing traversal does not count; restart from the beginning if tracking is lost.",
            "After completing traversal, lower the tool onto the finish support. The completed traversal remains valid when the loop leaves the wire to rest on the support.",
            f"Match the finish resting pose within {mm(terminal['finish_position_tolerance_m'])} and {terminal['finish_angle_tolerance_deg']:g} degrees. "
            "A half-turn about the handle axis is an equivalent orientation. The tool must actually contact the finish support.",
            "Keep all metal parts of the tool clear of the metal wire throughout the episode. Wooden-handle contact is not a metal-wire failure. "
            "Remove all robot contact before final confirmation.",
        ]
        failures += ["Any metal-tool touch of the metal wire ends the episode in failure, including brief or zero-force touches.",
                     "The tool falling more than 100 mm below the tabletop ends the episode in failure."]
    elif name == "blanket_flatten":
        summary = "Unfold and spread the blanket flat on the table without overlaps or excessive stretching, then release it and withdraw."
        rules += [
            f"Cover at least {100*cfg['minimum_coverage_ratio']:g}% of the blanket's unfolded material area in top-down projection. "
            "Overlapping layers count only once, holes do not count, and a large outer bounding box is insufficient.",
            f"Keep every cloth point at most {mm(cfg['maximum_height_m'])} above the tabletop and no more than {mm(cfg['particle_size_m'])} below it.",
            f"No material edge may stretch beyond {cfg['maximum_stretch_ratio']:g} times its original length. Raised corners or pulling the blanket taut in the air do not count.",
        ]
        failures.append("Any cloth point falling more than 100 mm below the tabletop ends the episode in failure.")

    settling = task.final_settling_spec()
    if settling is not None:
        rules += [
            f"Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least {mm(settling.clearance_m)} "
            "of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.",
            f"During confirmation, every target point or rigid body's linear speed must be at most {mm(settling.maximum_speed_m_s)}/s "
            f"and its displacement from the start of confirmation at most {mm(settling.maximum_drift_m)}."
            + (f" Each target rigid body's angular speed must be at most {settling.maximum_angular_speed_rad_s:g} rad/s "
               f"and angular drift at most {settling.maximum_rotation_drift_rad:g} rad." if settling.rigid_targets else ""),
        ]
    return dict(schema_version=1, task_id=name, variation_id=task.variation_id, seed=int(task.seed),
                terminal_revision=task.terminal_revision, summary=summary,
                stable_duration_s=float(cfg.get("stable_duration_s", .5)),
                success_conditions=rules, failure_conditions=failures)
