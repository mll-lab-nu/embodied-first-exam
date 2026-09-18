"""Conservative interval certificate for the limited-angle reindex family.

The graph OVER-approximates coaxial key/slot coupling, allowing the entire
angular backlash and arbitrary free rotation in every axial gap. An absent
0/1-retreat route therefore does not depend on a sampled angular grid.
It is not a global search of arbitrary 6-DOF contact manipulation.
"""

from collections import deque


def certificate(g, stops):
    if len(g.slots[1]) != 1 or len(g.slots[2]) != 1:
        raise ValueError("This certificate expects one slot in D2 and D3")
    a, b = map(float, stops[0].bounds_deg)
    c, d = map(float, stops[1].bounds_deg)
    if b - a >= 360 or d - c >= 360:
        raise ValueError("The first two rotors must have finite stops")
    m = g.slot_half_deg - g.tab_half_deg
    s2 = g.slots[1][0]
    relative_bands = [(s - s2 - 2 * m, s - s2 + 2 * m) for s in g.slots[0]]

    def overlap(x, y):
        return max(x[0], y[0]) <= min(x[1], y[1])

    if any(
        overlap(x, y)
        for i, x in enumerate(relative_bands)
        for y in relative_bands[i + 1 :]
    ):
        raise ValueError(
            "Relative-angle bands overlap: gap reindexing may avoid a retreat"
        )
    bands = [
        (max(c, a + s - s2 - 2 * m), min(d, b + s - s2 + 2 * m)) for s in g.slots[0]
    ]
    initial = [
        i for i, (lo, hi) in enumerate(bands) if lo <= g.initial_disc_deg[1] <= hi
    ]
    edges = {
        i: [j for j in range(len(bands)) if i != j and overlap(bands[i], bands[j])]
        for i in range(len(bands))
    }
    third = g.initial_disc_deg[2] + g.slots[2][0]
    targets = [
        i
        for i, s in enumerate(g.slots[0])
        if overlap((a + s - m, b + s + m), (third - m, third + m))
    ]
    queue = deque((i, [i]) for i in initial)
    paths = []
    minimum = None
    while queue:
        node, path = queue.popleft()
        if minimum is not None and len(path) - 1 > minimum:
            continue
        if node in targets:
            minimum = len(path) - 1
            paths.append(path)
            continue
        for j in edges[node]:
            if j not in path:
                queue.append((j, path + [j]))
    return dict(
        model="coaxial key-only slot-sidewall coupling, all axial gaps and angular backlash allowed",
        angular_margin_deg=m,
        rotor1_slot_deg=list(g.slots[0]),
        relative_rotor_angle_bands_deg=relative_bands,
        rotor2_angle_intervals_by_rotor1_slot_deg=bands,
        initially_reachable_branches=initial,
        third_layer_branches=targets,
        reset_graph=edges,
        minimum_required_decoupling_retreats=minimum,
        shortest_branch_sequences=paths,
        unique_shortest_branch_sequence=len(paths) == 1,
        zero_and_one_retreat_excluded=minimum is not None and minimum >= 2,
        assumptions=[
            "Rotors change angle by the key engaging slot sidewalls; no direct external rotor actuation.",
            "Key tab planes remain coaxial and share the same radial phase and axial pitch.",
            "A branch change at D1/D2 requires leaving simultaneous engagement and revisiting D1 alone.",
            "D3 is initially unchanged until its slot can be entered; planar face clutching is excluded.",
            "Quasi-static operation: a disengaged rotor retains its angle; inertial kicks are excluded.",
        ],
        limits=[
            "Continuous trajectories and velocities are not unique.",
            "Arbitrary off-axis wedging, impacts and alternate tool contacts are not certified.",
        ],
    )


def measured_retreat_cycles(frames):
    """Count observed D2 -> D1 -> D2 excursions, with axial hysteresis."""
    deep = False
    pending = None
    events = []
    for frame in frames:
        if not frame.get("grasp_weld", False):
            continue
        depth = float(frame["depth"])
        if depth >= 1.9:
            if pending is not None:
                pending["reentered_second_s"] = frame["time_s"]
                events.append(pending)
                pending = None
            deep = True
        elif deep and depth <= 1.15:
            pending = dict(reached_first_s=frame["time_s"], minimum_depth=depth)
            deep = False
        if pending is not None:
            pending["minimum_depth"] = min(pending["minimum_depth"], depth)
    return events
