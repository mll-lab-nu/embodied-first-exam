"""M3's work on leg 1 (disc1's end of the chain up to the ring's hole): B behind the post.

pre_pull: with the ring in the slot (A's face grip), B pulls leg 1 back and to the left until leg 1's part of the
bight is at most PRE_LEG1_LINKS long (the slack the push left hanging behind the post goes back through the ring's
hole). pin_leg1: with the ring out of the slot, B takes leg 1 from above and lifts it off the base; held there, the
ring carried out draws the bight (bead1) round its tube. pull_off: B pulls leg 1 until no cord passes the ring's
hole, then leaves (b_out).
"""
import numpy as np

from .motion import ARMS, IK_REACH_M, JUMP_RAD, PAD_M, StageFailure, back_off, move_nj
from .parts import CHAIN_OPEN_M, fingers_clear, support_z
from .session import scene
from .states import ring_crossings

LEG_TAKE_Y_M = (.05, .11)      # B takes leg 1 from above (lying on the base: no link is high enough for a side pinch
                               # after a perturbation) at a link midpoint this far behind the post's mid-plane,
LEG_TAKE_CLEAR_M = .03         # this far from the ring's tube centreline, the one nearest the ring along the cord
LEG_TAKE_MAX_X_M = .02         # (of those at most this far right, if any: further right, B's hand behind the ring in
                               # the slot meets A's on its face)
LEG_STAND_OFF_M = .05          # its stand-off up the approach
FINGER_DROP_M = (.004, .0115)  # a finger's end past the pads' middle, its half width across the closing (the pinch
PRESS_M = .0025                # leans: one corner lowest), at most this far into what the link lies on
LEG_HELD_M = .0005             # B's opening over a held link (the 7 mm cord reads 2.8-4.9 mm: the pads sink in),
LEG_DOUBLE_M = .0058           # over two (6.6 mm: a strand of the bight lying beside leg 1 taken with it)
PRE_PULL_TILT_DEG = 30         # pre_pull, the ring in the slot: the approach leans back this far (fingertips forwards;
PRE_LIFT_M = .01               # the hand clears the ring's back), lifted this much,
PRE_PULL_STEP_M = np.r_[-.01, .0173, 0.]   # pulled back 30 deg to the left (off disc1) this much a step (IK: >= 20
PRE_STROKE_M = .15             # cm), at most this far a stroke,
PRE_LEG1_LINKS = 11            # until leg 1's part of the bight (its ring crossing to bead1) is at most this many links
                               # (9-11 where the carry then takes the bight off; 20-21 where it does not) ...
PRE_PULLS = 5                  # ... in at most this many strokes (the first takes leg 1's own slack off the base)
PIN_TILT_DEG = 0               # pin_leg1, the ring out: straight down,
PIN_LIFT_M = .04               # lifted this much off the base, pulled straight back (IK: >= 20 cm)
LEG_PULL_STEP_M = np.r_[0., .02, 0.]   # B pulls leg 1 back this much a step,
LEG_PULL_M = .20               # this far a stroke (at 10 cm the first 4-6 cm take up slack and bead1 is let go half
                               # way up to the hole),
LEG_PULLS = 3                  # at most this many strokes


def tube_distance(p, ring, lay):
    """Distance of p from the ring's tube centreline."""
    c, r = ring
    n = r.apply([0., 0., 1.])
    h = (p-c) @ n
    return float(np.hypot(h, np.linalg.norm(p-c-h*n)-lay.ring_major_radius_m))


def leg1_link(H, s, first, skip=()):
    """The link of leg 1 (before the ring's first crossing) B takes from above: midpoint LEG_TAKE_Y_M behind the post,
    LEG_TAKE_CLEAR_M from the ring's tube, the open fingers' footprint clear of the beads and discs, not in `skip`;
    the one nearest the ring along the cord (the least of leg 1's slack between); None if there is none."""
    lay = H.layout
    mids = (s.points[:-1]+s.points[1:])/2
    ok = [k for k in range(first) if k not in skip and LEG_TAKE_Y_M[0] < mids[k, 1] < LEG_TAKE_Y_M[1]
          and tube_distance(mids[k], s.poses["ring"], lay) > LEG_TAKE_CLEAR_M
          and fingers_clear(s, lay, mids[k], s.points[k+1]-s.points[k])]
    left = [k for k in ok if mids[k, 0] <= LEG_TAKE_MAX_X_M]
    return max(left or ok) if ok else None


def leg_path(tcp, a, lift_m, pull_m, step):
    """B's TCP points taking leg 1 and pulling it: the stand-off, the pinch (3 straight steps), the lift (1 cm steps),
    the pull's steps (`step` each, pull_m in all)."""
    pre = tcp-a*LEG_STAND_OFF_M
    lift = tcp+[0., 0., lift_m]
    n = max(1, int(round(lift_m/.01)))
    return ([pre]+[pre+(tcp-pre)*j/3 for j in (1, 2, 3)]+[tcp+(lift-tcp)*j/n for j in range(1, n+1)]
            + [lift+j*step for j in range(1, int(round(pull_m/np.linalg.norm(step)))+1)])


def leg_quat(H, a, closing, path):
    """B's rotation (approach a, closing +-closing) whose IK chain along `path` (each pose seeded at the solution
    before, as move_ee's are; from B's joints to the stand-off any) keeps the most of it in reach (residual
    IK_REACH_M, no IK jump); of two that reach as far, the one nearer B's joints at the stand-off. Returns (rotation,
    poses in reach)."""
    rb = H.session.robot
    frame = rb.tcp_frames[ARMS["B"]]
    sl = [rb.arm_joints.index(n) for n in rb.groups[ARMS["B"]].arm_joints]
    out = []
    for sign in (1., -1.):
        q = H.quat("B", a, sign*np.asarray(closing, float))
        seed = q0 = np.asarray(rb.arm_q(), float)
        n = 0
        for k, p in enumerate(path):
            nq, err = rb.ik({frame: np.r_[p+H.origin, q]}, seed, 1e-4, 1e-3, 200)
            if err[frame][0] > IK_REACH_M or (k and np.abs(nq[sl]-seed[sl]).max() > JUMP_RAD):
                break
            n, seed = k+1, nq
            if k == 0:
                swing = float(np.abs(nq[sl]-q0[sl]).max())
        out.append((n, -swing if n else 0., q))
    n, _, q = max(out, key=lambda o: o[:2])
    return q, n


def take_leg1(H, tilt_deg, lift_m, pull_m, step=LEG_PULL_STEP_M, required=True):
    """B takes leg 1 (disc1's end of the chain up to the ring's hole) at leg1_link from above, the approach leaning
    back tilt_deg (fingertips forwards), the pads across the link 1.5 mm over what it lies on (m4b.carry_disc's;
    higher for a leaning approach: its fingers' lowest corner PRESS_M into it), the closing sign whose IK chain
    reaches the most of the lift and a pull_m pull by `step`s (leg_quat), and lifts it lift_m; holding two strands
    (LEG_DOUBLE_M) it lets go and takes another link. Returns B's rotation, None if no cord passes the ring's hole (or, not
    `required`, no link qualifies)."""
    lay = H.layout
    t = np.radians(tilt_deg)
    a = np.r_[0., -np.sin(t), -np.cos(t)]
    over = max(lay.rope_radius_m-.002, FINGER_DROP_M[0]*np.cos(t)+FINGER_DROP_M[1]*np.sin(t)-PRESS_M)
    skip = set()
    for _ in range(3):                             # again if the fingers closed on nothing or on two strands
        H.hold(10)                                 # the cord let go settles
        s = scene(H.session)
        cross = ring_crossings(s.points, s.poses["ring"], lay)
        if not cross:
            H.note("no cord through the ring: nothing to take")
            return None
        first = min(i for i, _ in cross)
        k = leg1_link(H, s, first, skip)
        if k is None:
            if not required:
                H.note("no link of leg 1 to take", first_crossing=first)
                return None
            raise StageFailure(f"no link of leg 1 to take behind the post (before crossing {first})")
        mid, along = (s.points[k]+s.points[k+1])/2, s.points[k+1]-s.points[k]
        pads = np.r_[mid[:2], max(mid[2], support_z(lay, mid)+over)]
        tcp = pads-a*PAD_M
        path = leg_path(tcp, a, lift_m, pull_m, step)
        q, reach = leg_quat(H, a, np.cross(a, np.r_[along[:2], 0.]), path)
        H.grip("B", CHAIN_OPEN_M)
        move_nj(H, "B", tcp-a*LEG_STAND_OFF_M, q)
        try:
            H.reach("B", tcp, q, linear=3)
        except StageFailure as exc:                # stopped on the base or another strand: closes there (the width
            H.note("leg 1 reach stopped", link=k, why=str(exc)[:160])   # tells), else another link
            skip |= set(range(k-2, k+3))
        H.close("B")
        H.note("leg 1 taken", link=k, mid=mid.round(3).tolist(), first_crossing=first, width=H.width("B"),
               path_in_reach=f"{reach}/{len(path)}")
        if LEG_HELD_M < H.width("B") < LEG_DOUBLE_M:
            H.move("B", tcp+[0., 0., lift_m], q, linear=max(1, int(round(lift_m/.01))))
            return q
        if H.width("B") >= LEG_DOUBLE_M:
            skip |= set(range(k-2, k+3))
        H.grip("B", CHAIN_OPEN_M)
        H.move("B", tcp-a*LEG_STAND_OFF_M, q, linear=2)
    raise StageFailure("B did not take leg 1")


def pin_leg1(H):
    """B takes leg 1 behind the post straight from above and lifts it PIN_LIFT_M off the base (take_leg1); returns
    B's rotation, None if no cord passes the ring's hole. Held there, the ring carried out draws the bight (bead1)
    round its tube (free, it draws leg 1's extra through the slot instead)."""
    return take_leg1(H, PIN_TILT_DEG, PIN_LIFT_M, LEG_PULL_M)


def bight_links(H):
    """Links between the ring's first and last crossing (the bight through its hole), None if none passes it."""
    s = scene(H.session)
    cross = ring_crossings(s.points, s.poses["ring"], H.layout)
    return cross[-1][0]-cross[0][0] if cross else None


def leg1_links(H):
    """Links of the bight on leg 1's side: from the ring's first crossing to bead1 (the chain point nearest its
    centre; it slides on the cord), None if no cord passes the ring's hole."""
    s = scene(H.session)
    cross = ring_crossings(s.points, s.poses["ring"], H.layout)
    bead = int(np.argmin(np.linalg.norm(s.points-s.pos("bead_left"), axis=1)))
    return bead-cross[0][0] if cross else None


def pre_pull(H):
    """(1) The ring in the slot (A's face grip), B takes leg 1 behind the post (take_leg1, leaning back
    PRE_PULL_TILT_DEG, lifted PRE_LIFT_M) and pulls it back and to the left: the bight's slack (pushed in, the ring left it
    hanging behind the post, and bead1's cord the M2 draw left long before the post) through the ring's hole, until
    leg 1's part of the bight is at most PRE_LEG1_LINKS, in at most PRE_PULLS strokes (fewer if no link of leg 1
    qualifies; M2 pushed disc1 off leg 1's links behind the post); B lets go and backs off.
    bead1 must stay in front and the cord pass the hole twice."""
    lay = H.layout
    n0 = bight_links(H)
    done = lambda: (leg1_links(H) or 0) <= PRE_LEG1_LINKS
    for k in range(PRE_PULLS):
        if done() or (k and leg1_links(H) >= before):      # done, or the last stroke gained nothing
            break
        before = leg1_links(H)
        q = take_leg1(H, PRE_PULL_TILT_DEG, PRE_LIFT_M, PRE_STROKE_M, PRE_PULL_STEP_M, required=False)
        if q is None:                              # no link clear of the discs and the ring: the bight as it is
            break
        target = H.tcp("B")[0]
        for _ in range(int(round(PRE_STROKE_M/np.linalg.norm(PRE_PULL_STEP_M)))):
            target = target+PRE_PULL_STEP_M
            try:
                H.move("B", target, q, settle=4)
            except StageFailure as exc:
                H.note("pre-pull stopped", why=str(exc)[:200])
                break
            if done():
                break
        back_off(H, "B", .03)
        s = scene(H.session)
        H.note("leg 1 pre-pulled", stroke=k, bight_links=[n0, bight_links(H)], leg1_links=leg1_links(H),
               tcp=H.tcp("B")[0].round(3).tolist(),
               crossings=ring_crossings(s.points, s.poses["ring"], lay), bead1=s.pos("bead_left").round(3).tolist())
    s = scene(H.session)
    cross = ring_crossings(s.points, s.poses["ring"], lay)
    if len(cross) != 2 or s.pos("bead_left")[1] > -lay.post_depth_m/2:
        raise StageFailure(f"the pre-pull left crossings {cross}, bead1 at {s.pos('bead_left').round(3).tolist()}")


def pull_leg1(H, qb):
    """B draws leg 1 back (LEG_PULL_STEP_M a step) at most LEG_PULL_M: the bight round the ring's tube and bead1
    through its hole; True once no cord passes the hole."""
    lay = H.layout
    target = H.tcp("B")[0]
    for _ in range(int(round(LEG_PULL_M/np.linalg.norm(LEG_PULL_STEP_M)))):
        target = target+LEG_PULL_STEP_M
        try:
            H.move("B", target, qb, settle=4)
        except StageFailure as exc:
            H.note("pull stopped", why=str(exc)[:200])
            break
        s = scene(H.session)
        cross = ring_crossings(s.points, s.poses["ring"], lay)
        H.note("leg 1 pulled", tcp=H.tcp("B")[0].round(3).tolist(), crossings=cross,
               bead1=s.pos("bead_left").round(3).tolist(), width=H.width("B"))
        if not cross:
            return True
    return False


def pull_off(H, qb, clear):
    """B (pinning leg 1) pulls it back (pull_leg1) in at most LEG_PULLS strokes, taking it again between them, until
    no cord passes the ring's hole (`clear`: none does already), and leaves (b_out). True if none does."""
    for k in range(LEG_PULLS):
        clear = clear or pull_leg1(H, qb)
        back_off(H, "B", .03)                      # up off the cord
        if clear or k == LEG_PULLS-1:
            break
        q = pin_leg1(H)
        if q is None:                              # let go, the cord slipped off the ring
            clear = True
            break
        qb = q
    b_out(H, qb)
    return clear


def b_out(H, qb):
    for p in ([-.2, .13, .12], [-.2, -.15, .12], [-.16, -.12, .2]):   # out to the left low, under A's hand,
        move_nj(H, "B", np.r_[p], qb, linear=3)                         # and round the post's left side
