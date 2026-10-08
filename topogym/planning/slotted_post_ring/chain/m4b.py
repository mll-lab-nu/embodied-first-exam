"""M4b, S3 -> S4b: every part but the ring back inside the separator.

Start (states.s3): the ring free of the chain, flat front right. End (states.s4b): the chain, the beads and the discs on
the system side of the separator (the task's own check), disc1 at its set-down target (fixed-state tolerance in
states.py).

Each disc beyond the separator is carried by a chain link next to its eye to beside the base's front half on its side
(carry_disc: lifted until it hangs free, carried beside the base where only the table is under it, lowered onto its
target, the hand following the hanging disc's miss). If the cord beyond is all on leg 2 (a loop M3 left behind the
post), A draws leg 2 forward (draw_leg2); else the hand on bead1's side draws bead1 forward until everything is
INSIDE_M inside the separator.
"""
import numpy as np

from .motion import ARMS, IK_REACH_M, JUMP_RAD, OPEN_M, PAD_M, StageFailure, from_home
from .parts import CHAIN_OPEN_M, fingers_clear, pinch_link, support_z
from .session import scene

DISC_TARGETS_XY_M = dict(disc_left=(-.19, -.05), disc_right=(.2, -.05))   # beside the base's front half on their
                                    # sides, inside the separator (M3 leaves disc1 behind the post): a hanging disc set
                                    # down topples up to ~6 cm from the hand, its rim then still ~8 cm inside
DISC_CLEAR_M = .02        # the hanging disc's lowest point this far over the base's top while carried
LIFT_SEGMENTS = 8         # the lift's straight line in this many IK targets (in 4 the wrist jumps 0.51 rad). A hand
                          # that cannot lift to the carry height lifts as high as it reaches (lift_height): the disc
                          # carried beside the base need only clear the table
PINCH_MORE_LINKS = 16     # the chain round the disc's rim from its eye (M3's pulls): a link this near it, on the disc
SIDE_CLEAR_M = .015       # a lifted disc is carried this far beside the base
PUSH_ASIDE_M = .08        # a disc lying close behind the post pushed this far aside before it is lifted
AIM_STEP_M = .03          # the set-down's hand moved at most this much a step towards the disc over its target
AIM_MAX_M = .10           # and at most this far off the target in all
INSIDE_M = .02            # every other part this far inside the separator after the draw
DRAW_STEP_M, DRAW_MAX_M = .01, .14
LEG2_FRONT_M = .05        # draw_leg2 pinches leg 2 this far before the post's front face (at 2.9 cm A's gripper body
                          # meets the post) and draws it at most
LEG2_DRAW_MAX_M = .25     # this far (a loop behind the post comes out doubled)


def separator_y(task):
    return task.goal_region.separator_offset_m-task.origin[1]


def beyond(s, lay, limit):
    """{part: furthest +y} of the non-ring parts that reach past `limit` (assembly frame)."""
    from topogym.assets.geometry.slotted_chain import part_vertices
    vertices = part_vertices(lay)
    far = dict(cord=float(s.points[:, 1].max()+lay.rope_radius_m))
    for name in ("bead_left", "bead_right", "disc_left", "disc_right"):
        p, r = s.poses[name]
        far[name] = float((r.apply(vertices[name])+p)[:, 1].max())
    return {k: round(v, 4) for k, v in far.items() if v > limit}


def push_disc_aside(H, disc, side):
    """The other side's hand (A for side -1) pushes the disc PUSH_ASIDE_M along x towards `side` with its closed
    fingertips from above, at its rim on the far side: lying behind the post, close to it, it leaves no chain link
    between it and the slot clear of it (and no hand gets between it and the post)."""
    lay = H.layout
    hand = "A" if side < 0 else "B"
    c = scene(H.session).pos(disc)
    d = np.r_[side, 0., 0.]
    q = H.quat_away(hand, [0., 0., -1.], [0., 1., 0.], [0., 1., 0.])
    far = c-d*(lay.disc_radius_m+.012)
    H.close(hand)
    from_home(H, hand, H.tcp(hand)[0], q)           # turned at home by the joints (route() would turn it by move())
    H.route(hand, far+[0., 0., .06], q, z_m=far[2]+.06)
    H.move(hand, np.r_[far[:2], c[2]+.01], q, linear=2)       # the fingertips (16 mm past the TCP) by the disc
    H.move(hand, np.r_[far[:2], c[2]+.01]+d*PUSH_ASIDE_M, q, linear=4)
    H.move(hand, H.tcp(hand)[0]+[0., 0., .06], q)
    H.go_home(hand)
    H.note("disc pushed aside", disc=disc, at=scene(H.session).pos(disc).round(3).tolist())


def lift_height(H, hand, q, top_z):
    """The highest TCP height up to top_z, straight up from where `hand` is in LIFT_SEGMENTS steps, whose IK chain (each
    pose seeded at the one before, as move_ee's) stays within IK_REACH_M without an IK jump (JUMP_RAD)."""
    rb = H.session.robot
    frame = rb.tcp_frames[ARMS[hand]]
    sl = [rb.arm_joints.index(n) for n in rb.groups[ARMS[hand]].arm_joints]
    p = H.tcp(hand)[0]
    seed, best = np.asarray(rb.arm_q(), float), p[2]
    for z in np.linspace(p[2], top_z, LIFT_SEGMENTS+1)[1:]:
        nq, err = rb.ik({frame: np.r_[np.r_[p[:2], z]+H.origin, q]}, seed, 1e-4, 1e-3, 200)
        if err[frame][0] > IK_REACH_M or np.abs(nq[sl]-seed[sl]).max() > JUMP_RAD:
            break
        best, seed = z, nq
    return float(best)


def disc_lowest(H, disc, k, label):
    """The hanging disc's lowest point (noted with the pinched link)."""
    s = scene(H.session)
    c, r = s.poses[disc]
    lowest = float(c[2]-H.layout.disc_radius_m*np.sqrt(max(0., 1.-r.apply([0., 0., 1.])[2]**2)))
    H.note(label, link_mid=((s.points[k]+s.points[k+1])/2).round(3).tolist(), disc=c.round(3).tolist(),
           lowest=round(lowest, 3))
    return lowest


def carry_disc(H, disc, target):
    """Pinch the chain near the disc's eye (pinch_link; from above, across the link), lift so that the disc hangs from
    it (lift_height), carry it beside the base (SIDE_CLEAR_M), lift it there as high as the hand reaches, carry it
    over `target` along the base's side, lower it until it rests and let go. The hand on the target's side, or the
    other where that one cannot reach the chain."""
    from topogym.assets.geometry.slotted_chain import EYE_LOCAL_M
    lay = H.layout
    s = scene(H.session)
    try:
        k = pinch_link(s, lay, disc)
    except StageFailure:
        try:                                    # the chain drawn over the disc or round its rim (M3's pulls of leg 1)
            k = pinch_link(s, lay, disc, on_disc_ok=True, links=PINCH_MORE_LINKS)
        except StageFailure:                    # lying close to the post: no link clear of it between
            push_disc_aside(H, disc, np.sign(target[0]))
            s = scene(H.session)
            k = pinch_link(s, lay, disc)
    a, b = s.points[k], s.points[k+1]
    mid, along = (a+b)/2, b-a
    across = np.cross([0., 0., 1.], along)
    # Lifted so far that the disc hangs free (dragged, it lands where it trails): the links to its eye, then its eye's
    # offset and its radius under the pads.
    n = len(s.points)-1
    hang = (k+.5 if disc == "disc_left" else n-k-.5)*np.linalg.norm(along)+EYE_LOCAL_M[1]+lay.disc_radius_m
    carry_z = hang+PAD_M+lay.base_height_m+DISC_CLEAR_M
    for hand in (("B", "A") if target[0] < 0 else ("A", "B")):       # first the hand on the target's side
        away = np.sign(mid[1]) or 1.                                   # the camera mount off the post, unless that
        q = H.quat_away(hand, [0., 0., -1.], across, [0., away, 0.])  # turn of the hand cannot lift it to carry_z
        if H.session.ik(ARMS[hand], np.r_[mid[:2], carry_z]+H.origin, q)[1] > IK_REACH_M:
            q = H.quat_away(hand, [0., 0., -1.], across, [0., -away, 0.])
        try:
            H.grip(hand, CHAIN_OPEN_M)
            from_home(H, hand, H.tcp(hand)[0], q)       # turned at home by the joints (route() would turn it by move())
            H.route(hand, mid, q)
            under = max(support_z(lay, mid), mid[2]-lay.rope_radius_m)    # the table, the base or the disc
            H.reach(hand, np.r_[mid[:2], under+lay.rope_radius_m+PAD_M-.002], q, linear=3)
            break
        except StageFailure as exc:
            H.note("disc pinch unreachable", disc=disc, hand=hand, error=str(exc)[:300])
            H.go_home(hand)
    else:
        raise StageFailure(f"no hand reaches the chain at {disc}")
    H.close(hand)
    lift_z = lift_height(H, hand, q, carry_z)
    H.note("chain pinched", disc=disc, hand=hand, link=k, mid=mid.round(4).tolist(), tcp=H.tcp(hand)[0].round(4).tolist(),
           width=H.width(hand), lift_z=round(float(lift_z), 3), carry_z=round(float(carry_z), 3))
    H.move(hand, np.r_[mid[:2], lift_z], q, linear=LIFT_SEGMENTS)
    disc_lowest(H, disc, k, "lifted")
    side = np.sign(target[0])*(lay.base_width_m/2+lay.disc_radius_m+SIDE_CLEAR_M)
    H.move(hand, np.r_[side, mid[1], lift_z], q, linear=4)        # beside the base (only the table under the disc,
    lift_z = lift_height(H, hand, q, carry_z)                     # swinging and trailing: carried over the base it
    H.move(hand, np.r_[side, mid[1], lift_z], q, linear=LIFT_SEGMENTS)   # catches on its corner), where
    lowest = disc_lowest(H, disc, k, "lifted beside the base")          # the hand also reaches higher
    if lowest < .005:
        raise StageFailure(f"{disc} not lifted clear by its chain: lowest {lowest:.3f}")
    H.route(hand, np.r_[target, 0.], q, z_m=lift_z, side_x_m=abs(side))
    aim = np.asarray(target, float)
    for z in np.arange(lift_z-.02, .03, -.02):             # down until the disc rests on the table, the hand moved
        miss = np.asarray(target)-scene(H.session).pos(disc)[:2]    # by the hanging disc's miss each step (its cord
        if np.sign(target[0])*miss[0] < 0:                 # pulls it off, up to 9 cm back); a disc further out than
            miss[0] = 0.                                   # its target is left so: there it draws more of its cord
        aim = aim+np.clip(miss, -AIM_STEP_M, AIM_STEP_M)   # off the base
        aim = target+np.clip(aim-target, -AIM_MAX_M, AIM_MAX_M)
        H.move(hand, np.r_[aim, z], q)
        if scene(H.session).pos(disc)[2] < lay.disc_thickness_m:
            break
    H.grip(hand, OPEN_M)
    H.note("disc set down", disc=disc, hand=hand, at=scene(H.session).pos(disc).round(3).tolist())
    H.go_home(hand, up_m=.15)


def draw_leg2(H, limit):
    """If the cord beyond the separator is all on leg 2 (past the slot's last crossing: M3's pre-pull can draw leg 2's
    cord in behind the post, a loop that comes out round the post's right side), A pinches leg 2 at its first link
    past that cord lying LEG2_FRONT_M before the post (from above, across the link, clear of the parts) and draws it
    forward 1 cm at a time until nothing lies beyond (at most LEG2_DRAW_MAX_M); True if nothing does then."""
    from .states import slot_crossings
    lay = H.layout
    s = scene(H.session)
    slot = slot_crossings(s.points, lay)
    out = np.nonzero(s.points[:, 1]+lay.rope_radius_m > limit)[0]
    if not len(out) or not slot or out.min() <= slot[-1] or set(beyond(s, lay, limit)) != {"cord"}:
        return False
    for k in range(out.max()+1, len(s.points)-1):
        a, b = s.points[k], s.points[k+1]
        mid = (a+b)/2
        if (mid[1] < -lay.post_depth_m/2-LEG2_FRONT_M and mid[2]-support_z(lay, mid) < .03
                and fingers_clear(s, lay, mid, b-a)):
            break
    else:
        return False
    q = H.quat_away("A", [0., 0., -1.], np.cross([0., 0., 1.], b-a), [0., -1., 0.])
    H.grip("A", CHAIN_OPEN_M)
    from_home(H, "A", np.r_[mid[:2], .1], q)
    H.reach("A", np.r_[mid[:2], support_z(lay, mid)+lay.rope_radius_m+PAD_M-.002], q, linear=3)
    H.close("A")
    H.note("leg 2 pinched", link=k, mid=mid.round(3).tolist(), width=H.width("A"))
    p = H.tcp("A")[0]+[0., 0., .03]
    H.move("A", p, q, linear=2)
    for _ in range(int(round(LEG2_DRAW_MAX_M/DRAW_STEP_M))):
        if not beyond(scene(H.session), lay, limit):
            break
        p = p+[0., -DRAW_STEP_M, 0.]
        try:
            H.move("A", p, q)
        except StageFailure as exc:
            H.note("leg 2 draw stopped", why=str(exc)[:200])
            break
    H.note("leg 2 drawn", beyond=beyond(scene(H.session), lay, limit), tcp=H.tcp("A")[0].round(3).tolist())
    H.grip("A", OPEN_M)
    H.go_home("A", up_m=.1)
    H.hold(20)
    return not beyond(scene(H.session), lay, limit)


def m4b(H):
    lay, task = H.layout, H.session.env._task
    limit = separator_y(task)-INSIDE_M
    for disc, target in DISC_TARGETS_XY_M.items():
        if beyond(scene(H.session), lay, limit).get(disc) is not None:
            carry_disc(H, disc, np.asarray(target))
    far = beyond(scene(H.session), lay, limit)
    H.note("after the discs", beyond=far)
    if not far:
        return
    if draw_leg2(H, limit):
        return
    s = scene(H.session)
    b, r = s.poses["bead_left"]
    hand = "A" if b[0] > 0 else "B"         # bead1 on the right after M3's ring set-down in perturbed runs
    bore = r.apply([0., 0., 1.])
    closing = np.cross([0., 0., 1.], bore)
    closing = closing if np.linalg.norm(closing) > .2 else np.array([1., 0., 0.])
    q = H.quat(hand, [0., 0., -1.], closing)
    H.grip(hand, OPEN_M)
    from_home(H, hand, b+[0., 0., PAD_M+.06], q)
    H.reach(hand, b+[0., 0., PAD_M], q, linear=3)
    H.close(hand)
    p = H.tcp(hand)[0]+[0., 0., .03]
    H.move(hand, p, q, linear=2)
    for _ in range(int(DRAW_MAX_M/DRAW_STEP_M)):
        far = beyond(scene(H.session), lay, limit)
        if not far:
            break
        p = p+[0., -DRAW_STEP_M, 0.]
        try:
            H.move(hand, p, q)
        except StageFailure as exc:         # out of reach: as far as it went
            H.note("bead1 draw stopped", why=str(exc)[:200])
            p = H.tcp(hand)[0]
            far = beyond(scene(H.session), lay, limit)
            break
    H.note("bead1 drawn", hand=hand, beyond=far, bead1=scene(H.session).pos("bead_left").round(3).tolist())
    H.move(hand, np.r_[p[:2], p[2]-.025], q)
    H.grip(hand, OPEN_M)
    H.go_home(hand, up_m=.1)
    H.hold(20)
    far = beyond(scene(H.session), lay, limit)       # let go, the cord settles (held, it stands 3 mm further back)
    H.note("bead1 let go", beyond=far)
    if far:
        raise StageFailure(f"still beyond the separator after drawing bead1 {DRAW_MAX_M} m: {far}")
