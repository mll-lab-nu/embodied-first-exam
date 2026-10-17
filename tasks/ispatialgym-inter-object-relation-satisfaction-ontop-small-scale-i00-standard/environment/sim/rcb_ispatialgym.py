"""
rcb_ispatialgym.py -- iSpatialGym's tooling in a standard task's trusted `sim` sidecar (docs/benchmarks/ispatialgym.md):
the frozen instance, loaded and judged by upstream's own code, the episode, its record and its fresh-process replay. The
agent never imports it: it reaches the robot through the service (server.py) only.

instance : a directory holding instance.json, the frozen START of the task, byte-identical in both twins and in the
           privileged agent's container (the scene template, the loader's template_meta keys and the start-only TRO, the
           objects without upstream's role names); on the scoring side also goal.json (what was taken out of upstream's
           TRO and template_meta: the targets, the goal camera pose, the variant; restored here and checked against
           upstream's own TRO by sha256), upstream.json (where it came from) and facts.json (measured here, `freeze`).
           Judged (goal.json present): the BDDL problem is the image's own copy (ispatialgym/assets/bddl), checked
           against upstream.json's sha256. Not judged (a privileged agent's container): the start-only problem the image
           build wrote (START_BDDL), nothing scores, no step budget.
           Both are written out in the layout run_isg loads a sampler output from, and loading is upstream's InstanceLoader (TRO state, hinges, grasps, a settle, the reset snapshot) with the
           evaluation configured as `run_isg --mode policy` configures it (the isg-v2 tolerances x 3), with upstream's settle-eval ON:
           success needs the goal and every target held over the last settle_steps (45) steps, the task's objects and the robot at rest; then
           upstream's texture wait (renders only, never steps).
episode  : one row of the R1Pro's 23-D JoyLo action per 30 Hz control step (env.step with one render: BEHAVIOR's
           observation convention, frames lag the physics by 2 steps). It ends at the first step at which upstream's
           geometric success holds under settle-eval (the BDDL goal and every measured target within tolerance at every
           step of the last settle_steps, the goal's objects and the robot at rest over them), or after max_steps =
           max(300, 2 x the demo's length) steps (run_isg's policy budget).
replay   : the recorded rows from the frozen instance in a fresh process; on Isaac only the first episode in a process is
           bit-exact, so determinism is fresh process == fresh process.
frames   : poses the agent sees are in the odometry frame: the robot's base_link at the start of the episode (x forward,
           y left, z up). Nothing in the world frame leaves this process.

CLI
  python rcb_ispatialgym.py freeze --instance DIR [--hold] [--probe N]   # facts.json: start hash, budget, tolerances, ...
  python rcb_ispatialgym.py replay --instance DIR --traj T.npz [--video V.mp4]   # one JSON line: the verdict and the hash
"""
from __future__ import annotations

import os
os.environ.setdefault("OMNIGIBSON_HEADLESS", "1")

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

CTRL_HZ = 30                # run_isg: action_frequency 30, physics_frequency 120
SUBSTEPS = 4
TOLERANCE_SCALE = 3.0       # run_isg --mode policy's default --tolerance-scale
SETTLE_EVAL = True          # upstream's settle-eval (subset.toml): with it off, a blind sweep of a held object's poses succeeds
SETTLE_STEPS = 45           # configs/eval.yaml settle_steps
IMAGE_SIZE, HEAD_APERTURE_MM = 1080, 40.0   # configs/eval.yaml: evaluation camera profile isg-v1 (the goal images')
TCP_FRAMES = {"left": "left_tcp", "right": "right_tcp"}
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])     # camera frame, OpenGL axes (x right, y up, z back) -> OpenCV (x right, y down, z forward)
POSE = ["x", "y", "z", "qx", "qy", "qz", "qw"]
KIN_TOL_POS_M, KIN_TOL_ROT_RAD, KIN_MAX_ITERS = 1e-3, 1e-2, 200
POSE_TOL_M, POSE_TOL_RAD = 2e-3, 2e-2       # a rebuilt start state counts as the frozen one within these (instance_ok)


def _log(*a: Any) -> None:
    print("[rcb_ispatialgym]", *a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- poses (as rcb_behavior.py)
def _R_of_xyzw(q) -> np.ndarray:
    x, y, z, w = np.asarray(q, dtype=np.float64).reshape(4) / max(1e-12, float(np.linalg.norm(q)))
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def _xyzw_of_R(R) -> np.ndarray:
    R = np.asarray(R, dtype=np.float64)
    t = R[0, 0] + R[1, 1] + R[2, 2]
    if t > 0:
        s = 2.0 * math.sqrt(t + 1.0); q = [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, 0.25 * s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]); q = [0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s, (R[2, 1] - R[1, 2]) / s]
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]); q = [(R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s, (R[0, 2] - R[2, 0]) / s]
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]); q = [(R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s, (R[1, 0] - R[0, 1]) / s]
    q = np.asarray(q); q = q / np.linalg.norm(q)
    return q if q[3] >= 0 else -q


def _T_of(pos, quat_xyzw) -> np.ndarray:
    T = np.eye(4); T[:3, :3] = _R_of_xyzw(quat_xyzw); T[:3, 3] = np.asarray(pos, dtype=np.float64).reshape(3)
    return T


def _pose7(T) -> list[float]:
    return [float(v) for v in T[:3, 3]] + [float(v) for v in _xyzw_of_R(T[:3, :3])]


def _rotvec(R) -> np.ndarray:
    """Axis * angle of the rotation R (the log map)."""
    c = max(-1.0, min(1.0, (float(np.trace(R)) - 1.0) / 2.0)); a = math.acos(c)
    if a < 1e-9:
        return np.zeros(3)
    if a > math.pi - 1e-6:
        ax = np.sqrt(np.maximum((np.diag(R) + 1.0) / 2.0, 0.0))
        i = int(np.argmax(ax)); ax[(i + 1) % 3] = math.copysign(ax[(i + 1) % 3], R[i, (i + 1) % 3]); ax[(i + 2) % 3] = math.copysign(ax[(i + 2) % 3], R[i, (i + 2) % 3])
        return ax / np.linalg.norm(ax) * a
    return np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) * (a / (2.0 * math.sin(a)))


def _np(x) -> np.ndarray:
    return np.asarray(x.cpu() if hasattr(x, "cpu") else x)


# --------------------------------------------------------------------------- kinematics (rcb_behavior.py's _Kin)
class _Kin:
    """The robot's kinematic model, read from the simulator's own articulation (every USD joint of the robot: its two
    bodies, joint frames and axis). Forward kinematics of the links below the base link for the trunk + arm joints `q`,
    analytic Jacobians and a damped-least-squares IK; every pose in the base-link frame. Pure numpy after construction."""

    def __init__(self, robot, stage, q_names: list[str], base_link: str):
        from pxr import Usd, UsdPhysics
        self.joints: dict[str, dict] = {}
        for prim in Usd.PrimRange(stage.GetPrimAtPath(robot.prim_path)):
            if not prim.IsA(UsdPhysics.Joint):
                continue
            b0, b1 = prim.GetRelationship("physics:body0").GetTargets(), prim.GetRelationship("physics:body1").GetTargets()
            if not b0 or not b1 or not all(str(b[0]).startswith(robot.prim_path + "/") for b in (b0, b1)) or \
                    (prim.HasAttribute("physics:excludeFromArticulation") and prim.GetAttribute("physics:excludeFromArticulation").Get()):
                continue
            tn = prim.GetTypeName()
            kind = "revolute" if "Revolute" in tn else "prismatic" if "Prismatic" in tn else "fixed" if "Fixed" in tn else None
            if kind is None:
                continue

            def frame(p, r):
                p = prim.GetAttribute(p).Get(); r = prim.GetAttribute(r).Get()
                im = r.GetImaginary()
                return _T_of([p[0], p[1], p[2]], [im[0], im[1], im[2], r.GetReal()])
            ax = prim.GetAttribute("physics:axis").Get() if prim.HasAttribute("physics:axis") else "X"
            self.joints[prim.GetName()] = {"parent": str(b0[0]).split("/")[-1], "child": str(b1[0]).split("/")[-1], "kind": kind,
                                           "T0": frame("physics:localPos0", "physics:localRot0"),
                                           "T1inv": np.linalg.inv(frame("physics:localPos1", "physics:localRot1")),
                                           "axis": "XYZ".index(str(ax).upper())}
        self.by_child = {j["child"]: n for n, j in self.joints.items()}
        self.base_link, self.q_names = base_link, list(q_names)
        self.qi = {n: i for i, n in enumerate(self.q_names)}
        kids: dict[str, list[str]] = {}
        for n, j in self.joints.items():
            kids.setdefault(j["parent"], []).append(n)
        self.order, todo = [], [base_link]
        while todo:
            p = todo.pop(0)
            for n in sorted(kids.get(p, [])):
                self.order.append(n); todo.append(self.joints[n]["child"])
        self.links = [base_link] + [self.joints[n]["child"] for n in self.order]
        self.chain = {}
        for link in self.links:
            ch, c = [], link
            while c in self.by_child and c != base_link:
                n = self.by_child[c]
                if n in self.qi:
                    ch.append(n)
                c = self.joints[n]["parent"]
            self.chain[link] = ch[::-1]
        missing = [n for n in self.q_names if n not in self.joints]
        assert not missing, f"joints not found in the robot's articulation: {missing}"

    def _motion(self, j: dict, v: float) -> np.ndarray:
        M_ = np.eye(4)
        if j["kind"] == "revolute":
            c, s = math.cos(v), math.sin(v); a = j["axis"]; b, d = (a + 1) % 3, (a + 2) % 3
            M_[b, b], M_[b, d], M_[d, b], M_[d, d] = c, -s, s, c
        elif j["kind"] == "prismatic":
            M_[j["axis"], 3] = v
        return M_

    def fk(self, q, want_joint_frames: bool = False):
        q = np.asarray(q, dtype=np.float64).reshape(-1)
        T = {self.base_link: np.eye(4)}; JF = {}
        for n in self.order:
            j = self.joints[n]
            Tj = T[j["parent"]] @ j["T0"]
            if n in self.qi:
                JF[n] = Tj
                Tj = Tj @ self._motion(j, float(q[self.qi[n]]))
            T[j["child"]] = Tj @ j["T1inv"]
        return (T, JF) if want_joint_frames else T

    def jacobian(self, JF: dict, link: str, p: np.ndarray, cols: list[int]) -> np.ndarray:
        Jm = np.zeros((6, len(cols)))
        on = set(self.chain[link])
        for k, i in enumerate(cols):
            n = self.q_names[i]
            if n not in on:
                continue
            j = self.joints[n]; a = JF[n][:3, j["axis"]]
            if j["kind"] == "revolute":
                Jm[:3, k] = np.cross(a, p - JF[n][:3, 3]); Jm[3:, k] = a
            else:
                Jm[:3, k] = a
        return Jm

    def solve(self, targets: dict, q0, cols: list[int], lo, hi, tol_p: float, tol_r: float, iters: int):
        """Damped least squares from q0 over the joints `cols`: targets = {name: (link, link_T_frame, base_T_target)}."""
        q = np.clip(np.asarray(q0, dtype=np.float64).copy(), lo, hi); W = 0.3

        def errors(qq):
            T, JF = self.fk(qq, True); out = {}
            for name, (link, off, Tt) in targets.items():
                Tc = T[link] @ off
                out[name] = (Tt[:3, 3] - Tc[:3, 3], _rotvec(Tt[:3, :3] @ Tc[:3, :3].T), Tc, link)
            return out, JF

        def cost(e):
            return sum(float(ep @ ep) + W * W * float(er @ er) for ep, er, _, _ in e.values())

        e, JF = errors(q); c = cost(e); lam = 1e-3
        for _ in range(max(1, int(iters))):
            if all(np.linalg.norm(ep) <= tol_p and np.linalg.norm(er) <= tol_r for ep, er, _, _ in e.values()):
                break
            J = np.vstack([np.vstack([Jm[:3], W * Jm[3:]]) for Jm in (self.jacobian(JF, link, Tc[:3, 3], cols) for _, _, Tc, link in e.values())])
            r = np.concatenate([np.concatenate([ep, W * er]) for ep, er, _, _ in e.values()])
            step_ok = False
            for _ in range(8):
                dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(J.shape[0]), r)
                s = float(np.max(np.abs(dq)))
                if s > 0.3:
                    dq *= 0.3 / s
                qn = q.copy(); qn[cols] = np.clip(q[cols] + dq, lo[cols], hi[cols])
                en, JFn = errors(qn); cn = cost(en)
                if cn < c:
                    q, e, JF, c = qn, en, JFn, cn; lam = max(lam * 0.3, 1e-6); step_ok = True
                    break
                lam *= 10.0
            if not step_ok:
                break
        err = {name: (float(np.linalg.norm(ep)), float(np.linalg.norm(er))) for name, (ep, er, _, _) in e.items()}
        return q, err, all(p <= tol_p and r_ <= tol_r for p, r_ in err.values())


# --------------------------------------------------------------------------- the session
START_BDDL = Path(os.environ.get("RCB_ISG_START_BDDL", "/opt/tools/activity_definitions"))   # privileged image (scrub.sh)


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def restore_goal(start: dict, goal: dict) -> tuple[dict, dict]:
    """upstream's TRO and template_meta from the frozen start and goal.json (mk_tasks.py split_instance's inverse),
    asserted equal to upstream's own TRO by sha256: a failed restore is a grader error, never a 0."""
    tro = json.loads(json.dumps(start["tro"]))
    isg = tro["ispatialgym"]
    isg.update(goal["tro_ispatialgym"])
    isg["scene"] = {**isg["scene"], **goal["tro_scene"]}
    meta = {**start["template_meta"], **goal["template_meta"]}
    if hashlib.sha256(canonical(tro)).hexdigest() != goal["tro_sha256"]:
        raise RuntimeError("goal.json does not restore upstream's TRO of this instance (sha256)")
    return tro, meta


def write_layout(start: dict, tro: dict, meta: dict) -> Path:
    """The eval dataset's layout upstream's loader reads (ispatialgym.eval.instances.template_files):
    scenes/<scene>/json/<prefix>_0_0_template{,-meta}.json and <prefix>_instances/<id>-tro_state.json."""
    import tempfile
    j = Path(tempfile.mkdtemp(prefix="rcb-isg-")) / "scenes" / str(meta["scene"]) / "json"
    (j / "frozen_task_start_instances").mkdir(parents=True)
    (j / "frozen_task_start_0_0_template.json").write_text(json.dumps(start["template"]))
    (j / "frozen_task_start_0_0_template-meta.json").write_text(json.dumps(meta))
    (j / "frozen_task_start_instances" / "instance-tro_state.json").write_text(json.dumps(tro))
    return j / "frozen_task_start_instances" / "instance-tro_state.json"


def _no_judge() -> None:
    """A privileged agent's simulator judges nothing: its instance has no targets and its BDDL problem one neutral goal
    atom (neutral_bddl.py), so upstream's task is kept from requiring a measured target at load, from ending an episode
    on that goal and from computing success or reward each step. Physics is not touched."""
    from omnigibson.tasks.task_base import BaseTask
    from omnigibson.termination_conditions.timeout import Timeout
    from ispatialgym.eval import metrics as MET
    from ispatialgym.tasks.ispatialgym_task import ISpatialGymTask as T
    MET.error_metric_case = lambda atoms, where="": "none"
    T._create_termination_conditions = lambda self: {"timeout": Timeout(max_steps=self._termination_config["max_steps"])}
    T._step_termination = lambda self, env, action, infos=None: BaseTask._step_termination(self, env=env, action=action, infos=infos)
    T.get_potential = lambda self, env, env_idx=0: 0.0


class Session:
    """One frozen instance in this process: load, step, observe, record. The first episode in a process is the exact one.
    Without goal.json (a privileged agent's container) nothing is judged and there is no step budget."""

    def __init__(self, instance: str | Path):
        t0 = time.time()
        self.dir = Path(instance)
        start = json.loads((self.dir / "instance.json").read_text())
        self.judge = judge = (self.dir / "goal.json").exists()
        self.up = json.loads((self.dir / "upstream.json").read_text()) if judge else {}
        fp = self.dir / "facts.json"
        self.facts = json.loads(fp.read_text()) if fp.exists() else None
        if judge:
            tro = write_layout(start, *restore_goal(start, json.loads((self.dir / "goal.json").read_text())))
        else:
            tro = write_layout(start, start["tro"], start["template_meta"])
        import torch as th
        import omnigibson as og
        from ispatialgym import single_env as SE
        from ispatialgym.activity import problem as P
        from ispatialgym.eval import instances as INST
        from ispatialgym.eval.executor import isg_info
        from ispatialgym.eval.loader import InstanceLoader
        from ispatialgym.eval.texture_wait import wait_for_textures
        from ispatialgym.tasks import ispatialgym_task as IT
        self.th, self.og, self.SE, self._isg_info = th, og, SE, isg_info
        if judge:                                     # run_isg's standard track (configs/eval.yaml), settle-eval on
            self.budget = INST.step_budget(self.up["max_steps"], settle_steps=SETTLE_STEPS, settle_eval=SETTLE_EVAL)
            problem = Path(P.problem_path(self.up["activity"], self.up["definition_id"]))
            if hashlib.sha256(problem.read_bytes()).hexdigest() != self.up["bddl_problem_sha256"]:
                raise RuntimeError(f"{problem} is not the BDDL problem this instance was frozen with (upstream.json)")
        else:
            _no_judge()
            IT.ACTIVITY_DEFINITIONS_ROOT = str(START_BDDL)                # the start-only problem the image build wrote
        L = InstanceLoader(str(tro), image_size=IMAGE_SIZE, head_aperture=HEAD_APERTURE_MM)
        L.build_env()
        if judge:
            L.task.configure_evaluation(SETTLE_EVAL, self.budget["settle_steps"])
        if not judge:   # the joints restore() holds through its settle and resets: its targets' instances, by name, taken
            grasps = L._restore_grasps   # where restore() takes them (its next call), so both modes settle alike
            def _held_then_grasps(records):
                L._articulation_q = {i: L.physical[i].get_joint_positions().clone() for i in start["held_articulations"] if i in L.physical}
                return grasps(records)
            L._restore_grasps = _held_then_grasps
        obs, _ = L.restore()
        self.tolerances = L.task.apply_tolerance_profile(TOLERANCE_SCALE) if judge else None
        self.loader, self.env, self.task, self.robot = L, L.env, L.task, L.robot
        self.head_camera = L.cam_key                                       # the goal image's camera
        self.texture_wait, o2 = wait_for_textures(lambda: SE.get_obs(self.env)[0], og.sim.render, self.robot.name, None)
        self.obs = o2 if o2 is not None else obs
        self.max_steps = int(self.budget["max_steps"]) if judge else None
        self.action_dim = int(self.robot.action_dim)
        self.odom = np.linalg.inv(self._base_world())                      # world -> the start's base_link frame
        self.n, self.success, self.done, self.reason, self.isg = 0, False, False, None, None
        self.success_step = None
        self.rows: list[np.ndarray] = []
        self._last = _np(L.hold.action()).astype(np.float32).reshape(-1)   # holds the start's targets (and any grasp)
        self._camfix = self._kinm = None
        self.start_sha = self.state_sha()
        self.start_poses = self.poses()
        self.load_s = round(time.time() - t0, 1)
        self.instance_exact = self.facts is None or self.start_sha == self.facts["start_sha"]
        self.instance_ok = self.facts is None or self.instance_exact or self._poses_match(self.facts["start_poses"])
        _log(f"loaded {self.up.get('subtask', self.dir)} in {self.load_s} s; start {self.start_sha}; max_steps {self.max_steps}")

    # ---- state
    def state_sha(self) -> str:
        st = self.og.sim.dump_state(serialized=True)
        if isinstance(st, dict):
            st = self.th.cat([self.th.as_tensor(v).flatten() for v in st.values()])
        return hashlib.sha1(self.th.as_tensor(st).detach().cpu().contiguous().numpy().tobytes()).hexdigest()[:16]

    def _base_world(self) -> np.ndarray:
        return _T_of(*[_np(x) for x in self.robot.get_position_orientation()])

    def poses(self) -> dict[str, list[float]]:
        """World poses of the task's physical objects and the robot's joints: what a rebuilt start state is compared on."""
        out = {k: _pose7(_T_of(*[_np(x) for x in v.get_position_orientation()])) for k, v in sorted(self.loader.physical.items())}
        out["robot_q"] = [float(v) for v in _np(self.robot.get_joint_positions())]
        return out

    def _poses_match(self, ref: dict) -> bool:
        cur = self.poses()
        if set(cur) != set(ref):
            return False
        for k, v in ref.items():
            a, b = np.asarray(cur[k]), np.asarray(v)
            if k == "robot_q":
                if a.shape != b.shape or float(np.max(np.abs(a - b))) > POSE_TOL_RAD:
                    return False
            elif float(np.linalg.norm(a[:3] - b[:3])) > POSE_TOL_M or \
                    float(np.linalg.norm(_rotvec(_R_of_xyzw(a[3:]) @ _R_of_xyzw(b[3:]).T))) > POSE_TOL_RAD:
                return False
        return True

    # ---- the episode
    def hold_action(self) -> np.ndarray:
        """The last row sent with the base velocity at 0: every other target (trunk, arms, grippers) held."""
        a = self._last.copy()
        a[_np(self.robot.controller_action_idx["base"]).astype(int)] = 0.0
        return a

    def step(self, action) -> bool:
        """One control step of `action` (23 floats); True once the episode is over (success or max_steps)."""
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.size != self.action_dim or not np.all(np.isfinite(a)):
            raise ValueError(f"an action is {self.action_dim} finite numbers")
        if self.done:
            raise RuntimeError(f"the episode is over ({self.reason})")
        self.obs, _, _, _, info = self.SE.step(self.env, self.th.as_tensor(a), n_render_iterations=1)
        self.n += 1; self._last = a; self.rows.append(a)
        if not self.judge:
            return False
        self.isg = self._isg_info(info)                                  # upstream's reader (OmniGibson nests it)
        if self.isg["official_success"]:
            self.success, self.done, self.reason, self.success_step = True, True, "success", self.n
        elif self.n >= self.max_steps:
            self.done, self.reason = True, "max_steps"
        return self.done

    def reset(self) -> None:
        """Back to the frozen start in this process (upstream's reset and re-restores: hinges, grasps, joint values). Only
        the first episode in a process is bit-exact; a fresh process is the exact start."""
        self.obs, _ = self.SE.reset(self.env)
        self.loader.restore_after_reset()
        self.robot.apply_action(self.loader.hold.action())
        self._last = _np(self.loader.hold.action()).astype(np.float32).reshape(-1)
        self.n, self.success, self.done, self.reason, self.isg, self.success_step = 0, False, False, None, None, None
        self.rows = []

    def status(self) -> dict[str, Any]:
        if not self.judge:
            return {"steps": self.n, "state_sha": self.state_sha()}
        isg = self.isg or {}
        return {"success": self.success, "steps": self.n, "max_steps": self.max_steps, "reason": self.reason,
                "success_step": self.success_step, "symbolic_success": bool(isg.get("symbolic_success")),
                "geometric_success": bool(isg.get("geometric_success")), "state_sha": self.state_sha(),
                "error_metric": (isg.get("evaluation") or {}).get("error_metric")}

    def save_trajectory(self, path: str | Path, meta: dict | None = None) -> None:
        rows = np.stack(self.rows) if self.rows else np.zeros((0, self.action_dim), np.float32)
        np.savez(path, actions=rows.astype(np.float32), subtask=self.up.get("subtask", ""), start_sha=self.start_sha,
                 meta=json.dumps(meta or {}))

    # ---- cameras (OpenCV axes; poses in the odometry frame)
    def cameras(self) -> list[str]:
        return sorted(n for n, s in self.robot.sensors.items() if hasattr(s, "image_width"))

    def _cam_view(self, sensor) -> np.ndarray:
        """World pose (OpenGL axes) the sensor's latest frame was rendered with (the renderer's view matrix: frames lag the
        physics by 2 control steps while the robot moves); before the first render, the prim's pose."""
        try:
            V = np.asarray(_np(sensor.camera_parameters["cameraViewTransform"]), dtype=np.float64).reshape(4, 4).T
            if np.any(V):
                return np.linalg.inv(V)
        except Exception:  # noqa: BLE001
            pass
        return _T_of(*[_np(x) for x in sensor.get_position_orientation()])

    def _cam_fixed(self) -> dict:
        if self._camfix is None:
            out = {}
            for n in self.cameras():
                s = self.robot.sensors[n]
                link = s.prim.GetParent().GetName()
                W, H = int(s.image_width), int(s.image_height)
                f = W * float(s.focal_length) / float(s.horizontal_aperture)
                T_link = _T_of(*[_np(x) for x in self.robot.links[link].get_position_orientation()])
                T_cam = _T_of(*[_np(x) for x in s.get_position_orientation()])
                out[n] = {"parent_link": link, "link_T_cam_cv": (np.round(np.linalg.inv(T_link) @ T_cam @ GL2CV, 6) + 0.0).tolist(),
                          "K": [[f, 0.0, W / 2.0], [0.0, f, H / 2.0], [0.0, 0.0, 1.0]], "size": [W, H]}
            self._camfix = out
        return self._camfix

    def frames(self, cams) -> dict[str, np.ndarray]:
        """RGB uint8 (H, W, 3) of the frame the last control step rendered, per camera."""
        o = self.obs[self.robot.name]
        return {c: np.ascontiguousarray(_np(o[c]["rgb"])[..., :3].astype(np.uint8)) for c in cams}

    def extrinsics(self, cams) -> dict[str, np.ndarray]:
        """Per camera, odometry frame -> camera (3x4, OpenCV axes) of its latest frame."""
        return {c: np.linalg.inv(self.odom @ self._cam_view(self.robot.sensors[c]) @ GL2CV)[:3] for c in cams}

    # ---- proprioception (odometry frame)
    def proprio_layout(self) -> tuple[list[str], dict]:
        r = self.robot; names = list(r.joints); base = set(_np(r.base_idx).tolist())
        jn = [n for i, n in enumerate(names) if i not in base]; nj = len(jn)
        lay = jn + [f"base_{k}" for k in POSE] + ["base_vx", "base_vy", "base_wz"] + [f"{a}_eef_{k}" for a in ("left", "right") for k in POSE] \
            + [f"{j}_vel" for j in jn] + ["left_gripper_opening", "right_gripper_opening"] + [f"{a}_tcp_{k}" for a in ("left", "right") for k in POSE] \
            + [f"{j}_effort" for j in jn]
        g = {"joint_pos": [0, nj, "measured joint positions of robot_spec.joints (rad; the fingers in m): trunk, the arms interleaved left/right, the fingers"],
             "base_pose": [nj, 7, "base_link pose in the odometry frame (the base_link at the start of the episode): x y z qx qy qz qw"],
             "base_twist": [nj + 7, 3, "base velocity in its own frame: forward and left (m/s), yaw rate (rad/s)"],
             "eef_pose": [nj + 10, 14, "left, then right end-effector pose (robot_spec.tcp *_eef_link) in the odometry frame"],
             "joint_vel": [nj + 24, nj, "measured joint velocities of robot_spec.joints (rad/s; fingers m/s)"],
             "gripper_opening": [2 * nj + 24, 2, "left, right: measured opening in m (the two fingers' travel summed)"],
             "tcp_pose": [2 * nj + 26, 14, "left, then right fingertip centre (robot_spec.tcp left_tcp / right_tcp) in the odometry frame"],
             "joint_effort": [2 * nj + 40, nj, "drive effort per joint of robot_spec.joints as PhysX measures it (N m; fingers N)"]}
        assert g["joint_effort"][0] + nj == len(lay)
        return lay, g

    def proprio_row(self) -> np.ndarray:
        r = self.robot; self._kin()
        base = _np(r.base_idx).tolist(); keep = [i for i in range(len(r.joints)) if i not in base]
        q, qd, eff = (_np(f()).astype(np.float64) for f in (r.get_joint_positions, r.get_joint_velocities, r.get_joint_efforts))
        Tb = self._base_world(); Rb = Tb[:3, :3]
        v = Rb.T @ _np(r.get_linear_velocity()).astype(np.float64); w = Rb.T @ _np(r.get_angular_velocity()).astype(np.float64)
        eef, tcp, opening = [], [], []
        for a in ("left", "right"):
            Te = self.odom @ _T_of(*[_np(x) for x in r.eef_links[a].get_position_orientation()])
            eef += _pose7(Te); tcp += _pose7(Te @ self._tcp[TCP_FRAMES[a]][1])
            opening.append(float(sum(q[i] for i in _np(r.gripper_control_idx[a]).tolist())))
        return np.concatenate([q[keep], _pose7(self.odom @ Tb), [v[0], v[1], w[2]], eef, qd[keep], opening, tcp, eff[keep]]).astype(np.float32)

    # ---- robot spec and stateless kinematics (base_link frame)
    def _kin(self) -> _Kin:
        if self._kinm is None:
            r = self.robot; names = list(r.joints)
            qn = [names[i] for i in _np(r.trunk_control_idx).tolist()] + [names[i] for a in ("left", "right") for i in _np(r.arm_control_idx[a]).tolist()]
            k = _Kin(r, self.og.sim.stage, qn, r.base_footprint_link_name)
            self._kin_lo = np.array([float(r.joints[n].lower_limit) for n in qn])
            self._kin_hi = np.array([float(r.joints[n].upper_limit) for n in qn])
            self._kin_reset = np.array([float(_np(r.reset_joint_pos)[names.index(n)]) for n in qn])
            tip = {a: float(np.mean(list(r.eef_to_fingertip_lengths[a].values()))) for a in ("left", "right")}
            self._tcp = {TCP_FRAMES[a]: (r.eef_link_names[a], _T_of([0.0, 0.0, tip[a]], [0.0, 0.0, 0.0, 1.0])) for a in ("left", "right")}
            keep = [r.base_footprint_link_name, *r.trunk_link_names, *[ln for a in ("left", "right") for ln in r.arm_link_names[a]],
                    *[r.eef_link_names[a] for a in ("left", "right")], *[f["parent_link"] for f in self._cam_fixed().values()]]
            self._kin_frames = {**{ln: (ln, np.eye(4)) for ln in dict.fromkeys(keep) if ln in k.links}, **self._tcp}
            self._kinm = k
        return self._kinm

    def robot_spec(self) -> dict:
        r = self.robot; self._kin(); names = list(r.joints); base = set(_np(r.base_idx).tolist())
        groups = (("trunk", r.trunk_control_idx), ("left_arm", r.arm_control_idx["left"]), ("right_arm", r.arm_control_idx["right"]),
                  ("left_gripper", r.gripper_control_idx["left"]), ("right_gripper", r.gripper_control_idx["right"]))
        joints = []
        for i, (n, j) in enumerate(r.joints.items()):
            if i in base:
                continue
            pris = "prismatic" in str(j.joint_type).lower()
            joints.append({"name": n, "type": "prismatic" if pris else "revolute", "unit": "m" if pris else "rad",
                           "position_limits": [float(j.lower_limit), float(j.upper_limit)],
                           "group": next(g for g, idx in groups if i in _np(idx).tolist())})
        grip, tcp = {}, {}
        for a in ("left", "right"):
            fi = _np(r.gripper_control_idx[a]).tolist(); lo, hi = float(r.joint_lower_limits[fi[0]]), float(r.joint_upper_limits[fi[0]])
            grip[a] = {"joints": [names[i] for i in fi], "opening_m": [round(2 * lo, 6), round(2 * hi, 6)], "tcp_frame": TCP_FRAMES[a],
                       "command": (f"gripper_{a}: one number in [-1, 1], the fingers' target as a fraction of their travel (-1 = closed at {lo:g} m "
                                   f"per finger, 1 = fully open at {hi:g} m). Closing on an object holds it (assisted grasping); the hand lets go "
                                   "only at 1, the fully open command.")}
            eef = r.eef_link_names[a]; link, off = self._tcp[TCP_FRAMES[a]]
            tcp[eef] = {"parent_link": eef, "link_T_frame": np.eye(4).tolist(), "definition": f"the {a} end-effector frame: z along the fingers"}
            tcp[TCP_FRAMES[a]] = {"parent_link": link, "link_T_frame": off.tolist(),
                                  "definition": f"the {a} fingertip centre: {off[2, 3] * 100:.2f} cm along +z of {eef}"}
        from ispatialgym.robot import r1pro as M
        return {"name": "R1Pro", "description": "Galaxea R1 Pro as iSpatialGym models it (BEHAVIOR-1K's R1Pro, JoyLo controllers): a holonomic "
                                                "wheeled base, a 4-joint trunk, two 7-joint arms with parallel-jaw grippers, a head camera, a wrist camera per arm",
                "base": {"type": "mobile", "root_link": r.base_footprint_link_name,
                         "command": f"base: 3 numbers in [-1, 1], a velocity command in the robot's own frame: forward, left, yaw rate, scaled to "
                                    f"{M.BASE_VEL_LIMITS[0]:g} m/s, {M.BASE_VEL_LIMITS[1]:g} m/s, {M.BASE_VEL_LIMITS[2]:g} rad/s; it holds until the next "
                                    "command, 0 stops"},
                "joints": joints, "grippers": grip, "tcp": tcp,
                "controller": {"type": "trunk and arms: absolute joint position targets (PD drives); base: velocity; grippers: smooth position",
                               "control_hz": CTRL_HZ, "physics_hz": CTRL_HZ * SUBSTEPS}}

    def kinematics_spec(self) -> dict:
        r, k = self.robot, self._kin()
        eef = [r.eef_link_names[a] for a in ("left", "right")]; tcp = [TCP_FRAMES[a] for a in ("left", "right")]
        return {"endpoint": "/kinematics", "joint_names": list(k.q_names), "frame": "base", "quaternion_order": "xyzw",
                "links": list(self._kin_frames), "tcp_frames": tcp, "ee_frames": eef, "ik_targets": eef + tcp,
                "ik": {"solver": "damped least squares from the seed (the targeted arms' joints first, then with the trunk)",
                       "seed_default": "the robot's reset configuration", "tol_pos_m": KIN_TOL_POS_M, "tol_rot_rad": KIN_TOL_ROT_RAD,
                       "max_iters": KIN_MAX_ITERS, "collision_checking": "none", "joint_limits": "enforced"},
                "stateless": True,
                "note": f"q = trunk + both arms (joint_names). Poses are in the base frame ({r.base_footprint_link_name}: x forward, y left, "
                        "z up) unless the request gives base_pose (the 7 base_pose proprio columns): then in the odometry frame."}

    def kinematics(self, req: dict) -> dict:
        k = self._kin(); n = len(k.q_names); spec = self.kinematics_spec()

        def vec(x, m, what):
            a = np.asarray(x, dtype=np.float64).reshape(-1) if x is not None else None
            if a is None or a.size != m or not np.all(np.isfinite(a)):
                raise ValueError(f"{what} must be {m} finite numbers")
            return a

        def pose(x, what):
            p = vec(x, 7, what); nq = float(np.linalg.norm(p[3:]))
            if nq < 1e-6:
                raise ValueError(f"{what}: quaternion has zero norm")
            return _T_of(p[:3], p[3:] / nq)
        Tw = pose(req["base_pose"], "base_pose") if req.get("base_pose") is not None else None
        frame = "odometry" if Tw is not None else "base"
        if req.get("op") == "fk":
            q = vec(req.get("q"), n, "q"); links = req.get("links") or list(self._kin_frames)
            bad = [ln for ln in links if ln not in self._kin_frames]
            if bad:
                raise ValueError(f"unknown links {bad}; known: {list(self._kin_frames)}")
            T = k.fk(q); pre = Tw if Tw is not None else np.eye(4)
            return {"ok": True, "op": "fk", "frame": frame, "poses": {ln: _pose7(pre @ T[self._kin_frames[ln][0]] @ self._kin_frames[ln][1]) for ln in links}}
        if req.get("op") != "ik":
            raise ValueError("op must be 'fk' or 'ik'")
        tg = req.get("targets")
        if not isinstance(tg, dict) or not tg or any(f not in spec["ik_targets"] for f in tg):
            raise ValueError(f"targets must map frames from {spec['ik_targets']} to poses")
        tol_p = float(req.get("tol_pos_m") or KIN_TOL_POS_M); tol_r = float(req.get("tol_rot_rad") or KIN_TOL_ROT_RAD)
        iters = int(req.get("max_iters") or KIN_MAX_ITERS)
        seed = self._kin_reset.copy() if req.get("seed") is None else np.clip(vec(req["seed"], n, "seed"), self._kin_lo, self._kin_hi)
        inv = np.linalg.inv(Tw) if Tw is not None else np.eye(4)
        targets = {f: (self._kin_frames[f][0], self._kin_frames[f][1], inv @ pose(p, f"targets[{f}]")) for f, p in tg.items()}
        trunk = list(range(4)); arms = sorted({k.qi[j] for f in targets for j in k.chain[targets[f][0]]} - set(trunk))
        best = None
        for cols in (arms, trunk + arms):
            q, err, ok = k.solve(targets, seed, cols, self._kin_lo, self._kin_hi, tol_p, tol_r, iters)
            if best is None or ok or sum(p + 0.3 * r_ for p, r_ in err.values()) < sum(p + 0.3 * r_ for p, r_ in best[1].values()):
                best = (q, err, ok)
            if ok:
                break
        q, err, ok = best; q = q.copy(); rest = [i for i in range(n) if i not in trunk + arms]; q[rest] = seed[rest]
        return {"ok": bool(ok), "op": "ik", "frame": frame, "q": [float(v) for v in q],
                "error": {f: {"pos_m": float(e[0]), "rot_rad": float(e[1])} for f, e in err.items()}}

    def close(self) -> None:
        try:
            self.og.shutdown()
        except BaseException:  # noqa: BLE001  (og.shutdown exits the process)
            pass


# --------------------------------------------------------------------------- CLI
class _Video:
    """Head-camera frames of an episode to an mp4 through ffmpeg (10 fps: every third control step, 540 px). The
    recording never decides a replay (PROTOCOL §4): a failure of the encoder disables it and is reported as `error`."""

    def __init__(self, path: str, size: int = 540, fps: int = 10):
        self.size, self.p, self.error, self.n = size, None, None, 0
        try:
            self.p = subprocess.Popen(
                ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size}x{size}", "-r", str(fps),
                 "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path], stdin=subprocess.PIPE)
        except Exception as exc:  # noqa: BLE001
            self.error = f"start: {exc!r}"[:300]

    def _fail(self, where: str, exc: BaseException) -> None:
        self.error = f"{where}: {exc!r}"[:300]
        try:
            self.p.kill()
        except Exception:  # noqa: BLE001
            pass
        self.p = None

    def add(self, frame) -> None:
        """`frame`: an RGB array, or a callable returning one (read only while the recording works)."""
        if self.p is None:
            return
        try:
            from PIL import Image
            rgb = frame() if callable(frame) else frame
            self.p.stdin.write(np.asarray(Image.fromarray(rgb).resize((self.size, self.size))).tobytes()); self.n += 1
        except Exception as exc:  # noqa: BLE001
            self._fail("frame", exc)

    def close(self) -> None:
        if self.p is None:
            return
        try:
            self.p.stdin.close(); rc = self.p.wait(timeout=900)
            if rc != 0:
                self.error = f"ffmpeg exit {rc}"
        except Exception as exc:  # noqa: BLE001
            self._fail("close", exc)


def joint_types(s: Session) -> dict[str, dict[str, str]]:
    """Per articulation target, the type of each measured joint ("revolute" | "prismatic"): the unit of its tolerance."""
    out = {}
    for inst, art in (s.loader.tro.meta.articulation_targets or {}).items():
        obj = s.loader.physical[inst]
        out[inst] = {j: ("prismatic" if "prismatic" in str(obj.joints[j].joint_type).lower() else "revolute") for j in art.joints}
    return out


class StepError(RuntimeError):
    """A control step of the replayed rows raised (after the start rebuilt): the trajectory's own outcome, not the host's."""

    def __init__(self, step: int, exc: BaseException):
        super().__init__(f"step {step}: {exc!r}"[:500]); self.step, self.kind = step, f"{type(exc).__name__}: {str(exc)[:120]}"


def run_rows(s: Session, rows: np.ndarray, video: str | None = None, info: dict | None = None) -> dict:
    vid = _Video(video) if video else None
    head = lambda: s.frames([s.head_camera])[s.head_camera]  # noqa: E731
    try:
        if vid is not None:
            vid.add(head)                                    # the start: a video even of an episode without actions
        for i, a in enumerate(rows):
            try:
                done = s.step(a)
            except (MemoryError, OSError) as exc:            # the host's, not the rows': stays an infrastructure failure
                raise RuntimeError(f"step {s.n}: {exc!r}") from exc
            except Exception as exc:  # noqa: BLE001
                if "OutOfMemory" in type(exc).__name__ or "CUDA" in str(exc)[:300]:
                    raise RuntimeError(f"step {s.n}: {exc!r}") from exc
                raise StepError(s.n, exc) from exc
            if vid is not None and i % 3 == 0:
                vid.add(head)
            if done:
                break
    finally:
        if vid is not None:
            vid.close()
            if info is not None:
                info.update({"video_frames": vid.n, **({"video_error": vid.error} if vid.error else {})})
    return s.status()


def cmd_replay(a) -> None:
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)    # a dead encoder is an EPIPE the recorder absorbs, never a kill
    out: dict[str, Any] = {"replays": []}
    try:
        s = Session(a.instance)
        out.update({"instance_matches": s.instance_ok, "instance_exact": s.instance_exact, "start_sha": s.start_sha})
        rows = np.load(a.traj)["actions"]
        st = run_rows(s, rows, a.video, out)
        out["replays"].append({**st, "rows": int(len(rows))})
    except StepError as exc:     # the rows themselves fail to step (the same step in every fresh process): sim_error
        import traceback; traceback.print_exc()
        out["error"] = str(exc); out["step_error"] = {"step": int(exc.step), "kind": exc.kind}
    except Exception as exc:  # noqa: BLE001
        import traceback; traceback.print_exc()
        out["error"] = repr(exc)[:500]
    print(json.dumps(out), flush=True)
    os._exit(0)                    # Kit's own shutdown can hang or crash after the result is out


def _probe_rows(s: Session, n: int) -> np.ndarray:
    """A fixed, smooth, seeded excursion from the start (base, trunk and arm targets, both grippers closing and opening):
    a determinism probe that moves the robot and whatever it touches. Not a solution of anything."""
    rng = np.random.default_rng(0); a0 = s.hold_action().astype(np.float64); idx = s.robot.controller_action_idx
    sl = {k: _np(v).tolist() for k, v in idx.items()}
    amp = np.zeros_like(a0); amp[sl["base"]] = 0.3; amp[sl["trunk"]] = 0.1; amp[sl["arm_left"] + sl["arm_right"]] = 0.4
    ph = rng.uniform(0, 2 * np.pi, a0.size); w = rng.uniform(0.2, 0.6, a0.size)
    t = np.arange(n)[:, None] / CTRL_HZ
    rows = a0 + amp * np.sin(2 * np.pi * w * t + ph) * np.minimum(1.0, t / 2.0)
    for g in ("gripper_left", "gripper_right"):
        rows[:, sl[g]] = np.where((t // 3) % 2 == 0, 1.0, -1.0)
    rows[:, sl["base"]] = np.clip(rows[:, sl["base"]], -1, 1)
    return rows.astype(np.float32)


def cmd_freeze(a) -> None:
    """Measure one instance in this process: its start state and, with --hold, the episode of holding still for the whole
    budget (it must not succeed); with --probe N, run the determinism probe's first N rows instead and save them."""
    s = Session(a.instance)
    facts = {"subtask": s.up["subtask"], "start_sha": s.start_sha, "start_poses": s.start_poses, "max_steps": s.max_steps,
             "settle_steps": int(s.budget["settle_steps"]), "action_dim": s.action_dim, "load_s": s.load_s,
             "tolerances": s.tolerances, "cameras": {c: f["size"] for c, f in s._cam_fixed().items()},
             "head_camera": s.head_camera, "joint_types": joint_types(s)}
    if a.hold:
        t0 = time.time()
        rows = np.tile(s.hold_action(), (s.max_steps, 1))
        st = run_rows(s, rows)
        facts["hold"] = {**st, "step_s": round((time.time() - t0) / max(1, st["steps"]), 3)}
    elif a.probe:
        rows = _probe_rows(s, a.probe)
        np.savez(a.out_traj, actions=rows)
        facts["probe"] = run_rows(s, rows)
    print("FACTS " + json.dumps(facts), flush=True)
    os._exit(0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--instance", required=True); f.add_argument("--hold", action="store_true")
    f.add_argument("--probe", type=int, default=0); f.add_argument("--out-traj", default="/tmp/probe.npz")
    r = sub.add_parser("replay"); r.add_argument("--instance", required=True); r.add_argument("--traj", required=True); r.add_argument("--video")
    a = p.parse_args()
    {"freeze": cmd_freeze, "replay": cmd_replay}[a.cmd](a)


if __name__ == "__main__":
    main()
