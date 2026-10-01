"""Construct and certify the current coaxial, passive lock reindex paths.

This is a quasi-static configuration-space witness, not a dynamics rollout.
Disengaged rotors retain their angles. Engaged rotors move only after a key
tab takes up the four-degree slot backlash and touches a driving sidewall.
"""
from collections import deque
from copy import deepcopy
import math

import numpy as np


def retreat_certificate(g, stops):
    """An interval over-approximation gives a lower bound on D2->D1 resets.

    Bands include all angular backlash and arbitrary free turns in axial gaps.
    This argument excludes off-axis wedging, face friction and inertial kicks.
    """
    if len(g.slots[1]) != 1 or len(g.slots[2]) != 1:
        raise ValueError("The certificate requires single slots in D2 and D3")
    a, b = stops[0]["bounds_deg"]
    c, d = stops[1]["bounds_deg"]
    m, second = g.slot_half_deg-g.tab_half_deg, g.slots[1][0]
    relative = [(s-second-2*m, s-second+2*m) for s in g.slots[0]]
    overlap = lambda x, y: max(x[0], y[0]) <= min(x[1], y[1])
    if any(overlap(x, y) for i, x in enumerate(relative) for y in relative[i+1:]):
        raise ValueError("Overlapping branch bands invalidate this reset certificate")
    bands = [(max(c, a+s-second-2*m), min(d, b+s-second+2*m)) for s in g.slots[0]]
    initial = [i for i, (lo, hi) in enumerate(bands) if lo <= g.initial_disc_deg[1] <= hi]
    third = g.initial_disc_deg[2]+g.slots[2][0]
    targets = [i for i, s in enumerate(g.slots[0])
               if overlap((a+s-m, b+s+m), (third-m, third+m))]
    edges = {i: [j for j in range(len(bands)) if i != j and overlap(bands[i], bands[j])]
             for i in range(len(bands))}
    queue, shortest = deque((i, [i]) for i in initial), []
    minimum = None
    while queue:
        node, path = queue.popleft()
        if minimum is not None and len(path)-1 > minimum:
            continue
        if node in targets:
            minimum = len(path)-1
            shortest.append(path)
        else:
            queue.extend((j, path+[j]) for j in edges[node] if j not in path)
    return dict(minimum_required_retreats=minimum, branch_intervals_deg=bands,
                relative_bands_deg=relative, initial_branches=initial, target_branches=targets,
                graph={str(k): v for k, v in edges.items()}, shortest_sequences=shortest,
                scope="Coaxial, quasi-static, key-sidewall actuation; no face clutching or impacts")


def construct_route(g, stops, *, stop_margin_deg=1.):
    """Use the existing slots/limits; never derive easier geometry from a path."""
    g.validate()
    slots = np.asarray(g.slots[0], float)
    step = np.diff(slots)
    bound = float(stops[0]["bounds_deg"][1])
    m = g.slot_half_deg-g.tab_half_deg
    if (len(slots) < 2 or not np.allclose(step, step[0])
            or not np.isclose(step[0], 2*bound)
            or not np.isclose(stops[0]["bounds_deg"][0], -bound)
            or not np.isclose(slots[-1], 0.) or list(g.slots[1]) != [slots[0]]
            or list(g.slots[2]) != [0.] or not np.allclose(g.initial_disc_deg, 0.)
            or g.initial_key_deg != 0. or g.endpoint_deg != 0.):
        raise ValueError("Route supports the current equal-spacing, zero-initial-angle families")
    if not 0 < stop_margin_deg < min(m, bound):
        raise ValueError("Stop margin must be positive and smaller than backlash and stop angle")
    swing = bound-stop_margin_deg
    states = [dict(phase="coaxial_start", depth=0., key_deg=0., disc_deg=[0., 0., 0.])]

    def append(phase, *, depth=None, key=None, discs=None):
        state = deepcopy(states[-1])
        state.update(phase=phase)
        if depth is not None:
            state["depth"] = float(depth)
        if key is not None:
            state["key_deg"] = float(key)
        if discs is not None:
            state["disc_deg"] = list(map(float, discs))
        states.append(state)

    def turn(target, active, phase):
        # Split at each sidewall contact: all resulting states are affine,
        # including the initial backlash take-up and a two-disc unequal take-up.
        start = states[-1]
        theta = start["key_deg"]
        old = np.array(start["disc_deg"])
        sign = 1 if target > theta else -1
        cuts = [theta, float(target)]
        for disc, slot in active.items():
            hit = old[disc]+slot+sign*m
            if min(theta, target) < hit < max(theta, target):
                cuts.append(hit)
        for angle in sorted(set(cuts), reverse=sign < 0)[1:]:
            new = old.copy()
            for disc, slot in active.items():
                limit = angle-slot-sign*m
                new[disc] = max(old[disc], limit) if sign > 0 else min(old[disc], limit)
            append(phase, key=angle, discs=new)

    append("align_entry", key=slots[0])
    append("insert_D1", depth=1.)
    append("insert_D2", depth=2.)
    for branch, slot in enumerate(slots):
        final = branch == len(slots)-1
        turn(m if final else slot+swing+m, {0: slot, 1: slots[0]},
             "align_final" if final else f"index_{branch+1}")
        if final:
            break
        append(f"retreat_{branch+1}_D1", depth=1.)
        turn(slot-swing-m, {0: slot}, f"reset_{branch+1}_D1")
        append(f"reset_{branch+1}_axial_gap", depth=1.5)
        append(f"select_slot_{branch+1}", key=slot+step[0]/2)
        append(f"reinsert_{branch+1}_D2", depth=2.)
    turn(0., {0: 0., 1: slots[0]}, "center_final_slots")
    append("insert_D3", depth=3.)
    append("enter_END", depth=4.)
    append("clear_END", depth=4.08)
    return states


def audit_route(g, stops, states):
    """Certify whole affine segments, including finite plate/tab thickness.

    Every slab-overlap interval is split exactly. Relative angle is affine,
    so its endpoints certify containment in one fixed slot throughout that
    interval. Rotating discs must touch the appropriate driving sidewall.
    """
    g.validate()
    if len(states) < 2:
        raise ValueError("A path needs at least two states")
    first, last = states[0], states[-1]
    if (first["depth"] != 0. or first["key_deg"] != g.initial_key_deg
            or not np.allclose(first["disc_deg"], g.initial_disc_deg, atol=1e-10)):
        raise ValueError("Path does not start at the declared coaxial initial state")
    half = (g.tab_thickness+g.disc_thickness)/(2*g.pitch)
    m = g.slot_half_deg-g.tab_half_deg
    minimum = math.inf
    stop_gap = math.inf
    checked, driven = 0, 0
    for state in states:
        numeric = [state["depth"], state["key_deg"], *state["disc_deg"]]
        if len(state["disc_deg"]) != 3 or not np.isfinite(numeric).all():
            raise ValueError("Malformed/nonfinite object state")
        for angle, stop in zip(state["disc_deg"], stops):
            lo, hi = stop["bounds_deg"]
            gap = min(angle-lo, hi-angle)
            if gap < -1e-9:
                raise ValueError(f"Rotor stop exceeded at {state['phase']}")
            stop_gap = min(stop_gap, gap)
        if g.clearance(state["depth"], state["key_deg"], state["disc_deg"], tolerance=1e-9):
            raise ValueError(f"Blocked waypoint: {state['phase']}")
    for a, b in zip(states, states[1:]):
        dd = b["depth"]-a["depth"]
        dt = b["key_deg"]-a["key_deg"]
        dr = np.asarray(b["disc_deg"])-a["disc_deg"]
        if dd and (abs(dt) > 1e-9 or np.any(abs(dr) > 1e-9)):
            raise ValueError("This witness uses separate insertion and turn strokes")
        cuts = {0., 1.}
        if dd:
            for tab in range(3):
                for disc in range(4):
                    for sign in (-1, 1):
                        u = (disc+tab+1+sign*half-a["depth"])/dd
                        if 0 < u < 1:
                            cuts.add(float(u))
        cuts = sorted(cuts)
        for left, right in zip(cuts, cuts[1:]):
            middle = a["depth"]+dd*(left+right)/2
            active = set()
            for tab in range(3):
                for disc in range(4):
                    if abs(middle-tab-disc-1) > half+1e-12:
                        continue
                    active.add(disc)
                    da = a["disc_deg"][disc] if disc < 3 else 0.
                    delta = dr[disc] if disc < 3 else 0.
                    ends = np.array([a["key_deg"]-da+(dt-delta)*u for u in (left, right)])
                    slots = g.slots[disc] if disc < 3 else [g.endpoint_deg]
                    # The path is unwrapped, but test every relevant slot copy.
                    candidates = [s+360*k for s in slots
                                  for k in range(math.floor((min(ends)-s)/360)-1,
                                                 math.ceil((max(ends)-s)/360)+2)]
                    margin = max(m-max(abs(ends-s)) for s in candidates)
                    minimum = min(minimum, float(margin))
                    if margin < -1e-8:
                        raise ValueError(f"Blocked continuous segment: {a['phase']} -> {b['phase']}")
                    checked += 1
                    if disc < 3 and abs(delta) > 1e-9:
                        if (not np.isclose(delta, dt, atol=1e-9, rtol=0)
                                or not any(np.allclose(ends-s, np.sign(delta)*m,
                                                      atol=1e-9, rtol=0) for s in candidates)):
                            raise ValueError("Rotor moves without a driving key sidewall")
                        driven += 1
            if any(abs(dr[i]) > 1e-9 and i not in active for i in range(3)):
                raise ValueError("Disengaged rotor moved")
    # The actual task requires the back of the leading tab beyond END,
    # while the shaft still spans the full thickness of its aperture.
    tip, end = g.tip_x(last["depth"]), g.disc_x(3)
    clearance = tip-g.tab_thickness/2-end-g.disc_thickness/2
    if clearance < .001 or not (tip-g.grip_offset-.02 <= end-g.disc_thickness/2
                               and tip+.015 >= end+g.disc_thickness/2):
        raise ValueError("Leading tab has not cleared END with the shaft still inserted")
    # Collision sectors use <=10-degree facets. The inscribed polygon bore
    # is slightly smaller than its nominal circular radius.
    bore_gap = g.bore_radius*math.cos(math.radians(5))-g.shaft_radius
    radial_gap = g.slot_radius*math.cos(math.radians(5))-g.tab_radius
    if min(bore_gap, radial_gap) <= 0:
        raise ValueError("No conservative radial clearance")
    retreats = sum(b["depth"] < a["depth"] for a, b in zip(states, states[1:]))
    lower = retreat_certificate(g, stops)
    return dict(passed=True, checked_overlap_intervals=checked, driving_intervals=driven,
                minimum_slot_margin_deg=minimum, minimum_rotor_stop_margin_deg=stop_gap,
                conservative_shaft_clearance_m=bore_gap, conservative_tab_radial_clearance_m=radial_gap,
                final_leading_tab_clearance_m=clearance, retreats=retreats,
                retreat_count_is_minimal=retreats == lower["minimum_required_retreats"],
                lower_bound=lower, passive_sidewall_coupling_verified=True,
                scope="Exact affine coaxial aperture/stop and quasi-static sidewall model",
                full_scene_collision_verified=False, dynamics_verified=False,
                released_equilibrium_verified=False, native_task_success=False)


def sample_route(g, states, *, translation_step_m=.002, angle_step_deg=1.):
    if translation_step_m <= 0 or angle_step_deg <= 0:
        raise ValueError("Sample spacings must be positive")
    samples = [deepcopy(states[0])]
    for index, (a, b) in enumerate(zip(states, states[1:])):
        n = max(1, math.ceil(abs(b["depth"]-a["depth"])*g.pitch/translation_step_m),
                math.ceil(abs(b["key_deg"]-a["key_deg"])/angle_step_deg))
        for u in np.linspace(0., 1., n+1)[1:]:
            samples.append(dict(phase=b["phase"], segment=index, progress=float(u),
                depth=a["depth"]+u*(b["depth"]-a["depth"]),
                key_deg=a["key_deg"]+u*(b["key_deg"]-a["key_deg"]),
                disc_deg=(np.asarray(a["disc_deg"])+u*(np.asarray(b["disc_deg"])-a["disc_deg"])).tolist()))
    return samples
