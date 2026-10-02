"""Fiber Bundling key sheath poses and strand measurements, read-only.

A key pose is the world pose of the grasped link. The last two sheath links are
treated as collinear, so the sheath front point lies FRONT_M along the grasped
link's x axis. Combing one strand: offset the sheath axis from the ring axis by
d0 opposite the strand's fan direction, advance until its tip is just past the
ring, reduce the offset to d_press so the ring's outer surface presses the
strand toward the sheath axis, then pull the sheath back at that offset so the
contact slides along the strand and off its tip; back out and re-center.
(Pressing alone leaves the part beyond the contact fanned out: easy_01 comb_01
reached 12.8 mm at the contact but 16.6 mm at the tip.) Nothing here writes to
the simulator.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.evaluation.task_metrics import body_points
from topogym.planning.buzz_wire_3d.policy import rotation

GRASP_LINK = "trunk_04"
FRONT_M = .08  # trunk_04 origin to the sheath front face: two 40 mm links.
UP = np.array([0., 0., 1.])
# A pressed-and-slid tip ends about this far inside the press offset (easy_01/02
# comb_01: tip = d_press - 21.6 mm; the geometric contact is 21.5 + 1.2 mm).
PRESS_CONTACT_M = .0216


def ring_frame(state):
    ring = state["bodies"]["bundling_ring"]
    axis = rotation(ring["quaternion_wxyz"]).apply([0., 0., 1.])
    return np.asarray(ring["position_m"], float), axis/np.linalg.norm(axis)


def reference_rotation(axis):
    """Sheath frame with x on the ring axis and z as close to world up as possible."""
    y = np.cross(UP, axis)
    y /= np.linalg.norm(y)
    return Rotation.from_matrix(np.column_stack([axis, y, np.cross(axis, y)]))


def link_pose(state, name):
    link = state["articulations"]["fiber_bundle"]["links"][name]
    return np.asarray(link["position_m"], float), rotation(link["quaternion_wxyz"])


def sheath_pose(center, axis, offset, roll_deg, front_s):
    """Grasped-link pose whose front point is center+offset+front_s*axis."""
    r = Rotation.from_rotvec(np.radians(roll_deg)*axis)*reference_rotation(axis)
    return center+np.asarray(offset, float)+(front_s-FRONT_M)*axis, r


def front_point(p, r):
    return p+FRONT_M*r.apply([1., 0., 0.])


def current_roll_deg(state, axis):
    _, r = link_pose(state, GRASP_LINK)
    return float(np.degrees((r*reference_rotation(axis).inv()).as_rotvec() @ axis))


def strands(state, layout):
    """Station points of every strand, root first (the Task lists them tip first)."""
    links = state["articulations"]["fiber_bundle"]["links"]
    step = layout.fiber_length_m/layout.fiber_segments
    result = []
    for i in range(layout.fiber_count):
        segments = [body_points(links[f"fiber_{i:02d}_{j:02d}"], [[0, 0, 0], [step, 0, 0]])
                    for j in range(layout.fiber_segments)]
        result.append(np.vstack([s[0] for s in segments]+[segments[-1][1]]))
    return result


def strand_measures(state, layout):
    """Per strand: largest station distance from the fiber-carrying link's axis,
    tip distance, largest bend between neighbouring segments, tip position along
    that axis relative to the sheath front, and fan angle in the reference frame
    of the ring axis (0 deg = world up, 90 deg = reference +y)."""
    origin, r = link_pose(state, f"trunk_{layout.trunk_segments-1:02d}")
    a = r.apply([1., 0., 0.])
    front = origin+layout.trunk_length_m/layout.trunk_segments*a
    _, axis = ring_frame(state)
    base = reference_rotation(axis)
    result = []
    for points in strands(state, layout):
        v = points-origin
        radial = v-np.outer(v @ a, a)
        tangents = np.diff(points, axis=0)
        tangents /= np.linalg.norm(tangents, axis=1)[:, None]
        bends = np.degrees(np.arccos(np.clip(np.sum(tangents[:-1]*tangents[1:], axis=1), -1, 1)))
        tip = base.inv().apply(radial[-1])
        result.append(dict(max_radius_m=float(np.linalg.norm(radial, axis=1).max()),
                           tip_radius_m=float(np.linalg.norm(radial[-1])),
                           max_bend_deg=float(bends.max()),
                           tip_ahead_of_front_m=float((points[-1]-front) @ a),
                           fan_deg=float(np.degrees(np.arctan2(tip[1], tip[2])))))
    return result


def roll_choices(fan_deg, current_roll_deg=0., rolls=(0., -70., 70.), minimum_from_up_deg=60.):
    """Absolute rolls, preferred first, after which the strand fans at least
    minimum_from_up_deg away from world up. An upward strand would put the
    offset sheath below the ring, where the ring post stands."""
    allowed = []
    for roll in rolls:
        after = fan_deg-(roll-current_roll_deg)
        if np.cos(np.radians(after)) <= np.cos(np.radians(minimum_from_up_deg))+1e-12:
            allowed.append(float(roll))
    return allowed


def pressed_radius(radius, theta, d_press, contact=PRESS_CONTACT_M):
    """Predicted tip distance from the sheath axis after a press at offset
    d_press, for a tip at angle theta from the press direction. The ring's outer
    surface, seen from the sheath axis, is a circle of radius `contact` centred
    d_press away; a tip reaching past its near side ends there."""
    side = d_press*np.sin(theta)
    near = d_press*np.cos(theta)-np.sqrt(max(contact**2-side**2, 0.))
    if abs(side) >= contact or near <= 0:  # the ring is beside or behind this strand
        return radius
    return min(radius, near)


def expected_radius(radius, theta, d_press):
    """pressed_radius scaled by the share of it reached in physics. Measured in
    hard_guided_01 presses 1-3 (d_press 29 mm, 20 strands): within 5 deg of the
    press direction the full reduction; 17-38 deg about 45-75 % (mean 0.6),
    because the ring also pushes those strands sideways around itself; 42-46 deg
    0-46 %, and nothing beyond. 40 deg is taken as the edge."""
    angle = abs((np.degrees(theta)+180.) % 360.-180.)
    share = 1. if angle <= 7. else .6 if angle <= 40. else 0.
    return radius-share*(radius-pressed_radius(radius, theta, d_press))


def excess(measures, target):
    return sum(max(0., m["max_radius_m"]-target) for m in measures)


def sector_choices(measures, d_press, target, step_deg=5.):
    """Press directions (fan-frame degrees), best first: most strands now beyond
    target expected to come within it, then the largest drop in the summed
    excess beyond target. Directions gaining the same strand set are listed once."""
    rows, seen = [], set()
    for psi in np.arange(0., 360., step_deg):
        predicted = [expected_radius(m["tip_radius_m"], np.radians(m["fan_deg"]-psi), d_press) for m in measures]
        gained = frozenset(i for i, (m, after) in enumerate(zip(measures, predicted))
                           if m["max_radius_m"] > target and after <= target)
        reduction = sum(max(0., m["max_radius_m"]-target)-max(0., min(m["max_radius_m"], after)-target)
                        for m, after in zip(measures, predicted))
        rows.append(dict(psi_deg=float(psi), gained=sorted(gained), reduction_m=float(reduction),
                         contacted=[i for i, (m, after) in enumerate(zip(measures, predicted))
                                    if after < m["tip_radius_m"]]))
    rows.sort(key=lambda row: (-len(row["gained"]), -row["reduction_m"]))
    result = []
    for row in rows:
        if row["gained"] and frozenset(row["gained"]) not in seen:
            seen.add(frozenset(row["gained"]))
            result.append(row)
    return result


def comb_keyframes(state, layout, strand, d_press, roll_deg, *, approach_margin_m=.008,
                   tip_past_ring_m=.004, slide_m=.02, select_back_m=.02, psi_deg=None):
    """Two guides from the measured start: A presses and slides the contact off
    the tip, B backs out and returns to the axis at the starting front position.
    The offset and roll happen select_back_m before the approach position, which
    keeps the gripper clear of the cradle while every tip stays before the ring.
    `strand` is one index or a group pressed together toward psi_deg (default:
    the first strand's fan direction); the approach clears the group's farthest
    tip and brings its least advanced tip just past the ring."""
    center, axis = ring_frame(state)
    group = [strand] if isinstance(strand, (int, np.integer)) else list(strand)
    rows = strand_measures(state, layout)
    p, r = link_pose(state, GRASP_LINK)
    park_s = float((front_point(p, r)-center) @ axis)
    psi = rows[group[0]]["fan_deg"] if psi_deg is None else psi_deg
    after = np.radians(psi-(roll_deg-current_roll_deg(state, axis)))
    u = reference_rotation(axis).apply([0., np.sin(after), np.cos(after)])
    outer = layout.ring_inner_radius_m+2*layout.ring_tube_radius_m+layout.fiber_radius_m
    d0 = outer+max(rows[i]["tip_radius_m"] for i in group)+approach_margin_m
    if not 0 < d_press < d0:
        raise ValueError(f"Press offset {d_press} must lie between 0 and the approach offset {d0}")
    approach_s = tip_past_ring_m-min(rows[i]["tip_ahead_of_front_m"] for i in group)
    measures = rows[group[0]] if len(group) == 1 else [rows[i] for i in group]
    select_s = max(park_s, approach_s-select_back_m)
    slide_s = approach_s-slide_m

    def pose(label, d, roll, s):
        q, rr = sheath_pose(center, axis, -d*u, roll, s)
        return dict(label=label, position_m=q.tolist(), quaternion_wxyz=rr.as_quat()[[3, 0, 1, 2]].tolist())
    start = dict(label="measured_start", position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())
    guide_a = [start, pose("select", d0, roll_deg, select_s), pose("approach", d0, roll_deg, approach_s),
               pose("press", d_press, roll_deg, approach_s), pose("slide", d_press, roll_deg, slide_s)]
    guide_b = [guide_a[-1], pose("release", d0, roll_deg, slide_s), pose("center", 0., 0., park_s)]
    return guide_a, guide_b, dict(strand=strand, psi_deg=float(psi), d0_m=d0, d_press_m=d_press, roll_deg=roll_deg,
                                  press_direction=u.tolist(), park_front_s_m=park_s, select_front_s_m=select_s,
                                  approach_front_s_m=approach_s, slide_front_s_m=slide_s, measures=measures)


def feed_keyframes(state, front_s=.03):
    center, axis = ring_frame(state)
    p, r = link_pose(state, GRASP_LINK)
    q, rr = sheath_pose(center, axis, np.zeros(3), 0., front_s)
    return [dict(label="measured_start", position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist()),
            dict(label="feed_end", position_m=q.tolist(), quaternion_wxyz=rr.as_quat()[[3, 0, 1, 2]].tolist())]


def front_offsets(refs, state):
    """Distance of the planned front point from the ring axis at each reference."""
    center, axis = ring_frame(state)
    result = []
    for row in refs:
        v = front_point(np.asarray(row["position_m"]), rotation(row["quaternion_wxyz"]))-center
        result.append(float(np.linalg.norm(v-(v @ axis)*axis)))
    return result


def grasp_tcp(state, tilt_deg, closing_local, home_r):
    """TCP at the grasped link's middle, tool z tilted tilt_deg from straight down
    toward the ring, fingers closing across the sheath. Of the two finger
    orderings, the one nearer the home orientation is returned."""
    _, axis = ring_frame(state)
    p, r = link_pose(state, GRASP_LINK)
    target = p+r.apply([FRONT_M/4, 0., 0.])  # middle of the 40 mm grasped link
    t = np.radians(tilt_deg)
    z = np.sin(t)*axis-np.cos(t)*UP
    closing = np.cross(z, axis)
    closing /= np.linalg.norm(closing)
    c_local = np.asarray(closing_local, float)
    c_local = c_local-c_local[2]*np.array([0., 0., 1.])
    c_local /= np.linalg.norm(c_local)
    local = np.column_stack([c_local, [0., 0., 1.], np.cross(c_local, [0., 0., 1.])])
    options = []
    for sign in (1., -1.):
        world = np.column_stack([sign*closing, z, np.cross(sign*closing, z)])
        options.append(Rotation.from_matrix(world @ local.T))
    return target, min(options, key=lambda rr: (rr*home_r.inv()).magnitude())
