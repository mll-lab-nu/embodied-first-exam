"""Plan R stage logic shared by the offline kinematic dry run and the Isaac oracle.

An executor provides: q(side), wand(), grasp(side) [link6 pose in the wand frame], run(side, qs, w_max, lin, tcp),
grip(side, value, steps), hold(n), phase(name), held_by(side_or_None, G) [offline bookkeeping].
"""
import numpy as np
from scipy.spatial.transform import Rotation
from grasps import pen, ring, T_from
from plan_r import (PlanError, frame_h_n, interp_T, n_steps, rrt_connect, densify, plan_grasp)

OPEN, CLOSED = -0.0475, 0.0
FQ_PEN, FQ_RING, FQ_OPEN_PEN, FQ_OPEN_RING = -0.0056, -0.0023, -0.0089, -0.0053
GUP, GDN, RG = pen("up", 0.033, -0.0275, 4.0), pen("down", 0.033, -0.0275, 4.0), ring()
HZ_HANDOVER1, BETA1, HZ_FINISH, YAW_HANDOVER2 = 0.055, 40.0, 0.062, -120.0


def Rz(d):
    return Rotation.from_euler("z", d, degrees=True).as_matrix()


def yaw_of(W):
    return np.degrees(np.arctan2(W[1, 0], W[0, 0]))


def wrap(d):
    """Signed yaw change in (-180, 180]."""
    return (d + 180.0) % 360.0 - 180.0


def back(T, d):
    return T @ T_from(np.eye(3), [0, 0, -d])


class StagesR:
    def __init__(self, P, ex, notes, skip_traverse=False):
        self.P, self.ex, self.notes = P, ex, notes
        self.s = P.s
        self.p0, self.p1 = self.s.rail[0, :2], self.s.rail[-1, :2]
        self.Rfd = (self.s.finish_R * Rotation.from_euler("x", 180, degrees=True)).as_matrix()
        self.ang_f = yaw_of(self.Rfd)
        self.skip_traverse = skip_traverse
        P.other_state = lambda: {sd: (ex.q(sd), ex.finger(sd)) for sd in ("left", "right")}

    # -------------------------------------------------------------- helpers
    def wand_moves(self, Ws_list):
        out = []
        for Wa, Wb in zip(Ws_list[:-1], Ws_list[1:]):
            out += interp_T(Wa, Wb, n_steps(Wa, Wb))
        return out

    def held_track(self, side, Ws, G, fq, lin, ignore=(), check_every=4):
        """Move the held wand through Ws (re-seeded from the measured joints)."""
        q0 = self.ex.q(side)
        T_now = self.P.ik[side].fk(q0[None])[0][0]
        Ts = [W @ G for W in Ws]
        Ts = interp_T(T_now, Ts[0], n_steps(T_now, Ts[0], lin=0.001)) + Ts[1:]
        qs, worst = self.P.track(side, Ts, q0, fq, ignore=ignore, check_every=check_every)
        self.ex.run(side, qs, lin=lin, tcp=[T[:3, 3] for T in Ts])
        return worst

    def grasp(self, side, T_grasp, follow_Ts, fq_open, fq_hold, name, approach_ignore=(), follow_ignore=(),
              other_parked=True, approach_axes=((0, 0, 1),)):
        o = "left" if side == "right" else "right"
        g = plan_grasp(self.P, side, self.ex.q(side), T_grasp, follow_Ts, fq_open, fq_hold,
                       approach_ignore=approach_ignore, follow_ignore=follow_ignore,
                       follow_other={o: (np.zeros(6), OPEN)} if other_parked else None, approach_axes=approach_axes)
        self.notes[f"{name}_approach_m"] = g["d"]
        self.ex.grip(side, fq_open, 10)  # the free path was planned with the fingers nearly closed
        self.free_path(side, g["path"])
        if g["slide"]:
            self.ex.run(side, g["slide"], lin=0.03, tcp=[T[:3, 3] for T in g["slide_T"]])
            self.ex.converge(side)
        self.notes[f"{name}_staging"] = None if g["staging"] is None else list(g["staging"])
        self.ex.grip(side, fq_open, 10)
        self.ex.run(side, g["approach"], lin=0.012, tcp=[T[:3, 3] for T in g["approach_T"]])
        self.ex.hold(10)
        self.ex.grip(side, CLOSED, 20)
        self.ex.hold(15)
        self.ex.attach(side, self.ex.grasp_meas(side))
        return self.ex.grasp(side)

    def free_path(self, side, path, w_max=0.15):
        """Execute an RRT path vertex by vertex, waiting for the arm to settle at each vertex (PD lag)."""
        for a, b in zip(path[:-1], path[1:]):
            self.ex.run(side, densify([a, b], 0.01), w_max=w_max)
            self.ex.converge(side)

    def release(self, side, G, d=0.05, park=True, fq_open=OPEN, from_tcp=False):
        """from_tcp: retreat relative to the gripper itself (after a drop the wand is no longer at the grasp)."""
        self.ex.grip(side, fq_open, 15)
        self.ex.detach(side)
        self.ex.hold(5)
        q0 = self.ex.q(side)
        T_now = self.P.ik[side].fk(q0[None])[0][0]
        T = T_now if from_tcp else self.ex.wand() @ G
        last = None
        opts = [(d, 0, 0), (0.03, 0, 0), (0.04, 0, -0.015), (0.03, 0, -0.025), (0.05, 0, -0.03), (0.02, 0, 0),
                (0.03, 0, 0.02), (0.02, -0.03, 0.0), (0.03, -0.05, 0.0), (0.01, -0.04, 0.005), (0.04, -0.06, 0.0)]
        for dd, dx, dz in opts:
            Tb = back(T, dd)
            Tb[0, 3] += dx
            Tb[2, 3] += dz
            Ts = interp_T(T_now, Tb, n_steps(T_now, Tb))
            try:
                qs, _ = self.P.track(side, Ts, q0, fq_open, ignore=("stops",))
                path = rrt_connect(self.P, side, qs[-1], np.zeros(6), fq_open) if park else None
                break
            except PlanError as e:
                last = e
        else:
            raise PlanError(f"{side} release retreat: {last}")
        self.ex.run(side, qs, lin=0.03, tcp=[x[:3, 3] for x in Ts])
        if park:
            self.free_path(side, path)
            self.ex.grip(side, OPEN, 10)

    # -------------------------------------------------------------- stages
    def run(self):
        s, ex, P = self.s, self.ex, self.P
        ex.hold(5)
        # 1-2: right G_up pick + lift with tilt (branch chosen so that the lift tracks)
        ex.phase("1_right_pick_start")
        W0 = ex.wand()
        h0 = W0[:3, 0].copy(); h0[2] = 0; h0 /= np.linalg.norm(h0)
        W1 = W0.copy(); W1[2, 3] += 0.003

        def lift_path(nodes):
            out = [W0, W1]
            for hz_, b_ in nodes:
                n_ = Rotation.from_rotvec(np.radians(b_) * h0).apply([0, 0, 1.0])
                out.append(T_from(frame_h_n(h0, n_), np.r_[self.p0, s.deck_top + hz_]))
            return out
        # (height, tilt) nodes from tools/lift_grid.py: tilting the loop normal away from the robot keeps the
        # wrist camera and forearm >= 18 mm below the span while the fingers stay >= 4 mm above the deck
        # end node (52 mm, -30 deg) also suits the left ring grip (tools/handover1_grid.py)
        lift_plans = [lift_path([(0.012, -10), (0.020, -20), (0.028, -30), (0.040, -30), (0.052, -30)]),
                      lift_path([(0.012, -10), (0.024, -20), (0.032, -30), (0.052, -30)]),
                      lift_path([(0.016, -10), (0.024, -20), (0.040, -20), (0.055, -20)])]
        last = None
        for Wl in lift_plans:
            try:
                Ws = self.wand_moves(Wl)
                G = self.grasp("right", W0 @ GUP, [W @ GUP for W in Ws], FQ_OPEN_PEN, FQ_PEN, "pick",
                               approach_ignore=("stops",), follow_ignore=("stops",))
                break
            except PlanError as e:
                last = e
                print("   lift plan rejected:", e, flush=True)
        else:
            raise PlanError(f"pick+lift: {last}")
        ex.phase("2_right_lift_tilt")
        W = ex.wand()
        Wl2 = [W] + Wl[1:]
        self.held_track("right", self.wand_moves(Wl2), G, FQ_PEN, lin=0.012, ignore=("stops",))
        ex.hold(15)
        Gr = G
        # 3: left ring grip (handover 1); its branch must carry the loop along the whole rail
        ex.phase("3_left_ring_handover")
        Wm = ex.wand()
        hz = Wm[2, 3] + 0.015
        Wm2 = Wm.copy(); Wm2[2, 3] = hz
        W3 = T_from(frame_h_n([1, 0, 0], [0, 0, 1]), np.r_[self.p0, hz])
        a1 = hz - s.rail[0, 2]
        a2 = s.arc[-1] - (s.deck_top + HZ_FINISH - s.rail[-1, 2])
        route = P.wand_route(a1, a2, h=(1, 0, 0))
        if self.skip_traverse:
            route = interp_T(W3, route[-1], n_steps(W3, route[-1]))
        carry = self.wand_moves([Wm, Wm2, W3]) + route
        Gl = self.grasp("left", Wm @ RG, [W @ RG for W in carry] if not self.skip_traverse else [], FQ_OPEN_RING, FQ_RING, "ring",
                        approach_axes=((0, 0, 1), (0, 1, 0), (0, -1, 0), (0, 0.7071, 0.7071), (0, -0.7071, 0.7071)))
        ex.phase("3b_right_release")
        self.release("right", Gr)
        ex.hold(10)
        # 4: left untilt/yaw + carry
        ex.phase("4_left_carry")
        W = ex.wand()
        self.held_track("left", self.wand_moves([W, Wm2, W3]), Gl, FQ_RING, lin=0.012)
        self.notes["carry_worst_clear_mm"] = {k: v * 1000 for k, v in
                                               self.held_track("left", route, Gl, FQ_RING, lin=0.02, check_every=8).items()}
        ex.hold(10)
        # 5: yaw the handle to -120 deg on the finish post
        ex.phase("5_left_yaw_finish")
        W = ex.wand()
        Wa = T_from(frame_h_n(W[:3, 0] * [1, 1, 0], [0, 0, -1]), np.r_[self.p1, W[2, 3]])
        # yaw to -75 deg at 62 mm, descend to 57 mm, finish the yaw there (tools/yaw2_grid.py: the left forearm
        # passes within 1-2 mm of the span at -90 deg if this is done at 62-70 mm)
        Wb = P.wand_yaw(Wa, self.p1, wrap(-75.0 - yaw_of(Wa)))[-1]
        Wc = Wb.copy(); Wc[2, 3] = s.deck_top + 0.057
        Ws = [Wa] + P.wand_yaw(Wa, self.p1, wrap(-75.0 - yaw_of(Wa))) + interp_T(Wb, Wc, n_steps(Wb, Wc)) + \
            P.wand_yaw(Wc, self.p1, wrap(YAW_HANDOVER2 - yaw_of(Wc)))
        self.held_track("left", Ws, Gl, FQ_RING, lin=0.012)
        ex.hold(15)
        # 6: right G_down (handover 2); its branch must lower the wand and yaw it to 180 deg on the deck
        ex.phase("6_right_gdown_handover")
        Wm = ex.wand()
        W6 = T_from(Rz(yaw_of(Wm) - self.ang_f) @ self.Rfd, np.r_[self.p1, s.finish_p[2] + 0.0015])
        Wy = P.wand_yaw(W6, self.p1, wrap(180.0 - yaw_of(W6)))
        follow = self.wand_moves([Wm, W6]) + Wy
        Gr = self.grasp("right", Wm @ GDN, [W @ GDN for W in follow], FQ_OPEN_PEN, FQ_PEN, "gdown",
                        follow_ignore=("stops",))
        ex.phase("6b_left_release")
        self.release("left", Gl, fq_open=-0.007)  # ring grip: open just enough (a wide-open finger would hit the deck)
        ex.hold(10)
        # 7: right lowers onto the deck, yaws to 180 deg, sets down, releases, parks
        ex.phase("7_right_lower_yaw")
        W = ex.wand()
        self.held_track("right", self.wand_moves([W, W6]), Gr, FQ_PEN, lin=0.008, ignore=("stops",))
        ex.hold(10)
        self.held_track("right", Wy, Gr, FQ_PEN, lin=0.01, ignore=("stops",))
        W = ex.wand()
        W7 = T_from(W[:3, :3], W[:3, 3] - [0, 0, 0.0012])
        self.held_track("right", [W7], Gr, FQ_PEN, lin=0.004, ignore=("stops",))
        ex.hold(10)
        ex.phase("7b_right_release")
        self.release("right", Gr)
        ex.hold(20)
        # 8: left G_down from the front, yaw to the finish pose, place, release, park
        ex.phase("8_left_gdown_final")
        Wm = ex.wand()
        Wl = T_from(Rz(yaw_of(Wm) - self.ang_f) @ self.Rfd, np.r_[self.p1, s.finish_p[2] + 0.0015])
        Wy = P.wand_yaw(Wl, self.p1, wrap(self.ang_f - yaw_of(Wl)))
        Wt = T_from(self.Rfd, s.finish_p + [0, 0, 0.0005])
        follow = [Wl] + Wy + [Wt]
        Gl = self.grasp("left", Wm @ GDN, [W @ GDN for W in follow], FQ_OPEN_PEN, FQ_PEN, "final",
                        approach_ignore=("stops",), follow_ignore=("stops",))
        W = ex.wand()
        self.held_track("left", [W, Wl] + Wy, Gl, FQ_PEN, lin=0.008, ignore=("stops",))
        for _ in range(2):
            W = ex.wand()
            self.held_track("left", interp_T(W, Wt, n_steps(W, Wt, lin=0.0005)), Gl, FQ_PEN, lin=0.004, ignore=("stops",))
            ex.hold(10)
        ex.phase("8b_left_release")
        self.release("left", Gl)
        ex.phase("9_settle")
        ex.hold(60)


class OfflineExecutor:
    """Kinematic stand-in: joints follow commands exactly; a grasped wand follows its holder."""

    def __init__(self, P, scene):
        self.P = P
        self.qs = {"left": np.zeros(6), "right": np.zeros(6)}
        self.W = T_from(scene.start_R.as_matrix(), scene.start_p)
        self.holder = None
        self.G = {}
        self.traj = []
        self.cur = "init"
        self.fingers = {}

    def q(self, side):
        return self.qs[side].copy()

    def finger(self, side):
        return self.fingers.get(side, OPEN)

    def wand(self):
        return self.W.copy()

    def grasp(self, side):
        return self.G[side]

    def grasp_meas(self, side):
        return np.linalg.inv(self.W) @ self.P.ik[side].fk(self.qs[side][None])[0][0]

    def attach(self, side, G):
        self.G[side] = G
        self.holder = side

    def detach(self, side):
        if self.holder == side:
            self.holder = None

    def run(self, side, qs, w_max=0.5, lin=None, tcp=None):
        for q in qs:
            self.qs[side] = np.array(q)
            if self.holder == side:
                T = self.P.ik[side].fk(self.qs[side][None])[0][0]
                self.W = T @ np.linalg.inv(self.G[side])
            self.traj.append((self.cur, side, np.array(q)))

    def converge(self, side):
        pass

    def grip(self, side, v, steps=15):
        self.fingers[side] = v if v < -0.001 else -0.0056  # closed on the tool

    def hold(self, n):
        pass

    def phase(self, name):
        self.cur = name
        print("phase", name, "wand", np.round(self.W[:3, 3], 4), flush=True)
