"""The fixed states between stages: what the next stage relies on (topology and where the key parts are), never the
cord's shape. Each check returns (holds, measurements); s1-s3 take a Scene (session.scene) and the layout, s4a and s4b
(the task's own goal check) the World state and the task. oracle.run brings both hands home and lets the scene settle before
each check.

S1  disc1 through the slot (the chain passes it twice), parked behind or beside the base clear of the ring; bead1
    outside the ring in front of the post; the ring still round the post and not threaded.
S2  the ring off the post behind it, threaded by the two back strands only (not by bead1's bight); bead1 in front.
S3  the ring free of the chain, flat on the table front right (clear of bead1's way forward in M4b).
S4a the ring inside the goal region (the task's own region), flat and quiet.
S4b every other part (chain, discs, beads) on the system side of the separator.
"""
import numpy as np

AT_REST_M_S = .005
# Fixed states: where the stages leave the parts, with tolerances (every passing E run of the three settings within).
# Each stage brings the scene there (M2 sets the ring down at its spot and pushes disc1 aside, M3 lays the ring down at
# its spot, M4b sets disc1 down at its target), so a perturbation stays within the stage it happens in.
S2_RING_BOX_M = ((.12, .20), (.08, .20))        # the ring's centre (x, y ranges) after M2's set-down and pushes
S2_DISC1_BOX_M = ((-.13, -.08), (.13, .21))     # disc1's centre after M2's push aside
S3_RING_AT_M, S3_RING_TOL_M = (.207, -.196), .02     # the ring laid down by M3
S4B_DISC1_BOX_M = ((-.27, -.14), (-.10, -.01))  # disc1 set down by M4b
RING_LIFTED_M = .02           # the ring's centre this far over its rest on the base: lifted (bead1 rule)
S3_RING_MIN_X_M, S3_RING_MAX_Y_M = .06, -.17


def slot_crossings(points, lay):
    """Chain segment indices passing the post's mid-plane (y = 0) inside the slot opening."""
    out = []
    for i, (a, b) in enumerate(zip(points[:-1], points[1:])):
        if (a[1] < 0) != (b[1] < 0):
            u = a[1]/(a[1]-b[1])
            x, z = a[0]+u*(b[0]-a[0]), a[2]+u*(b[2]-a[2])
            if abs(x) < lay.slot_width_m/2 and lay.slot_bottom_m < z < lay.slot_top_m:
                out.append(i)
    return out


def ring_crossings(points, ring, lay):
    """[(segment index, sign)] where the chain passes the ring's disk inside its hole; a dip in and out sums to 0."""
    c, r = ring
    n = r.apply([0., 0., 1.])
    p = points-c
    h = p @ n
    out = []
    for i in np.nonzero(np.sign(h[:-1]) != np.sign(h[1:]))[0]:
        u = h[i]/(h[i]-h[i+1])
        x = p[i]+u*(p[i+1]-p[i])
        if np.linalg.norm(x-(x @ n)*n) < lay.ring_inner_radius:
            out.append((int(i), int(np.sign(h[i+1]-h[i]))))
    return out


def ring_on_post(ring, lay):
    c, _ = ring
    corners = np.array([[sx*lay.post_width_m/2, sy*lay.post_depth_m/2] for sx in (-1, 1) for sy in (-1, 1)])
    return bool(np.linalg.norm(corners-c[:2], axis=1).max() < lay.ring_inner_radius
                and c[2] < lay.base_height_m+lay.post_height_m)


def bead1_with_post_in_hole(scene, lay):
    """The ring, lifted off the base, passes the post and bead1 together, which the user's rule forbids (the hole may
    pass bead1 alone): all four of the post's vertical edges cross the ring's plane inside its hole below the post top,
    and bead1's centre is inside the hole within a bead and a tube radius of that plane. (In M1 bead1 waits at the
    slot's mouth in the hole of the ring lying on the base: not counted.)"""
    c, rot = scene.poses["ring"]
    n = rot.apply([0., 0., 1.])
    if abs(n[2]) < .2:                        # the ring stands: its hole cannot go round the vertical post
        return False
    if c[2] < lay.base_height_m+lay.ring_tube_radius_m+RING_LIFTED_M:
        return False
    top = lay.base_height_m+lay.post_height_m
    for x in (-lay.post_width_m/2, lay.post_width_m/2):
        for y in (-lay.post_depth_m/2, lay.post_depth_m/2):
            z = c[2]-(n[0]*(x-c[0])+n[1]*(y-c[1]))/n[2]
            if not (lay.base_height_m < z < top and np.linalg.norm(np.r_[x, y, z]-c) < lay.ring_inner_radius):
                return False
    d = scene.pos("bead_left")-c
    h = float(d @ n)
    return bool(abs(h) < lay.bead_radius_m+lay.ring_tube_radius_m and np.linalg.norm(d-h*n) < lay.ring_inner_radius)


def ring_outer(lay):
    return lay.ring_major_radius_m+lay.ring_tube_radius_m


def s1(scene, lay):
    slot = slot_crossings(scene.points, lay)
    ring = scene.poses["ring"]
    disc, bead = scene.pos("disc_left"), scene.pos("bead_left")
    m = dict(slot_crossings=slot, ring_crossings=ring_crossings(scene.points, ring, lay),
             disc1_clear_of_ring=bool(np.linalg.norm(disc[:2]-ring[0][:2]) > ring_outer(lay)+lay.disc_radius_m),
             disc1_behind_or_beside=bool(disc[1] > -lay.base_depth_m/2),
             bead1_in_front=bool(bead[1] < -lay.post_depth_m/2 and bead[2] < lay.slot_bottom_m),
             ring_on_post=ring_on_post(ring, lay))
    m["ring_not_threaded"] = sum(s for _, s in m["ring_crossings"]) == 0
    # bead1 outside the ring, not in its hole (user decision, 2026-10-07)
    m["bead1_outside_ring"] = bool(np.linalg.norm(bead[:2]-ring[0][:2]) > ring_outer(lay)+lay.bead_radius_m)
    return len(slot) == 2 and all(v for k, v in m.items() if isinstance(v, bool)), m


DIP_LINKS = 3                 # a pass into the ring's hole and straight back out within this many links is a dip


def net_crossings(cross, slot):
    """Ring crossings with dips removed: consecutive passes of opposite sign at most DIP_LINKS links apart with no
    slot crossing between (the cord touching the hole's edge, as a lying ring's plane meets it, crosses it twice)."""
    out = []
    for i, sign in cross:
        if out and out[-1][1] == -sign and i-out[-1][0] <= DIP_LINKS and not any(out[-1][0] < k <= i for k in slot):
            out.pop()
        else:
            out.append((i, sign))
    return out


def s2(scene, lay):
    slot = slot_crossings(scene.points, lay)
    ring = scene.poses["ring"]
    cross = ring_crossings(scene.points, ring, lay)
    net = net_crossings(cross, slot)
    bight = range(slot[0]+1, slot[-1]+1) if len(slot) == 2 else range(0)
    m = dict(slot_crossings=slot, ring_crossings=cross, net_ring_crossings=net, ring_off_post=not ring_on_post(ring, lay),
             ring_behind=bool(ring[0][1] > lay.post_depth_m/2),
             two_back_strands=len(net) == 2 and not any(i in bight for i, _ in net),
             bead1_in_front=bool(scene.pos("bead_left")[1] < -lay.post_depth_m/2),
             ring_at_spot=in_box(ring[0], S2_RING_BOX_M), disc1_aside=in_box(scene.pos("disc_left"), S2_DISC1_BOX_M))
    return len(slot) == 2 and all(v for k, v in m.items() if isinstance(v, bool)), m


def s3(scene, lay):
    ring = scene.poses["ring"]
    c = ring[0]
    tilt = float(np.degrees(np.arccos(abs(ring[1].apply([0., 0., 1.])[2]))))
    m = dict(ring_crossings=ring_crossings(scene.points, ring, lay), ring_off_post=not ring_on_post(ring, lay),
             ring_flat=bool(c[2] < lay.ring_tube_radius_m+.005 and tilt < 5.),
             ring_front_right=bool(c[0] >= S3_RING_MIN_X_M and c[1] <= S3_RING_MAX_Y_M),
             ring_at_spot=bool(np.linalg.norm(c[:2]-S3_RING_AT_M) < S3_RING_TOL_M))
    m["ring_free"] = not m["ring_crossings"]
    return all(v for k, v in m.items() if isinstance(v, bool)), m


def s4a(world, task):
    """The task's own goal check, restricted to the ring."""
    _, _, metrics = task.evaluate_goal_region(world, task.goal_region)
    ring = world["articulations"]["slotted_chain"]["links"]["ring"]
    m = dict(ring_inside=bool(metrics["all_target_inside"]), ring_quiet=bool(metrics["quiet"]),
             ring_speed_m_s=round(float(np.linalg.norm(ring["linear_velocity_m_s"])), 5),
             ring_spin_rad_s=round(float(np.linalg.norm(ring["angular_velocity_rad_s"])), 4))
    return m["ring_inside"] and m["ring_quiet"], m


def s4b(world, task):
    """The task's own goal check, restricted to the other parts; disc1 at its set-down target."""
    _, _, metrics = task.evaluate_goal_region(world, task.goal_region)
    disc1 = np.asarray(world["articulations"]["slotted_chain"]["links"]["disc_left"]["position_m"], float)-task.origin
    m = dict(remainder_on_system_side=bool(metrics["remainder_on_system_side"]),
             outside=[k for k, v in metrics["remainder_on_side"].items() if not v],
             disc1_at_target=in_box(disc1, S4B_DISC1_BOX_M))
    return m["remainder_on_system_side"] and m["disc1_at_target"], m


def in_box(p, box):
    """p's x and y within box's ranges ((x0, x1), (y0, y1))."""
    return bool(box[0][0] <= p[0] <= box[0][1] and box[1][0] <= p[1] <= box[1][1])
