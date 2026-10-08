"""M4a, S4b -> S4a: the ring into the goal region (the task's success).

Start (states.s4b): every part but the ring inside the separator, the ring free and flat front right. End
(states.s4a): the ring inside the goal region, flat and quiet; the task's own goal check.

A takes the flat ring's tube on its +x side (pads across the tube, from above); lifted, the ring swings down and hangs
below the pads in the x-z plane. A carries it round the post's right side and behind it, sets its lowest point on the
table one ring radius +x of the goal's centre and lays it down by swinging the pads about that point to the table
towards -x, so it lies flat centred on the goal; then lets go and lifts clear.
"""
import numpy as np

from .motion import ARMS, OPEN_M, PAD_M, StageFailure, from_home
from .session import scene

GOAL_MARGIN_M = .015      # ring kept this far inside the goal square's edges
CARRY_Z_M = .27           # TCP height on the way round the post's right side (the hanging ring ~12 cm above the table)
SIDE_X_M = .17            # the way round: past the post's right side, then behind it
BEHIND_Y_M = .16
LAY_STEPS = 9             # waypoints of the arc that lays the ring down about its lowest point
LAY_DIR = np.array([-1., 0., 0.])     # the ring is laid down towards -x: the right arm reaches that arc (IK, 135-225 deg)
LIFT_M, LIFT_MOVES = .25, 8           # A's lift off the laid ring before it goes home, in this many moves (in 3, the
                                      # elbow and wrist turn 0.68 rad in one of them: an IK jump)


def ring_goal_centre(H):
    """The goal square's point nearest the right arm where the flat ring fits GOAL_MARGIN_M inside (assembly)."""
    task, lay = H.session.env._task, H.layout
    region = task.goal_region
    centre = np.asarray(region.center_xy_m)-task.origin[:2]
    room = np.asarray(region.half_size_m)-lay.ring_major_radius_m-lay.ring_tube_radius_m-GOAL_MARGIN_M
    return centre+np.clip(H.arm_base("A")-centre, -room, room)


def lowest_point(ring, lay):
    """The ring's lowest centreline point."""
    c, r = ring
    th = np.linspace(0., 2*np.pi, 72, endpoint=False)
    p = c+r.apply(lay.ring_major_radius_m*np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)]))
    return p[np.argmin(p[:, 2])]


def m4a(H):
    lay, task = H.layout, H.session.env._task
    s = scene(H.session)
    c = s.pos("ring")
    goal = ring_goal_centre(H)
    u = LAY_DIR
    grasp = c-lay.ring_major_radius_m*u
    grasp[2] = c[2]
    q = H.quat("A", [0., 0., -1.], u)
    H.grip("A", OPEN_M)
    from_home(H, "A", grasp+[0., 0., PAD_M+.08], q)
    H.reach("A", grasp+[0., 0., PAD_M], q, linear=4)
    H.close("A")
    H.note("ring taken", tcp=H.tcp("A")[0].round(4).tolist(), ring=c.round(4).tolist())
    H.move("A", np.r_[grasp[:2], CARRY_Z_M], q, linear=6)
    ring = scene(H.session).poses["ring"]
    if ring[0][2] < c[2]+.1:
        raise StageFailure(f"ring not lifted: {ring[0].round(3).tolist()}")
    pivot = np.r_[goal-lay.ring_major_radius_m*u[:2], lay.ring_tube_radius_m]
    for xy in ((SIDE_X_M, grasp[1]), (SIDE_X_M, BEHIND_Y_M), pivot[:2]):
        H.move("A", np.r_[xy, CARRY_Z_M], q, linear=4)
    # Where the hanging ring's lowest point is relative to the pads, measured.
    pads = H.tcp("A")[0]+[0., 0., -PAD_M]
    hang = lowest_point(scene(H.session).poses["ring"], lay)-pads
    H.note("ring hanging", hang=hang.round(4).tolist())
    H.move("A", pivot-hang+[0., 0., PAD_M+.01], q, linear=3)
    H.move("A", pivot-hang+[0., 0., PAD_M+.002], q, linear=2)
    radius = float(np.linalg.norm(hang))
    for th in np.linspace(np.pi/2, 0., LAY_STEPS)[1:]:
        H.move("A", pivot+radius*(np.cos(th)*u+[0., 0., np.sin(th)])+[0., 0., PAD_M+.002], q)
    H.grip("A", OPEN_M)
    H.note("ring set down", ring=scene(H.session).pos("ring").round(4).tolist(), goal=goal.round(4).tolist())
    p = H.tcp("A")[0]
    for z in np.arange(1, LIFT_MOVES+1)*LIFT_M/LIFT_MOVES:   # high first: the joint path home otherwise sweeps the parts
        if H.session.episode_end is not None:    # behind the base. The task's success ends the episode and the arm stays
            return                               # where it is: each further pose would be an IK jump from there
        H.P["move_ee"](ARMS["A"], p+[0., 0., z]+H.origin, q, settle=4)
    H.go_home("A", up_m=0.)
