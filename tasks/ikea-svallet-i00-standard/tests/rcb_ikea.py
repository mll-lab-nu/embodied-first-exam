"""IKEA MuJoCo tooling (privileged mode): one furniture scene, plain MuJoCo 3.14.0 on the CPU (float64), the scene's own
runtime and mechanism (latched retention welds, spring jaws, ...), two robot arms of the scene's type.

    from rcb_ikea import Session
    s = Session("lack")                 # builds /opt/ikea/scenes/lack (scene.py load(): keyframe 'home')
    s.model, s.data                     # the MuJoCo model and data (privileged: read anything)
    s.step(row)                         # one control tick: data.ctrl[:] = row, then SUBSTEPS physics steps + mechanism
    s.status()                          # {'success', 'goal', 'released', 'at_rest', 'breakdown', 'rows', 'state_sha', ...}
    s.final_check()                     # the grader's verdict: status() now and after the SETTLE_S hold of the last row
    st = s.get_state(); s.set_state(st) # save / restore (physics, mechanism, monitor, the rows recorded so far)
    s.reset()                           # a fresh build of the scene: exactly the grader's initial state
    s.replay(ctrl)                      # reset, run the rows open-loop, return final_check()
    s.save_trajectory(path="/app/output/trajectory.npz")   # the rows recorded since the last reset (or pass ctrl)

The trajectory is replayed by the grader exactly like replay(): a fresh process builds the scene, then for every row
`data.ctrl[:] = row; S.step(SUBSTEPS)`. The verdict (verdict(), the benchmark's terminal rules on top of success.py):
  - at the end of your rows: success.py holds, no robot link touches any part (released), every part is at rest
    (linear speed <= REST_LIN_M_S, angular <= REST_ANG_RAD_S), and the simulation never broke down;
  - then the grader holds your last row for SETTLE_S more seconds (not recorded, not yours to change) and the same
    must hold again at its end (final_check());
  - a breakdown anywhere (a non-finite state, a MuJoCo BADQACC / BADQPOS / BADQVEL warning, a part contact deeper than
    BREAKDOWN_DEPTH_M) makes success impossible for the episode.

CLI (the grader's replay): python rcb_ikea.py replay --task lack --traj /app/output/trajectory.npz [--scene-dir D] [--out F]
Only mujoco and numpy are needed. Source: scripts/ikea_mujoco/shared/rcb_ikea.py (copied unchanged into every task).
"""
from __future__ import annotations

import argparse, copy, hashlib, importlib, json, os, re, sys, time

import numpy as np
import mujoco

SCENES_ROOT = os.environ.get("IKEA_SCENES", "/opt/ikea/scenes")
# A frozen scene reads nothing from the environment: one scene's mechanism lets SW_FROM_OP / SW_FROM_T override its
# sw_cutover.json (a development switch). The tooling, the grader's replays and the standard service drop them, so the
# physics is the pinned files' whatever the environment says.
SCENE_ENV_OVERRIDES = ("SW_FROM_OP", "SW_FROM_T")
for _k in SCENE_ENV_OVERRIDES:
    os.environ.pop(_k, None)
SUBSTEPS = 4                      # physics steps per control tick in every IKEA scene (the demos' layout)
MAX_ROWS = 50_000_000             # a sanity bound on the file, not a step budget
# Terminal rules (the benchmark's, on top of each scene's success.py; the same in every task and both modes)
SETTLE_S = 1.0                    # the grader holds the last row this long after the rows end, then checks again
REST_LIN_M_S = 0.01               # every part's linear speed at most this (m/s) ...
REST_ANG_RAD_S = 0.05             # ... and its angular speed at most this (rad/s), at the end
BREAKDOWN_DEPTH_M = 0.010         # a contact of a part deeper than this is a simulator breakdown
_BAD_WARNINGS = ("mjWARN_BADQACC", "mjWARN_BADQPOS", "mjWARN_BADQVEL")
# Speed clamp (the robots' real limits; clamp, not fail): every control tick a target moves at most limit x control
# tick from the target applied on the previous tick, in both modes, in the tooling and in the grader's replay
# (Session.step) - THE one table, the standard service reads it too. A row within limit + SPEED_TOL of the previous
# target is applied unchanged (bit for bit), so rows already within the limits (up to floating-point round-off) are never
# touched. Arm joints (rad/s): Franka Panda (Franka datasheet) j1-j4 2.1750, j5-j7 2.6100; ViperX 300 s (Interbotix
# vx300s) 3.14159 (the value the standard references were made with). Grippers: see GRIPPER_SPEED_LIMITS. The Franka
# Hand rule (318.75 units/s = 0.1 m/s of finger width, the hand's 0.05 m/s per finger, over the command's 255 units for
# 0.08 m) stops the instant-close finger slam (~2.5 m/s, 11.6 kN pad contacts; stress reproducer eket__mutate__s420015).
SPEED_TOL = 1e-9
JOINT_SPEED_LIMITS_RAD_S = {
    "panda": {f"actuator{i}": v for i, v in zip(range(1, 8), (2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61))},
    "viperx": {j: 3.14159 for j in ("waist", "shoulder", "elbow", "forearm_roll", "wrist_angle", "wrist_rotate")},
}
# The Franka Hand slew (318.75 command units/s = 0.1 m/s of finger width) is the long-term rule. It is off until the
# references are retimed for it in both modes; the current ones close faster and lose lack's and ikea365's goals under
# it (2026-10-16): GRIPPER_SPEED_LIMITS = {"panda": {"actuator8": 318.75}}.
GRIPPER_SPEED_LIMITS: dict = {}   # command units per second
# End-pose rule (the benchmark's, on top of a scene's success.py where the source grader checks only its operations'
# history): every listed part must end within POS_M / ANGLE_DEG of its goal pose in the frame of FRAME. EKET: the
# source grader accepts the back's slide once and never looks at the back again (it has no frame joint), so a back
# pulled out again after its slide and the bottom fitted without it passed (review of PR #299, 2026-10-17). The bound is
# loose on purpose: the reference's back ends 5.0 mm from its goal (the bottom's insertion pushes it after its slide was
# accepted), while the back's slide travels 0.30 m, so a removed back is far outside it.
END_POSE_RULES = {
    "eket": {"frame": "top", "goals": "goals_in_top_frame", "parts": ("top", "bottom", "side_a", "back", "side_b"),
             "pos_m": 0.010, "angle_deg": 2.0},
}


def joint_speed_limits(actuators: list) -> np.ndarray:
    """rad/s per actuator (inf: not limited, the grippers), from the actuator names (`left_` / `right_` + joint, or
    `left/` / `right/` + joint in the scenes that name the arms MuJoCo Menagerie's way)."""
    out = np.full(len(actuators), np.inf)
    for i, n in enumerate(actuators):
        j = re.sub(r"^(left|right)[_/]", "", n)
        for table in (*JOINT_SPEED_LIMITS_RAD_S.values(), *GRIPPER_SPEED_LIMITS.values()):
            if j in table:
                out[i] = table[j]
    return out


class InvalidTrajectory(ValueError):
    pass


def file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def scene_files(scene_dir: str) -> dict:
    """relative path -> sha256 of every file of a staged scene directory (caches excluded)."""
    out = {}
    for root, dirs, files in os.walk(scene_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            p = os.path.join(root, f)
            out[os.path.relpath(p, scene_dir)] = file_sha(p)
    return out


def digest(files: dict) -> str:
    return hashlib.sha256("".join(f"{k} {files[k]}\n" for k in sorted(files)).encode()).hexdigest()


def robot_bodies(model) -> np.ndarray:
    """Bodies of the robot: every body tree under the world that carries an actuated joint (the arms with their hands)."""
    roots = set()
    for a in range(model.nu):
        if int(model.actuator_trntype[a]) in (int(mujoco.mjtTrn.mjTRN_JOINT), int(mujoco.mjtTrn.mjTRN_JOINTINPARENT)):
            roots.add(int(model.body_rootid[model.jnt_bodyid[model.actuator_trnid[a, 0]]]))
        elif int(model.actuator_trntype[a]) == int(mujoco.mjtTrn.mjTRN_TENDON):
            t = int(model.actuator_trnid[a, 0])
            for w in range(int(model.tendon_adr[t]), int(model.tendon_adr[t]) + int(model.tendon_num[t])):
                if int(model.wrap_type[w]) == int(mujoco.mjtWrap.mjWRAP_JOINT):
                    roots.add(int(model.body_rootid[model.jnt_bodyid[int(model.wrap_objid[w])]]))
    return np.array([b for b in range(model.nbody) if int(model.body_rootid[b]) in roots], dtype=np.int64)


def part_bodies(model) -> np.ndarray:
    """Bodies of the parts: every movable body (some joint on its path to the world) that is not the robot's."""
    robot = set(robot_bodies(model).tolist())
    out = []
    for b in range(1, model.nbody):
        p, moving = b, False
        while p > 0:
            if model.body_dofnum[p] > 0:
                moving = True
                break
            p = int(model.body_parentid[p])
        if moving and b not in robot:
            out.append(b)
    return np.array(out, dtype=np.int64)


class Validity:
    """The terminal rules' measurements on a live MuJoCo data (read-only): breakdown evidence on every control tick,
    and released / at rest on demand."""

    def __init__(self, model, data):
        self.m, self.d = model, data
        self.robot = robot_bodies(model)
        self.parts = part_bodies(model)
        self.is_robot = np.zeros(model.nbody, bool); self.is_robot[self.robot] = True
        self.is_part = np.zeros(model.nbody, bool); self.is_part[self.parts] = True
        self.geom_body = np.asarray(model.geom_bodyid)
        self._warn_idx = [int(getattr(mujoco.mjtWarning, w)) for w in _BAD_WARNINGS]
        self.reset()

    def reset(self):
        self.breakdown = None
        self.max_part_depth_m = 0.
        self.ticks = 0
        self._warn0 = [int(self.d.warning[i].number) for i in self._warn_idx]

    def state(self) -> dict:
        return dict(breakdown=copy.deepcopy(self.breakdown), max_part_depth_m=self.max_part_depth_m, ticks=self.ticks,
                    warn0=list(self._warn0))

    def set_state(self, st: dict):
        self.breakdown = copy.deepcopy(st["breakdown"]); self.max_part_depth_m = st["max_part_depth_m"]
        self.ticks = st["ticks"]; self._warn0 = list(st["warn0"])

    def tick(self):
        self.ticks += 1
        d = self.d
        if self.breakdown is None and not (np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all()):
            self.breakdown = dict(kind="non_finite_state", tick=self.ticks)
        if self.breakdown is None:
            for w, i, n0 in zip(_BAD_WARNINGS, self._warn_idx, self._warn0):
                if int(d.warning[i].number) > n0:
                    self.breakdown = dict(kind="warning", warning=w, tick=self.ticks)
                    break
        n = int(d.ncon)
        if n:
            c = d.contact
            b1, b2 = self.geom_body[c.geom1[:n]], self.geom_body[c.geom2[:n]]
            sel = self.is_part[b1] | self.is_part[b2]
            if sel.any():
                dist = np.asarray(c.dist[:n])[sel]
                k = int(np.argmin(dist))
                depth = -float(dist[k])
                if depth > self.max_part_depth_m:
                    self.max_part_depth_m = depth
                if depth > BREAKDOWN_DEPTH_M and self.breakdown is None:
                    i = np.flatnonzero(sel)[k]
                    self.breakdown = dict(kind="extreme_penetration", tick=self.ticks, depth_mm=round(1000 * depth, 3),
                                          bodies=[self.m.body(int(b1[i])).name, self.m.body(int(b2[i])).name])

    def robot_part_contacts(self) -> list:
        n = int(self.d.ncon)
        if not n:
            return []
        c = self.d.contact
        b1, b2 = self.geom_body[c.geom1[:n]], self.geom_body[c.geom2[:n]]
        sel = (self.is_robot[b1] & self.is_part[b2]) | (self.is_part[b1] & self.is_robot[b2])
        return sorted({(self.m.body(int(x)).name, self.m.body(int(y)).name) for x, y in zip(b1[sel], b2[sel])})

    def part_speeds(self) -> tuple:
        v = np.zeros(6)
        lin = ang = 0.
        worst = None
        for b in self.parts.tolist():
            mujoco.mj_objectVelocity(self.m, self.d, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
            l, a = float(np.linalg.norm(v[3:])), float(np.linalg.norm(v[:3]))
            if l / REST_LIN_M_S + a / REST_ANG_RAD_S > (lin / REST_LIN_M_S + ang / REST_ANG_RAD_S):
                worst = self.m.body(b).name
            lin, ang = max(lin, l), max(ang, a)
        return lin, ang, worst

    def terminal(self) -> dict:
        contacts = self.robot_part_contacts()
        lin, ang, worst = self.part_speeds()
        return dict(released=not contacts, robot_part_contacts=[list(x) for x in contacts[:10]],
                    at_rest=lin <= REST_LIN_M_S and ang <= REST_ANG_RAD_S, max_part_speed_m_s=lin,
                    max_part_angular_rad_s=ang, fastest_part=worst, breakdown=copy.deepcopy(self.breakdown),
                    max_part_depth_mm=round(1000 * self.max_part_depth_m, 3))


def state_sha(model, data) -> str:
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    s = np.zeros(mujoco.mj_stateSize(model, spec))
    mujoco.mj_getState(model, data, s, spec)
    return hashlib.sha256(s.tobytes()).hexdigest()


MAX_SMALL_MEMBER = 1 << 20        # bytes: the members read besides `ctrl` (substeps, timestep)
MAX_MEMBERS = 64                  # members of the archive (ctrl, substeps, timestep, actuators, and a few of the agent's own)


MAX_DIRECTORY = MAX_MEMBERS * (46 + 1024 + 256)   # bytes of the central directory (entry header, name, extra fields)


def _zip_entries(path: str) -> int:
    """The number of members the archive's end-of-central-directory record declares, read without parsing the directory
    (a file of a million empty members takes a GB to parse). The directory's declared size is bounded too: zipfile
    parses the directory by its size, not by the declared count."""
    import zipfile
    with open(path, "rb") as fp:
        rec = zipfile._EndRecData(fp)   # noqa: SLF001 -- the standard library's own EOCD reader (zip64 aware)
    if not rec:
        raise InvalidTrajectory("not an .npz archive")
    if int(rec[zipfile._ECD_SIZE]) > MAX_DIRECTORY:  # noqa: SLF001
        raise InvalidTrajectory(f"the archive's directory is {rec[zipfile._ECD_SIZE]} bytes (at most {MAX_DIRECTORY})")  # noqa: SLF001
    return int(rec[zipfile._ECD_ENTRIES_TOTAL])  # noqa: SLF001


def _check_members(path: str, nu: int, max_rows: int) -> None:
    """The file's members, from the zip directory and the .npy headers only (nothing is decompressed beyond a header):
    `ctrl` a numeric (N, nu) array with 1 <= N <= max_rows, every other member small. A file that would not fit in
    memory or lies about its contents is refused before it is read (a zip bomb is the deliverable's fault)."""
    import zipfile
    size = os.path.getsize(path)
    if size > max_rows * nu * 8 + (64 << 20):
        raise InvalidTrajectory(f"the file is {size} bytes, more than {max_rows} rows of {nu} float64 can need")
    n = _zip_entries(path)
    if not 1 <= n <= MAX_MEMBERS:
        raise InvalidTrajectory(f"the archive has {n} members (at most {MAX_MEMBERS})")
    with zipfile.ZipFile(path) as zf:
        names = [i.filename for i in zf.infolist()]
        if len(names) != n:
            raise InvalidTrajectory(f"the archive declares {n} members and holds {len(names)}")
        infos = {i.filename: i for i in zf.infolist()}
        keys = [x[:-4] if x.endswith(".npy") else x for x in names]
        if len(set(keys)) != len(keys):
            raise InvalidTrajectory("the archive has two members of one name")
        if "ctrl.npy" not in infos:
            raise InvalidTrajectory("missing key 'ctrl'")
        for name in ("substeps.npy", "timestep.npy"):
            if name in infos and infos[name].file_size > MAX_SMALL_MEMBER:
                raise InvalidTrajectory(f"member {name!r} is {infos[name].file_size} bytes (at most {MAX_SMALL_MEMBER})")
        with zf.open("ctrl.npy") as f:
            version = np.lib.format.read_magic(f)
            if version == (1, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_1_0(f)
            elif version in ((2, 0), (3, 0)):
                shape, fortran, dtype = np.lib.format.read_array_header_2_0(f)
            else:
                raise InvalidTrajectory(f"unsupported .npy version {version}")
        if dtype.hasobject or dtype.kind not in "fiu" or len(shape) != 2 or shape[1] != nu or not 1 <= shape[0] <= max_rows:
            raise InvalidTrajectory(f"ctrl must be a numeric (N, {nu}) array with 1 <= N <= {max_rows}, got {dtype} {shape}")
        if infos["ctrl.npy"].file_size > shape[0] * nu * dtype.itemsize + 65536:
            raise InvalidTrajectory("ctrl's member is larger than its header says")


def _scalar(z, key: str):
    v = np.asarray(z[key]).reshape(-1)
    if v.size != 1 or v.dtype.kind not in "fiu":
        raise InvalidTrajectory(f"{key} must be one number")
    return v[0]


def load_trajectory(path: str, nu: int, timestep: float | None = None, max_rows: int | None = None) -> np.ndarray:
    """The ctrl rows of a trajectory file, validated (InvalidTrajectory otherwise, whatever is wrong with the file: the
    deliverable's fault, never the grader's). max_rows: the task's row cap, checked before the rows are read."""
    cap = MAX_ROWS if max_rows is None else min(MAX_ROWS, int(max_rows))
    try:
        _check_members(path, nu, cap)
        with np.load(path, allow_pickle=False) as z:
            if not isinstance(z, np.lib.npyio.NpzFile):
                raise InvalidTrajectory("not an .npz archive")
            if "substeps" in z.files and _scalar(z, "substeps") != SUBSTEPS:
                raise InvalidTrajectory(f"substeps must be {SUBSTEPS}")
            if timestep is not None and "timestep" in z.files and float(_scalar(z, "timestep")) != timestep:
                raise InvalidTrajectory(f"timestep must be {timestep}")
            c = z["ctrl"]
        if c.dtype.kind not in "fiu" or c.ndim != 2 or c.shape[1] != nu or not 1 <= c.shape[0] <= cap:
            raise InvalidTrajectory(f"ctrl must be a numeric (N, {nu}) array with 1 <= N <= {cap}, got {c.dtype} {c.shape}")
        c = np.ascontiguousarray(c, dtype=np.float64)
        if not np.isfinite(c).all():
            raise InvalidTrajectory("ctrl has NaN or inf")
        return c
    except (InvalidTrajectory, MemoryError):
        raise                           # MemoryError: the file was bounded above, so the host is out of memory (infra)
    except Exception as exc:  # noqa: BLE001
        raise InvalidTrajectory(f"not a readable trajectory .npz file: {exc!r}"[:300])


class Session:
    def __init__(self, task: str, scene_dir: str | None = None):
        self.task = task
        self.scene_dir = os.path.abspath(scene_dir or os.path.join(SCENES_ROOT, task))
        if self.scene_dir not in sys.path:
            sys.path.insert(0, self.scene_dir)
        self._mod = importlib.import_module("scene")   # one scene per process (its modules are top-level imports)
        if os.path.dirname(os.path.abspath(self._mod.__file__)) != self.scene_dir:
            raise RuntimeError("another scene is already loaded in this process")
        self.reset()

    # ---- building and state
    def reset(self) -> None:
        """A fresh build of the scene (keyframe 'home'), bit-identical to the grader's initial state."""
        self.S = self._mod.load()
        self.model, self.data = self.S.model, self.S.data
        self.nu = int(self.model.nu)
        self.timestep = float(self.model.opt.timestep)
        self.control_dt = SUBSTEPS * self.timestep
        self.actuators = [self.model.actuator(i).name for i in range(self.nu)]
        self.rows: list[np.ndarray] = []
        self.validity = Validity(self.model, self.data)
        self.step_limit = joint_speed_limits(self.actuators) * self.control_dt   # rad per control tick (inf: none)
        self._limited = np.isfinite(self.step_limit)
        cr = np.asarray(self.model.actuator_ctrlrange, dtype=np.float64)
        cl = np.asarray(self.model.actuator_ctrllimited).astype(bool)
        self._clo = np.where(cl, cr[:, 0], -np.inf)
        self._chi = np.where(cl, cr[:, 1], np.inf)
        self.slewed_ticks = 0                         # ticks on which the joint-speed clamp moved some target
        rule = END_POSE_RULES.get(self.task)
        self._end_pose = None
        if rule:
            goals = json.load(open(os.path.join(self.scene_dir, "task.json")))[rule["goals"]]
            self._end_pose = dict(rule, ids={p: self.model.body(p).id for p in rule["parts"]},
                                  frame_id=self.model.body(rule["frame"]).id,
                                  goal_pos={p: np.asarray(goals[p], dtype=np.float64) for p in rule["parts"]})

    def get_state(self) -> dict:
        st = copy.deepcopy(self.S.get_state())
        st["rows"] = list(self.rows)
        st["validity"] = self.validity.state()
        # MuJoCo's warning counters are not part of the integration state; restored with it, so a warning raised after
        # this state (e.g. in final_check's hold) is not read as a breakdown on every later tick
        st["warnings"] = [(int(w.number), int(w.lastinfo)) for w in self.data.warning]
        return st

    def set_state(self, st: dict) -> None:
        """Restore a get_state() of this Session; the recorded rows go back to that state's rows."""
        self.S.set_state(st)
        self.rows = list(st["rows"])
        if "validity" in st:
            self.validity.set_state(st["validity"])
        for w, (n, info) in zip(self.data.warning, st.get("warnings") or []):
            w.number, w.lastinfo = n, info

    def state_sha(self) -> str:
        return state_sha(self.model, self.data)

    # ---- acting
    def hold_action(self) -> np.ndarray:
        return self.data.ctrl.copy()

    def step(self, row) -> None:
        a = np.asarray(row, dtype=np.float64).reshape(-1)
        if a.shape != (self.nu,) or not np.isfinite(a).all():
            raise ValueError(f"a row has {self.nu} finite entries (actuators {self.actuators})")
        self.data.ctrl[:] = self.applied(a)
        self.S.step(SUBSTEPS)
        self.validity.tick()
        self.rows.append(a.copy())

    def applied(self, a: np.ndarray) -> np.ndarray:
        """The targets a row applies this tick: clipped to the control range, then each limited target that would move more
        than its speed limit x control tick (+ SPEED_TOL) from the target applied on the previous tick (data.ctrl) is set
        to the previous target +- that step. Targets within the tolerance are applied unchanged. The row itself is what
        is recorded; the grader's replay applies it through this same function."""
        t = np.clip(a, self._clo, self._chi)
        prev = self.data.ctrl
        lim = self.step_limit
        d = t - prev
        over = self._limited & (np.abs(d) > lim + SPEED_TOL)
        if not over.any():
            return t
        self.slewed_ticks += 1
        out = t.copy()
        out[over] = prev[over] + np.sign(d[over]) * lim[over]
        return out

    def run(self, ctrl) -> None:
        for row in np.asarray(ctrl, dtype=np.float64):
            self.step(row)

    def success(self) -> dict:
        return self.S.success()

    def status(self) -> dict:
        """The verdict on the current state: success = goal (success.py) and released and at rest and no breakdown so
        far. The grader also requires it after the settle hold (final_check())."""
        rep = self.S.success()
        term = self.validity.terminal()
        goal = bool(rep.get("success"))
        if self._end_pose is not None:
            ep = self.end_pose()
            rep = dict(rep, end_pose=ep)
            goal = goal and ep["ok"]
        ok = goal and term["released"] and term["at_rest"] and term["breakdown"] is None
        return {"success": ok, "goal": goal, "released": term["released"], "at_rest": term["at_rest"],
                "breakdown": term["breakdown"], "rows": len(self.rows), "sim_time_s": float(self.data.time),
                "state_sha": self.state_sha(), "terminal": json.loads(json.dumps(term, default=_plain)),
                "report": json.loads(json.dumps(rep, default=_plain))}

    def end_pose(self) -> dict:
        """END_POSE_RULES: each listed part's position and orientation error against its goal in the rule's frame (the
        assembled panels are identity-oriented in it)."""
        r, d = self._end_pose, self.data
        f = r["frame_id"]
        Rf = d.xmat[f].reshape(3, 3)
        worst_mm, worst_deg, bad = 0.0, 0.0, []
        for p, b in r["ids"].items():
            err = float(np.linalg.norm(Rf.T @ (d.xpos[b] - d.xpos[f]) - r["goal_pos"][p]))
            Rrel = Rf.T @ d.xmat[b].reshape(3, 3)
            ang = float(np.degrees(np.arccos(np.clip((np.trace(Rrel) - 1.0) / 2.0, -1.0, 1.0))))
            if not (np.isfinite(err) and np.isfinite(ang)) or err > r["pos_m"] or ang > r["angle_deg"]:
                bad.append(p)
            worst_mm, worst_deg = max(worst_mm, 1000 * err), max(worst_deg, ang)
        return {"ok": not bad, "parts_off_goal": bad, "max_error_mm": round(worst_mm, 3), "max_angle_deg": round(worst_deg, 3),
                "pos_m": r["pos_m"], "angle_deg": r["angle_deg"]}

    def final_check(self) -> dict:
        """The grader's verdict on the rows so far: status() now, then the last row held for SETTLE_S (not recorded),
        status() again; success needs both. The session is restored afterwards (rows and state unchanged)."""
        end = self.status()
        st = self.get_state()
        hold = self.rows[-1] if self.rows else self.hold_action()
        try:
            for _ in range(int(round(SETTLE_S / self.control_dt))):
                self.data.ctrl[:] = self.applied(np.asarray(hold, dtype=np.float64))
                self.S.step(SUBSTEPS)
                self.validity.tick()
            settled = self.status()
        finally:
            self.set_state(st)
        return {"success": bool(end["success"] and settled["success"]), "end": end, "settled": settled,
                "settle_s": SETTLE_S, "state_sha": end["state_sha"], "settled_sha": settled["state_sha"]}

    def replay(self, ctrl=None) -> dict:
        """Reset, run the rows open-loop, return the grader's verdict (final_check())."""
        ctrl = np.array(self.rows if ctrl is None else ctrl, dtype=np.float64)
        self.reset()
        self.run(ctrl)
        return self.final_check()

    def save_trajectory(self, ctrl=None, path: str = "/app/output/trajectory.npz") -> str:
        ctrl = np.array(self.rows if ctrl is None else ctrl, dtype=np.float64).reshape(-1, self.nu)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp.npz"
        np.savez_compressed(tmp, ctrl=ctrl, substeps=np.int64(SUBSTEPS), timestep=np.float64(self.timestep),
                            actuators=np.array(self.actuators))
        os.replace(tmp, path)
        return path


def _plain(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return str(x)


def replay_cli(a) -> int:
    t0 = time.time()
    s = Session(a.task, a.scene_dir)
    out = {"initial_state_sha": s.state_sha(), "nu": s.nu, "timestep": s.timestep, "actuators": s.actuators}
    try:
        ctrl = load_trajectory(a.traj, s.nu, s.timestep)
    except InvalidTrajectory as exc:
        out.update(bad_trajectory=str(exc))
    else:
        try:
            s.run(ctrl)
            fc = s.final_check()
        except (MemoryError, OSError):
            raise                       # the host's problem: the grader reports it as its own error
        except Exception as exc:  # noqa: BLE001
            # The scene's own code (mechanism, success.py) or MuJoCo raised on the state these rows drove it into: a
            # simulator breakdown caused by the deliverable (the agent's 0), never a grader error (PROTOCOL H.5).
            out.update(success=False, goal=False, replay_exception=f"{type(exc).__name__}: {exc}"[:500],
                       breakdown=dict(kind="exception", error=type(exc).__name__, row=len(s.rows)), rows=len(s.rows),
                       state_sha=s.state_sha(), settled_sha=None, sim_steps=len(s.rows) * SUBSTEPS,
                       wall_s=round(time.time() - t0, 1))
        else:
            out.update(fc["end"], success=fc["success"], settled=fc["settled"], settled_sha=fc["settled_sha"],
                       settle_s=fc["settle_s"], sim_steps=len(ctrl) * SUBSTEPS, wall_s=round(time.time() - t0, 1))
    text = json.dumps(out, default=_plain)
    if a.out:
        tmp = a.out + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, a.out)
    print(text, flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="replay a trajectory from the scene's initial state; print the result as JSON")
    r.add_argument("--task", required=True)
    r.add_argument("--traj", required=True)
    r.add_argument("--scene-dir", default=None)
    r.add_argument("--out", default=None)
    b = sub.add_parser("info", help="the scene's initial-state hash, actuators and file digest as JSON")
    b.add_argument("--task", required=True)
    b.add_argument("--scene-dir", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "replay":
        return replay_cli(a)
    s = Session(a.task, a.scene_dir)
    files = scene_files(s.scene_dir)
    print(json.dumps({"task": a.task, "initial_state_sha256": s.state_sha(), "nu": s.nu, "timestep": s.timestep,
                      "substeps": SUBSTEPS, "actuators": s.actuators, "scene_digest": digest(files),
                      "scene_files": files, "cylinder_prisms": getattr(s.S, "cylinder_prisms", []), "runtime": {"mujoco": mujoco.__version__, "numpy": np.__version__,
                                                        "python": sys.version.split()[0]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
