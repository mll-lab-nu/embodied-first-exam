"""M1, S0 -> S1: disc1 through the slot, parked behind the base.

Start: the task's reset (S0). End (states.s1): disc1 through the slot (the chain passes it twice), lying behind or
beside the base clear of the ring; bead1 where it lay, before the post and outside the ring; the ring still round the
post.

B pinches disc1's chain by its eye and draws it until disc1 stands on its far rim; A grips the rim from above-right,
B lets go, A rolls disc1 on the table towards a top grip, lifts it and turns it edge-on (face normal along x), carries
it before the slot and pushes it in, leaning back once the hand meets the post's face (stand_grip, into_slot). B grips
the part of disc1 out behind the post, A lets go, B pulls it out and lays it flat at PARK_XY_M (out_back). bead1 is
not moved: the long cord's extra between disc1's eye and bead1 lets disc1 go round.
"""
import numpy as np

from .motion import ARMS, OPEN_M, PAD_M, StageFailure, from_home, turn_to
from .parts import CHAIN_OPEN_M, pinch_link, support_z
from .session import scene

DISC_OPEN_M = .03
DISC_SLOT_CLEAR_M = .02   # disc1's lowest point over the slot's bottom while it goes in
DISC_PUSH_TO_Y_M = .012   # disc1's centre pushed towards this (the hand stops at the post's face before)
BACK_GRIP_DEPTH_M = 0.    # B's TCP this far into disc1 from its back rim (~2.5 cm stick out behind the post: the
                          # fingertips, 16 mm further, stay behind its back face). The fingers meet the post's back
                          # face beside the slot with the TCP 3.2-3.4 cm behind its mid-plane
BACK_GRIPS_DEG = ((25, 25), (0, 25))   # B's grips of disc1's back rim: (the rim point this far above its centre's
                          # level, the approach this far down), the first whose pads' middle is EYE_CLEAR_M from disc1's
                          # eye (else the pads close on the eye and its link). The arms reach no level approach there;
                          # 20 deg down and steeper they do (every rim point from -10 to 35 deg)
EYE_CLEAR_M = .02         # in disc1's plane (a finger's half width 12 mm, the eye's ring and its link)
PARK_XY_M = np.array([-.12, .11])     # disc1 laid flat here: left behind the base, clear of the ring and of the hands
                                      # taking the ring in M2, the chain to bead1 not taut (B reaches x < -0.05 there)
STAND_NORMAL_Z = .16      # disc1 stands when its face normal's vertical part is below this (at .15 a run that came
                          # to .150 went a step on, over its rim, and back: A's grip then missed it)
STAND_MAX_NORMAL_Z = .4   # at most this much where it stops rising
STAND_GRIP_DEG = 45       # A grips the standing disc1's rim this far above its centre's level, on the +x side
STAND_GRIP_DEPTH_M = .022 # A's TCP this far into disc1 from the rim (it turns the last ROLL_SHORT_DEG in the fingers)
ROLL_SHORT_DEG = 15       # the roll that would bring the grip to disc1's top ends this short of it (out of reach)
ROLL_POSES = 9            # the roll in this many poses, held only at the end (in thirds the first turned the wrist
                          # 0.55 rad: the forearm roll and the wrist rotation are nearly in line there)
GRIP_OFF_M = .004         # disc1's mid-plane this close to the fingers' middle before they close (open 30 mm on 11)
RIM_DEPTH_M = .012        # the rim this far past the TCP towards the disc's centre: ~2.5 cm of disc in the fingers
LEAN_DEG = 25             # the hand leans back this far about disc1's centre in the slot (its centre then ~2 cm off
                          # the vertical through the pads: a small torque in the fingers)
TOP_TURN_POSES = 12       # the turn to A's top grip in this many poses: the elbow moves fastest at its end (0.29 rad)
BACK_ROUTE_SHORT_M = .07  # B's way round the post ends this far left of its stand-off behind disc1, the rest in 3
                          # moves: the elbow turns fast there (0.5 rad in one third of the route's last leg)
RESET_XY_M = np.array([-.092, -.324])   # disc1's centre at the task's reset
DRAW_BACK_M = .03         # disc1 lying farther than this from RESET_XY_M is first drawn back there by B's pinch on its
                          # chain (A reaches disc1 standing up to ~2.5 cm further from it than at the reset)
AIM_DEG = 3.              # at the stand-off, a grip is aimed anew when disc1's face has turned more than this since
AIM_TRIES = 4             # (standing on B's chain it swings about the vertical; aimed at the swing's end, a finger
                          # meets its face and knocks it over)


def disc_frame(H):
    """(centre, face normal, unit horizontal in-plane direction with y >= 0) of disc1."""
    c, r = scene(H.session).poses["disc_left"]
    n = r.apply([0., 0., 1.])
    t = np.cross([0., 0., 1.], n)
    t = t/np.linalg.norm(t)
    return c, n, t if t[1] >= 0 else -t


def grip_disc(H, hand, point, approach, n, depth=RIM_DEPTH_M, stand_off=.07, aim=None):
    """Grip disc1's rim at `point` along `approach` (into the disc), the fingers across its thickness (closing along
    its normal n), the TCP `depth` past the rim, coming in from `stand_off` before the rim. The hand is beside the
    disc already: the closing sign is the one nearest its own (a 180 deg wrist turn there is an IK jump). aim(): the
    grip (point, approach, n) for disc1 now, to aim anew at the stand-off if its face has turned."""
    from scipy.spatial.transform import Rotation as R

    def quat(approach, n):
        closing = R.from_quat(H.tcp(hand)[1][[1, 2, 3, 0]]).apply(H.session.robot.axes[ARMS[hand]][1])
        return H.quat(hand, approach, n if closing @ n >= 0 else -n)
    q = quat(approach, n)
    H.grip(hand, DISC_OPEN_M)
    turn_to(H, hand, point-approach*stand_off, q, 3)      # in poses: from beside disc1 (stand_grip) the rim has turned
    for _ in range(AIM_TRIES if aim else 0):
        now = aim()
        if abs(now[2] @ n) > np.cos(np.radians(AIM_DEG)):
            break
        H.note("aimed anew", hand=hand, turned_deg=round(float(np.degrees(np.arccos(min(1., abs(now[2] @ n))))), 1))
        point, approach, n = now
        q = quat(approach, n)
        turn_to(H, hand, point-approach*stand_off, q, 3)  # in poses (a 15 deg turn in one moves the wrist 0.58 rad)
    H.note("rim approach", hand=hand, point=point.round(3).tolist(), approach=np.round(approach, 2).tolist(),
           n=np.round(n, 2).tolist(), tcp=H.tcp(hand)[0].round(3).tolist(), disc=disc_frame(H)[0].round(3).tolist())
    H.reach(hand, point+approach*depth, q, linear=3)
    for _ in range(2):                         # disc1's mid-plane onto the fingers' middle (it may have moved)
        off = float((disc_frame(H)[0]-H.tcp(hand)[0]) @ n)
        if abs(off) < GRIP_OFF_M:
            break
        H.move(hand, H.tcp(hand)[0]+off*n, q, settle=6)
    off = float((disc_frame(H)[0]-H.tcp(hand)[0]) @ n)
    H.close(hand)
    H.note("disc1 gripped", hand=hand, width=H.width(hand), point=point.round(3).tolist(), off_mm=round(off*1e3, 1))
    if not .006 < H.width(hand) < .016:
        raise StageFailure(f"{hand} did not grip disc1's rim: width {H.width(hand)}")
    return q


def pinch_disc1_chain(H):
    """B pinches the chain at the first clear link from disc1's eye, from above; returns (B's rotation, the link's
    midpoint)."""
    lay = H.layout
    s = scene(H.session)
    k = pinch_link(s, lay, "disc_left")
    a, b = s.points[k], s.points[k+1]
    mid = (a+b)/2
    q = H.best_quat("B", [0., 0., -1.], np.cross([0., 0., 1.], b-a), np.r_[mid[:2], .2])
    H.grip("B", CHAIN_OPEN_M)
    from_home(H, "B", mid+[0., 0., PAD_M+.06], q)
    H.reach("B", np.r_[mid[:2], support_z(lay, mid)+lay.rope_radius_m+PAD_M-.002], q, linear=3)
    H.close("B")
    H.note("disc1's chain pinched", link=k, width=H.width("B"), link_mid=mid.round(3).tolist(),
           link_dir=((b-a)/np.linalg.norm(b-a)).round(2).tolist(), touching=H.touching())
    if not .002 < H.width("B") < .0065:
        raise StageFailure(f"B did not pinch disc1's chain: width {H.width('B')}")
    return q, mid


def draw_back(H, q, mid):
    """disc1 lying farther than DRAW_BACK_M from RESET_XY_M drawn back there by B's pinch on its chain (drawn, not
    pushed: pushed, the chain folds)."""
    c = disc_frame(H)[0]
    off = RESET_XY_M-c[:2]
    if np.linalg.norm(off) > DRAW_BACK_M and off @ (mid-c)[:2] > 0:
        p = H.tcp("B")[0]+[0., 0., .01]
        H.move("B", p, q)
        H.move("B", p+np.r_[off, 0.], q, linear=int(np.ceil(np.linalg.norm(off)/.02)))
        H.hold(10)
        H.note("disc1 drawn back", off_mm=(off*1e3).round().tolist(), disc=disc_frame(H)[0].round(3).tolist(),
               normal=disc_frame(H)[1].round(2).tolist(), b_tcp=H.tcp("B")[0].round(3).tolist())


def stand_up(H, q):
    """B lifts the chain straight up until disc1 leans at 40 deg on its far rim, then on towards -y until it stands
    (it turns about that rim, which stays on the table: it neither swings nor turns on the chain, as it does hanging
    in the air)."""
    for _ in range(30):
        if disc_frame(H)[1][2] < np.cos(np.radians(40.)):
            break
        H.move("B", H.tcp("B")[0]+[0., 0., .01], q)
    step = np.array([0., -.01, .005])
    best = abs(disc_frame(H)[1][2])
    for _ in range(25):                                     # until it stands, or falls back
        if best < STAND_NORMAL_Z:
            break
        H.move("B", H.tcp("B")[0]+step, q)
        now = abs(disc_frame(H)[1][2])
        H.note("standing up", normal_z=round(now, 3), disc=disc_frame(H)[0].round(3).tolist(), b_tcp=H.tcp("B")[0].round(3).tolist())
        if now > best+.01:                                  # past its best: one step back
            H.move("B", H.tcp("B")[0]-step, q)
            break
        best = min(best, now)
    H.hold(5)
    c, n, _ = disc_frame(H)
    H.note("disc1 standing", disc=c.round(3).tolist(), normal=n.round(2).tolist(), b_tcp=H.tcp("B")[0].round(3).tolist())
    if abs(n[2]) > STAND_MAX_NORMAL_Z:
        raise StageFailure(f"disc1 not standing on B's chain: normal {n.round(2).tolist()}")


def rim_point(H):
    """(centre, face normal, up and side in disc1's plane, the rim direction STAND_GRIP_DEG above its centre's level
    on the +x side) of the standing disc1."""
    c, n, _ = disc_frame(H)
    up = np.array([0., 0., 1.])-n[2]*n
    up /= np.linalg.norm(up)
    side = np.cross(up, n)
    side = side if side[0] >= 0 else -side
    return c, n, up, side, np.cos(np.radians(STAND_GRIP_DEG))*side+np.sin(np.radians(STAND_GRIP_DEG))*up


def a_rim_grip(H):
    """A grips the standing disc1's rim STAND_GRIP_DEG above its centre's level on the +x side, along the radius, from
    above-right (clear of B's hand over the eye; aimed anew as disc1 turns slowly on its rim); B lets go."""
    lay = H.layout
    c, n, up, side, rim = rim_point(H)
    qa = H.quat_away("A", -rim, n, [0., 0., -1.])          # camera mount down: off B's hand over disc1's eye
    H.grip("A", DISC_OPEN_M, steps=5)
    from_home(H, "A", c+(lay.disc_radius_m+.06)*rim+[0., 0., .06], qa)
    H.note("disc1 with A beside", disc=disc_frame(H)[0].round(3).tolist(), normal=disc_frame(H)[1].round(2).tolist())

    def aim():
        c, n, _, _, rim = rim_point(H)
        return c+lay.disc_radius_m*rim, -rim, n
    grip_disc(H, "A", *aim(), depth=STAND_GRIP_DEPTH_M, aim=aim)
    H.grip("B", OPEN_M)
    H.hold(10)
    H.go_home("B", up_m=.05)


def roll_to_top_grip(H):
    """A rolls disc1 on the table until its grip is ROLL_SHORT_DEG short of disc1's top (turning in the fingers
    instead, under its weight, it also slides out of them: only that much is left to turn), lifts it and turns about
    the vertical until disc1's face normal is along x."""
    from scipy.spatial.transform import Rotation as R
    lay = H.layout
    c0, n, up, side, _ = rim_point(H)                      # as gripped (A may have aimed anew)
    p0, q0 = H.tcp("A")
    axis = np.cross(side, up)                       # turns the gripped side up: disc1 rolls towards -side
    for k in range(1, ROLL_POSES+1):
        th = np.radians(90.-STAND_GRIP_DEG-ROLL_SHORT_DEG)*k/ROLL_POSES
        turn = R.from_rotvec(axis*th)
        c = c0-side*lay.disc_radius_m*th
        H.move("A", c+turn.apply(p0-c0), (turn*R.from_quat(q0[[1, 2, 3, 0]])).as_quat()[[3, 0, 1, 2]],
               settle=4 if k == ROLL_POSES else 0)
    c, n, _ = disc_frame(H)
    H.note("disc1 rolled", disc=c.round(3).tolist(), normal=n.round(2).tolist(),
           centre_from_tcp=(c-H.tcp("A")[0]).round(3).tolist())
    p, qa = H.tcp("A")
    H.move("A", p+[.06, .04, .07], qa, linear=3)          # up and towards the right arm (straight up is out of reach)
    top = H.quat_away("A", [0., 0., -1.], [1., 0., 0.], [0., -1., 0.])     # camera mount off the post (pushing in)
    turn_to(H, "A", H.tcp("A")[0], top, TOP_TURN_POSES)
    H.hold(10)
    c, n, _ = disc_frame(H)
    H.note("disc1 in A's top grip", disc=c.round(3).tolist(), normal=n.round(2).tolist(),
           centre_from_tcp=(c-H.tcp("A")[0]).round(3).tolist())
    if abs(n[0]) < .9:
        raise StageFailure(f"disc1 not edge-on along the slot: normal {n.round(2).tolist()}")


def stand_grip(H):
    """disc1 from lying flat into A's top grip, edge-on along the slot."""
    q, mid = pinch_disc1_chain(H)
    draw_back(H, q, mid)
    stand_up(H, q)
    a_rim_grip(H)
    roll_to_top_grip(H)


def push_in(H, q, z, part="disc_left", x=0., to_y=DISC_PUSH_TO_Y_M):
    """A moves `part` along y at height z (and x) in 1 cm steps towards to_y until the hand is stopped."""
    y0 = scene(H.session).pos(part)[1]
    step = .01 if to_y > y0 else -.01
    for y in np.arange(y0+step, to_y+step/2, step):
        try:
            H.place("A", part, np.r_[x, y, z], q, tries=1)
        except StageFailure as exc:
            H.note("push stopped", at=round(float(y), 3), why=str(exc)[:600], contacts=H.contacts(part)[:6])
            break


def into_slot(H):
    """disc1, in A's top grip, lifted and turned upright (face normal along x), carried before the slot with its
    lowest point DISC_SLOT_CLEAR_M over the slot's bottom (clear of the cord in the slot) and pushed in until the hand
    meets the post's face; then the hand leans back LEAN_DEG about disc1's centre (fingertips towards the post: the
    fingers and the finger carriage, wider than the slot, come off the post's face) and pushes on; still held."""
    from scipy.spatial.transform import Rotation as R
    lay = H.layout
    p, q = H.tcp("A")
    H.move("A", p+[.05, .03, .04], q, linear=2)          # up and towards the right arm (straight up is out of reach)
    c, n, _ = disc_frame(H)
    fix = R.align_vectors([[np.sign(n[0]), 0., 0.]], [n])[0]
    q = (fix*R.from_quat(q[[1, 2, 3, 0]])).as_quat()[[3, 0, 1, 2]]
    H.move("A", H.tcp("A")[0], q)
    z = lay.slot_bottom_m+lay.disc_radius_m+DISC_SLOT_CLEAR_M
    front = np.r_[0., -(lay.post_depth_m/2+lay.disc_radius_m+.03), z]
    H.place("A", "disc_left", front, q, linear=4)
    c, n, _ = disc_frame(H)
    H.note("disc1 before the slot", disc=c.round(3).tolist(), normal=n.round(2).tolist(),
           centre_from_tcp=(c-H.tcp("A")[0]).round(3).tolist())
    push_in(H, q, z)
    c, _, _ = disc_frame(H)
    p, q0 = H.tcp("A")
    for t in (1/3, 2/3, 1.):
        lean = R.from_rotvec([np.radians(LEAN_DEG)*t, 0., 0.])     # the TCP over disc1's centre goes towards -y
        q = (lean*R.from_quat(q0[[1, 2, 3, 0]])).as_quat()[[3, 0, 1, 2]]
        H.move("A", c+lean.apply(p-c), q)
    push_in(H, q, z)
    c, n, _ = disc_frame(H)
    H.note("disc1 pushed in", disc=c.round(3).tolist(), normal=n.round(2).tolist(), tcp=H.tcp("A")[0].round(3).tolist(),
           centre_from_tcp=(c-H.tcp("A")[0]).round(3).tolist())


def out_back(H):
    """B grips the part of disc1 out behind the post (from behind and above, across its thickness, clear of its eye:
    BACK_GRIPS_DEG), A lets go, B lifts it off the cord under it a little, pulls it out back and lays it flat at
    PARK_XY_M."""
    lay = H.layout
    c, n, t = disc_frame(H)
    up = np.array([0., 0., 1.])-n[2]*n
    up /= np.linalg.norm(up)
    eye = scene(H.session).points[0]-c
    eye -= (eye @ n)*n                                    # disc1's eye in its plane, from its centre

    def back_grip(rim_deg, down_deg):                     # (rim point, approach, the pads' middle's way to the eye)
        r, d = np.radians([rim_deg, down_deg])
        rim = lay.disc_radius_m*(np.cos(r)*t+np.sin(r)*up)
        approach = -(np.cos(d)*t+np.sin(d)*up)
        return c+rim, approach, float(np.linalg.norm(rim+approach*(BACK_GRIP_DEPTH_M+PAD_M)-eye))
    grips = [back_grip(*g) for g in BACK_GRIPS_DEG]
    k = next((i for i, g in enumerate(grips) if g[2] > EYE_CLEAR_M), int(np.argmax([g[2] for g in grips])))
    point, approach, clear = grips[k]
    H.note("back grip", rim_down_deg=BACK_GRIPS_DEG[k], eye_clear_mm=round(clear*1e3),
           eye_deg=round(float(np.degrees(np.arctan2(eye @ up, eye @ t)))))
    stand_off = point-approach*.04
    q = H.quat_away("B", approach, n, [0., 0., -1.])     # camera mount down: off the post and A's hand over disc1
    from_home(H, "B", H.tcp("B")[0], q)       # turned at home by the joints (route() would turn it there by move())
    H.route("B", stand_off-[BACK_ROUTE_SHORT_M, 0., 0.], q, z_m=stand_off[2])  # round the post's left side
    H.move("B", stand_off, q, linear=3)
    qb = grip_disc(H, "B", point, approach, n, depth=BACK_GRIP_DEPTH_M, stand_off=.04)
    H.grip("A", OPEN_M)
    H.move("A", H.tcp("A")[0]+[0., -.05, .02], H.tcp("A")[1])
    H.go_home("A", up_m=.05)
    p = H.tcp("B")[0]
    H.move("B", p+[0., 0., .02], qb)
    for _ in range(12):
        c, _, _ = disc_frame(H)
        if c[1]-lay.disc_radius_m > lay.post_depth_m/2+.01:
            break
        H.move("B", H.tcp("B")[0]+[0., .01, 0.], qb)
    c, n, _ = disc_frame(H)
    H.note("disc1 out behind the post", disc=c.round(3).tolist(), normal=n.round(2).tolist())
    if c[1]-lay.disc_radius_m < lay.post_depth_m/2:
        raise StageFailure(f"disc1 not out of the slot: {c.round(3).tolist()}")
    # Laid down: carried over the park spot, lowered until it touches, let go (it falls flat).
    off = H.tcp("B")[0]-c
    H.move("B", np.r_[PARK_XY_M, c[2]]+off, qb, linear=8)   # in 4 moves the elbow turns 0.5 rad in one (an IK jump)
    for _ in range(12):
        if disc_frame(H)[0][2] < lay.disc_radius_m+.005:
            break
        H.move("B", H.tcp("B")[0]-[0., 0., .01], qb)
    H.grip("B", OPEN_M)
    H.hold(20)
    n = disc_frame(H)[1]
    if abs(n[2]) < .5:      # still on its rim (held at its back rim's level, it hangs upright): pushed over by a
        tip = np.r_[n[:2]*np.sign(n[0] or 1.), 0.]           # finger towards +x, as it falls from the upper grip
        H.move("B", H.tcp("B")[0]+.04*tip/np.linalg.norm(tip), qb)
        H.hold(20)
    H.go_home("B", up_m=.08)
    H.hold(20)
    c, n, _ = disc_frame(H)
    H.note("disc1 parked", disc=c.round(3).tolist(), normal=n.round(2).tolist())


def m1(H):
    stand_grip(H)
    into_slot(H)
    out_back(H)
