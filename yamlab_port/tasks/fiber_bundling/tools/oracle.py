"""Scripted privileged-state oracle for FiberBundling (YAMLab, YAM left arm).

Method (port of the old planner topogym/planning/fiber_bundling, without the grasp weld):
  1. friction-grasp the trunk jacket behind the strand roots (left arm, tool pitched, fingers
     closing across the jacket; the pads also pinch the trunk_03/04/05 joints),
  2. comb every strand with the ring's outer surface (old comb_keyframes): offset the sheath
     beside the ring opposite the strand's fan direction, advance until the tip is just past
     the ring plane, move toward the ring so its outer surface presses the strand toward the
     sheath axis, slide back so the contact runs off the tip, back out, re-centre,
  3. feed straight along the ring axis (closed loop on the measured trunk_05 front pose) until
     the strands and the front face are past and clear, hold for the stable window.
Every control step: Cartesian target for the grasped trunk link -> hand target through the
measured grasp relation -> damped least-squares IK (numpy FK of the YAM chain) -> 14-D joint
targets. The action sequence is saved for open-loop replay.

Run (vast, physics only):
  YAMLAB_STRIP_CAMERAS=1 PYTHONPATH=<yamlab copy> python oracle.py --device cpu --out <dir> [--variant naive_offset]
"""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--task", default="FiberBundling-VeryEasy-v0")
p.add_argument("--out", required=True)
p.add_argument("--variant", default="oracle", choices=["oracle", "nop", "naive_nocomb", "naive_offset"])
p.add_argument("--pitch_deg", type=float, default=45.0)
p.add_argument("--grasp_back_m", type=float, default=0.070, help="grasp centre behind the trunk front face")
p.add_argument("--final_front_m", type=float, default=0.021, help="final front face position past the ring plane")
p.add_argument("--d_press_m", type=float, default=0.031)
p.add_argument("--speed", type=float, default=0.015, help="m/s for trunk moves")
p.add_argument("--max_steps", type=int, default=4000)
p.add_argument("--fiber_damping", type=float, default=None, help="EXPERIMENT ONLY: override strand joint damping at runtime")
p.add_argument("--squeeze", type=float, default=-0.0105, help="gripper target while holding (pads touch at -0.012)")
p.add_argument("--naive_offset_m", type=float, default=0.012, help="lateral feed offset of the naive_offset variant")
p.add_argument("--stop_after", default=None, help="stop after this phase (debug)")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app

import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yam_kin as K
import approach as A
from yamlab.utils.task_creation import create_task_environment
from yamlab.envs.tasks.fiber_bundling_goal import quat_wxyz_to_mat

OPEN, = [-0.0475]
os.makedirs(args.out, exist_ok=True)


def T_of(p, R):
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = p; return T


def slerp_R(R0, R1, u):
    w = K.rot_err(R1, R0)  # world-frame rotation vector from R0 to R1
    ang = np.linalg.norm(w)
    if ang < 1e-12: return R0.copy()
    k = w/ang; a = ang*u
    Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return (np.eye(3)+np.sin(a)*Kx+(1-np.cos(a))*Kx@Kx) @ R0


class Oracle:
    def __init__(self, env):
        self.env = env
        self.arm = env.scene["left_arm"]; self.rarm = env.scene["right_arm"]
        self.cab = env.scene["cable"]
        self.lay = env.layout
        self.c = np.array(self.lay["ring"]["center"]); self.n = np.array(self.lay["ring"]["normal"])
        self.i6 = self.arm.body_names.index("link_6")
        self.front = self.lay["trunk"]["names"][-1]
        self.L5 = self.lay["links"][self.front]["length"]
        self.q_cmd = self.arm.data.joint_pos[0, :6].cpu().numpy().astype(float)
        self.q_right = self.rarm.data.joint_pos[0, :6].cpu().numpy().astype(float)
        self.grip = OPEN
        self.log = dict(t=[], action=[], q=[], hand=[], links=[], force=[], success=[], failed=[], reached=[], phase=[],
                        front_offset=[], front_ahead=[], max_radial=[], max_bend=[], strand_net=[])
        self.actions = []
        self.phase = "start"
        self.done = False
        self.info = None
        self.events = []
        self.fail_reason = None; self.fail_step = None

    # ---------------- state ----------------
    def poses(self):
        pos = self.cab.data.body_link_pos_w[0].cpu().numpy().astype(float)
        R = quat_wxyz_to_mat(self.cab.data.body_link_quat_w[0].cpu().numpy().astype(float))
        return {n: (pos[i], R[i]) for i, n in enumerate(self.cab.body_names)}

    def hand(self):
        p6 = self.arm.data.body_link_pos_w[0, self.i6].cpu().numpy().astype(float)
        R6 = quat_wxyz_to_mat(self.arm.data.body_link_quat_w[0, self.i6].cpu().numpy().astype(float))
        return T_of(p6, R6)

    def T5(self):
        p, R = self.poses()[self.front]; return T_of(p, R)

    def front_point(self, T5=None):
        T5 = self.T5() if T5 is None else T5
        return T5[:3, 3]+T5[:3, 0]*self.L5

    def strand_rows(self):
        """Per strand: tip radius/direction from the trunk_05 axis, tip ahead of front, max radius."""
        P = self.poses(); p5, R5 = P[self.front]; a = R5[:, 0]; front = p5+a*self.L5
        rows = []
        for names in self.lay["fibers"]["names"]:
            pts = [P[n][0] for n in names]+[P[names[-1]][0]+P[names[-1]][1][:, 0]*self.lay["links"][names[-1]]["length"]]
            pts = np.array(pts); v = pts-p5; rad = v-np.outer(v @ a, a)
            t = np.diff(pts, axis=0); t /= np.linalg.norm(t, axis=1)[:, None]
            bend = np.degrees(np.arccos(np.clip(np.sum(t[:-1]*t[1:], 1), -1, 1))).max()
            rows.append(dict(tip_r=float(np.linalg.norm(rad[-1])), u=rad[-1]/max(np.linalg.norm(rad[-1]), 1e-9),
                             max_r=float(np.linalg.norm(rad, axis=1).max()), tip_ahead=float((pts[-1]-front) @ a),
                             bend=float(bend)))
        return rows

    # ---------------- stepping ----------------
    def step(self, q_left, grip):
        a = np.zeros(14, np.float32)
        a[:6] = q_left; a[6] = grip; a[7:13] = self.q_right; a[13] = OPEN
        self.q_cmd = np.array(q_left, float); self.grip = grip
        obs, r, term, trunc, info = self.env.step(torch.tensor(a).unsqueeze(0))
        self.actions.append(a.copy())
        self.info = info
        m = info["goal_metrics"][0]
        L = self.log
        # evaluated state of this step (taken before any auto-reset at the episode end)
        qe = self.env.last_eval_q["left_arm"][0]
        L["t"].append(len(self.actions)); L["action"].append(a.copy()); L["q"].append(qe.copy())
        L["hand"].append(K.fk_all(qe[:6].astype(float), "left")[-1]); L["phase"].append(self.phase)
        L["links"].append(self.env.last_eval_links[0].astype(np.float32))
        nf = self.env.strand_sensor.data.net_forces_w_history
        L["strand_net"].append(float(torch.linalg.norm(nf, dim=-1).max()) if nf is not None else np.nan)
        L["force"].append(m.get("strand_gripper_force_n", np.nan)); L["success"].append(bool(info["success"][0]))
        L["failed"].append(bool(info["failed"][0])); L["reached"].append(bool(info["goal_reached"][0]))
        L["front_offset"].append(m.get("front_radial_offset_m", np.nan)); L["front_ahead"].append(m.get("front_ahead_of_ring_m", np.nan))
        L["max_radial"].append(max(m.get("strand_max_radial_m", [np.nan]))); L["max_bend"].append(m.get("maximum_bend_deg", np.nan))
        if bool(info["failed"][0]) and self.fail_reason is None:
            self.fail_reason = info["failure_reason"][0]; self.fail_step = len(self.actions)-1
        if bool(term[0]) or bool(trunc[0]):
            self.done = True
        if len(self.actions) >= args.max_steps:
            self.done = True
        return info

    def hold(self, n, grip=None):
        for _ in range(n):
            if self.done: return
            self.step(self.q_cmd, self.grip if grip is None else grip)

    def ik6(self, T6, q0=None):
        q, pe, re = K.ik(T6, self.q_cmd if q0 is None else q0, "left", tcp_z=0.0, iters=100, tol=1e-7)
        if pe > 2e-4 or re > 2e-3:
            self.events.append(dict(step=len(self.actions), ik_pos_err=pe, ik_rot_err=re))
        return q

    def move_hand(self, T6_target, speed=0.05, ang_speed=0.6, grip=None):
        """Straight-line Cartesian move of the link_6 frame (commanded, open loop)."""
        T0 = K.fk_all(self.q_cmd, "left")[-1]
        d = np.linalg.norm(T6_target[:3, 3]-T0[:3, 3]); ang = np.linalg.norm(K.rot_err(T6_target[:3, :3], T0[:3, :3]))
        N = max(1, int(np.ceil(max(d/speed, ang/ang_speed)/self.env.step_dt)))
        for k in range(1, N+1):
            if self.done: return
            u = k/N; u = u*u*(3-2*u)
            T = T_of(T0[:3, 3]+(T6_target[:3, 3]-T0[:3, 3])*u, slerp_R(T0[:3, :3], T6_target[:3, :3], u))
            self.step(self.ik6(T), self.grip if grip is None else grip)

    def gripper(self, target, steps=20):
        g0 = self.grip
        for k in range(1, steps+1):
            if self.done: return
            self.step(self.q_cmd, g0+(target-g0)*k/steps)

    # ---------------- trunk moves (closed loop on the measured grasp relation) ----------------
    def measure_grasp(self):
        self.X = np.linalg.inv(self.hand()) @ self.T5()  # trunk_05 frame in link_6 frame
        return self.X

    def trunk_target(self, offset, s, R5):
        """trunk_05 pose whose front face centre is c + offset + s*n and axis along n."""
        p = self.c+np.asarray(offset)+(s-self.L5)*self.n
        return T_of(p, R5)

    def aligned_R(self, R5):
        """R5 rotated minimally so that its x axis is the ring normal (keeps the roll)."""
        x = R5[:, 0]; v = np.cross(x, self.n); s = np.linalg.norm(v); cth = float(x @ self.n)
        if s < 1e-12: return R5.copy()
        k = v/s; a = np.arctan2(s, cth)
        Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        return (np.eye(3)+np.sin(a)*Kx+(1-np.cos(a))*Kx@Kx) @ R5

    def move_trunk(self, offset, s, speed=None, settle=10, feedback=0.0):
        """Move the front face centre along a straight line to c+offset+s*n (axis along n).

        The hand command follows the trunk target through the grasp relation X measured at the start
        of the move; `feedback` adds a proportional correction of the measured front position error
        (fraction per control step), which keeps the jacket on the ring axis while feeding.
        """
        speed = speed or args.speed
        self.measure_grasp()
        T5 = self.T5(); R5d = self.aligned_R(T5[:3, :3])
        f0 = self.front_point(T5)
        f1 = self.c+np.asarray(offset)+s*self.n
        R0 = T5[:3, :3]
        N = max(1, int(np.ceil(np.linalg.norm(f1-f0)/speed/self.env.step_dt)))
        corr = np.zeros(3)
        for k in range(1, N+1+settle):
            if self.done: return
            u = min(k, N)/N; u = u*u*(3-2*u)
            f = f0+(f1-f0)*u
            R = slerp_R(R0, R5d, min(1.0, 3*u))
            if feedback > 0:
                err = f-self.front_point()
                corr = np.clip(corr+feedback*err, -0.003, 0.003)
            Tt = T_of(f+corr-R[:, 0]*self.L5, R)
            T6 = Tt @ np.linalg.inv(self.X)
            self.step(self.ik6(T6), self.grip)

    # ---------------- task phases ----------------
    def jacket_point(self, back):
        """Point on the jacket axis `back` metres behind the front face (walking the trunk links) + its axis."""
        P = self.poses(); names = self.lay["trunk"]["names"][::-1]
        rem = back
        for i, nm in enumerate(names):
            L = self.lay["links"][nm]["length"]
            if rem <= L or i == len(names)-1:
                p, R = P[nm]
                return p+R[:, 0]*(L-rem), R[:, 0]
            rem -= L

    def grasp(self, back=None, phase="grasp", squeeze=None):
        squeeze = args.squeeze if squeeze is None else squeeze
        self.phase = phase
        back = args.grasp_back_m if back is None else back
        g, a = self.jacket_point(back)                      # grasp centre on the jacket axis
        S = A.cable_spheres(self.poses(), self.lay)
        # The start state is fixed, so the approach plan is cached per (tier, grasp point).
        key = f"{self.lay['tier']}_{np.round(g, 5).tolist()}_{np.round(self.q_cmd, 5).tolist()}"
        cache = os.path.join(os.path.dirname(os.path.abspath(args.out)), f"approach_cache_{self.lay['tier']}.json")
        db = json.load(open(cache)) if os.path.exists(cache) else {}
        if key in db:
            plan = {k: (np.array(v) if isinstance(v, list) else v) for k, v in db[key].items()}
        else:
            plan = A.plan_grasp_approach(self.q_cmd, S, g, a)
            if plan is not None:
                db[key] = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in plan.items()}
                json.dump(db, open(cache, "w"))
        assert plan is not None and plan["score"] > 0.005, f"no collision-free grasp approach: {plan}"
        self.events.append(dict(step=len(self.actions), grasp_centre=g.tolist(), **{k: (v.tolist() if hasattr(v, "tolist") else v)
                                for k, v in plan.items()}))
        legs = ([plan["q_mid"]] if plan["q_mid"] is not None else [])+[plan["q_ready"]]
        for qt in legs:                                     # home -> (mid) -> ready, joint space
            q0 = self.q_cmd.copy(); N = 90
            for k in range(1, N+1):
                u = k/N; u = u*u*(3-2*u); self.step(q0+(qt-q0)*u, OPEN)
            self.q_cmd = np.array(qt, float)
        self.hold(10)
        if plan["up"] > 0:
            self.move_hand(plan["T_pre"], speed=0.03)
        self.move_hand(plan["T_grasp"], speed=0.02)
        self.hold(15)
        self.gripper(squeeze, steps=25)                      # pads at +-12 mm touch the jacket; 8 mm squeeze
        self.hold(20)
        self.measure_grasp()
        self.events.append(dict(step=len(self.actions), grasp_rel=self.X.tolist(),
                                finger=self.arm.data.joint_pos[0, 6:8].cpu().numpy().tolist()))

    def release(self, retreat=0.06):
        """Open the gripper and back the hand out along the tool axis."""
        self.gripper(OPEN, steps=20)
        self.hold(10)
        T = K.fk_all(self.q_cmd, "left")[-1]; T[:3, 3] -= T[:3, 2]*retreat
        self.move_hand(T, speed=0.03)

    def lift_out_of_cradle(self, back=0.110, dz=0.035):
        """Grasp the trunk just in front of the U cradle, lift it clear of the cradle walls, let go.

        The working trunk rests in the open U cradle (walls 14 mm above the axis, 4 mm side gap); its
        rear links must be out of the U before the sheath can be offset sideways for combing."""
        self.grasp(back=back, phase="lift")
        self.phase = "lift"
        T = K.fk_all(self.q_cmd, "left")[-1]; T[:3, 3] += np.array([0, 0, dz])
        self.move_hand(T, speed=0.01)
        self.hold(20)
        self.release()

    def comb(self, k, d_press, target=0.0115):
        rows = self.strand_rows(); r = rows[k]
        self.phase = f"comb_{k}"
        park = float((self.front_point()-self.c) @ self.n)
        u = r["u"]-(r["u"] @ self.n)*self.n; u /= np.linalg.norm(u)
        outer = self.lay["ring"]["inner_radius"]+2*self.lay["ring"]["tube_radius"]+self.lay["fibers"]["radius"]
        d0 = outer+r["tip_r"]+0.008
        approach = 0.004-r["tip_ahead"]
        select = max(park, approach-0.02); slide = approach-0.02
        self.events.append(dict(step=len(self.actions), comb=k, u=u.tolist(), d0=d0, d_press=d_press, approach=approach,
                                select=select, slide=slide, park=park, before=r))
        trace = []
        finished = False
        for lab, off, s_, sp in (("select", -d0*u, select, None), ("approach", -d0*u, approach, None),
                                 ("press", -d_press*u, approach, 0.01), ("slide", -d_press*u, slide, 0.01),
                                 ("release", -d0*u, slide, None), ("centre", np.zeros(3), park, None)):
            if lab == "release" and max(r["max_r"] for r in self.strand_rows()) <= target:
                # every strand is combed: re-centre straight from the press offset, slowly (backing out to
                # d0 and returning to the park position lets the combed strands spread again)
                self.move_trunk(np.zeros(3), slide-0.005, speed=0.005)
                trace.append(("recentre", [round(r["max_r"]*1000, 1) for r in self.strand_rows()]))
                finished = True
                break
            self.move_trunk(off, s_, speed=sp)
            trace.append((lab, [round(r["max_r"]*1000, 1) for r in self.strand_rows()]))
        self.events.append(dict(step=len(self.actions), comb_trace=trace, finished=finished))
        self.events.append(dict(step=len(self.actions), comb_done=k, after=self.strand_rows()[k]))
        return finished

    def comb_all(self, target=0.0115, accept=0.016, limit=None):
        """Old stages(): comb the strand farthest from the sheath axis until all are within target
        (at most 3 combs per strand); a residual within the tube's guiding band (16 mm) is accepted."""
        limit = limit or 3*len(self.lay["fibers"]["names"])
        presses = [args.d_press_m, args.d_press_m-0.001, args.d_press_m-0.002]
        for i in range(limit):
            if self.done: return
            rows = self.strand_rows()
            k = int(np.argmax([r["max_r"] for r in rows]))
            if rows[k]["max_r"] <= target: break
            if self.comb(k, presses[min(i//len(rows), 2)], target=target): break
        self.phase = "verify"; self.hold(15)
        rows = self.strand_rows()
        self.events.append(dict(step=len(self.actions), combed=rows, within_accept=bool(max(r["max_r"] for r in rows) <= accept)))

    def feed(self, final, offset=np.zeros(3)):
        self.phase = "feed"
        # Align on the axis first while backing off 10 mm (the combed tips sit just before the ring plane, so an
        # off-axis sheath must not move forward), then advance to the alignment station and feed.
        cur = float((self.front_point()-self.c) @ self.n)
        self.move_trunk(offset, min(cur-0.010, -0.045), speed=0.008, feedback=0.15)
        self.move_trunk(offset, -0.045, feedback=0.15)
        self.move_trunk(offset, final, speed=0.01, feedback=0.15, settle=0)
        self.phase = "hold"
        self.hold(60)


def main():
    env = create_task_environment(task_name=args.task, assets_instance_paths={}, mode="evaluation",
                                  observation_modalities=["proprioception"], num_envs=1, device=args.device or "cpu",
                                  timeout_steps=args.max_steps+10)
    obs, _ = env.reset(seed=0)
    if args.fiber_damping is not None:
        cab = env.scene["cable"]; fj = [i for i, n in enumerate(cab.joint_names) if n.startswith("fiber")]
        cab.write_joint_damping_to_sim(torch.full((1, len(fj)), args.fiber_damping), joint_ids=fj)
    o = Oracle(env)
    t0 = time.time()
    if args.variant == "nop":
        o.phase = "nop"
        o.hold(args.max_steps)
    else:
        o.lift_out_of_cradle()
        if args.stop_after != "lift":
            o.grasp()
        if args.stop_after in ("lift", "grasp"):
            pass
        elif args.variant == "oracle":
            o.comb_all()
            o.feed(args.final_front_m)
        elif args.variant == "naive_nocomb":       # skip combing: feed the fanned strands straight in
            o.feed(args.final_front_m)
        elif args.variant == "naive_offset":       # comb, then feed off the ring axis
            o.comb_all()
            o.feed(args.final_front_m, offset=np.array([args.naive_offset_m, 0, 0]))
        if not o.done:
            o.hold(30)
    wall = time.time()-t0
    L = o.log
    i_end = len(L["t"])-1
    success = any(L["success"]); failed = any(L["failed"])
    metrics = dict(task=args.task, variant=args.variant, success=bool(success), failed=bool(failed),
                   failure_reason=o.fail_reason, failure_step=o.fail_step,
                   steps=len(o.actions), sim_time_s=len(o.actions)*env.step_dt, wall_time_s=wall,
                   first_success_step=int(np.argmax(L["success"])) if success else None,
                   max_strand_gripper_force_n=float(np.nanmax(L["force"])) if L["force"] else None,
                   final_metrics=o.info["goal_metrics"][0] if o.info else None,
                   params=vars(args), events=o.events)
    np.save(os.path.join(args.out, "actions.npy"), np.array(o.actions, np.float32))
    np.savez_compressed(os.path.join(args.out, "states.npz"), action=np.array(L["action"]), q=np.array(L["q"]),
                        hand=np.array(L["hand"]), links=np.array(L["links"]), force=np.array(L["force"]),
                        success=np.array(L["success"]), failed=np.array(L["failed"]), reached=np.array(L["reached"]),
                        front_offset=np.array(L["front_offset"]), front_ahead=np.array(L["front_ahead"]),
                        max_radial=np.array(L["max_radial"]), max_bend=np.array(L["max_bend"]), strand_net=np.array(L["strand_net"]),
                        phase=np.array(L["phase"]), link_names=np.array(o.cab.body_names))
    json.dump(metrics, open(os.path.join(args.out, "metrics.json"), "w"), indent=1, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))
    print("RESULT", json.dumps({k: metrics[k] for k in ("variant", "success", "failed", "failure_reason", "steps", "sim_time_s", "wall_time_s",
                                                       "first_success_step", "max_strand_gripper_force_n")}))
    print("FINAL", json.dumps(metrics["final_metrics"], default=str))
    sys.stdout.flush(); os._exit(0)


main()
