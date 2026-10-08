"""M3, S2 -> S3: the ring back through the slot to the front and off the bight at bead1.

Start (states.s2): the ring behind the post at its set-down spot, threaded by the two back strands; bead1 in front.
End (states.s3): the ring free of the chain, lying flat front right at RING_DOWN_XY_M (clear of bead1's way forward
in M4b).

With the grasp assist (contact_weld_v1: a closed hand welds the ring; the weld passes to the other closed hand when
the first opens): A takes the ring by a face grip from above and turns it edge-on about the pads (take_ring_edge_on),
pushes it in on the right rail and onto the left one (push_ring_in); B takes its back (b_rear_take), A takes its face
(a_face_take) and B lets go (b_off_ring). Then (m3_tail): B pulls leg 1 back behind the post until its part of the
bight is short (m3_leg.pre_pull); A carries the ring out, B takes leg 1 behind the post from above and lifts it off the
base (m3_leg.pin_leg1), A turns the ring about the vertical (a_turn: bead1 then fits through the hole across the legs'
pull) and carries it on along -y; B pulls leg 1 if it is still threaded (m3_leg.pull_off); A sets the ring down front
right (ring_down_front_right).
"""
import numpy as np

from .m3_leg import pin_leg1, pre_pull, pull_off
from .motion import ARMS, IK_REACH_M, JUMP_RAD, OPEN_M, PAD_M, StageFailure, back_off, move_nj, route_nj
from .session import scene
from .states import ring_crossings

TAKE_AT_DEG = 30               # A takes the ring lying behind the post at its tube point this far from +x towards +y
                               # (the chain >= 7 cm from the fingers; at -x a link touches the inner finger: no weld)
GRIP_TILT_DEG = -5             # A's pinch turned this far about the tube's tangent (the approach at the push then 5 deg
                               # off -x towards -y): the swing leaves A's wrist in its flipped branch, where the push's
                               # end needs wrist rotation -3.14 untilted (its limit: a 3.13 rad IK jump drops the ring),
                               # -3.04 at -5 deg; at -10 B's rear take meets A's finger
SWING_PADS_M = np.r_[.04, .12, .19]    # A's pads here while it turns the welded ring (121 deg): IK, clearance, the
                                       # ring's lowest point >= 4.5 cm up
GRIP_BACK_DEG = 75             # turned edge-on, A's grip this far from the ring's top towards its back: A alone pushes
                               # it onto the slot's bottom, its fingers >= 4.7 mm off the post (80-85: B's rear take
                               # meets A's fingers)
TURN_STEP_DEG = 15             # A's turns in steps this large (30 deg of wrist is an IK jump)
RAIL_GAP_M = .0005             # the tube off a rail: 7.5 mm left on the other side for the 7 mm cord
ALIGN_DEG = 2.                 # the ring's axis this close to x before it goes into the slot (the tube has 4 mm
                               # beside it there: 7 deg off, its front arc meets the post's back face)
PASS_RAISE_M = .005            # the welded ring pushed in this much over rails()' passing height: at that height it
                               # jams on the cord on the slot's bottom and the weld breaks
PUSH_TO_Y_M = -.01             # the ring's centre pushed this far past the post's mid-plane (over the slot's bottom)
REAR_GRIP_DOWN_DEG = 20        # B takes the ring's back from behind this far down (no level grip there),
REAR_AT_DEG = 45               # at its tube this far below its centre's level
REAR_TURN_AT_M = np.r_[-.15, -.05, .30]   # B turns to that grip here, over the front left, in this many equal
REAR_TURN_STEPS = 12                      # steps (turned lower its wrist flips: the joint line dips under the table)
FACE_TAKE_DEG = 60             # A's face grip on the ring in the slot, this far from its top towards the front
FACE_GRIPS = ((FACE_TAKE_DEG, 1., False), (FACE_TAKE_DEG, 1., True), (45, 1., False), (75, 1., False))
                               # A's face grips in order (deg from the top, closing sign, approach along -x instead of
                               # the ring's axis; a_face_take). The easy ring yawed 7.5 deg in B's grip leaves A's wrist
                               # rotation at its limit on the carry out at 60 deg along its axis (a 3.1 rad IK jump
                               # turns the ring); the closing sign flipped meets B's hand
TURN_AT_Y_M = -.10             # A carries the ring out to this centre y, turns it TURN_DEG about the vertical through
TURN_DEG = 45                  # its centre and carries it on; bead1 (39 mm + 10) then fits the hole's width across the
                               # legs' pull, 102 mm cos(45 deg) = 72 mm
CARRY_OUT_Z_M = .17            # A's TCP height while it carries the ring out (its lowest point ~4 cm over the table)
CARRY_OUT_M = .25              # carried out at most this far (A reaches TCP y ~ -0.28 there)
CARRY_PAST_M = .04             # and on this far once the cord no longer passes its hole
RING_TIP_XY_M = np.r_[.16, -.20]    # A's face grip turned 45 deg tips the ring flat over here
RING_DOWN_XY_M = np.r_[.20, -.20]   # and lays it here, front right (S3), clear of the cord (x <~ 0.06), bead2 and
                                    # disc2 (lying at (0.07, -0.26), r 5.5 cm: at (0.16, -0.25) the ring rests on it)


def ring_frame(H):
    """(centre, unit axis along +-x nearest) of the ring."""
    c, r = scene(H.session).poses["ring"]
    a = r.apply([0., 0., 1.])
    return c, a if a[0] >= 0 else -a


def ring_top_front(axis):
    """Unit vectors in the ring's plane towards its top and towards the front (-y)."""
    top = np.r_[0., 0., 1.]-axis[2]*axis
    top /= np.linalg.norm(top)
    front = np.cross(axis, top)
    return top, front if front[1] < 0 else -front


def rails(lay):
    """(the ring's centre x on the right rail (centred where the cord passes on either side), its centre height
    passing the slot, its centre y behind the slot)."""
    outer = lay.ring_major_radius_m+lay.ring_tube_radius_m
    free = lay.slot_width_m/2-lay.ring_tube_radius_m           # beside the tube with the ring centred
    rail = 0. if free > 2*lay.rope_radius_m+.002 else lay.slot_width_m/2-lay.ring_tube_radius_m-RAIL_GAP_M
    return rail, lay.slot_bottom_m+outer+2*lay.rope_radius_m, lay.post_depth_m/2+outer+.02


def pinch(H, hand, point, approach, closing, *, away=None, stand_off=.06):
    """`hand`'s pads at `point` (the tube's centre), coming in along `approach`, closing along `closing` (its sign as
    given, or the one that puts the camera mount on `away`'s side); checks the tube is between the fingers."""
    q = H.quat(hand, approach, closing) if away is None else H.quat_away(hand, approach, closing, away)
    a = np.asarray(approach, float)/np.linalg.norm(approach)
    H.grip(hand, OPEN_M)
    start = point-a*(PAD_M+stand_off)
    route_nj(H, hand, start, q, z_m=start[2])       # round the post's side when the way crosses its plane
    H.reach(hand, point-a*PAD_M, q, linear=3)
    H.close(hand)
    if H.width(hand) < 2*H.layout.ring_tube_radius_m-.005:
        raise StageFailure(f"{hand} did not take the ring's tube: width {H.width(hand)}")
    return q


def turn_about_pads(H, q_new):
    """A turned to q_new about its pads' middle (what it holds stays where it is)."""
    from scipy.spatial.transform import Rotation as R
    p, q = H.tcp("A")
    pads = p+R.from_quat(q[[1, 2, 3, 0]]).apply(H.session.robot.axes["right"][0])*PAD_M
    move_nj(H, "A", pads-R.from_quat(q_new[[1, 2, 3, 0]]).apply(H.session.robot.axes["right"][0])*PAD_M, q_new)


def ring_to(H, q, target, label):
    """The ring's centre to `target`, x within 1 mm (A moved by the measured error); False if A is stopped."""
    try:
        for _ in range(3):
            e = target-ring_frame(H)[0]
            if abs(e[0]) < .001 and np.linalg.norm(e) < .004:
                return True
            H.move("A", H.tcp("A")[0]+e, q, settle=6)
    except StageFailure as exc:
        H.note(f"{label} stopped", at=np.round(target, 3).tolist(), why=str(exc)[:600], contacts=H.contacts("ring")[:6])
        return False
    return True


def take_ring_edge_on(H):
    """A takes the ring (lying behind the post) TAKE_AT_DEG from its +x side towards the back from above, the pads
    across its tube (closing along its radius, towards the centre: one finger in the hole; turned GRIP_TILT_DEG about
    the tube's tangent). Welded there it does not swing edge-on by itself, so A lifts it to SWING_PADS_M and turns
    about the pads until the ring's axis is along x and the grip GRIP_BACK_DEG from its top towards the back (A's
    approach then -x: from the right). Returns A's rotation."""
    from scipy.spatial.transform import Rotation as R, Slerp
    lay = H.layout
    c, r = scene(H.session).poses["ring"]
    n = r.apply([0., 0., 1.])
    n = n if n[2] > 0 else -n
    t = np.radians(TAKE_AT_DEG)
    u = np.r_[np.cos(t), np.sin(t), 0.]-(np.r_[np.cos(t), np.sin(t), 0.] @ n)*n
    u /= np.linalg.norm(u)
    grasp = c+lay.ring_major_radius_m*u
    lean = R.from_rotvec(np.cross(u, n)*np.radians(GRIP_TILT_DEG))   # about the tube's tangent
    q = (lean*R.from_quat(H.quat("A", -n, -u)[[1, 2, 3, 0]])).as_quat()[[3, 0, 1, 2]]   # this closing sign keeps the
    a = lean.apply(-n)                                    # push in reach (the other: 13 mm short); A's approach
    stand_off = grasp-a*(PAD_M+.06)
    H.grip("A", OPEN_M)
    route_nj(H, "A", stand_off, q, z_m=stand_off[2])
    H.reach("A", grasp-a*PAD_M, q, linear=4)
    H.close("A")
    H.note("ring taken", width=H.width("A"), ring=c.round(3).tolist())
    if H.width("A") < 2*lay.ring_tube_radius_m-.005:
        raise StageFailure(f"A did not take the ring's tube: width {H.width('A')}")
    H.move("A", H.tcp("A")[0]+n*.04, q, linear=2)                   # off the base
    H.move("A", SWING_PADS_M-a*PAD_M, q, linear=4)
    r0 = R.from_quat(q[[1, 2, 3, 0]])
    b = np.radians(GRIP_BACK_DEG)
    turn = R.align_vectors([[1., 0., 0.], [0., np.sin(b), np.cos(b)]], [n, u])[0]   # its axis to x, the grip up its back
    swing = Slerp([0., 1.], R.from_quat([r0.as_quat(), (turn*r0).as_quat()]))
    for f in np.linspace(0., 1., int(np.ceil(np.degrees(turn.magnitude())/TURN_STEP_DEG))+1)[1:]:
        turn_about_pads(H, swing(f).as_quat()[[3, 0, 1, 2]])
    c, axis = ring_frame(H)
    H.note("ring swung edge-on", ring=c.round(3).tolist(), axis=axis.round(2).tolist(),
           centre_from_tcp=(c-H.tcp("A")[0]).round(3).tolist())
    return (turn*r0).as_quat()[[3, 0, 1, 2]]


def axis_along_x(H, q):
    """A turns the welded ring about its centre until its axis is along x (within ALIGN_DEG); returns A's rotation."""
    from scipy.spatial.transform import Rotation as R
    c, axis = ring_frame(H)
    if np.degrees(np.arccos(min(1., axis[0]))) < ALIGN_DEG:
        return q
    fix = R.align_vectors([[1., 0., 0.]], [axis])[0]
    q = (fix*R.from_quat(q[[1, 2, 3, 0]])).as_quat()[[3, 0, 1, 2]]
    H.move("A", c+fix.apply(H.tcp("A")[0]-c), q, settle=6)
    return q


def push_ring_in(H, q):
    """A sets the welded ring behind the slot on the right rail, PASS_RAISE_M over the passing height, pushes it in to
    PUSH_TO_Y_M 1 cm at a time, its axis kept along x, and moves it onto the left rail. Returns A's rotation."""
    lay = H.layout
    rail, z, behind = rails(lay)
    z += PASS_RAISE_M
    q = axis_along_x(H, q)
    H.place("A", "ring", np.r_[rail, behind, z], q, linear=4)
    for y in np.arange(behind-.01, PUSH_TO_Y_M-.001, -.01):
        q = axis_along_x(H, q)
        if not ring_to(H, q, np.r_[rail, y, z], "push"):
            break
    ring_to(H, q, np.r_[-rail, PUSH_TO_Y_M, z], "onto the left rail")
    s = scene(H.session)
    c, axis = ring_frame(H)
    H.note("ring pushed in", ring=c.round(3).tolist(), axis=axis.round(2).tolist(), tcp=H.tcp("A")[0].round(3).tolist(),
           crossings=ring_crossings(s.points, s.poses["ring"], lay), welded=H.session.object_in_hand("right"))
    return q


def b_rear_take(H):
    """B takes the ring's tube REAR_AT_DEG down its back (approach REAR_GRIP_DOWN_DEG down from behind, across the tube),
    coming down in front and round the post's left side low (A's hand is over the ring behind the post); A lets go and
    backs off: the grasp assist's weld passes to B. Returns B's rotation."""
    r = H.layout.ring_major_radius_m
    c, _ = ring_frame(H)
    t = np.radians(REAR_GRIP_DOWN_DEG)
    a = np.array([0., -np.cos(t), -np.sin(t)])
    low = c+r*np.r_[0., np.cos(np.radians(REAR_AT_DEG)), -np.sin(np.radians(REAR_AT_DEG))]   # down its back: under A's hand
    from scipy.spatial.transform import Rotation as R, Slerp
    qb = H.quat_away("B", a, [1., 0., 0.], [0., 0., -1.])     # camera mount down: A's is up behind
    q0 = H.tcp("B")[1]
    H.move("B", REAR_TURN_AT_M, q0)
    turn = Slerp([0., 1.], R.from_quat([q0[[1, 2, 3, 0]], qb[[1, 2, 3, 0]]]))
    for f in np.arange(1, REAR_TURN_STEPS+1)/REAR_TURN_STEPS:
        H.move("B", REAR_TURN_AT_M, turn(f).as_quat()[[3, 0, 1, 2]], settle=0)
    H.move("B", np.r_[-.15, -.05, .12], qb, linear=3)    # down in front, then round the post's left side, low:
    route_nj(H, "B", np.r_[-.05, .12, .1], qb, z_m=.1)      # A's hand is over the ring behind the post
    qb = pinch(H, "B", low, a, [1., 0., 0.], away=[0., 0., -1.], stand_off=.02)
    back_off(H, "A")
    c, axis = ring_frame(H)
    H.note("ring in B's grip", ring=c.round(3).tolist(), axis=axis.round(2).tolist(), width=H.width("B"))
    return qb


def a_face_take(H):
    """A goes round the post's right side and takes the ring (held by B) by a face grip from its right: approach
    along -x (the axis), closing along the radius (one finger in the hole). A keeps this grip to the end: it turns
    the ring and still carries it on. The grip is the first of FACE_GRIPS that, taken, has an IK chain through A's
    hold without a jump (face_chain, from A's joints with it): a grip that would jump is let go again, one that stops
    short (the ring sagging in B's grip, a finger on the post) backed off from."""
    for deg, sign, level in FACE_GRIPS:
        c, axis = ring_frame(H)
        a, u, point = face_grip(H, c, axis, deg, level)
        try:
            qa = pinch(H, "A", point, -a, sign*u)
        except StageFailure as exc:
            H.note("face grip stopped", deg=deg, sign=sign, level=level, why=str(exc)[:160])
            back_off(H, "A", .05)
            H.go_home("A")                         # the next grip approached from home as the first (no IK jump)
            continue
        held, reached = face_chain(H, qa, H.tcp("A")[0], ring_frame(H)[0])
        if held:
            H.note("ring taken by its face", deg=deg, sign=sign, level=level, ring=c.round(3).tolist(),
                   width=H.width("A"), poses_in_reach=reached)
            return qa
        H.note("face grip would jump", deg=deg, sign=sign, level=level, poses_in_reach=reached)
        back_off(H, "A", .05)
        H.go_home("A")
    raise StageFailure("no face grip holds the ring through the carry without an IK jump")


def face_grip(H, c, axis, deg, level):
    """A face grip deg from the ring's top towards the front: (the axis approached along: the ring's, or -x if
    `level`; the closing; the pads' point on the tube's centre)."""
    top, front = ring_top_front(axis)
    t = np.radians(deg)
    u = np.cos(t)*top+np.sin(t)*front
    a = np.r_[np.sign(axis[0]), 0., 0.] if level else axis
    u = u-(u @ a)*a
    u /= np.linalg.norm(u)
    return a, u, c+H.layout.ring_major_radius_m*u


def face_chain(H, q, tcp, c):
    """A's IK chain (each pose seeded at the solution before, as move_ee's are; the first at A's joints) through its
    hold of the ring from the face grip (TCP tcp, rotation q; c the ring's centre): carried out to TURN_AT_Y_M, turned
    TURN_DEG in steps, carried on CARRY_OUT_M. Returns (no IK jump through the turn and none on the carry on as far as
    it is in reach, poses in reach)."""
    from scipy.spatial.transform import Rotation as R
    rb = H.session.robot
    frame = rb.tcp_frames[ARMS["A"]]
    sl = [rb.arm_joints.index(n) for n in rb.groups[ARMS["A"]].arm_joints]
    out = max(0., c[1]-TURN_AT_Y_M)
    poses = [(tcp+[0., -.01*k, 0.], q) for k in range(int(round(out/.01))+1)]
    p, c = poses[-1][0], c+[0., -out, 0.]
    r0 = R.from_quat(q[[1, 2, 3, 0]])
    n = int(np.ceil(TURN_DEG/TURN_STEP_DEG))
    for deg in TURN_DEG*np.arange(1, n+1)/n:
        t = R.from_euler("z", -deg, degrees=True)
        poses.append((c+t.apply(p-c), (t*r0).as_quat()[[3, 0, 1, 2]]))
    turned = len(poses)
    poses += [(poses[-1][0]+[0., -.01*k, 0.], poses[-1][1]) for k in range(1, int(round(CARRY_OUT_M/.01))+1)]
    seed = np.asarray(rb.arm_q(), float)
    for k, (p, q) in enumerate(poses):
        nq, err = rb.ik({frame: np.r_[p+H.origin, q]}, seed, 1e-4, 1e-3, 200)
        if k and np.abs(nq[sl]-seed[sl]).max() > JUMP_RAD:
            return False, k
        if err[frame][0] > IK_REACH_M:
            return k >= turned, k
        seed = nq
    return True, len(poses)


def b_off_ring(H, qb):
    H.grip("B", OPEN_M)
    H.hold(4)
    t = np.radians(REAR_GRIP_DOWN_DEG)
    H.move("B", H.tcp("B")[0]+.04*np.r_[0., np.cos(t), np.sin(t)], qb, settle=2)   # back off the tube


def a_turn(H, qa, turn_deg=TURN_DEG):
    """A turns the ring (welded in its face grip) turn_deg about the vertical through its centre, R_z(-turn_deg) in
    equal steps of at most TURN_STEP_DEG: the bight's side (+x) swings towards -y, the legs' pull along -y then turn_deg
    off the hole's plane. Returns A's rotation."""
    from scipy.spatial.transform import Rotation as R
    lay = H.layout
    c = ring_frame(H)[0]
    p0 = H.tcp("A")[0]
    r0 = R.from_quat(qa[[1, 2, 3, 0]])
    n = int(np.ceil(turn_deg/TURN_STEP_DEG))
    for deg in turn_deg*np.arange(1, n+1)/n:
        t = R.from_euler("z", -deg, degrees=True)
        qa = (t*r0).as_quat()[[3, 0, 1, 2]]
        H.move("A", c+t.apply(p0-c), qa)
        s = scene(H.session)
        ring = s.poses["ring"]
        H.note("turned", deg=round(float(deg), 1), ring=ring[0].round(3).tolist(), axis=ring[1].apply([0., 0., 1.]).round(2).tolist(),
               crossings=ring_crossings(s.points, ring, lay), bead1=s.pos("bead_left").round(3).tolist())
    return qa


def carry_out(H, qa, out_m=CARRY_OUT_M, z_m=CARRY_OUT_Z_M):
    """A carries the ring straight out before the post 1 cm at a time (TCP at z_m), at most out_m: with leg 1 held
    behind the post, the bight slides round its tube and bead1 comes through its hole; on CARRY_PAST_M once no cord
    passes it. True if none does."""
    lay = H.layout
    target = H.tcp("A")[0]
    clear = None
    for k in range(int(round(out_m/.01))):
        target = np.r_[target[0], target[1]-.01, target[2]+np.clip(z_m-target[2], -.01, .01)]
        try:
            H.move("A", target, qa, settle=4)
        except StageFailure as exc:
            H.note("carry stopped", why=str(exc)[:200])
            break
        s = scene(H.session)
        cross = ring_crossings(s.points, s.poses["ring"], lay)
        c = s.pos("ring")
        if k % 3 == 0 or not cross:
            H.note("carrying", ring=c.round(3).tolist(), crossings=cross, bead1=s.pos("bead_left").round(3).tolist(),
                   width=H.width("A"))
        if not cross and clear is None:
            clear = k
        if clear is not None and k-clear >= CARRY_PAST_M/.01:
            break
    return clear is not None


def ring_down_front_right(H, qa):
    """A carries the ring (held edge-on by its face) to RING_TIP_XY_M, tips it flat about its centre, its top away from
    A's hand, lays it at RING_DOWN_XY_M 1 cm over the table and lets go upwards. (Let go upright it topples: onto the
    cord, or onto A's withdrawing fingers, one of which is in its hole, and goes up with them.)"""
    from scipy.spatial.transform import Rotation as R
    lay = H.layout
    c, _ = ring_frame(H)
    move_nj(H, "A", H.tcp("A")[0]+np.r_[RING_TIP_XY_M-c[:2], 0.], qa, linear=5)
    c, _ = ring_frame(H)
    p = H.tcp("A")[0]
    r0 = R.from_quat(qa[[1, 2, 3, 0]])
    a = r0.apply(H.session.robot.axes[ARMS["A"]][0])
    d = np.r_[a[:2], 0.]/np.linalg.norm(a[:2])                 # away from the hand, along the ring's axis
    for deg in range(TURN_STEP_DEG, 91, TURN_STEP_DEG):
        k = R.from_rotvec(np.cross([0., 0., 1.], d)*np.radians(deg))
        qa = (k*r0).as_quat()[[3, 0, 1, 2]]
        move_nj(H, "A", c+k.apply(p-c), qa)
    c, axis = ring_frame(H)
    H.note("ring tipped flat", ring=c.round(3).tolist(), axis=axis.round(2).tolist())
    move_nj(H, "A", H.tcp("A")[0]+np.r_[RING_DOWN_XY_M-c[:2], lay.ring_tube_radius_m+.01-c[2]], qa, linear=4)
    back_off(H, "A")                   # straight up out of the hole
    H.go_home("A", up_m=.1)
    H.hold(40)
    c, axis = ring_frame(H)
    H.note("ring laid down", ring=c.round(3).tolist(), axis=axis.round(2).tolist())


def m3(H):
    push_ring_in(H, take_ring_edge_on(H))
    qb = b_rear_take(H)
    qa = a_face_take(H)
    b_off_ring(H, qb)                             # the weld passes to A
    m3_tail(H, qa)


def m3_tail(H, qa, turn_deg=TURN_DEG):
    """From A's weld (the ring in the slot by its face grip, B off it): B's pre-pull, A carries the ring out, B pins
    leg 1 (lifted off the base), A turns the ring and carries it on, B pulls leg 1 off, A sets the ring down."""
    pre_pull(H)
    carry_out(H, qa, out_m=ring_frame(H)[0][1]-TURN_AT_Y_M, z_m=H.tcp("A")[0][2])
    qb = pin_leg1(H)                              # the ring out of the slot: B's hand clears its back
    qa = a_turn(H, qa, turn_deg)
    pull_off(H, qb, carry_out(H, qa, z_m=H.tcp("A")[0][2]))
    s = scene(H.session)
    if ring_crossings(s.points, s.poses["ring"], H.layout):
        raise StageFailure(f"the ring still on the bight: {ring_crossings(s.points, s.poses['ring'], H.layout)}")
    ring_down_front_right(H, qa)
