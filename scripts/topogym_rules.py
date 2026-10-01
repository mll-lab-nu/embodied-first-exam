"""Grader details for the TopoGym tier instructions (both modes), added to Jianwen's public goal text.

The base text is his: topogym/tasks/goal_description.py describe_goal() + render_goal() (the instance's "public_goal" in
describe.json, rendered by the generators as "## Success requirements" + "## Task failure conditions"). It is copied
verbatim. This module adds ONLY what the grader checks and his text does not state (sizes, radii, distances, counts,
sampling, edge cases), read from his task code at 2ec4b8d6 (build78/predicates_table_2ec4b8d6.md has the file:line
citations), with the tier's values from the frozen instance.json. It repeats nothing his text says and contradicts none
of it. No positions or poses: conditions, thresholds, names and sizes only (the limited-mode rule)."""

RIGID = {"cast_coil", "cast_keyhole", "interlocked_claws", "hedgehog_in_cage", "horseshoe_ring"}
PLACEMENT = {"cast_keyhole", "interlocked_claws", "hedgehog_in_cage", "horseshoe_ring", "orbits", "slotted_post_ring"}
# remaining components of the placement families that are free bodies (the rest are fixed), as named in s.objects()
FREE_REMAINDER = {"cast_keyhole": "the gold piece", "interlocked_claws": "the other claw piece",
                  "horseshoe_ring": "the horseshoes and chain links", "slotted_post_ring": "the cord, beads and end discs"}
# failure strings as `s.status()["episode_end"]` reports them (unlimited); limited mode reports `task_failed`
FAIL_STRINGS = {
    "rigid": ['"Held finger contact penetration exceeded 2 mm"', '"Task contact penetration exceeded 1 mm"',
              '"A task body fell below the table"'],
    "horseshoe_ring": ['"Physical chain/eye connection lost"'],
    "buzz_wire_3d": ['"wire_touched"', '"Wand fell below table"'],
    "lock_picking": ['"rotor_limit_exceeded"', '"Key fell below table"'],
    "fiber_bundling": ['"fiber_gripper_contact"', '"Fiber below table"'],
    "orbits": ['"connection_or_volume_invalid"'], "slotted_post_ring": ['"connection_or_volume_invalid"'],
    "knot_untying": ['"rope_volume_invalid"'], "rope_threading": ['"rope_volume_invalid"'],
    "blanket_flatten": ['"Cloth fell below the table"'],
}


def _mm(m, nd=1):
    s = f"{float(m) * 1000:.{nd}f}"
    return (s.rstrip("0").rstrip(".") if "." in s else s) + " mm"


def _or(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " or " + xs[-1]


def _square_mm(inst):
    """Side of the usable goal square: the inner edge of the 2 mm dashed stripe (goal_region size - 4 mm; the stripe
    is centred on the region's border, topogym/assets/geometry/goal_region.py)."""
    size = inst.get("objects", {}).get("goal_region", {}).get("size")
    return None if not size else (float(size[0]) - .004) * 1000


def grader_details(fam, inst, *, limited):
    """Bullet lines (without the leading "- ") for one instance."""
    tp = inst.get("effective_task_parameters", {}) or {}
    g = tp.get("geometry", {}) or {}
    out = []
    if fam in PLACEMENT:
        side = _square_mm(inst)
        if side:
            out.append(f"Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment "
                       f"limit (the region's border runs along the middle of the line); it encloses a {side:.1f} mm x "
                       f"{side:.1f} mm square. Every point counts: for a rigid part every vertex of its visual and collision "
                       "meshes" + ("; for the cord every vertex of its simulated volume" if fam in ("orbits", "slotted_post_ring")
                                   else "") + ".")
        free = FREE_REMAINDER.get(fam)
        out.append("The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond "
                   "the point of all remaining components that was closest to the goal square at the start; the square's "
                   "near edge is at least 30 mm beyond it. " + (
                       f"{free[0].upper() + free[1:]} are free to move (their speed is not checked), but no point of them "
                       "may cross that plane." if free and free.endswith("s") else
                       f"{free[0].upper() + free[1:]} is free to move (its speed is not checked), but no point of it may "
                       "cross that plane." if free else "The remaining components here are fixed."))
    if fam in RIGID:
        out.append("Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per "
                   "control step). \"Held\" is decided anew at every tick: a zero-force touch counts, and if one finger "
                   "loses contact (with no active assisted grasp), the other finger is back at the 1 mm limit in the same "
                   "tick." + (" The cage is fixed, so finger contact with it is never held (always the 1 mm limit)."
                              if fam == "hedgehog_in_cage" else ""))
    if fam == "horseshoe_ring":
        out.append("The four permanent connections (the upper and lower eye of each horseshoe with its chain link) are "
                   "checked at every tick by the linking number of the two loops.")
    if fam == "cast_coil" or fam == "buzz_wire_3d":
        out.append("The release clearance is measured between axis-aligned bounding boxes: one around each collision geometry "
                   "of the whole robot (every link of both arms) and one around each collision geometry of the "
                   + ("pieces" if fam == "cast_coil" else "tool") + ", so the true gap usually has to be larger than 5 mm.")
    if fam == "buzz_wire_3d":
        term = tp.get("terminal", {}) or {}
        out += [
            "The loop's usable opening: the wire's centreline must cross the loop's disk less than 12.67 mm from the loop's "
            "centre (loop inner radius 14.14 mm minus the 1.47 mm wire radius).",
            "Continuous traversal: from one physics tick to the next, the crossing point may move along the wire by at most "
            "twice the loop's own motion in that tick (its displacement plus 12.67 mm times its rotation angle) plus "
            f"{_mm(term.get('route_progress_tolerance_m', .003))}. A larger jump, no crossing, two crossings or a tangency "
            "cancels the traversal; it must then start again within "
            f"{_mm(term.get('start_route_tolerance_m', .01))} of the starting end, the end where the tool rests at the start.",
            "The finish support is the deck, and the finish resting pose is the start resting pose repeated at the wire's "
            "finishing end: the tool lies on the deck with its loop at that end of the wire and its handle pointing inward, "
            "the way it lies at the start.",
            "Metal contact is sampled at all 4 solver substeps of every tick. If any tick since the start had incomplete "
            "contact coverage (a simulator-side condition), the episode can no longer succeed.",
        ]
    if fam == "lock_picking":
        bore, shaft = float(g.get("bore_radius", .0075)), float(g.get("shaft_radius", .0065))
        tab_r, tab_h, slot_h = float(g.get("tab_radius", .036)), float(g.get("tab_half_deg", 4)), float(g.get("slot_half_deg", 8))
        tol = float((tp.get("terminal", {}) or {}).get("shaft_contact_tolerance_m", 1e-5))
        rot_tol = float((tp.get("terminal", {}) or {}).get("rotor_tolerance_deg", .5))
        out += [
            f"Sizes: bore radius {_mm(bore)}, shaft radius {_mm(shaft)}. At each of the 8 plate faces (three "
            f"{_mm(g.get('disc_thickness', .01))} rotor plates and END, {_mm(g.get('pitch', .15), 0)} apart), the shaft axis' "
            f"distance from the bore axis plus {_mm(shaft)} / cos(tilt) may exceed {_mm(bore)} by at most {_mm(tol, 2)}: "
            f"about {_mm(bore - shaft + tol, 2)} of offset when the key is straight, which over the stack allows only about "
            "0.25 degrees of tilt.",
            f"The shaft reaches from {_mm(float(g.get('grip_offset', .495)) + .02, 0)} behind the leading tab to 15 mm in "
            "front of it; all 8 plate faces must lie within that length.",
            f"Tabs: radius {_mm(tab_r, 0)}, half-width {tab_h:g} degrees; slots: half-width {slot_h:g} degrees. A tab that "
            f"overlaps a plate must sit inside one of that plate's slots with an angular margin of at least asin(axis offset / "
            f"{_mm(tab_r, 0)}) + the tilt.",
        ]
        stops = tp.get("rotor_stops") or []
        lim = []
        for k, st in enumerate(stops[:3]):
            lo, hi = (st["bounds_deg"] if isinstance(st, dict) else st)
            if hi - lo < 360:
                lim.append(f"rotor {k + 1} {abs(lo):g} degrees one way and {abs(hi):g} degrees the other"
                           if lo < 0 < hi and abs(lo) != abs(hi) else f"rotor {k + 1} {abs(hi):g} degrees either way")
            else:
                lim.append(f"rotor {k + 1} turns freely")
        if lim:
            out.append("Rotor stops (from each rotor's start angle; \"the other way\" is the sense that turns rotor 2's slot "
                       f"toward the tabs' starting angle): {'; '.join(lim)}. Going more than {rot_tol:g} degrees beyond a "
                       "stop ends the episode.")
    if fam == "fiber_bundling":
        n = g.get("fiber_count")
        out += [
            f"Sizes: ring inner radius {_mm(g.get('ring_inner_radius_m', .0135))}, ring tube radius 4 mm; "
            f"{n} fibers of radius 1.2 mm; sheath radius 12 mm." if n else
            f"Sizes: ring inner radius {_mm(g.get('ring_inner_radius_m', .0135))}, ring tube radius 4 mm; fiber radius "
            "1.2 mm; sheath radius 12 mm.",
            "Each fiber is tracked at 11 points from tip to root. A point counts when it crosses the ring's plane less than "
            "17.48 mm from the ring's axis, in tip-to-root order; a crossing out of order or outside that radius resets that "
            "point and every point behind it, and crossing back loses the credit.",
            "At the end every fiber point must be more than 5.2 mm past the ring's plane (tube + fiber radius) and the centre "
            "of the sheath's front face more than 16 mm past it (tube + sheath radius). The exit side is the side opposite "
            "to where the fibers start.",
            "The failure counts contact between a fine fiber and the gripper (fingers and hand, housing included); arm links "
            "touching a fiber do not count. Contact is sampled at all 4 solver substeps of every tick; if any tick since the "
            "start had incomplete contact coverage (a simulator-side condition), the episode can no longer succeed.",
        ]
    if fam == "knot_untying":
        out += [
            "The rope is 8 mm thick (radius 4 mm), so its highest point may be at most 11 mm above the tabletop.",
            "\"Nonlocal\" means at least 16 mm apart along the rope: such parts of the rope's centreline must be at least "
            "8 mm apart in the top view. Closer parts are exempt, but an actual crossing always counts.",
            "The release clearance is measured between axis-aligned bounding boxes of the robot's collision geometries and "
            "the rope (refined per tetrahedron where they are close).",
        ]
    if fam == "rope_threading":
        inner = g.get("ring_inner_radius_m") or .069
        out += [
            f"Sizes: each ring's inner radius is {_mm(inner)} and its tube 12 mm thick (radius 6 mm); the rope's radius is "
            f"4 mm. So the rope's centreline must pass less than {_mm(float(inner) - .004 - .0001, 1)} from a ring's centre, "
            "and the passage is checked on the ring's middle plane and on the planes 6 mm to either side of it.",
            "The material start is the rope end that is farther from the rings at the start.",
        ]
    if fam == "blanket_flatten":
        L, W = float(tp.get("length_m", .6)), float(tp.get("width_m", .48))
        cov, pad = float(tp.get("minimum_coverage_ratio", .9)), float(tp.get("particle_size_m", .008))
        out += [
            f"The blanket is {L:g} m x {W:g} m ({L * W:.3f} m^2), so the coverage needs at least {cov * L * W:.4f} m^2 of "
            "its area in the top view. Heights are measured at the cloth particles' centres.",
            f"The release clearance is measured from one box around all cloth particles, grown by {_mm(pad, 0)}: every robot "
            f"collision box must stay at least 5 mm from it, i.e. at least {_mm(pad + .005, 0)} outside the cloth's bounding "
            "box, above its highest point too.",
        ]
    g = grasp_regions(fam, inst, limited=limited)
    if g:
        out.append(g)
    if not limited:
        strings = (FAIL_STRINGS["rigid"] if fam in RIGID else []) + FAIL_STRINGS.get(fam, [])
        if strings:
            out.append("A failure is reported in `s.status()[\"episode_end\"]` as " + _or(strings) + ".")
    return out


# where his declared grasp regions sit, by construction of his recipes (76583213 topogym/tasks/<family>/common.py
# recommended_grasp_assist and the tooling's explicit lock_picking entry): words only, never a centre (a position)
GRASP_WHERE = {("buzz_wire_3d", "wand"): "on the wand's grip", ("lock_picking", "lock_key"): "on the key's handle"}
GRASP_WHOLE = {"hedgehog_in_cage", "horseshoe_ring"}      # rigid_grasp_region: the part's whole mesh + 5 mm


def grasp_regions(fam, inst, *, limited):
    """The sizes of his grasp regions (the frozen simulator.grasp_assist): one sphere per graspable part. His grasp text
    (Grippers) names the parts and the tool-frame gate but not the regions' sizes."""
    ga = ((inst or {}).get("simulator") or {}).get("grasp_assist") or {}
    targets = [t for t in ga.get("targets", []) if isinstance(t, dict)]
    if ga.get("model", "none") == "none" or not targets:
        return None
    regs = []
    for t in targets:
        where = "enclosing the whole part" if fam in GRASP_WHOLE else GRASP_WHERE.get((fam, t["entity"]))
        regs.append(f"{t['entity']}: radius {_mm(t['radius_m'])}" + (f", {where}" if where else ""))
    out = ("Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): " + "; ".join(regs)
           + ". Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.")
    if not limited:
        out += " Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`."
    return out


def details_section(fam, inst, *, limited):
    """Markdown section placed right after his requirements; "" if there is nothing to add. Starts and ends with a
    newline so that it fits between his text and the next section."""
    lines = grader_details(fam, inst, limited=limited)
    if not lines:
        return ""
    return ("\n## Grader details (in addition to the requirements above)\n\n"
            + "\n".join(f"- {x}" for x in lines) + "\n")


def step_seconds(d: dict) -> float:
    """The per-control-step wall time the texts quote: the measured arm-motion value where the build measured one
    (describe.json sec_per_step_motion: FEM / IPC families, 2026-10-01: motion steps on an unloaded GPU, the slower of our
    GPU types), else describe's sec_per_step."""
    return float(d.get("sec_per_step_motion") or d["sec_per_step"])


def step_time_words(d: dict) -> str:
    """'One control step takes about ...' for the instruction texts (no claim about checkpoints: the simulator keeps a
    complete checkpoint only at the episode start). With describe.json `sec_per_step_unloaded` (a hold step measured on an
    unloaded GPU), the texts give both ends: the unloaded time and the measured time on a shared GPU, which the chunk advice
    keeps using (the safe end)."""
    if d.get("sec_per_step_motion"):
        return (f"One control step with the arms moving takes about {step_seconds(d):.0f} s of wall clock here (measured on an "
                f"unloaded GPU, the slower of our GPU types; holding still is faster)")
    if d.get("sec_per_step_unloaded"):
        return (f"One control step takes about {float(d['sec_per_step_unloaded']):.1f} s of wall clock on an unloaded GPU, and "
                f"up to about {step_seconds(d):.1f} s when other simulations share the GPU; the call metadata reports the time")
    return f"One control step takes about {step_seconds(d):.1f} s of wall clock here"


def limited_timing(sec_per_step, control_hz=40.0, submit_timeout_s=1800, observe_timeout_s=600, max_chunk_s=10.0, safety=2.0,
                   motion=False, unloaded=None):
    """Client-side timeouts (rcb_client.py: submit 1800 s, get_obs 600 s) against this instance's measured speed (motion:
    the measured arm-motion step time, describe.json sec_per_step_motion)."""
    per = max(float(sec_per_step), 1e-3)
    chunk_steps = int(submit_timeout_s / (safety * per)); watch_steps = int(observe_timeout_s / (safety * per))
    chunk_line = (f"keep each `submit` to at most {chunk_steps} control steps ({chunk_steps / control_hz:.2f} s of simulated "
                  f"time: rows x dt)" if chunk_steps < max_chunk_s * control_hz else
                  f"a `submit` of the maximum {max_chunk_s:g} s chunk fits")
    watch_line = (f"keep each `get_obs(seconds=...)` watch to at most {watch_steps} control steps "
                  f"({watch_steps / control_hz:.2f} s)" if watch_steps < 30 * control_hz else "any watch up to 30 s fits")
    return ("## Time per call\n"
            + (f"- One control step with the arms moving takes about {per:.0f} s of wall clock here (holding still is faster). "
               if motion else f"- One control step takes about {float(unloaded):.1f} s of wall clock on an unloaded GPU and up to about "
               f"{per:.1f} s when other simulations share it; the advice below assumes the slower figure. "
               if unloaded else f"- One control step takes about {per:.1f} s of wall clock here. ")
            + "A request returns only when all of its steps "
            f"have run, and the client gives up waiting after {submit_timeout_s} s for `submit` and {observe_timeout_s} s "
            f"for `get_obs`: {chunk_line}; {watch_line} (both with a 2x margin).\n"
            "- If a request times out in the client anyway, the service still runs it to the end: do NOT send it again "
            "(it would run twice). Call `r.get_obs()` (repeat it if it also times out): it answers once the earlier "
            "request has finished and shows the state after it.\n")
