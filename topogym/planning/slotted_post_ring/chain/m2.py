"""M2, S1 -> S2: the ring over the post top and set down behind it, bead1 left outside the ring.

Start (states.s1): disc1 parked behind the base, the ring round the post, bead1 before it. End (states.s2): the ring
off the post behind it at its set-down spot, threaded by the two back strands only (not by bead1's bight); bead1 in
front; disc1 pushed aside to the left (fixed-state tolerances in states.py).

The hand on bead1's side draws it forward over the table towards BEAD_FAR_Y_M (the cord stops it earlier) and lets go:
the front bight's legs then run long and low from the slot (draw_bead1_far). Both hands pinch the ring's left and
right sides (from outside, the fingers pointing at the post; each pinch turned up to PINCH_SEARCH_DEG off its side,
away from the chain and with room before the post) and lift it level, its centre held TWO_HAND_RING_Y_M before the
post's axis. The front tube catches the legs and draws bead1 up the post's front, outside the ring's hole; bead1 enters
the hole only once the ring is over the post top and falls through it alone (the hole never holds bead1 and the post
together). Past the post top the ring is carried behind the post over SET_DOWN_XY_M on A's side (further right if
disc1 lies there), lowered to SET_DOWN_Z_M and let go on the two back strands (lift_over). A then pushes disc1 (the
lift draws it in behind the post) towards -x, so leg 1 lies clear behind the post for M3 and disc1 stays in B's reach
for M4b (push_disc1_aside).
"""
import numpy as np

from .motion import OPEN_M, PAD_M, StageFailure, from_home, move_nj
from .parts import support_z
from .session import scene
from .states import ring_crossings

LIFT_STEP_M = .01
TOP_CLEAR_M = .015        # the ring's lowest point this far over the post top before it leaves it, and on until
OVER_LIFT_M = .15         # bead1 is drawn over its front tube (bead1_through) or the ring's centre is this far up
BEAD_DROP_STEPS = 20      # then held: bead1 falls through the hole
RING_DOWN_DEG = 35.       # a pinch's approach on the ring: towards the post, this far down
RING_OPEN_M = .028        # opening over the 20 mm tube: the lower finger stays clear of the base
RING_PINCH_UP_M = .006    # pads' centre over the tube's centre (parallel pads still close across its diameter)
RING_DEEP_M = .006        # the tube this much deeper between the fingers than the pads' middle
BEAD_TILT_DEG = 25.       # a hand's approach on bead1 leaning towards the post
BEAD_DRAW_TILT_DEG = 45.  # ... when bead1 is drawn forward (the hand stays clear of the cord)
BEAD_FAR_Y_M = -.25       # bead1 drawn to this y: farther, the legs are so long that bead1 is still under the post
                          # top when the ring goes behind, and goes over the post top with it
BEAD_DRAW_STEP_M = .04
PINCH_SEARCH_DEG = 40.    # a pinch turned at most this far off its side, in 10 deg steps, away from the chain
POST_ROOM_M = .01         # with this much room between its tube's inner side and the post for the fingertips
TWO_HAND_RING_Y_M = -.01  # the ring's centre before the post's axis while it rises
SET_DOWN_XY_M = np.r_[.15, .17]   # behind the post the ring's centre is carried here, on A's side, off the base (A
                                  # takes it there in M3; let go to the side away from disc1, which the lift draws in
                                  # behind the post, it falls out of A's reach),
RELEASE_DROP_M = .15              # this much lower than over the post top,
SET_DOWN_Z_M = .05                # then lowered 1 cm at a time to this centre height (its tube 4 cm over the table) and
                                  # let go
SET_DOWN_MAX_X_M = .18            # the spot moved right, at most to here, until the ring lies DISC1_CLEAR_M clear of
DISC1_CLEAR_M = .01               # disc1 (at 0.186 A's forearm roll jumps 2.75 rad)
DISC1_TO_X_M = -.12               # then A pushes disc1's centre to this x (the lift draws it in behind the post, next
                                  # to the ring: over leg 1's links M3 takes, and dragged on there out of B's reach in
                                  # M4b)
PUSH_GAP_M = .008                 # A's closed fingertips come down this far off disc1's +x rim; their footprint
FOOTPRINT_M = np.r_[.012, .01]    # (half extent along the push, across it) must lie PUSH_CLEAR_M clear of the ring's
PUSH_CLEAR_M = .005               # tube (the lift draws disc1 in next to the ring, 2-18 mm apart), else A
RING_PUSH_M = .05                 # first pushes the ring off, at most this far (its fingertips in its hole);
PUSH_STEP_M = .01                 # each push 1 cm at a time


def take_bead(H, hand, away=None, lift_m=.05, tilt_deg=BEAD_TILT_DEG, at_post=False):
    """Pads on bead1's sides across its bore (not on the bore's ends, where the cord comes out), the approach leaning
    BEAD_TILT_DEG along the bore: towards the post when the bore runs mostly along y (the gripper's wide base, above
    the fingers, then stays clear of the post's front face), else away from the hand's arm. at_post: bead1 against
    the post's front, the pads on its left and right whatever its bore (no finger fits between it and the post), the
    approach leaning towards the post (away: the camera mount's side, else the IK's choice)."""
    b, rot = scene(H.session).poses["bead_left"]
    bore = np.array([0., 1., 0.]) if at_post else rot.apply([0., 0., 1.])*[1., 1., 0.]
    bore = bore/np.linalg.norm(bore) if np.linalg.norm(bore) > .3 else np.array([0., 1., 0.])
    closing = np.cross([0., 0., 1.], bore)
    lean = bore*(np.sign(bore[1]) if abs(bore[1]) >= abs(bore[0]) else np.sign(bore[0])*(1. if hand == "B" else -1.))
    t = np.radians(tilt_deg)
    approach = np.sin(t)*lean+np.cos(t)*np.array([0., 0., -1.])
    q = H.quat(hand, approach, closing) if away is None else H.quat_away(hand, approach, closing, away)
    H.grip(hand, OPEN_M)
    from_home(H, hand, b-approach*(PAD_M+.06), q)
    H.reach(hand, b-approach*PAD_M, q, linear=3)
    H.close(hand)
    if lift_m:              # on its joint line (B's forearm roll and wrist rotation near in line: an IK jump)
        move_nj(H, hand, b-approach*PAD_M+[0., 0., lift_m], q, linear=2)
        if scene(H.session).pos("bead_left")[2] < b[2]+.6*lift_m:
            raise StageFailure("bead1 not lifted")
    return q, approach


def draw_bead1_far(H):
    hand = "B" if scene(H.session).pos("bead_left")[0] < 0 else "A"
    q, _ = take_bead(H, hand, tilt_deg=BEAD_DRAW_TILT_DEG)
    b = scene(H.session).pos("bead_left")
    try:
        for y in np.arange(b[1]-BEAD_DRAW_STEP_M, BEAD_FAR_Y_M-.001, -BEAD_DRAW_STEP_M):
            H.place(hand, "bead_left", np.r_[b[0], y, .09], q, tries=1)
        H.place(hand, "bead_left", np.r_[b[0], BEAD_FAR_Y_M, H.layout.bead_radius_m+.004], q, linear=2, tries=1)
    except StageFailure as exc:                       # the cord at its length: let go where bead1 is
        H.note("bead1 held back by the cord", error=str(exc)[:200])
    H.grip(hand, OPEN_M)
    H.hold(10)
    H.go_home(hand, up_m=.06)
    H.hold(40)
    H.note("bead1 drawn far", bead1=scene(H.session).pos("bead_left").round(3).tolist())


def clear_angle(H, angle_deg):
    """The pinch angle within PINCH_SEARCH_DEG of angle_deg farthest from the chain (at the tube's centre), of those
    whose tube leaves the fingertips POST_ROOM_M before the post (a ring pushed against the post leaves 2 mm at
    180 deg); if none does, the one with the most room."""
    lay = H.layout
    s = scene(H.session)
    c, _ = s.poses["ring"]

    def clearance(a):
        p = c+lay.ring_major_radius_m*np.r_[np.cos(np.radians(a)), np.sin(np.radians(a)), 0.]
        return float(np.linalg.norm(s.points-p, axis=1).min())

    def room(a):                                   # the tube's inner side to the post's footprint
        inner = c[:2]+(lay.ring_major_radius_m-lay.ring_tube_radius_m)*np.r_[np.cos(np.radians(a)), np.sin(np.radians(a))]
        return float(np.linalg.norm(np.maximum(np.abs(inner)-[lay.post_width_m/2, lay.post_depth_m/2], 0.)))
    angles = angle_deg+np.arange(-PINCH_SEARCH_DEG, PINCH_SEARCH_DEG+1., 10.)
    roomy = [a for a in angles if room(a) >= POST_ROOM_M]
    return float(max(roomy, key=clearance) if roomy else max(angles, key=room))


def pinch_ring(H, hand, angle_deg):
    """A pinch across the ring's tube at angle_deg from outside: the approach towards the ring's centre and
    RING_DOWN_DEG down, the pads closing inwards-up across the tube (opened RING_OPEN_M)."""
    lay = H.layout
    c, _ = scene(H.session).poses["ring"]
    inward = -np.array([np.cos(np.radians(angle_deg)), np.sin(np.radians(angle_deg)), 0.])
    t = np.radians(RING_DOWN_DEG)
    approach = np.cos(t)*inward+np.sin(t)*np.array([0., 0., -1.])
    closing = np.sin(t)*inward+np.cos(t)*np.array([0., 0., 1.])
    q = H.quat(hand, approach, closing)
    p = c-lay.ring_major_radius_m*inward+[0., 0., RING_PINCH_UP_M]
    H.grip(hand, RING_OPEN_M)
    from_home(H, hand, p-approach*(PAD_M+.06), q)
    H.reach(hand, p-approach*(PAD_M-RING_DEEP_M), q, linear=3)
    return q


def lowest_ring_z(ring, lay):
    c, r = ring
    n = r.apply([0., 0., 1.])
    return c[2]-np.sqrt(max(0., 1.-n[2]**2))*lay.ring_major_radius_m-lay.ring_tube_radius_m


def bead1_through(H):
    """bead1 drawn over the ring's front tube into its hole (inside the hole's radius): it falls through alone."""
    s = scene(H.session)
    c, rot = s.poses["ring"]
    n = rot.apply([0., 0., 1.])
    d = s.pos("bead_left")-c
    return bool(np.linalg.norm(d-(d @ n)*n) < H.layout.ring_inner_radius)


def lift_over(H):
    lay = H.layout
    top = lay.base_height_m+lay.post_height_m
    qb = pinch_ring(H, "B", clear_angle(H, 180.))
    qa = pinch_ring(H, "A", clear_angle(H, 0.))
    H.close("B")
    H.close("A")
    H.note("ring taken by both hands", widths=[H.width("B"), H.width("A")])
    target = {hand: H.tcp(hand)[0] for hand in ("B", "A")}      # accumulated: the hands lag under the cord's drag
    for _ in range(int(.5/LIFT_STEP_M)):
        c, _ = scene(H.session).poses["ring"]
        shift = np.r_[-c[0], TWO_HAND_RING_Y_M-c[1], LIFT_STEP_M]
        for hand, q in (("B", qb), ("A", qa)):
            target[hand] = np.r_[H.tcp(hand)[0][:2]+shift[:2], target[hand][2]+LIFT_STEP_M]
            H.move(hand, target[hand], q)
        ring = scene(H.session).poses["ring"]
        tilt = float(np.degrees(np.arccos(abs(ring[1].apply([0., 0., 1.])[2]))))
        H.note("lift", ring=ring[0].round(3).tolist(), tilt_deg=round(tilt, 1), widths=[H.width("B"), H.width("A")],
               bead1=scene(H.session).pos("bead_left").round(3).tolist())
        if min(H.width("B"), H.width("A")) < .012:
            raise StageFailure(f"the ring slipped out at {ring[0].round(3).tolist()}")
        if lowest_ring_z(ring, lay) > top+TOP_CLEAR_M and (bead1_through(H) or ring[0][2] > top+OVER_LIFT_M):
            break
    else:
        raise StageFailure(f"ring not above the post top: {scene(H.session).pos('ring').round(3).tolist()}")
    H.hold(BEAD_DROP_STEPS)
    s = scene(H.session)
    H.note("ring over the post top", ring=s.pos("ring").round(3).tolist(), bead1=s.pos("bead_left").round(3).tolist(),
           crossings=ring_crossings(s.points, s.poses["ring"], lay))
    goal_y = lay.post_depth_m/2+lay.ring_major_radius_m+.01
    target = {hand: H.tcp(hand)[0] for hand in ("B", "A")}
    for _ in range(12):                        # 1 cm at a time; the hands lag under the cord's drag
        if scene(H.session).pos("ring")[1] >= goal_y:
            break
        for hand, q in (("B", qb), ("A", qa)):
            target[hand] = target[hand]+[0., .01, 0.]
            try:
                H.move(hand, target[hand], q)
            except StageFailure:
                pass
    ring = scene(H.session).pos("ring")
    if ring[1] < lay.post_depth_m/2+lay.ring_major_radius_m-.01:
        raise StageFailure(f"the ring not behind the post: {ring.round(3).tolist()}")
    s = scene(H.session)
    spot, d1 = SET_DOWN_XY_M.copy(), s.pos("disc_left")[:2]
    clear = lay.ring_major_radius_m+lay.ring_tube_radius_m+lay.disc_radius_m+DISC1_CLEAR_M
    if np.linalg.norm(spot-d1) < clear:      # disc1 under the spot: moved right until clear
        spot[0] = min(SET_DOWN_MAX_X_M, d1[0]+np.sqrt(max(0., clear**2-(spot[1]-d1[1])**2)))
    shift = np.r_[spot-s.pos("ring")[:2], -RELEASE_DROP_M]
    for _ in range(5):
        for hand, q in (("B", qb), ("A", qa)):
            target[hand] = target[hand]+shift/5
            try:
                H.move(hand, target[hand], q)
            except StageFailure:            # lagging under the cord's drag
                pass
    for _ in range(30):                     # down 1 cm at a time, the centre kept over the spot
        c = scene(H.session).pos("ring")
        if c[2] < SET_DOWN_Z_M+.005:
            break
        step = np.r_[np.clip(spot-c[:2], -.01, .01), max(-.01, SET_DOWN_Z_M-c[2])]
        for hand, q in (("B", qb), ("A", qa)):
            try:
                H.move(hand, H.tcp(hand)[0]+step, q)
            except StageFailure as exc:     # lagging under the cord's drag, or a finger on the strands
                H.note("set-down lagging", hand=hand, why=str(exc)[:300])
    H.note("ring to its release", ring=scene(H.session).pos("ring").round(3).tolist(), spot=spot.round(3).tolist(),
           disc1=scene(H.session).pos("disc_left").round(3).tolist())
    H.grip("B", OPEN_M)
    H.grip("A", OPEN_M)
    H.hold(20)
    H.note("ring let go behind the post", ring=scene(H.session).pos("ring").round(3).tolist())
    H.go_home("A", up_m=.05)
    H.go_home("B", up_m=.05)


def ring_clearance(H, c):
    """Top view: the gap between the ring's tube and A's closed fingers' footprint PUSH_GAP_M off disc1's +x rim (disc1
    at c), less the tube's radius."""
    lay = H.layout
    rc, rr = scene(H.session).poses["ring"]
    th = np.linspace(0., 2*np.pi, 72, endpoint=False)
    ring = (rc+rr.apply(lay.ring_major_radius_m*np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)])))[:, :2]
    p = c[:2]+[lay.disc_radius_m+FOOTPRINT_M[0]+PUSH_GAP_M, 0.]
    return float(np.linalg.norm(np.maximum(np.abs(ring-p)-FOOTPRINT_M, 0.), axis=1).min())-lay.ring_tube_radius_m


def fingertips_push(H, start, direction, done, max_m, label, width=0.):
    """A's fingertips (closing across `direction`; closed, or open `width`) down at `start` (the TCP), then moved along
    `direction` 1 cm at a time (at most max_m) until done() is true or None (stop); up 6 cm and home. A comes from
    home."""
    q = H.quat_away("A", [0., 0., -1.], np.cross([0., 0., 1.], direction), [0., 1., 0.])
    if width:
        H.grip("A", width)
    else:
        H.close("A")
    from_home(H, "A", H.tcp("A")[0], q)               # turned at home by the joints (route() would turn it by move())
    H.route("A", start+[0., 0., .06], q, z_m=start[2]+.06)
    try:
        H.move("A", start, q, linear=2)
    except StageFailure as exc:                       # on a link: pushed from there
        H.note(f"{label}: fingertips held up", why=str(exc)[:200])
    target = start
    for _ in range(int(round(max_m/PUSH_STEP_M))):
        if done() in (True, None):
            break
        target = target+direction*PUSH_STEP_M
        try:
            H.move("A", target, q)
        except StageFailure as exc:
            H.note(f"{label} stopped", why=str(exc)[:300])
            break
    try:
        H.move("A", H.tcp("A")[0]+[0., 0., .06], q)
    except StageFailure:
        pass
    H.go_home("A")


def push_disc1_aside(H):
    """The ring set down and both hands free, A pushes disc1 towards -x, away from behind the post (what is in the way
    first): its closed fingertips (fingertips_push) PUSH_GAP_M off disc1's +x rim, 3 mm over what lies under them,
    until its centre is at DISC1_TO_X_M (or the fingers pass over it). If the ring lies there (ring_clearance), A first
    pushes it off, away from disc1, its open fingers in its hole against the tube's far side (open: a closed hand
    touching the ring welds it, the grasp assist, and takes it along)."""
    lay = H.layout
    s = scene(H.session)
    c = s.pos("disc_left")
    if c[0] <= DISC1_TO_X_M:
        return
    if ring_clearance(H, c) < PUSH_CLEAR_M:
        rc = s.pos("ring")
        v = np.r_[(rc-c)[:2], 0.]
        v /= np.linalg.norm(v)
        across = OPEN_M/2+FOOTPRINT_M[1]                              # the open fingers' outer faces off the middle
        start = rc+v*(np.sqrt(lay.ring_inner_radius**2-across**2)-FOOTPRINT_M[0]-.004)
        start[2] = max(rc[2]-.006, support_z(lay, start)+.003)+.016    # the TCP: the fingertips 16 mm past it
        H.note("ring pushed off disc1", clearance_mm=round(ring_clearance(H, c)*1e3, 1), ring=rc.round(3).tolist())
        fingertips_push(H, start, v, lambda: ring_clearance(H, c) > PUSH_CLEAR_M, RING_PUSH_M+.004, "ring push",
                        width=OPEN_M)
        H.note("ring pushed", clearance_mm=round(ring_clearance(H, c)*1e3, 1),
               ring=scene(H.session).pos("ring").round(3).tolist())
    c = scene(H.session).pos("disc_left")
    reach = lay.disc_radius_m+FOOTPRINT_M[0]+PUSH_GAP_M
    start = c+[reach, 0., 0.]
    start[2] = support_z(lay, start)+.003+.016

    def done():
        d = scene(H.session).pos("disc_left")
        if H.tcp("A")[0][0]-reach < d[0]-PUSH_GAP_M-.02:               # the fingers over disc1: it stays behind
            return None
        return d[0] <= DISC1_TO_X_M
    fingertips_push(H, start, np.r_[-1., 0., 0.], done, c[0]-DISC1_TO_X_M+PUSH_GAP_M+.02, "disc1 push")
    H.note("disc1 pushed aside", disc1=scene(H.session).pos("disc_left").round(3).tolist(),
           ring=scene(H.session).pos("ring").round(3).tolist())


def m2(H):
    draw_bead1_far(H)
    lift_over(H)
    push_disc1_aside(H)
