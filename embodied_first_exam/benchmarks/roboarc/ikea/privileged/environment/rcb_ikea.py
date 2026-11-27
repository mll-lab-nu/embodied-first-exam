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
Identical parts (the same asset) are interchangeable: any of them may take any of their places, one part per place
(IDENTICAL_PARTS: VESKEN, STEGESUND, GLADOM, EKET; the scene's mechanism and success.py otherwise unchanged).

CLI (the grader's replay): python rcb_ikea.py replay --task lack --traj /app/output/trajectory.npz [--scene-dir D] [--out F]
Only mujoco and numpy are needed.
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


# ---- Identical parts (the benchmark's rule, on top of a scene's mechanism and success.py) ---------------------------
# Parts that are the same asset (same inertia, geoms, meshes, colours, joints and child bodies, checked on the compiled
# model at every build: _same_part; EKET's two side panels up to a turn: _turned_same_part) cannot be told apart, so
# any of them may take any of their places, one part per place. VESKEN, STEGESUND, GLADOM and EKET ported source graders
# that bound every place to one named part (foot_0 into corner 0, bolt_1 into the A-front bore, screw_bottom into the
# bottom nut, side_a into side A): a correct assembly with two identical parts swapped never connected or failed the
# check. Here:
#   - VESKEN (feet; the 12 columns; trays 1-2; caps): every open snap operation tracks its own parts with the source's
#     computation, unchanged, and every other free part of the same groups (same zone, gates and dwell, measured at the
#     place's own design points); the first that connects takes the place from then on, and the operation's retention
#     weld is pointed at the bodies that are there. success.py measures each place against the parts that took it.
#   - STEGESUND (the two halves; the four bolts): a bolt arms on any free bore it threads into (not only its own) and is
#     welded with that bore's thread and the half its head clamps there; success.py's assembled check passes when it
#     passes for some one-to-one assignment of the halves and of the bolts to their places.
#   - GLADOM (the three short screws): each short screw may take any free short-screw nut (bottom or ring); the frame-b
#     and ring connections wait for their nuts to be taken by any short screw; success.py measures the screws against
#     the one-to-one assignment with the smallest summed lateral error (the source did this for the two ring screws).
#   - EKET (the two side panels: one panel, side_b is side_a turned 180 deg about its long axis, _turned_same_part):
#     side A's place may take either panel (the first accepted side_a_entry, measured on the panel turned into side A's
#     frame); the other panel is then side B, and the frame joints, success.py's gates and the end-pose rule follow.
# Order rules are unchanged (they are rules on the places), and a run that puts every part only into its own place is
# computed exactly as before, bit for bit.
IDENTICAL_PARTS = {
    "vesken": (("foot_0", "foot_1", "foot_2", "foot_3"),
               tuple(f"column_{lv}_{k}" for lv in range(3) for k in range(4)),
               ("tray_1", "tray_2"),
               ("cap_0", "cap_1", "cap_2", "cap_3")),
    "stegesund": (("half_A", "half_B"), ("bolt_1", "bolt_2", "bolt_3", "bolt_4")),
    "gladom": (("screw_bottom", "screw_ring_l", "screw_ring_r"),),
    "eket": (("side_a", "side_b"),),
}


def _same_part(m, a: int, b: int, root: bool = True) -> bool:
    """Bodies a and b are the same asset: inertial, every geom (type, size, pose in the body, mesh, contact and colour
    fields), every joint but a free one, and the child bodies (in the same pose, recursively)."""
    eq = np.array_equal
    if not all(eq(x[a], x[b]) for x in (m.body_mass, m.body_inertia, m.body_ipos, m.body_iquat)):
        return False
    if not root and not (eq(m.body_pos[a], m.body_pos[b]) and eq(m.body_quat[a], m.body_quat[b])):
        return False
    ga, gb = np.flatnonzero(m.geom_bodyid == a), np.flatnonzero(m.geom_bodyid == b)
    if len(ga) != len(gb):
        return False
    for x, y in zip(ga, gb):
        if not all(eq(f[x], f[y]) for f in (m.geom_type, m.geom_size, m.geom_pos, m.geom_quat, m.geom_contype,
                                             m.geom_conaffinity, m.geom_condim, m.geom_priority, m.geom_friction,
                                             m.geom_solref, m.geom_solimp, m.geom_solmix, m.geom_margin, m.geom_gap,
                                             m.geom_rgba, m.geom_matid, m.geom_group)):
            return False
        if int(m.geom_type[x]) in (int(mujoco.mjtGeom.mjGEOM_MESH), int(mujoco.mjtGeom.mjGEOM_SDF)):
            i, j = int(m.geom_dataid[x]), int(m.geom_dataid[y])
            if i != j:
                vi = m.mesh_vert[m.mesh_vertadr[i]:m.mesh_vertadr[i] + m.mesh_vertnum[i]]
                vj = m.mesh_vert[m.mesh_vertadr[j]:m.mesh_vertadr[j] + m.mesh_vertnum[j]]
                fi = m.mesh_face[m.mesh_faceadr[i]:m.mesh_faceadr[i] + m.mesh_facenum[i]]
                fj = m.mesh_face[m.mesh_faceadr[j]:m.mesh_faceadr[j] + m.mesh_facenum[j]]
                if not (eq(vi, vj) and eq(fi, fj) and eq(m.mesh_scale[i], m.mesh_scale[j])):
                    return False
    ja, jb = np.flatnonzero(m.jnt_bodyid == a), np.flatnonzero(m.jnt_bodyid == b)
    if len(ja) != len(jb):
        return False
    for x, y in zip(ja, jb):
        if int(m.jnt_type[x]) != int(m.jnt_type[y]):
            return False
        if int(m.jnt_type[x]) == int(mujoco.mjtJoint.mjJNT_FREE):
            continue
        dx, dy, qx, qy = m.jnt_dofadr[x], m.jnt_dofadr[y], m.jnt_qposadr[x], m.jnt_qposadr[y]
        if not (all(eq(f[x], f[y]) for f in (m.jnt_axis, m.jnt_pos, m.jnt_range, m.jnt_limited, m.jnt_stiffness))
                and eq(m.qpos_spring[qx], m.qpos_spring[qy]) and eq(m.qpos0[qx], m.qpos0[qy])
                and all(eq(f[dx], f[dy]) for f in (m.dof_damping, m.dof_armature, m.dof_frictionloss))):
            return False
    ca = [c for c in range(1, m.nbody) if m.body_parentid[c] == a and c != a]
    cb = [c for c in range(1, m.nbody) if m.body_parentid[c] == b and c != b]
    return len(ca) == len(cb) and all(_same_part(m, x, y, root=False) for x, y in zip(ca, cb))


def _vesken_rule(groups):
    import itertools, math
    import vesken_mechanism as VM
    import success as SU
    from ikea_runtime import rotate

    class Mechanism(VM.VeskenMechanism):
        """VeskenMechanism with identical parts interchangeable (see IDENTICAL_PARTS). `bound`: a part name of the
        source (a role) -> the body that took its place (set when the operation that places it connects)."""

        def __init__(self, model, data, task):
            self.group = {n: g for g in groups for n in g}
            super().__init__(model, data, task)
            m = model
            self.eq_obj0 = (m.eq_obj1id.copy(), m.eq_obj2id.copy())
            self.roles = {o['key']: list(dict.fromkeys([o['part'], o['host']] + [c['receiver'] for c in o['connectors']]))
                          for o in self.ops}
            self.socket = {o['part']: o for o in self.ops}             # a role's own operation (its place)
            self.jinfo = {j['name']: (int(m.jnt_qposadr[m.joint(j['joint']).id]), float(j['axis'][0])) for j in task['jaws']}
            self.jparent = {j['name']: m.body(int(m.body_parentid[m.body(j['name']).id])).name for j in task['jaws']}
            # a jaw of a role played by another body of its group -> that body's jaw in the same pose
            kids = {}
            for jn in self.jinfo:
                kids.setdefault(self.jparent[jn], []).append(jn)
            self.jmap = {}
            for jn, par in self.jparent.items():
                for b in self.group.get(par, ()):
                    for c in kids.get(b, ()):
                        if np.array_equal(m.body_pos[m.body(c).id], m.body_pos[m.body(jn).id]):
                            self.jmap[(jn, b)] = c
            self.reset()

        def reset(self):
            super().reset()
            self.bound, self.alt = {}, {}
            if hasattr(self, 'eq_obj0'):
                for i in self.eq.values():
                    self.m.eq_obj1id[i], self.m.eq_obj2id[i] = self.eq_obj0[0][i], self.eq_obj0[1][i]

        def state(self):
            s = super().state()
            s.update(bound=dict(self.bound), alt=copy.deepcopy(self.alt),
                     eq_obj={k: (int(self.m.eq_obj1id[i]), int(self.m.eq_obj2id[i])) for k, i in self.eq.items()})
            return s

        def set_state(self, s):
            super().set_state(s)
            self.bound, self.alt = dict(s.get('bound', {})), copy.deepcopy(s.get('alt', {}))
            for k, i in self.eq.items():
                o1, o2 = s.get('eq_obj', {}).get(k, (self.eq_obj0[0][i], self.eq_obj0[1][i]))
                self.m.eq_obj1id[i], self.m.eq_obj2id[i] = o1, o2

        # -- candidates: role -> body
        def _opts(self, r, taken):
            if r in self.bound:
                return [self.bound[r]]
            if r not in self.group:
                return [r]
            free = [b for b in self.group[r] if b not in taken]
            return ([r] if r in free else []) + [b for b in free if b != r]

        def candidates(self, o):
            """[(A, own)]: the operation's own parts first (own: every role played by its own part, the source's
            case, measured however far), then every assignment of free identical parts whose part sits within `near`
            of its place on the host (the source's prefilter); a receiver played by another part must sit at its
            own place already."""
            k, d = o['key'], self.d
            P, H = o['part'], o['host']
            taken = set(self.bound.values())
            parts, hosts = self._opts(P, taken), self._opts(H, taken)
            rest = [r for r in self.roles[k] if r not in (P, H)]
            ropts = []
            for r in rest:
                ro = self._opts(r, taken)
                if r not in self.bound and r in self.group:
                    p = self._where(r)
                    ro = [b for b in ro if b == r or (p is not None and np.linalg.norm(d.xpos[self.bid[b]] - p) <= self.near)]
                ropts.append(ro)
            out = []
            if not parts:
                return out
            pid = np.array([self.bid[b] for b in parts])
            for h in hosts:
                hb = self.bid[h]
                tgt = d.xpos[hb] + d.xmat[hb].reshape(3, 3) @ (self.c[P] - self.c[H])
                near = np.linalg.norm(d.xpos[pid] - tgt, axis=1) <= self.near
                for p, ok in zip(parts, near):
                    if p == h or not (ok or (p == P and h == H)):
                        continue
                    for combo in itertools.product(*ropts):
                        A = dict(zip(rest, combo)); A[P] = p; A[H] = h
                        if len(set(A.values())) != len(A):
                            continue
                        own = all(b == r for r, b in A.items())
                        if own or ok:
                            out.append((A, own))
            out.sort(key=lambda x: not x[1])          # the source's own case first
            return out

        def _where(self, r):
            """world position of role r's place (its own operation's design pose on its host's body), or None"""
            o = self.socket.get(r)
            if o is None:
                return None
            hb = self.bid[self.bound.get(o['host'], o['host'])]
            return self.d.xpos[hb] + self.d.xmat[hb].reshape(3, 3) @ (self.c[r] - self.c[o['host']])

        def _jaws(self, o, A):
            return [self.jmap[(j, A[self.jparent[j]])] if A[self.jparent[j]] != self.jparent[j] else j for j in o['jaws']]

        def _geometry(self, o, A):
            d = self.d; P = o['part']; bp = self.bid[A[P]]
            pp = d.xpos[bp]; qp = d.xquat[bp]; qh = d.xquat[self.bid[A[o['host']]]]
            out = rotate(qh, o['outward'])
            gaps, lats = [], []
            for c in o['connectors']:
                r = c['receiver']; pt = np.asarray(c['point'], float); br = self.bid[A[r]]
                actual = pp + rotate(qp, pt - self.c[P])
                desired = d.xpos[br] + rotate(d.xquat[br], pt - self.c[r])
                dl = actual - desired; g = float(dl @ out)
                gaps.append(g); lats.append(float(np.linalg.norm(dl - g * out)))
            gap = max(gaps, key=abs); lat = max(lats)
            ax = math.degrees(math.acos(float(np.clip(rotate(qp, o['outward']) @ out, -1, 1))))
            return gap, lat, ax

        def update(self):
            self.counter += 1
            if self.counter % self.PERIOD:
                return
            dt = self.m.opt.timestep * self.PERIOD
            z = self.zone; d = self.d
            R = d.xmat[self.hid].reshape(-1, 3, 3)
            dist = np.linalg.norm(d.xpos[self.pid] - d.xpos[self.hid] - np.einsum('nij,nj->ni', R, self.rel), axis=1)
            seen = set()
            for idx, o in enumerate(self.ops):
                k = o['key']
                if d.eq_active[self.eq[k]]:
                    continue
                for A, own in self.candidates(o):
                    if own:                  # the source's computation, unchanged
                        s = self.st[k]
                        if dist[idx] > self.near:
                            if s['max_gap'] is not None:
                                s.update(max_gap=None, peak=[0.] * len(o['jaws']), dwell=0.)
                            continue
                        gap, lat, ax = self.geometry(o)
                        jn, part, cps = None, o['part'], o['counterparts']
                    else:                    # another part within `near` of the place (candidates())
                        ck = k + '|' + ','.join(A[r] for r in self.roles[k])
                        seen.add(ck)
                        s = self.alt.setdefault(ck, dict(max_gap=None, peak=[0.] * len(o['jaws']), dwell=0.))
                        gap, lat, ax = self._geometry(o, A)
                        jn, part = self._jaws(o, A), A[o['part']]
                        cps = [A[x] if x in A else jn[o['jaws'].index(x)] for x in o['counterparts']]
                    if not (lat < z['lateral_m'] and z['gap_min_m'] < gap < z['gap_max_m'] and ax < z['axis_deg']):
                        if s['max_gap'] is not None:
                            s.update(max_gap=None, peak=[0.] * len(o['jaws']), dwell=0.)
                        continue
                    jaws = self.jaw_travel(k) if own else [float(d.qpos[self.jinfo[j][0]]) * self.jinfo[j][1] for j in jn]
                    s['max_gap'] = gap if s['max_gap'] is None else max(s['max_gap'], gap)
                    s['peak'] = [max(a, b) for a, b in zip(s['peak'], jaws)]
                    g = o['gates']
                    v = self.h.state13(part)[7:10]; speed = float(np.linalg.norm(v))
                    contact = self.h.contact_force_between(part, cps)
                    deps = all(self.connected(x) for x in o['dependencies'])
                    good = (abs(gap) < g['axial_m'] and lat < g['lateral_m'] and ax < g['axis_deg'] and speed < g['speed_m_s']
                            and s['max_gap'] - gap >= g['min_travel_m'] and contact > g['min_contact_N']
                            and all(p > self.jg['peak_travel_min_m'] for p in s['peak'])
                            and all(j < self.jg['final_travel_max_m'] for j in jaws) and deps)
                    s['dwell'] = s['dwell'] + dt if good else 0.
                    if own or good:
                        self.metrics[k] = dict(gap_m=gap, lateral_m=lat, axis_deg=ax, speed_m_s=speed, travel_m=s['max_gap'] - gap,
                                               contact_N=contact, jaw_m=jaws, jaw_peak_m=list(s['peak']), dependencies_ok=deps,
                                               dwell_s=s['dwell'])
                        if not own:
                            self.metrics[k]['parts'] = {r: b for r, b in A.items() if r != b}
                    if s['dwell'] >= g['dwell_s']:
                        self.take(o, A, own)
                        break
            self.alt = {ck: v for ck, v in self.alt.items() if ck in seen}

        def take(self, o, A, own):
            for r, b in A.items():
                if r in self.group and r not in self.bound:
                    self.bound[r] = b
            if own:
                self.connect(o)
                return
            i = self.eq[o['key']]
            m = self.m
            for ids, ids0 in ((m.eq_obj1id, self.eq_obj0[0]), (m.eq_obj2id, self.eq_obj0[1])):
                n = m.body(int(ids0[i])).name
                ids[i] = self.bid[A[n]] if n in A else ids0[i]
            r, q = self.h.rel_pose(A[o['host']], A[o['part']])    # part pose in the host frame (body1=host, body2=part)
            m.eq_data[i, 0:3] = 0; m.eq_data[i, 3:6] = r; m.eq_data[i, 6:10] = q; m.eq_data[i, 10] = 1
            self.d.eq_active[i] = 1
            self.engaged_at[o['key']] = float(self.d.time)

    class Monitor(SU.Monitor):
        """success.py with each place measured against the parts that took it (Mechanism.bound)."""

        def _op(self, o):
            mech = self.scene.mech
            A = {r: mech.bound.get(r, r) for r in mech.roles[o['key']]}
            if all(b == r for r, b in A.items()):
                return super()._op(o)
            d = self.d; P = o['part']
            pp, qp = self.h.pose(A[P]); _, qh = self.h.pose(A[o['host']])
            out = rotate(qh, o['outward']); gaps, lats = [], []
            for c in o['connectors']:
                r = c['receiver']; pt = np.asarray(c['point'], float); pr, qr = self.h.pose(A[r])
                dl = (pp + rotate(qp, pt - self.c[P])) - (pr + rotate(qr, pt - self.c[r]))
                g = float(dl @ out); gaps.append(abs(g)); lats.append(float(np.linalg.norm(dl - g * out)))
            ax = math.degrees(math.acos(float(np.clip(rotate(qp, o['outward']) @ out, -1, 1))))
            g = o['gates']; conn = bool(d.eq_active[self.eq[o['key']]])
            return dict(key=o['key'], connected=conn, gap_m=max(gaps), lateral_m=max(lats), axis_deg=ax, parts=A,
                        passed=bool(conn and max(gaps) < g['axial_m'] and max(lats) < g['lateral_m'] and ax < g['axis_deg']))

    return Mechanism, Monitor


def _stegesund_rule(groups):
    import itertools, math
    import seat_weld as SW
    import stegesund_mech as SM
    import success as SU
    halves, bolts = groups

    class Mechanism(SM.StegesundMechanism):
        """StegesundMechanism with identical parts interchangeable (see IDENTICAL_PARTS). `bore`: bolt -> the bore (seat)
        it was armed in; the bore's thread, and the half at that bore, are the ones welded and switched off."""

        def __init__(self, model, data, task):
            super().__init__(model, data, task)
            m = model
            self.fx = {f.name: f for f in self.welder.f}
            self.seat0 = {b: task['fasteners'][b]['seat'] for b in self.fx}             # each bore's source bolt
            self.src = {s: b for b, s in self.seat0.items()}
            self.order = {b: [self.seat0[b]] + [self.seat0[x] for x in sorted(self.fx) if x != b] for b in self.fx}
            self.own_n = {b: len(self.arm_geoms[b][0]) for b in self.fx}
            self.off0 = {b: list(f.off_geoms) for b, f in self.fx.items()}
            self.welds0 = {b: list(f.welds) for b, f in self.fx.items()}
            self.clamped0 = {b: list(f.clamped) for b, f in self.fx.items()}
            self.obj1_0 = m.eq_obj1id.copy()
            self.bolt_of = np.full(m.ngeom, -1); self.seat_of = np.full(m.ngeom, -1)
            self.names = sorted(self.fx)
            for i, b in enumerate(self.names):
                self.bolt_of[self.arm_geoms[b][0]] = i
                self.seat_of[self.arm_geoms[b][1]] = i          # bore i = the source bore of bolt i
            asm = {k: np.array(v) for k, v in task['assembled_poses_world'].items()}
            # each bore's bolt origin in the frame of the half it clamps (source: bolt_1/2 -> half_A, bolt_3/4 -> half_B)
            self.at_half = {s: (np.linalg.inv(asm[self.clamped0[b][0]]) @ asm[b])[:3, 3] for s, b in self.src.items()}
            self.welder.apply_event = self._apply
            self.bore = {}

        def reset(self):
            super().reset()
            self.bore = {}
            if hasattr(self, 'obj1_0'):
                self.m.eq_obj1id[:] = self.obj1_0
                for b in self.fx:
                    self._bind(b, self.seat0[b], record=False)

        def _bind(self, b, seat, record=True):
            f, sb = self.fx[b], self.src[seat]
            if record:
                self.bore[b] = seat
            f.off_geoms = self.off0[b][:self.own_n[b]] + self.off0[sb][self.own_n[sb]:]
            f.welds = [self.welds0[b][0]] + self.welds0[sb][1:]
            f.clamped = list(self.clamped0[sb])

        def _claimed(self, seat, b):
            return any(s == seat and x != b and (self.fx[x].armed or self.fx[x].welded) for x, s in self.bore.items())

        def _arm(self):
            """the source arms a bolt at its first contact with its own nut's thread; here with any free bore's thread
            (its own checked first), and an armed bolt that is not welded yet moves to another free bore it threads
            into (not touching its own bore's thread any more)"""
            if all(f.welded for f in self.welder.f):
                return
            c = self.d.contact[: self.d.ncon]
            if not len(c):
                return
            g1, g2 = np.asarray(c.geom1), np.asarray(c.geom2)
            hits = set()
            for x, y in ((g1, g2), (g2, g1)):
                sel = (self.bolt_of[x] >= 0) & (self.seat_of[y] >= 0)
                if sel.any():
                    hits.update(zip(self.bolt_of[x][sel].tolist(), self.seat_of[y][sel].tolist()))
            if not hits:
                return
            sidx = {s: self.names.index(b) for s, b in self.src.items()}
            for f in self.welder.f:
                if f.welded:
                    continue
                i = self.names.index(f.name)
                cur = self.bore.get(f.name) if f.armed else None
                if cur is not None and (i, sidx[cur]) in hits:
                    continue
                if f.armed and cur is None and (i, sidx[self.seat0[f.name]]) in hits:
                    continue
                for seat in self.order[f.name]:
                    if seat == cur or (i, sidx[seat]) not in hits or self._claimed(seat, f.name):
                        continue
                    if f.armed and seat == self.seat0[f.name] and cur is None:
                        break
                    self._bind(f.name, seat)
                    if not f.armed:
                        self.welder.arm(f.name)
                        ev = {"time": float(self.d.time), "fastener": f.name}
                        if seat != self.seat0[f.name]:
                            ev["seat"] = seat
                        self.arm_events.append(ev)
                    break

        def _half_at(self, f, seat):
            """the half whose leg the bolt went through at this bore: the source's unless the other half is there"""
            src = self.clamped0[self.src[seat]][0]
            p = self.d.xpos[f.bid]
            err = {}
            for h in halves:
                hb = self.m.body(h).id
                err[h] = float(np.linalg.norm(self.d.xmat[hb].reshape(3, 3).T @ (p - self.d.xpos[hb]) - self.at_half[seat]))
            other = next(h for h in halves if h != src)
            return other if err[other] < 0.02 and err[other] < err[src] else src

        def _apply(self, m, d, ev, fasteners):
            f = self.fx[ev["fastener"]]
            seat = self.bore.get(f.name, self.seat0[f.name])
            half = self._half_at(f, seat)
            eq = self.welds0[self.src[seat]][1][0]
            hid = m.body(half).id
            m.eq_obj1id[eq] = hid
            f.welds = [self.welds0[f.name][0], (eq, hid)]
            if half != f.clamped[0] or seat != self.seat0[f.name]:
                f.clamped = [half]
                ev["clamped"] = [half]
                ev["seat"] = seat
            SW.SeatWelder.apply_event(m, d, ev, fasteners)

        def status(self):
            out = super().status()
            for b, s in self.bore.items():
                out[b]["seat"] = s
            return out

        def state(self):
            s = super().state()
            s.update(bore=dict(self.bore), eq_obj1id=self.m.eq_obj1id.copy())
            return s

        def set_state(self, s):
            super().set_state(s)
            self.bore = dict(s.get('bore', {}))
            self.m.eq_obj1id[:] = s.get('eq_obj1id', self.obj1_0)
            for b, f in self.fx.items():
                self._bind(b, self.bore.get(b, self.seat0[b]), record=False)
                eq = f.welds[1][0]
                f.welds = [f.welds[0], (eq, int(self.m.eq_obj1id[eq]))]
                if f.welds[1][1] != self.welds0[self.src[self.bore.get(b, self.seat0[b])]][1][1]:
                    f.clamped = [self.m.body(f.welds[1][1]).name]

    def mapped_report(m, d, task, M):
        """success.assembled_report with role -> body M (the same checks, each place measured on the body that took it)"""
        asm = {k: np.array(v) for k, v in task["assembled_poses_world"].items()}
        rep, ok = {}, True
        for n in task["part_types"]:
            if n in ("half_A", "hex_key"):
                continue
            ref = "shelf" if n.startswith("bolt") else "half_A"
            want = np.linalg.inv(asm[ref]) @ asm[n]
            have = np.linalg.inv(SU._T(d, m.body(M[ref]).id)) @ SU._T(d, m.body(M[n]).id)
            err = np.linalg.inv(want) @ have
            dp = float(np.linalg.norm(err[:3, 3])) * 1e3
            if n.startswith("bolt"):
                da = math.degrees(math.acos(min(max(float(err[2, 2]), -1.0), 1.0)))
                dp_ax = float(err[2, 3]) * 1e3
                lat = float(np.hypot(err[0, 3], err[1, 3])) * 1e3
                good = abs(dp_ax) < 0.6 and lat < 0.6 and da < 2
                rep[n] = dict(axial_mm=round(dp_ax, 3), lateral_mm=round(lat, 3), tilt_deg=round(da, 3), ok=bool(good))
            else:
                da = min(SU._angle_deg(err[:3, :3] @ S) for S in SU._symmetries(task, n))
                tol = 3.0 if n == "rod" else 0.6
                good = dp < tol and da < 1.0
                rep[n] = dict(pos_mm=round(dp, 3), rot_deg=round(da, 3), ok=bool(good))
            if M[n] != n:
                rep[n]["part"] = M[n]
            ok = ok and rep[n]["ok"]
        up = d.xmat[m.body(M["half_A"]).id].reshape(3, 3)[:, 2]
        rep["stand_upright_tilt_deg"] = round(math.degrees(math.acos(min(max(float(up[2]), -1.0), 1.0))), 3)
        ok = ok and rep["stand_upright_tilt_deg"] < 1.0
        rep["all_ok"] = bool(ok)
        return rep

    class Monitor(SU.Monitor):
        """success.py's assembled check, passed when it passes for some one-to-one assignment of the identical parts."""

        def report(self):
            rep = SU.assembled_report(self.m, self.d, self.task)
            if not rep["all_ok"]:
                ident = {n: n for n in self.task["part_types"]}
                for hp in itertools.permutations(halves):
                    for bp in itertools.permutations(bolts):
                        M = dict(ident, **dict(zip(halves, hp)), **dict(zip(bolts, bp)))
                        if M == ident:
                            continue
                        r2 = mapped_report(self.m, self.d, self.task, M)
                        if r2["all_ok"]:
                            rep = dict(r2, assignment={k: v for k, v in M.items() if k != v})
                            break
                    if rep["all_ok"]:
                        break
            out = {"success": rep["all_ok"], "assembled": rep}
            if self.mech is not None:
                out["fasteners"] = self.mech.status()
            return out

    return Mechanism, Monitor


def _gladom_rule(groups):
    import itertools, math
    import gladom_mechanism as GM
    import success as SU
    short = set(groups[0])

    class Mechanism(GM.GladomRetention):
        """GladomRetention with the three short screws interchangeable (see IDENTICAL_PARTS): each takes any free
        short-screw nut; a nut's prerequisite pose (frame_b aligned for the bottom nut, the ring placed for the ring
        nuts) and the connections that wait for it follow the nut, not the screw."""

        def __init__(self, model, data, task):
            super().__init__(model, data, task)
            self.short = [o['key'] for o in self.ops if o['part'] in short]
            self.nut = {}          # target position (tuple) -> the short operation that owns it in the source
            for o in self.ops:
                if o['key'] in self.short:
                    for p in [o['target_pos']] + o.get('alt_target_pos', []):
                        self.nut.setdefault(tuple(p), o)
            self.pre = {p: o.get('prerequisite_poses', []) for p, o in self.nut.items()}

        def _candidates(self, o):
            if o['key'] not in self.short:
                return super()._candidates(o)
            taken = [tuple(self.claimed[k]) for k in self.short if k != o['key'] and k in self.claimed]
            c = [o['target_pos']] + o.get('alt_target_pos', [])
            c = c + [list(p) for p in self.nut if list(p) not in c]
            return [p for p in c if tuple(p) not in taken]

        def _deps_ok(self, o):
            """a dependency on a short screw's operation waits for that screw's nut to be taken by any short screw"""
            held = {tuple(self.claimed[k]) for k in self.short if k in self.claimed and self.active(k)}
            for x in o.get('dependencies', []):
                if x not in self.eq:
                    continue
                if x in self.short:
                    if tuple(next(q for q in self.ops if q['key'] == x)['target_pos']) not in held:
                        return False
                elif not self.active(x):
                    return False
            return True

        def update(self):
            self.counter += 1
            if self.counter % self.period:
                return
            dt = self.m.opt.timestep * self.period
            for o in self.ops:
                k = o['key']
                if self.active(k):
                    continue
                g = o['gates']
                if self._far(o):
                    self.dwell[k] = 0.; self.prev_q.pop(k, None); self.peak.pop(k, None)
                    continue
                deps_ok = self._deps_ok(o)
                if not deps_ok and not o.get('count_turns'):
                    gap, lat = self._gap_lat(o)
                    self.peak[k] = max(self.peak.get(k, gap), gap) if lat < self.CORRIDOR_M else gap
                    self.dwell[k] = 0.
                    continue
                me = self.measure(o)
                if me is None:
                    continue
                if me['lateral'] < self.CORRIDOR_M:
                    self.peak[k] = max(self.peak.get(k, me['gap']), me['gap'])
                else:
                    self.peak[k] = me['gap']
                travel = self.peak[k] - me['gap']
                if o.get('count_turns'):
                    c = o['thread_corridor']
                    inside = (me['lateral'] < c['lateral_m'] and me['angle'] < c['axis_deg'] and c['gap_min_m'] < me['gap'] < c['gap_max_m'])
                    q = me['qrel']
                    if inside and k in self.prev_q:
                        dq = GM.qmul(q, GM.qinv(self.prev_q[k]))
                        if dq[0] < 0: dq = -dq
                        self.turns[k] += 2 * math.atan2(float(dq[1:] @ me['axis_host']), dq[0]) * o.get('turn_sign', 1) / (2 * math.pi)
                    if inside: self.prev_q[k] = q
                    else: self.prev_q.pop(k, None)
                contact = self._pair_force(o['part'], o['counterparts']) if o.get('counterparts') else 1e9
                ok = deps_ok and GM.gates_ok(me, g) and contact > g.get('min_contact_N', -1)
                if o.get('min_turns') is not None:
                    ok = ok and self.turns[k] >= o['min_turns']
                if o.get('min_travel_m') is not None:
                    ok = ok and travel >= o['min_travel_m']
                pre_ok = True
                pres = self.pre.get(tuple(me['target_pos']), o.get('prerequisite_poses', [])) if k in self.short else o.get('prerequisite_poses', [])
                for pr in pres:
                    pm = GM.pose_error(self.h, pr['part'], o['host'], pr['target_pos'], pr['target_quats'], tilt=pr.get('tilt', 'full'))
                    pre_ok &= GM.gates_ok(pm, pr['gates'])
                ok = ok and pre_ok
                self.dwell[k] = self.dwell[k] + dt if ok else 0.
                self.metrics[k] = dict(gap_m=me['gap'], lateral_m=me['lateral'], angle_deg=me['angle'], speed_m_s=me['speed'],
                                       contact_N=contact if contact < 1e8 else None, turns=self.turns[k], travel_m=travel,
                                       prerequisites_ok=bool(pre_ok), dependencies_ok=bool(deps_ok), dwell_s=self.dwell[k])
                if self.dwell[k] >= g['dwell_s']:
                    self.claimed[k] = list(me['target_pos'])
                    self.engage(o)

    class Monitor(SU.Monitor):
        """success.py with the three short screws measured against the one-to-one assignment to the bottom and ring
        nuts with the smallest summed lateral error (the source's rule for the two ring screws, extended)."""

        def evaluate(self):
            rep = dict(geometry={}, joints={}, failures=[])
            o = self.ops
            rep['geometry']['frame_b'] = self._pose('frame_b', o['s1-cross-align']['target_pos'], [o['s1-cross-align']['target_quat']] + o['s1-cross-align']['alt_target_quat'])
            rep['geometry']['ring'] = self._pose('ring', o['s3-ring-place']['target_pos'], [o['s3-ring-place']['target_quat']] + o['s3-ring-place']['alt_target_quat'])
            rep['geometry']['tray'] = self._pose('tray', o['s4-tray-place']['target_pos'], yaw_period=self.t['tray']['yaw_period_deg'])
            rep['geometry'][o['s1-123451']['part']] = self._pose(o['s1-123451']['part'], o['s1-123451']['target_pos'], tilt='axis')
            B, L, R = o['s2-122202'], o['s3-122202-left'], o['s3-122202-right']
            nuts = (B['target_pos'], L['target_pos'], R['target_pos'])
            parts = (B['part'], L['part'], R['part'])
            # the source's two choices first (ring screws as placed, then swapped); ties keep the earlier one
            orders = [(0, 1, 2), (0, 2, 1)] + [p for p in itertools.permutations(range(3)) if p not in ((0, 1, 2), (0, 2, 1))]
            best = None
            for p in orders:
                ms = [self._pose(parts[i], nuts[j], tilt='axis') for i, j in zip(p, range(3))]
                tot = sum(x['lateral_m'] for x in ms)
                if best is None or tot < best[0]:
                    best = (tot, p, ms)
            _, p, ms = best
            got = dict(zip(p, ms))
            for i in range(3):
                rep['geometry'][parts[i]] = got[i]
            rep['ring_screws_swapped'] = p == (0, 2, 1)
            if p not in ((0, 1, 2), (0, 2, 1)):
                rep['short_screw_nuts'] = {parts[i]: ('bottom', 'ring_left', 'ring_right')[j] for i, j in zip(p, range(3))}
            for n, r in rep['geometry'].items():
                r['passed'] = self._ok(r)
                if not r['passed']: rep['failures'].append('geometry:' + n)
            for pt, i in self.weld_ids.items():
                rep['joints'][pt] = bool(self.d.eq_active[i])
                if not rep['joints'][pt]: rep['failures'].append('missing_required_model_joint:' + pt)
            tray_ring, touch = self._contacts()
            hist = np.array(self.tray_hist if len(self.tray_hist) else [tray_ring])
            thr = self.t['tray']['min_contact_N']
            support = bool(len(hist) >= self.win and np.count_nonzero(hist > thr) >= math.ceil(self.t['tray']['min_active_fraction'] * self.win) and hist.mean() > thr)
            if not support: rep['failures'].append('unforced_gravity_support:tray')
            released = not touch and not any(self.touch_hist)
            if not released: rep['failures'].append('robot_contact_with_furniture')
            rep.update(tray_ring_contact_N=tray_ring, support=support, released=released,
                       geometry_fraction=float(np.mean([r['passed'] for r in rep['geometry'].values()])),
                       joint_fraction=float(np.mean(list(rep['joints'].values()))))
            if self.scene is not None and getattr(self.scene, 'mech', None) is not None:
                rep['operations'] = {k: dict(v, engaged=self.scene.mech.active(k)) for k, v in self.scene.mech.metrics.items()}
                for k in self.scene.mech.eq:
                    rep.setdefault('operations', {}).setdefault(k, {})['engaged'] = self.scene.mech.active(k)
            rep['instant_ok'] = not rep['failures']
            return rep

    return Mechanism, Monitor


def _turned_same_part(m, a: int, b: int, R: np.ndarray, tol: float = 1e-6) -> bool:
    """Body b is body a turned by R about its centre of mass (b's geometry = R (a's - a's CoM) + b's CoM): the same
    mass, principal inertia and frame (to 1e-6 relative), and every geom of a, turned, has a geom of b of the same type, colour and contact
    fields whose vertices (mesh) or corners (box) lie within tol of a's."""
    close = lambda x, y: np.allclose(x, y, rtol=1e-6, atol=1e-12)   # noqa: E731  (inertia from the meshes, last bits)
    if not (close(m.body_mass[a], m.body_mass[b]) and close(m.body_inertia[a], m.body_inertia[b])
            and close(m.body_iquat[a], m.body_iquat[b]) and np.array_equal(np.abs(R), np.eye(3))):
        return False

    def clouds(x, Rt):
        out = []
        for g in np.flatnonzero(m.geom_bodyid == x):
            q = np.zeros(9); mujoco.mju_quat2Mat(q, m.geom_quat[g]); Rg = q.reshape(3, 3)
            if int(m.geom_type[g]) == int(mujoco.mjtGeom.mjGEOM_MESH):
                i = int(m.geom_dataid[g])
                v = m.mesh_vert[m.mesh_vertadr[i]:m.mesh_vertadr[i] + m.mesh_vertnum[i]]
            elif int(m.geom_type[g]) == int(mujoco.mjtGeom.mjGEOM_BOX):
                v = np.array([[i, j, k] for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)]) * m.geom_size[g]
            else:
                return None
            pts = ((m.geom_pos[g] + v @ Rg.T) - m.body_ipos[x]) @ Rt.T
            key = (int(m.geom_type[g]), tuple(m.geom_rgba[g]), int(m.geom_contype[g]), int(m.geom_conaffinity[g]),
                   tuple(m.geom_friction[g]), len(pts))
            out.append((key, pts, pts.mean(axis=0)))
        return out

    ca, cb = clouds(a, R), clouds(b, np.eye(3))
    if ca is None or cb is None or len(ca) != len(cb):
        return False
    used = set()
    for key, pts, cen in ca:
        hit = None
        for j, (kb, pb, cb_) in enumerate(cb):
            if j in used or kb != key or np.abs(cen - cb_).max() > tol:
                continue
            d = np.linalg.norm(pts[:, None, :] - pb[None, :, :], axis=2)
            if max(d.min(axis=0).max(), d.min(axis=1).max()) <= tol:
                hit = j
                break
        if hit is None:
            return False
        used.add(hit)
    return True


# EKET: the two side panels are one panel (side_b = side_a turned 180 deg about its long x axis; _turned_same_part).
EKET_SIDE_TURN = np.diag([1.0, -1.0, -1.0])


def _eket_rule(groups):
    import eket_ops as EO
    import success as SU
    sa, sb = groups[0]
    R = EKET_SIDE_TURN
    qR = np.zeros(4); mujoco.mju_mat2Quat(qR, R.reshape(-1))

    class Measure(EO.Measure):
        """eket_ops.Measure with the two side panels' roles possibly swapped (`swap`): a role played by the other
        panel is measured at that panel's pose turned into the role's frame (EKET_SIDE_TURN about the CoM)."""

        def __init__(self, m, d, swap=False):
            super().__init__(m, d)
            self.swap = swap
            self.ipos = {r: m.body_ipos[self.bid[r]].copy() for r in (sa, sb)}

        def body(self, role):
            return {sa: sb, sb: sa}.get(role, role) if self.swap else role

        def pose(self, role):
            """world position, rotation matrix and quaternion of role's frame"""
            d = self.d
            b = self.bid[self.body(role)]
            if not self.swap or role not in (sa, sb):
                return d.xpos[b], d.xmat[b].reshape(3, 3), d.xquat[b]
            Rb = d.xmat[b].reshape(3, 3)
            q = np.zeros(4); mujoco.mju_mulQuat(q, d.xquat[b], qR)
            return d.xpos[b] + Rb @ (self.ipos[self.body(role)] - R @ self.ipos[role]), Rb @ R, q

        def relative(self, role, parent='top'):
            if not self.swap or role not in (sa, sb):
                return super().relative(role, parent)
            m, d = self.m, self.d
            a, b = self.bid[parent], self.bid[self.body(role)]
            qa = d.xquat[a]; Ra = d.xmat[a].reshape(3, 3)
            pb, _, qb = self.pose(role)
            delta = pb - d.xpos[a]
            va = np.zeros(6); vb = np.zeros(6)
            mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, a, va, 0)
            mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, vb, 0)
            omega = vb[:3] - va[:3]
            vbp = vb[3:] + EO._cross(vb[:3], pb - d.xpos[b])            # the role frame's origin on body b
            vel = vbp - va[3:] - EO._cross(va[:3], delta)
            return Ra.T @ delta, EO.qmul(EO.qconj(qa), qb), Ra.T @ vel, float(np.linalg.norm(omega))

        def contacts(self, role):
            out = super().contacts(self.body(role))
            return {self.body(k): v for k, v in out.items()} if self.swap else out

    class Tracker(EO.OpTracker):
        """OpTracker where side_a_entry may be done by either side panel: until it is accepted, a second tracker
        measures side_b in side_a's place (and so side_a in side_b's); the first accepted decides the roles. The
        source's own tracker is computed exactly as before."""

        def __init__(self, m, d, canonical):
            super().__init__(m, d, canonical)
            self.alt = None
            self.reset()

        def reset(self):
            super().reset()
            self.swap = False
            self.meas = Measure(self.m, self.d, swap=False)
            if hasattr(self, 'alt'):
                self.alt = EO.OpTracker(self.m, self.d, {k: v.tolist() for k, v in self.canon.items()})
                self.alt.meas = Measure(self.m, self.d, swap=True)

        def update(self):
            if self.alt is None:
                return super().update()
            done = super().update()
            if done is not None:
                self.alt = None          # the source's case: side_a took side A
                return done
            alt = self.alt.update()
            if alt is not None:          # side_b took side A: from now on the roles are swapped
                st = self.alt.state()
                self.alt = None
                self.swap = True
                self.meas = Measure(self.m, self.d, swap=True)
                self.set_state(dict(st, swap=True, alt=None))
            return alt

        def state(self):
            s = super().state()
            s.update(swap=self.swap, alt=None if self.alt is None else self.alt.state())
            return s

        def set_state(self, s):
            super().set_state(s)
            self.swap = bool(s.get('swap', False))
            self.meas = Measure(self.m, self.d, swap=self.swap)
            if s.get('alt') is not None:
                self.alt = EO.OpTracker(self.m, self.d, {k: v.tolist() for k, v in self.canon.items()})
                self.alt.meas = Measure(self.m, self.d, swap=True)
                self.alt.set_state(s['alt'])
            else:
                self.alt = None

    class Mechanism(EO.EketMechanism):
        """EketMechanism on Tracker; a frame joint latched with the side panels' roles swapped joins the panel that is
        there (its weld pointed at that body, the current relative pose as in the source)."""

        def __init__(self, model, data, task):
            super().__init__(model, data, task)
            self.obj0 = (model.eq_obj1id.copy(), model.eq_obj2id.copy())
            self.tracker = Tracker(model, data, task['canonical_in_cabinet_frame'])
            self.reset()

        def reset(self):
            super().reset()
            if hasattr(self, 'obj0'):
                for i in self.eq.values():
                    self.m.eq_obj1id[i], self.m.eq_obj2id[i] = self.obj0[0][i], self.obj0[1][i]

        def role_pose(self, role):
            return self.tracker.meas.pose(role)[:2]

        def latch(self, j):
            if not self.tracker.swap:
                return super().latch(j)
            a, b = (self.tracker.meas.body(x) for x in EO.JOINT_PAIRS[j])
            m, d = self.m, self.d
            ia, ib = m.body(a).id, m.body(b).id
            i = self.eq[j]
            m.eq_obj1id[i], m.eq_obj2id[i] = ia, ib
            Ra = d.xmat[ia].reshape(3, 3)
            r = Ra.T @ (d.xpos[ib] - d.xpos[ia]); q = EO.qmul(EO.qconj(d.xquat[ia]), d.xquat[ib])
            m.eq_data[i, 0:3] = 0; m.eq_data[i, 3:6] = r; m.eq_data[i, 6:10] = q / np.linalg.norm(q); m.eq_data[i, 10] = 1
            d.eq_active[i] = 1
            self.events.append(dict(time_s=float(d.time), joint=j, body1=a, body2=b, local_pos=r.tolist(), local_quat_wxyz=q.tolist()))

        def state(self):
            s = super().state()
            s['eq_obj'] = {j: (int(self.m.eq_obj1id[i]), int(self.m.eq_obj2id[i])) for j, i in self.eq.items()}
            return s

        def set_state(self, s):
            super().set_state(s)
            for j, i in self.eq.items():
                self.m.eq_obj1id[i], self.m.eq_obj2id[i] = s.get('eq_obj', {}).get(j, (self.obj0[0][i], self.obj0[1][i]))

    class Monitor(SU.Monitor):
        """success.py on its own Tracker (as the source's independent replay of the measurement journal)."""

        def __init__(self, model, data, task, scene=None):
            super().__init__(model, data, task, scene)
            self.tracker = Tracker(model, data, task['canonical_in_cabinet_frame'])
            self.reset()

        def report(self):
            rep = super().report()
            if self.tracker.swap:
                rep['side_panels_swapped'] = True
            return rep

    return Mechanism, Monitor


_IDENTICAL_RULES = {"vesken": _vesken_rule, "stegesund": _stegesund_rule, "gladom": _gladom_rule, "eket": _eket_rule}


def identical_parts(task: str, S) -> None:
    """IDENTICAL_PARTS: check that each group is one asset on the compiled model, then give the built scene S the
    scene's mechanism and success monitor with those parts interchangeable, and reset it (the same initial state)."""
    groups = IDENTICAL_PARTS.get(task)
    if not groups:
        return
    m = S.model
    for g in groups:
        bad = [n for n in g[1:] if not (_turned_same_part(m, m.body(g[0]).id, m.body(n).id, EKET_SIDE_TURN) if task == "eket"
                                        else _same_part(m, m.body(g[0]).id, m.body(n).id))]
        if bad:
            raise RuntimeError(f"IDENTICAL_PARTS[{task!r}]: {bad} are not the same part as {g[0]}")
    mech_cls, mon_cls = _IDENTICAL_RULES[task](groups)
    S.mech = mech_cls(S.model, S.data, S.task)
    S.monitor = mon_cls(S.model, S.data, S.task, S)
    S.reset()


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
        identical_parts(self.task, self.S)            # IDENTICAL_PARTS (vesken, stegesund, gladom, eket)
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
        role_pose = getattr(self.S.mech, "role_pose", None)     # IDENTICAL_PARTS: the part that took the place
        for p, b in r["ids"].items():
            xb, Rb = role_pose(p) if role_pose else (d.xpos[b], d.xmat[b].reshape(3, 3))
            err = float(np.linalg.norm(Rf.T @ (xb - d.xpos[f]) - r["goal_pos"][p]))
            Rrel = Rf.T @ Rb
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
