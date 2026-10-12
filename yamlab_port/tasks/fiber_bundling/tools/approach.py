"""Collision-checked approach from the YAM home pose to the trunk grasp (numpy only).

cable_spheres(): spheres along the cable centreline from a pose dict; plan_approach(): Cartesian
segments through via points, IK-continuous, with the coarse gripper-box clearance at each step.
"""
import numpy as np
import yam_kin as K


def cable_spheres(pose, lay, step=0.006):
    S = []
    for n, (p, R) in pose.items():
        L = lay["links"][n]["length"]; kind = lay["links"][n]["kind"]
        r = 0.0012 if kind == "fiber" else 0.012
        if kind == "terminal":
            continue
        for t in np.arange(0, L+1e-9, min(step, L)):
            S.append(np.r_[p+R[:, 0]*t, r])
    return np.array(S)


def tcp_pose(p, R):
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = p - R[:, 2]*K.TCP_Z; return T  # link_6 pose for a TCP pose


def segment(q0, T_goal, n_steps):
    T0 = K.fk_all(q0, "left")[-1]
    out = []; q = q0.copy()
    w = K.rot_err(T_goal[:3, :3], T0[:3, :3]); ang = np.linalg.norm(w)
    for k in range(1, n_steps+1):
        u = k/n_steps; u = u*u*(3-2*u)
        if ang > 1e-9:
            kk = w/ang; a = ang*u
            Kx = np.array([[0, -kk[2], kk[1]], [kk[2], 0, -kk[0]], [-kk[1], kk[0], 0]])
            R = (np.eye(3)+np.sin(a)*Kx+(1-np.cos(a))*Kx@Kx) @ T0[:3, :3]
        else:
            R = T0[:3, :3]
        T = np.eye(4); T[:3, :3] = R; T[:3, 3] = T0[:3, 3]+(T_goal[:3, 3]-T0[:3, 3])*u
        q, pe, re = K.ik(T, q, "left", tcp_z=0.0, iters=100, tol=1e-7)
        out.append((q.copy(), pe, re))
    return out


def plan(q_home, vias, spheres, q_finger=-0.0475, speed=0.06, dt=1/30):
    """vias: list of link_6 target poses. Returns joint path, min clearance, max ik error."""
    path, clear, ikerr = [], np.inf, 0.0
    q = q_home.copy()
    for T in vias:
        T0 = K.fk_all(q, "left")[-1]
        d = np.linalg.norm(T[:3, 3]-T0[:3, 3]); ang = np.linalg.norm(K.rot_err(T[:3, :3], T0[:3, :3]))
        n = max(5, int(np.ceil(max(d/speed, ang/0.8)/dt)))
        for qq, pe, re in segment(q, T, n):
            path.append(qq); ikerr = max(ikerr, pe)
            clear = min(clear, K.clearance(qq, q_finger, spheres))
        q = path[-1]
    return path, clear, ikerr


def jpath(q0, q1, n):
    return [q0+(q1-q0)*(k/n) for k in range(1, n+1)]


MIDS = [None, np.array([0.5, 0, 0, 0, 0, 0.]), np.array([0.8, 0, 0, 0, 0, 0.]), np.array([0.6, 0.4, 0.3, 0, 0, 0.]),
        np.array([0.9, 0.6, 0.6, -0.3, 0, 0.])]


def joint_legs(q_home, q_mid, q_ready, n=60):
    if q_mid is None:
        return jpath(q_home, q_ready, n)
    return jpath(q_home, q_mid, n//2)+jpath(q_mid, q_ready, n)


def plan_grasp_approach(q_home, spheres, g, a, pitches=(45, 60), ups=(0.0, 0.05, 0.10), back=0.07, n_seeds=30,
                        n_mid=150, top=5):
    """Grasp of the jacket at point g (axis a): returns the best plan as a dict.

    Tool axis pitched `pitch` deg from vertical away from the robot (+x), closing axis across the jacket.
    ready = pre-grasp lifted by `up`; home -> mid -> ready in joint space, ready -> pre -> grasp Cartesian.
    Score = min clearance (coarse gripper boxes vs cable spheres; the grasped jacket zone is excluded on the
    Cartesian legs). Deterministic (fixed seeds)."""
    rng = np.random.default_rng(0); seeds = [rng.uniform(K.LOWER, K.UPPER) for _ in range(n_seeds)]
    far = spheres[(np.linalg.norm(spheres[:, :3]-g, axis=1) > 0.060) | (spheres[:, 3] < 0.005)]
    cands = []
    for pit in pitches:
        t = np.radians(pit); z = np.array([np.sin(t), 0, -np.cos(t)]); z -= (z @ a)*a; z /= np.linalg.norm(z)
        x = np.cross(a, z); x /= np.linalg.norm(x)
        for sx in (1, -1):
            R = np.column_stack([sx*x, np.cross(z, sx*x), z])
            Tg = tcp_pose(g, R); Tpre = Tg.copy(); Tpre[:3, 3] -= z*back
            for up in ups:
                Tr = Tpre.copy(); Tr[:3, 3] += np.array([0, 0, up])
                sols = []
                for s in seeds:
                    q, pe, re = K.ik(Tr, s, "left", tcp_z=0.0, iters=150)
                    if pe > 1e-4 or re > 1e-3 or any(np.linalg.norm(q-o) < 0.05 for o in sols):
                        continue
                    sols.append(q)
                    path, c2, e2 = plan(q, [Tpre, Tg] if up > 0 else [Tg], far)
                    margin = float(np.min(np.minimum(path[-1]-K.LOWER, K.UPPER-path[-1])))
                    if e2 < 1e-3 and margin > 0.05 and c2 > 0.005:
                        cands.append(dict(c2=c2, pitch=pit, sx=sx, up=up, q_ready=q, T_pre=Tpre, T_grasp=Tg, margin=margin))
    cands.sort(key=lambda d: -d["c2"])
    mids = [m for m in MIDS]+[rng.uniform([-0.5, 0, 0, -1.2, -0.8, -1.5], [1.2, 1.2, 1.2, 0.6, 0.8, 1.5]) for _ in range(n_mid)]
    best = None
    for cd in cands[:top]:
        for m in mids:
            c1 = min(K.clearance(qq, -0.0475, spheres) for qq in joint_legs(q_home, m, cd["q_ready"]))
            score = min(c1, cd["c2"])
            if best is None or score > best["score"]:
                best = dict(cd, score=score, q_mid=m, joint_clearance=c1, cart_clearance=cd["c2"])
    return best
