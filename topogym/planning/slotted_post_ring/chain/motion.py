"""The two ALOHA hands for the stages (A the right arm, B the left): Session primitives in the assembly frame.

A grasp is given as the point the pads' middle should close on, the approach (hand -> fingertips) and the closing
direction. The PD tracking leaves a low TCP a few mm above its target (move_ee accepts 8 mm), so reach() corrects by
the measured error once.

The standard service refuses an end-effector row whose IK solution lies more than JUMP_RAD from the joints (an IK
jump). from_home, turn_to and move_nj keep every row within it: a joint move out of home, a turn in poses, a long move
on its joint line.
"""
import numpy as np

PAD_M = .012          # the middle of the pads past the TCP along the approach (fingertip ends at 16 mm)
OPEN_M = .045
ARRIVAL_M = .012       # a move ending farther than this from its target was blocked
ARMS = dict(A="right", B="left")
ARM_BASE_WORLD_XY_M = dict(A=(.333, 0.), B=(-.605, 0.))     # the arms' bases on the table (world)
JUMP_RAD = .5          # an IK solution farther than this from the joints on some joint is an IK jump
JOINT_STEP_RAD = .25   # move_nj commands a move to an IK solution beyond JUMP_RAD on its joint line, poses this far apart
IK_REACH_M = .005      # a pose of a planned IK chain is in reach with this residual


class StageFailure(RuntimeError):
    pass


def frame(arm_axes, approach, closing):
    """wxyz quaternion of the TCP whose approach and closing axes point along `approach` and `closing` (world)."""
    from scipy.spatial.transform import Rotation as R
    a = np.asarray(approach, float)
    a = a/np.linalg.norm(a)
    c = np.asarray(closing, float)
    c = c-(c @ a)*a
    c = c/np.linalg.norm(c)
    a_l, c_l = (np.asarray(v, float) for v in arm_axes)
    a_l = a_l/np.linalg.norm(a_l)
    c_l = c_l-(c_l @ a_l)*a_l
    c_l = c_l/np.linalg.norm(c_l)
    world = np.column_stack([a, c, np.cross(a, c)])
    local = np.column_stack([a_l, c_l, np.cross(a_l, c_l)])
    return R.from_matrix(world @ local.T).as_quat()[[3, 0, 1, 2]]


class Hands:
    def __init__(self, session, log):
        self.session, self.log = session, log
        self.P = session.primitives()
        self.origin = np.asarray(session.env._task.origin, float)
        self.layout = session.env._task.layout
        self.home = {arm: np.asarray(session.hold_action(), float)[session.robot.arm_slice[arm]].copy()
                     for arm in session.robot.arms}

    def note(self, event, **values):
        entry = dict(step=int(self.session.n_steps), event=event, **values)
        self.log.append(entry)
        print(entry, flush=True)

    def arm_base(self, hand):
        """The hand's arm base, xy in the assembly frame."""
        return np.asarray(ARM_BASE_WORLD_XY_M[hand])-self.origin[:2]

    def quat(self, hand, approach, closing):
        return frame(self.session.robot.axes[ARMS[hand]], approach, closing)

    def best_quat(self, hand, approach, closing, at):
        """quat() with the closing direction's sign (the same grasp) whose IK at `at` has the smaller residual."""
        options = [self.quat(hand, approach, c) for c in (closing, -np.asarray(closing, float))]
        residual = [self.session.ik(ARMS[hand], np.asarray(at, float)+self.origin, q)[1] for q in options]
        return options[int(np.argmin(residual))]

    def quat_away(self, hand, approach, closing, away):
        """quat() with the closing direction's sign (the same grasp) that puts the wrist camera's mount (+z of the TCP
        frame: 4-12 cm out, 10-14 cm behind the TCP) on the side of `away`."""
        from scipy.spatial.transform import Rotation as R
        options = [self.quat(hand, approach, c) for c in (closing, -np.asarray(closing, float))]
        return max(options, key=lambda q: R.from_quat(q[[1, 2, 3, 0]]).apply([0., 0., 1.]) @ np.asarray(away, float))

    def tcp(self, hand):
        p, q = self.session.ee_pose(ARMS[hand])
        return np.asarray(p, float)-self.origin, np.asarray(q, float)

    def move(self, hand, pos, quat=None, *, linear=0, settle=4):
        """TCP of `hand` to `pos` (assembly frame); raises StageFailure if the IK cannot reach it or the hand stops
        short of it (blocked by something it ran into)."""
        try:
            error = self.P["move_ee"](ARMS[hand], np.asarray(pos, float)+self.origin, quat, linear=linear,
                                      settle=settle)
        except Exception as exc:     # PrimitiveError: no IK solution within tolerance
            raise StageFailure(f"{hand} cannot reach {np.round(pos, 3).tolist()}: {exc}") from exc
        for _ in range(5):              # the PD lags a long joint move: let it catch up before calling it blocked
            if error <= ARRIVAL_M:
                break
            self.hold(4)
            error = float(np.linalg.norm(np.asarray(pos, float)-self.tcp(hand)[0]))
        if error > ARRIVAL_M:
            raise StageFailure(f"{hand} stopped {error*1e3:.0f} mm from {np.round(pos, 3).tolist()} "
                               f"at {np.round(self.tcp(hand)[0], 3).tolist()}; touching {self.touching()}")
        return error

    def contacts(self, link):
        """[(other link, normal force N)] of the task entity's link `link` (e.g. "ring") now, strongest first."""
        world = self.session.env._world
        entities = (world.entities["robot"], world.entities["slotted_chain"])
        names = {l.idx: l.name for e in entities for l in e.links}
        c = self.session.env.privileged.get("world")["contacts"]
        out = {}
        for a, b, f in zip(np.asarray(c["link_a"]).tolist(), np.asarray(c["link_b"]).tolist(), np.asarray(c["force"])):
            na, nb = names.get(int(a), "table"), names.get(int(b), "table")
            if link in (na, nb):
                other = nb if na == link else na
                out[other] = round(out.get(other, 0.)+float(np.linalg.norm(f)), 3)
        return sorted(out.items(), key=lambda kv: -kv[1])

    def touching(self):
        """[(robot link, other link)] in contact now: with the task's parts, and left arm with right arm."""
        world = self.session.env._world
        robot, task = world.entities["robot"], world.entities["slotted_chain"]
        names = {link.idx: link.name for e in (robot, task) for link in e.links}
        pairs = set()
        for c in (robot.get_contacts(with_entity=task), robot.get_contacts()):
            for a, b in zip(c["link_a"].tolist(), c["link_b"].tolist()):
                na, nb = names.get(int(a), "table"), names.get(int(b), "table")
                if na.split("/")[0] != nb.split("/")[0] or "/" not in na+nb:
                    pairs.add(tuple(sorted((na, nb))))
        return sorted(pairs)

    def route(self, hand, target, quat, *, z_m=.12, side_x_m=.15):
        """TCP to above `target` at z_m: round the post on the hand's side (A right, B left; |x| = side_x_m) when the
        way crosses the post's plane (y = 0), so the hand and forearm never pass over it low."""
        p, _ = self.tcp(hand)
        side = side_x_m if hand == "A" else -side_x_m
        waypoints = [np.r_[p[:2], max(p[2], z_m)]]
        if (p[1] > 0) != (target[1] > 0) and min(abs(p[0]-side), abs(target[0]-side)) > 0:
            waypoints += [np.r_[side, p[1], z_m], np.r_[side, target[1], z_m]]
        waypoints.append(np.r_[target[:2], z_m])
        for w in waypoints:
            self.move(hand, w, quat, linear=3)

    def reach(self, hand, pos, quat=None, *, linear=0, settle=4):
        """move(), then once more by the measured TCP error (a low target is tracked a few mm high)."""
        pos = np.asarray(pos, float)
        self.move(hand, pos, quat, linear=linear, settle=settle)
        error = pos-self.tcp(hand)[0]
        if np.linalg.norm(error) > .002:
            self.move(hand, pos+error, quat, settle=settle)
        return float(np.linalg.norm(pos-self.tcp(hand)[0]))

    def place(self, hand, part, target, quat, *, linear=0, tries=2):
        """Move `hand` so that the part it holds is at `target`: by the hand-part offset, then corrected by the part's
        measured error (it sits in the fingers where it sits)."""
        from .session import scene
        offset = self.tcp(hand)[0]-scene(self.session).pos(part)
        self.move(hand, np.asarray(target, float)+offset, quat, linear=linear)
        for _ in range(tries):
            error = np.asarray(target, float)-scene(self.session).pos(part)
            if np.linalg.norm(error) < .004:
                break
            self.move(hand, self.tcp(hand)[0]+error, quat)
        return float(np.linalg.norm(np.asarray(target, float)-scene(self.session).pos(part)))

    def grip(self, hand, width, steps=15):
        self.P["set_gripper"](ARMS[hand], width, steps)

    def close(self, hand, steps=20):
        self.P["close_gripper"](ARMS[hand], steps)

    def width(self, hand):
        return round(float(self.session.gripper_width(ARMS[hand])), 4)

    def go_home(self, hand, *, up_m=.08):
        """Straight up from where it is, then the home joints."""
        p, q = self.tcp(hand)
        try:
            self.move(hand, p+[0., 0., up_m], q, linear=3)
        except StageFailure:
            pass
        self.P["move_joints"](ARMS[hand], self.home[ARMS[hand]], settle=4)

    def hold(self, steps):
        self.P["hold"](steps)


def from_home(H, hand, pos, quat):
    """TCP of `hand`, at its home joints, to `pos` (assembly frame) by a joint move to the pose's IK solution (as
    go_home() comes back). From home (the forearm roll and the wrist rotation nearly in line) the IK solutions of the
    work poses, and of the poses a few cm off home towards them, lie more than JUMP_RAD away on some joint: as a move()
    that is an IK jump, which the standard service refuses for an ee_pose row (not for a joint move)."""
    q, error, turn = H.session.ik(ARMS[hand], np.asarray(pos, float)+H.origin, quat)
    if error > .008 or turn > .2:         # move_ee's tolerance
        raise StageFailure(f"{hand} cannot reach {np.round(pos, 3).tolist()} from home: {error*1e3:.0f} mm")
    H.P["move_joints"](ARMS[hand], q, settle=4)
    for _ in range(5):                    # the PD lags a long joint move: let it catch up (as move() does)
        if np.linalg.norm(np.asarray(pos, float)-H.tcp(hand)[0]) <= ARRIVAL_M:
            break
        H.hold(4)


def turn_to(H, hand, pos, quat, n):
    """move() through n poses with the position and the orientation interpolated from the TCP's, so that each IK
    solution stays within JUMP_RAD of the joints through a large turn; held only at the end (as move_ee's linear
    waypoints)."""
    from scipy.spatial.transform import Rotation as R, Slerp
    p0, q0 = H.tcp(hand)
    turn = Slerp([0., 1.], R.from_quat([q0[[1, 2, 3, 0]], np.asarray(quat, float)[[1, 2, 3, 0]]]))
    for k in range(1, n+1):
        H.move(hand, p0+(np.asarray(pos, float)-p0)*k/n, turn(k/n).as_quat()[[3, 0, 1, 2]], settle=4 if k == n else 0)


def move_nj(H, hand, pos, quat, *, linear=0, settle=4):
    """H.move(hand, pos, quat, linear=linear, settle=settle) without an IK jump: a straight-line waypoint whose IK
    solution (move_ee's: seeded at the measured joints) lies more than JUMP_RAD from them is reached through TCP poses
    on the joint line to it (the FK of joint vectors at most JOINT_STEP_RAD apart): the same joint motion, commanded in
    poses whose IK starts next to its solution."""
    rb = H.session.robot
    arm = ARMS[hand]
    frame = rb.tcp_frames[arm]
    sl = [rb.arm_joints.index(n) for n in rb.groups[arm].arm_joints]
    pos, quat = np.asarray(pos, float), np.asarray(quat, float)
    p0 = H.tcp(hand)[0]
    k = max(1, int(linear))
    for j in range(1, k+1):
        pj = p0+(pos-p0)*j/k
        q0 = np.asarray(rb.arm_q(), float)
        q1, _ = rb.ik({frame: np.r_[pj+H.origin, quat]}, q0, 1e-4, 1e-3, 200)
        d = float(np.abs(q1[sl]-q0[sl]).max())
        n = int(np.ceil(d/JOINT_STEP_RAD)) if d > JUMP_RAD else 1
        for i in range(1, n):
            w = np.asarray(rb.fk(q0+(q1-q0)*i/n, [frame])[frame], float)
            H.P["move_ee"](arm, w[:3], w[3:], settle=0)
        if j < k:
            H.P["move_ee"](arm, pj+H.origin, quat, settle=0)
    H.move(hand, pos, quat, settle=settle)


def route_nj(H, hand, target, quat, *, z_m=.12, side_x_m=.15):
    """Hands.route() (round the post on the hand's side when the way crosses its plane) by move_nj."""
    p, _ = H.tcp(hand)
    side = side_x_m if hand == "A" else -side_x_m
    waypoints = [np.r_[p[:2], max(p[2], z_m)]]
    if (p[1] > 0) != (target[1] > 0) and min(abs(p[0]-side), abs(target[0]-side)) > 0:
        waypoints += [np.r_[side, p[1], z_m], np.r_[side, target[1], z_m]]
    waypoints.append(np.r_[target[:2], z_m])
    for w in waypoints:
        move_nj(H, hand, w, quat, linear=3)


def back_off(H, hand, d=.04):
    """`hand` opens and backs off d along its approach (what it held stays)."""
    from scipy.spatial.transform import Rotation as R
    p, q = H.tcp(hand)
    H.grip(hand, OPEN_M)
    H.hold(4)
    H.move(hand, p-R.from_quat(q[[1, 2, 3, 0]]).apply(H.session.robot.axes[ARMS[hand]][0])*d, q, linear=2)
