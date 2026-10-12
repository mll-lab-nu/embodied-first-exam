"""Shared runner pieces for the RopeThreading oracle / replay (needs a running Kit app).

Arms: numpy YAM kinematics (yam_kin.py, from the unchanged USD; verified vs Isaac by cast_keyhole) on the
measured joint positions. TCP frame (yam_kin): x = approach (finger base -> tip), y = jaw axis, z = x cross y;
the TCP is the centre between the two pads, fingertips at +0.037 m along x, pads ~74 x 65 mm (x by z).
A rope held across the pads runs along z_tcp.
"""
import hashlib, json, os, time
import numpy as np
import torch
from scipy.spatial.transform import Rotation as Rot

import yam_kin as K
import plan_np as PN
from plan_np import frame

OPEN = -0.0475
SL = {"left": slice(0, 6), "right": slice(7, 13)}
GI = {"left": 6, "right": 13}
ART = {"left": "left_arm", "right": "right_arm"}


def make_env(task, cameras=False, mode="evaluation"):
    from yamlab.utils.task_creation import create_task_environment
    env = create_task_environment(task_name=task, assets_instance_paths={}, mode=mode,
                                  observation_modalities=["proprioception"], num_envs=1, device="cpu",
                                  strip_cameras=not cameras)
    env.reset()
    return env


def frame(approach, jaw_hint, pos=None):
    a = np.asarray(approach, float); a = a / np.linalg.norm(a)
    j = np.asarray(jaw_hint, float); j = j - a * (a @ j); j = j / np.linalg.norm(j)
    T = np.eye(4); T[:3, :3] = np.c_[a, j, np.cross(a, j)]
    if pos is not None:
        T[:3, 3] = pos
    return T


def frame_az(approach, z_dir, pos=None):
    """Frame with x = approach and z (rope axis) ~ z_dir: jaw = z cross x."""
    a = np.asarray(approach, float); a = a / np.linalg.norm(a)
    z = np.asarray(z_dir, float); z = z - a * (a @ z); z = z / np.linalg.norm(z)
    return frame(a, np.cross(z, a), pos)


class EpisodeDone(Exception):
    """Raised by Runner.step at the first terminated/truncated step (YAMLab auto-resets the env after it)."""


class Runner:
    def __init__(self, env, out_dir):
        self.env, self.out = env, out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.arts = {s: env.scene[ART[s]] for s in ("left", "right")}
        self.jids = {s: [a.joint_names.index(f"joint{i}") for i in range(1, 7)] for s, a in self.arts.items()}
        self.fid = {s: a.joint_names.index("left_finger") for s, a in self.arts.items()}
        self.origin = env.scene.env_origins[0].cpu().numpy().astype(float)
        self.cur = torch.zeros(1, 14)
        for s in ("left", "right"):
            self.cur[0, SL[s]] = torch.tensor(self.q(s), dtype=torch.float32)
            self.cur[0, GI[s]] = OPEN
        self.q_home = {s: self.q(s).copy() for s in ("left", "right")}
        self.actions, self.rope_pos, self.rope_quat, self.tcp_log, self.qlog, self.rows = [], [], [], [], [], []
        self.first_success = None
        self.fix = PN.fixture_capsules(env.scn["rings"])
        self.min_clear = 0.004
        self.t0 = time.time()
        self.done = False

    # ---------------------------------------------------------------- state
    def q(self, s):
        return self.arts[s].data.joint_pos[0, self.jids[s]].cpu().numpy().astype(float)

    def finger(self, s):
        return float(self.arts[s].data.joint_pos[0, self.fid[s]])

    def tcp(self, s, q=None):
        T = K.fk_tcp(self.q(s) if q is None else q)
        return K.base_to_world(T, s)

    def centerline(self):
        return self.env.centerline(0)

    # ---------------------------------------------------------------- stepping
    def step(self, a=None):
        if a is not None:
            self.cur = a.clone()
        obs, r, term, trunc, info = self.env.step(self.cur)
        self.actions.append(self.cur[0].numpy().copy())
        pos, quat, _, _ = self.env.rope_state(0)
        self.rope_pos.append(pos.astype(np.float32)); self.rope_quat.append(quat.astype(np.float32))
        self.tcp_log.append(np.r_[self.tcp("left")[:3, 3], self.tcp("right")[:3, 3]].astype(np.float32))
        self.qlog.append(np.r_[self.q("left"), self.finger("left"), self.q("right"), self.finger("right")].astype(np.float32))
        g = info["goal"][0]
        row = dict(step=len(self.actions), success=bool(info["success"][0]), goal_now=bool(info["goal_now"][0]),
                   hold=int(info["goal_hold_steps"][0]),
                   **{k: g.get(k) for k in ("threaded", "quiet", "intact", "crossing_sequence", "thickness_clear", "ambiguous",
                                            "maximum_speed_m_s", "max_joint_gap_m", "strict_threaded", "strict_quiet",
                                            "strict_crossing_sequence")})
        self.rows.append(row)
        if row["success"] and self.first_success is None:
            self.first_success = len(self.actions)
        if not np.isfinite(pos).all():
            self.done = True
        self.done |= bool(term[0] or trunc[0])
        if self.done:
            self.term_info = dict(terminated=bool(term[0]), truncated=bool(trunc[0]), step=len(self.actions))
            raise EpisodeDone(self.term_info)
        return self.done

    def hold(self, n):
        for _ in range(n):
            if self.step():
                return True
        return False

    def set_grip(self, s, g, n=10):
        g0 = float(self.cur[0, GI[s]])
        for i in range(1, n + 1):
            a = self.cur.clone(); a[0, GI[s]] = g0 + (g - g0) * i / n
            if self.step(a):
                return True
        return False

    def other(self, s):
        return "right" if s == "left" else "left"

    def clear(self, s, q):
        o = self.other(s)
        g_open = float(self.cur[0, GI[s]]) < -0.02
        return PN.arm_clearance(s, q, self.fix, other=(o, self.cur[0, SL[o]].numpy().astype(float),
                                                     float(self.cur[0, GI[o]]) < -0.02), grip_open=g_open)

    def check_q(self, s, q, what):
        c = self.clear(s, q)
        if min(c.values()) < self.min_clear:
            raise RuntimeError(f"collision on {s} {what}: {c}")

    def plan_line(self, s, T_goal, n, q_start=None, max_jump=0.25):
        """Joint targets along a straight line (position lerp, rotation slerp) from the commanded pose."""
        q0 = self.cur[0, SL[s]].numpy().astype(float) if q_start is None else q_start
        T0 = self.tcp(s, q0)
        R = Rot.from_matrix(np.stack([T0[:3, :3], T_goal[:3, :3]]))
        from scipy.spatial.transform import Slerp
        sl = Slerp([0, 1], R)
        qs, q = [], q0
        for i in range(1, n + 1):
            f = i / n
            f = 0.5 - 0.5 * np.cos(np.pi * f)
            T = np.eye(4); T[:3, :3] = sl(f).as_matrix(); T[:3, 3] = T0[:3, 3] + f * (T_goal[:3, 3] - T0[:3, 3])
            qn, ok, ep, er = K.ik(K.world_to_base(T, s), q, iters=200, margin=0.02)
            ok = ok or (ep < 1.5e-3 and er < 3e-2)
            if not ok or np.abs(qn - q).max() > max_jump:
                raise RuntimeError(f"IK failed on {s} line at {i}/{n}: ok={ok} ep={ep:.4f} er={er:.4f} jump={np.abs(qn-q).max():.3f}")
            if i % 3 == 0 or i == n:
                self.check_q(s, qn, f"line {i}/{n}")
            qs.append(qn); q = qn
        return qs

    def run_q(self, s, qs, other=None):
        """Execute joint targets for arm s (and optionally a parallel list for the other arm)."""
        for i, q in enumerate(qs):
            a = self.cur.clone(); a[0, SL[s]] = torch.tensor(q, dtype=torch.float32)
            if other is not None:
                so, qo = other
                a[0, SL[so]] = torch.tensor(qo[min(i, len(qo) - 1)], dtype=torch.float32)
            if self.step(a):
                return True
        return False

    def move(self, s, T_goal, speed=0.05, min_steps=8, ang_speed=0.8):
        q0 = self.cur[0, SL[s]].numpy().astype(float)
        T0 = self.tcp(s, q0)
        dist = np.linalg.norm(T_goal[:3, 3] - T0[:3, 3])
        ang = np.linalg.norm(Rot.from_matrix(T_goal[:3, :3] @ T0[:3, :3].T).as_rotvec())
        n = max(min_steps, int(np.ceil(30 * max(dist / speed, ang / ang_speed))))
        try:
            return self.run_q(s, self.plan_line(s, T_goal, n))
        except RuntimeError as e:
            # short moves: a joint-space interpolation to the nearest collision-free IK solution stays close to the line
            if dist > 0.10 or ang > 0.5:
                raise
            for q in self._ik_all(s, T_goal):
                if np.abs(q - q0).max() < 0.6 and self._path_ok(s, q0, q)[0]:
                    qs = []
                    for i in range(1, n + 1):
                        f = 0.5 - 0.5 * np.cos(np.pi * i / n)
                        qs.append(q0 + f * (q - q0))
                    # check the TCP deviation from the straight line stays small
                    dev = max(np.linalg.norm(np.cross(self.tcp(s, qq)[:3, 3] - T0[:3, 3], (T_goal[:3, 3] - T0[:3, 3]) / max(dist, 1e-9)))
                              for qq in qs[::max(1, n // 8)])
                    if dev < 0.01:
                        print(f"[MOVE] {s}: line IK failed ({str(e)[:60]}); joint-space short move, max deviation {dev*1000:.1f} mm")
                        return self.run_q(s, qs)
            raise

    def reachable(self, s, T_goal, margin=0.05, grip_open=True):
        from reach_map import seeds_for
        Tb = K.world_to_base(T_goal, s)
        q0 = self.cur[0, SL[s]].numpy().astype(float)
        o = self.other(s)
        for sd in [q0] + seeds_for(Tb[:3, 3]):
            q, ok, ep, er = K.ik(Tb, sd, iters=200, margin=margin)
            if ok:
                c = PN.arm_clearance(s, q, self.fix, other=(o, self.cur[0, SL[o]].numpy().astype(float),
                                                            float(self.cur[0, GI[o]]) < -0.02), grip_open=grip_open)
                if min(c.values()) >= self.min_clear + 0.01:
                    return True
        return False

    def _path_ok(self, s, qa, qb, k=12):
        for f in np.linspace(1.0 / k, 1.0, k):
            c = self.clear(s, qa + (0.5 - 0.5 * np.cos(np.pi * f)) * (qb - qa))
            if min(c.values()) < self.min_clear:
                return False, c
        return True, None

    def _ik_all(self, s, T):
        from reach_map import seeds_for
        q0 = self.cur[0, SL[s]].numpy().astype(float)
        Tb = K.world_to_base(T, s)
        sols = []
        for sd in [q0] + seeds_for(Tb[:3, 3]):
            q, ok, ep, er = K.ik(Tb, sd, iters=300, margin=0.03)
            if ok and min(self.clear(s, q).values()) >= self.min_clear:
                sols.append(q)
        sols.sort(key=lambda q: np.abs(q - q0).max())
        return sols

    def via_poses(self, s):
        sgn = 1.0 if s == "left" else -1.0
        out = []
        for x, y, z in ((0.40, 0.30, 1.05), (0.35, 0.20, 1.10), (0.45, 0.10, 1.10), (0.30, 0.30, 1.00), (0.40, 0.0, 1.12)):
            for a in ((1, 0, 0), (0.7, 0, -0.7), (0, -sgn, 0), (0.7, -0.7 * sgn, 0)):
                T = frame(a, (0, 0, 1) if abs(a[2]) < 0.5 else (0, 1, 0)); T[:3, 3] = (x, sgn * y, z)
                out.append(T)
        return out

    def goto(self, s, T_goal, n):
        """Collision-checked joint-space move to an IK solution of T_goal: direct, else through one via pose."""
        q0 = self.cur[0, SL[s]].numpy().astype(float)
        sols = self._ik_all(s, T_goal)
        if not sols:
            raise RuntimeError(f"goto: no collision-free IK for {s} at the goal")
        last = None
        for q in sols[:6]:
            ok, c = self._path_ok(s, q0, q)
            if ok:
                return self.move_joints(s, q, n)
            last = c
        for Tv in self.via_poses(s):
            for qv in self._ik_all(s, Tv)[:2]:
                if not self._path_ok(s, q0, qv)[0]:
                    continue
                for q in sols[:6]:
                    if self._path_ok(s, qv, q)[0]:
                        self.move_joints(s, qv, n)
                        return self.move_joints(s, q, n)
        raise RuntimeError(f"goto: no collision-free path for {s} ({len(sols)} goal IK solutions; last direct clash {last})")

    def move_route(self, s, T_goal, speed=0.05, ang_speed=0.8):
        """Cartesian move: the straight line if it is IK-feasible and collision-free, else the shortest pair of lines
        through one via point (x 0.30..0.80, y -0.30..0.40, z at start/goal/mid height; orientation slerped)."""
        q0 = self.cur[0, SL[s]].numpy().astype(float)
        T0 = self.tcp(s, q0)

        def nsteps(Ta, Tb):
            dist = np.linalg.norm(Tb[:3, 3] - Ta[:3, 3])
            ang = np.linalg.norm(Rot.from_matrix(Tb[:3, :3] @ Ta[:3, :3].T).as_rotvec())
            return max(8, int(np.ceil(30 * max(dist / speed, ang / ang_speed))))
        try:
            return self.run_q(s, self.plan_line(s, T_goal, nsteps(T0, T_goal)))
        except RuntimeError as e:
            first = str(e)
        p0, pg = T0[:3, 3], T_goal[:3, 3]
        cands = []
        for x in np.arange(0.30, 0.81, 0.05):
            for y in np.arange(-0.30, 0.41, 0.05):
                for z in sorted({round(p0[2], 3), round(pg[2], 3), round(0.5 * (p0[2] + pg[2]), 3)}):
                    v = np.array([x, y, z])
                    cands.append((np.linalg.norm(v - p0) + np.linalg.norm(pg - v), v))
        cands.sort(key=lambda c: c[0])
        Rm = Rot.from_matrix(np.stack([T0[:3, :3], T_goal[:3, :3]]))
        from scipy.spatial.transform import Slerp
        for L, v in cands[:80]:
            f = np.linalg.norm(v - p0) / max(L, 1e-9)
            Tv = np.eye(4); Tv[:3, :3] = Slerp([0, 1], Rm)(f).as_matrix(); Tv[:3, 3] = v
            try:
                qa = self.plan_line(s, Tv, nsteps(T0, Tv), q_start=q0)
                qb = self.plan_line(s, T_goal, nsteps(Tv, T_goal), q_start=qa[-1])
            except RuntimeError:
                continue
            print(f"[ROUTE] {s}: direct failed ({first[:90]}); via {np.round(v, 3)}")
            return self.run_q(s, qa + qb)
        raise RuntimeError(f"move_route: no route for {s}; direct: {first}")

    def move_joints(self, s, q_goal, n):
        q0 = self.cur[0, SL[s]].numpy().astype(float)
        qs = [q0 + (0.5 - 0.5 * np.cos(np.pi * i / n)) * (np.asarray(q_goal) - q0) for i in range(1, n + 1)]
        return self.run_q(s, qs)

    # ---------------------------------------------------------------- dev checkpoints (development only)
    def snapshot(self, path, extra=None):
        rope = self.env.scene["rope"]
        d = dict(rope_root=rope.data.root_state_w.clone(), rope_q=rope.data.joint_pos.clone(),
                 rope_qd=rope.data.joint_vel.clone(), rope_tgt=rope.data.joint_pos_target.clone(), cur=self.cur.clone(),
                 n_actions=len(self.actions), extra=extra or {})
        for sd, art in self.arts.items():
            d[sd + "_q"] = art.data.joint_pos.clone(); d[sd + "_qd"] = art.data.joint_vel.clone()
            d[sd + "_tgt"] = art.data.joint_pos_target.clone()
        d["q_ready"] = getattr(self, "q_ready", None)
        torch.save(d, path)

    def restore(self, path):
        d = torch.load(path, weights_only=False)
        rope = self.env.scene["rope"]
        rope.write_root_state_to_sim(d["rope_root"])
        rope.write_joint_state_to_sim(d["rope_q"], d["rope_qd"])
        rope.set_joint_position_target(d["rope_tgt"])
        for sd, art in self.arts.items():
            art.write_joint_state_to_sim(d[sd + "_q"], d[sd + "_qd"])
            art.set_joint_position_target(d[sd + "_tgt"])
        self.cur = d["cur"].clone()
        if d.get("q_ready") is not None:
            self.q_ready = d["q_ready"]
        self.env.sim.forward()
        self.env.scene.update(0.0)
        return d["extra"]

    # ---------------------------------------------------------------- output
    def state_hash(self):
        return hashlib.sha256(np.ascontiguousarray(np.stack(self.rope_pos)).tobytes()).hexdigest()[:16]

    def save(self, extra=None):
        np.save(os.path.join(self.out, "actions.npy"), np.stack(self.actions))
        np.savez_compressed(os.path.join(self.out, "states.npz"), rope_pos=np.stack(self.rope_pos),
                            rope_quat=np.stack(self.rope_quat), tcp=np.stack(self.tcp_log), q=np.stack(self.qlog),
                            actions=np.stack(self.actions))
        with open(os.path.join(self.out, "goal_log.jsonl"), "w") as f:
            for r in self.rows:
                f.write(json.dumps(r) + "\n")
        last = self.rows[-1] if self.rows else {}
        m = dict(success=self.first_success is not None, first_success_step=self.first_success, steps=len(self.actions),
                 sim_time_s=len(self.actions) * self.env.step_dt, wall_time_s=time.time() - self.t0,
                 rope_state_sha16=self.state_hash(), final=last)
        if extra:
            m.update(extra)
        json.dump(m, open(os.path.join(self.out, "metrics.json"), "w"), indent=1, default=str)
        return m
