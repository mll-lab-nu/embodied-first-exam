"""Numpy forward/inverse kinematics of one YAM arm (joint1..6 + finger pads).

Chain constants are read from yamlab/robot/yam/arm/yam.usd (joint localPos0/localRot0/
localPos1/localRot1, revolute axis X; dumped with tools/inspect_yam.py on 2026-10-12).
Frames: world = YAMLab world; the arm base is at ROBOT.arm_position(side), identity rotation.
TCP = link_6 frame offset along its +z (tool axis) to the middle of the finger pads.
Validated against Isaac body poses by tools/check_kin.py.
"""
import numpy as np

def qmat(w, x, y, z):
    n = np.sqrt(w*w + x*x + y*y + z*z); w, x, y, z = w/n, x/n, y/n, z/n
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])

def tf(p, q):
    T = np.eye(4); T[:3, :3] = qmat(*q); T[:3, 3] = p; return T

# (localPos0, localRot0 wxyz, localPos1, localRot1 wxyz, lower deg, upper deg)
JOINTS = [
    ((0, 0, 0.0631), (0.5, 0.5, -0.5, 0.5), (0, 0, 0), (0.7071069, 0, -0.7071069, 0), -149.99977, 175.00021),
    ((0.000025, -0.020000005, 0.04090003), (0.7071069, 0.7071069, 0, 0), (0, 0, 0), (0.7071069, 0, -0.7071069, 0), 0.0, 209.9999),
    ((0.264, 0, 0), (0, 0.7071069, 0, -0.7071069), (0, 0, 0), (0.7071069, 0, -0.7071069, 0), 0.0, 209.9999),
    ((-0.245, -0.060000002, 7.45e-9), (0.7071069, 0, -0.7071069, 0), (0, 0, 0), (0.7071069, 0, -0.7071069, 0), -90.0002, 90.0002),
    ((-0.074, -0.039500043, 0.00002503395), (0.7071069, 0, 0, 0.7071069), (0, 0, 0), (0.7071069, 0, -0.7071069, 0), -90.0002, 90.0002),
    ((7.45e-9, 0.03530001, 0.039499998), (0.5, -0.5, -0.5, 0.5), (0, 0, 0), (0.70710695, 0, -0.70710695, 0), -120.00027, 120.00027),
]
PRE = [tf(np.array(a), b) for a, b, *_ in JOINTS]
POST = [np.linalg.inv(tf(np.array(c), d)) for _, _, c, d, *_ in JOINTS]
LOWER = np.radians([j[4] for j in JOINTS]); UPPER = np.radians([j[5] for j in JOINTS])
BASES = {"left": np.array([0.2525, 0.305, 0.76]), "right": np.array([0.2525, -0.305, 0.76])}
# Finger pads (link_6 frame): pad faces at x = +-(opening), y in [-0.0345, 0.0345], z in [0.088, 0.145].
TCP_Z = 0.1165          # middle of the pad z-range (0.088..0.145)
PAD_HALF_WIDTH = 0.0345 # pad half extent along link_6 y
PAD_Z = (0.088, 0.145)

def rx(a):
    c, s = np.cos(a), np.sin(a); T = np.eye(4); T[1:3, 1:3] = [[c, -s], [s, c]]; return T

def fk_all(q, side="left"):
    T = np.eye(4); T[:3, 3] = BASES[side]
    out = []
    for i in range(6):
        T = T @ PRE[i] @ rx(q[i]) @ POST[i]
        out.append(T.copy())
    return out  # link_1..link_6 world transforms

def tcp(q, side="left", tcp_z=TCP_Z):
    T6 = fk_all(q, side)[-1]
    T = T6.copy(); T[:3, 3] = T6[:3, 3] + T6[:3, 2]*tcp_z
    return T

def rot_err(Rd, R):
    E = Rd @ R.T
    ang = np.arccos(np.clip((np.trace(E)-1)/2, -1, 1))
    if ang < 1e-9: return np.zeros(3)
    v = np.array([E[2,1]-E[1,2], E[0,2]-E[2,0], E[1,0]-E[0,1]])
    s = np.sin(ang)
    if ang > np.pi - 1e-3:  # near pi
        w, V = np.linalg.eigh((E+E.T)/2); axis = V[:, np.argmax(w)]; return axis*ang
    return v/(2*s)*ang

def jac(q, side="left", tcp_z=TCP_Z, eps=1e-6):
    T0 = tcp(q, side, tcp_z); J = np.zeros((6, 6))
    for i in range(6):
        dq = q.copy(); dq[i] += eps; T1 = tcp(dq, side, tcp_z)
        J[:3, i] = (T1[:3, 3]-T0[:3, 3])/eps
        J[3:, i] = rot_err(T1[:3, :3], T0[:3, :3])/eps
    return J

def ik(Td, q0, side="left", tcp_z=TCP_Z, iters=300, tol=1e-6, rot_w=1.0, damping=1e-4, margin=0.02):
    """Damped least squares, joint limits clamped (with margin). Returns q, pos err, rot err."""
    q = np.array(q0, float)
    lo, hi = LOWER+margin, UPPER-margin
    # joint2/joint3 lower limit is 0 and the home pose sits on it: allow it exactly
    lo[1] = 0.0; lo[2] = 0.0
    for _ in range(iters):
        T = tcp(q, side, tcp_z)
        e = np.r_[Td[:3, 3]-T[:3, 3], rot_w*rot_err(Td[:3, :3], T[:3, :3])]
        if np.linalg.norm(e[:3]) < tol and np.linalg.norm(e[3:]) < tol: break
        J = jac(q, side, tcp_z); J[3:] *= rot_w
        dq = J.T @ np.linalg.solve(J @ J.T + damping*np.eye(6), e)
        n = np.linalg.norm(dq)
        if n > 0.2: dq *= 0.2/n
        q = np.clip(q+dq, lo, hi)
    T = tcp(q, side, tcp_z)
    return q, float(np.linalg.norm(Td[:3, 3]-T[:3, 3])), float(np.linalg.norm(rot_err(Td[:3, :3], T[:3, :3])))

if __name__ == "__main__":
    np.set_printoptions(precision=4, suppress=True)
    for i, T in enumerate(fk_all(np.zeros(6), "left")):
        print(f"link_{i+1}", T[:3, 3]-BASES["left"])
    print("link6 R\n", fk_all(np.zeros(6))[-1][:3, :3])


# ---------------- coarse gripper collision boxes (link_6 frame, from the USD collision meshes) ----------------
# (centre, half extents); fingers: one box per finger whose x-extent depends on the opening q (q in [-0.0475, 0]).
def gripper_boxes(q_finger):
    o = -float(q_finger)   # pad face distance from the closing plane (open: 0.0475)
    return [
        (np.array([0.0, 0.0, 0.0265]), np.array([0.0516, 0.0331, 0.0376])),            # link_6 body
        (np.array([o+0.0114, 0.0, 0.1084]), np.array([0.0124, 0.0345, 0.0370])),      # +x finger, pad part
        (np.array([-o-0.0114, 0.0, 0.1084]), np.array([0.0124, 0.0345, 0.0370])),     # -x finger, pad part
        (np.array([o-0.012, 0.021, 0.061]), np.array([0.037, 0.0134, 0.0105])),       # +x finger base
        (np.array([-o+0.012, -0.021, 0.061]), np.array([0.037, 0.0134, 0.0105])),     # -x finger base
    ]


def clearance(q, q_finger, spheres, side="left"):
    """Min signed distance between the gripper boxes and spheres (N,4: x,y,z,r) in world."""
    T6 = fk_all(q, side)[-1]
    P = (spheres[:, :3]-T6[:3, 3]) @ T6[:3, :3]
    best = np.inf
    for c, h in gripper_boxes(q_finger):
        d = np.linalg.norm(np.maximum(np.abs(P-c)-h, 0.0), axis=1)-spheres[:, 3]
        best = min(best, float(d.min()))
    return best
