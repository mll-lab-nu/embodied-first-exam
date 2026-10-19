"""Two-handle pot to shelf transfer: frozen dual-arm scene, actuator-only stepping and a strict fail-fast predicate.

The scene is frozen (fixed Tianji Marvin stand with two 7-joint arms, a dexterous hand on each wrist,
a free 1 kg two-handle stockpot on a worktop and an open kitchen shelf). One action row is one 2 ms physics step
(500 Hz): every actuator target is applied for exactly one ``mj_step``. Nothing but the robot's position servos acts
on the world; the pot moves only through contact and gravity.

The success predicate is evaluated after every physics step from simulator state only (contacts, poses, velocities,
geometry distances); see ``task.json`` ``predicate`` for every threshold and ``Session._evaluate`` for the logic.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

import hands  # noqa: E402

HERE = Path(__file__).resolve().parent
TASK_ID = "pot_shelf_transfer"
CONFIG = json.loads((HERE / "task.json").read_text())
P = CONFIG["predicate"]
SUPPORTED_HANDS = ("sharpa", "wuji")
STATE = mujoco.mjtState.mjSTATE_INTEGRATION
# Owner codes of bodies/geoms: the pot, each hand (everything below its wrist mount), the rest of the robot, the world.
WORLD, POT, LEFT, RIGHT, ROBOT = 0, 1, 2, 3, 4
OWNER_NAMES = {WORLD: "world", POT: "pot", LEFT: "left_hand", RIGHT: "right_hand", ROBOT: "robot"}


class AssetError(RuntimeError):
    """A frozen model or mesh file is missing or differs from the pinned manifest."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _root_dir(name: str, record: dict) -> Path:
    if "relative" in record:
        return HERE / "assets" / record["relative"]
    if name == "sharpa":
        return hands.sharpa_dir()
    value = os.environ.get(record["env"])
    if value:
        return Path(value)
    candidates = [Path(record["default"]), hands.sharpa_dir().parent / name]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise AssetError(f"{name} assets not found; set {record['env']} or use the eai-dexhand image")


_VERIFIED: dict[str, str] = {}


def frozen_sharpa_xml() -> str:
    """The frozen MJCF with every mesh path resolved, after checking every byte against assets/manifest.json."""
    manifest = json.loads((HERE / "assets/manifest.json").read_text())
    raw = (HERE / "assets" / manifest["model"]["file"]).read_bytes()
    if _sha(raw) != manifest["model"]["sha256"]:
        raise AssetError("frozen scene XML differs from its manifest")
    text = raw.decode()
    for name, record in manifest["roots"].items():
        folder = _root_dir(name, record).resolve()
        key = f"{name}:{folder}"
        if key not in _VERIFIED:
            for relative, expected in record["files"].items():
                path = folder / relative
                if not path.is_file():
                    raise AssetError(f"{name} asset missing: {relative} under {folder}")
                data = path.read_bytes()
                if len(data) != expected["bytes"] or _sha(data) != expected["sha256"]:
                    raise AssetError(f"{name} asset integrity failure: {relative}")
            _VERIFIED[key] = str(folder)
        text = text.replace(f'file="{record["placeholder"]}/', f'file="{folder}/')
    if "@" in "".join(line for line in text.splitlines() if 'file="' in line):
        raise AssetError("unresolved asset placeholder in the frozen scene")
    return text


def build(hand: str):
    """Compile the frozen scene for ``hand``; returns (model, xml, records)."""
    xml = frozen_sharpa_xml()
    if hand == "sharpa":
        return mujoco.MjModel.from_xml_string(xml), xml, None
    root = ET.fromstring(xml)
    records = hands.replace_wave_hands(root, hand)
    root.set("model", root.get("model", "pot") + f" / {hand}")
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml, records


class Session:
    """Privileged tooling and the trusted replay engine of ``pot_shelf_transfer``.

    One ``step(row)`` applies one row of actuator position targets for one 2 ms physics step. The episode ends at the
    first failure (fail-fast, permanent) or when the terminal released hold on the shelf completes (success).
    """

    control_dt = 0.002
    control_hz = 500
    substeps = 1

    def __init__(self, task: str = TASK_ID, hand: str | None = None, instance=None):
        if task != TASK_ID:
            raise ValueError(f"Unknown task {task!r}; this runtime serves {TASK_ID!r}")
        self.task = TASK_ID
        self.hand = hands.selected(hand)
        if self.hand not in SUPPORTED_HANDS:
            raise hands.HandError(f"hand {self.hand!r} is not available in {TASK_ID}")
        self.config = CONFIG
        self.spec = CONFIG
        self.model, self.xml, self.hand_records = build(self.hand)
        self.data = mujoco.MjData(self.model)
        m = self.model
        if abs(float(m.opt.timestep) - self.control_dt) > 1e-15:
            raise AssetError("frozen timestep changed")
        self.action_dim = int(m.nu)
        self.actuator_names = [m.actuator(i).name for i in range(m.nu)]
        self.joint_names = [m.joint(int(m.actuator_trnid[i, 0])).name for i in range(m.nu)]
        self.actuator_ranges = m.actuator_ctrlrange.copy()
        self.max_rows = int(CONFIG["max_rows"])
        self.robot = CONFIG["robot"][self.hand]
        self.tcp_body = "r_hand_palm"
        self.tcp_bodies = ["l_hand_palm", "r_hand_palm"]
        # Path-independent scene identity: the pinned scene/asset manifest, the hand (and its pinned asset manifest)
        # and the frozen instance. Every file named there was verified byte for byte before compiling.
        identity = {"manifest": _sha((HERE / "assets/manifest.json").read_bytes()), "hand": self.hand,
                    "config": CONFIG}
        if self.hand == "wuji":
            # The pinned physics files (MJCF + meshes) only: the image ships a subset manifest of the same files.
            pinned = hands.verify_wuji()
            identity["wuji"] = {
                "source_commit": pinned.get("source_commit"),
                "files": {path: entry["sha256"] for path, entry in sorted(pinned["files"].items())
                          if path.startswith(("mjcf/", "meshes/"))},
            }
        self.scene_sha256 = _sha(json.dumps(identity, sort_keys=True).encode())
        self._classify()
        self._reset_targets()
        self.renderer = None
        self.reset()

    # ------------------------------------------------------------------ model bookkeeping
    def _classify(self) -> None:
        m = self.model
        owner = np.zeros(m.nbody, dtype=np.int8)
        for body in range(m.nbody):
            parent, code = body, WORLD
            while parent:
                name = m.body(parent).name or ""
                if name == "pot":
                    code = POT
                    break
                if name == "l_hand_palm":
                    code = LEFT
                    break
                if name == "r_hand_palm":
                    code = RIGHT
                    break
                if name == "base_link":
                    code = ROBOT
                    break
                parent = int(m.body_parentid[parent])
            owner[body] = code
        self.body_owner = owner
        self.geom_owner = owner[m.geom_bodyid]
        collides = (m.geom_contype | m.geom_conaffinity) > 0
        self.pot_body = m.body("pot").id
        joint = int(m.body_jntadr[self.pot_body])
        self.pot_qadr = int(m.jnt_qposadr[joint])
        self.pot_dadr = int(m.jnt_dofadr[joint])
        self.pot_geoms = np.flatnonzero((self.geom_owner == POT) & collides)
        self.hand_geoms = np.flatnonzero(((self.geom_owner == LEFT) | (self.geom_owner == RIGHT)) & collides)
        self.counter_geom = m.geom("source_counter").id
        self.shelf_geom = m.geom("target_shelf").id
        robot_joints = np.flatnonzero(m.jnt_type == mujoco.mjtJoint.mjJNT_HINGE)
        self.limit_qadr = m.jnt_qposadr[robot_joints]
        self.limit_range = m.jnt_range[robot_joints].copy()
        board = m.geom(self.shelf_geom)
        self.board_lo = board.pos[:2] - board.size[:2]
        self.board_hi = board.pos[:2] + board.size[:2]
        self.board_top = float(board.pos[2] + board.size[2])
        left, right, back, top = (m.geom(name) for name in ("shelf_left", "shelf_right", "shelf_back", "shelf_top"))
        self.bay_lo = np.array([left.pos[0] + left.size[0], self.board_lo[1] - P["front_overhang_m"]])
        self.bay_hi = np.array([right.pos[0] - right.size[0], back.pos[1] - back.size[1]])
        self.bay_top = float(top.pos[2] - top.size[2])
        self.target = np.asarray(CONFIG["target_pot_xyz_m"], dtype=float)

    def _reset_targets(self) -> None:
        """Per-hand reset: Sharpa = the frozen keyframe; Wuji = the same arm/pot state with neutral (0) fingers."""
        m = self.model
        record = json.loads((HERE / "assets/reset.json").read_text())
        self._keyframe = int(m.key(record["keyframe"]).id) if self.hand == "sharpa" else None
        qpos = m.qpos0.copy()
        for joint in range(m.njnt):
            name = m.joint(joint).name
            start = int(m.jnt_qposadr[joint])
            end = int(m.jnt_qposadr[joint + 1]) if joint + 1 < m.njnt else m.nq
            if name in record["qpos_by_joint"]:
                qpos[start:end] = record["qpos_by_joint"][name]
            elif m.jnt_type[joint] == mujoco.mjtJoint.mjJNT_HINGE and m.jnt_limited[joint]:
                qpos[start] = np.clip(0.0, *m.jnt_range[joint])
        ctrl = np.zeros(m.nu)
        for i, name in enumerate(self.actuator_names):
            if name in record["ctrl_by_actuator"]:
                ctrl[i] = record["ctrl_by_actuator"][name]
            else:
                ctrl[i] = np.clip(qpos[m.jnt_qposadr[m.actuator_trnid[i, 0]]], *m.actuator_ctrlrange[i])
        self._reset_qpos, self._reset_ctrl = qpos, ctrl

    # ------------------------------------------------------------------ episode
    def reset(self) -> dict:
        m, d = self.model, self.data
        if self._keyframe is not None:
            mujoco.mj_resetDataKeyframe(m, d, int(self._keyframe))
        else:
            mujoco.mj_resetData(m, d)
            d.qpos[:] = self._reset_qpos
            d.ctrl[:] = self._reset_ctrl
        mujoco.mj_forward(m, d)
        self.steps = 0
        self.actions: list[np.ndarray] = []
        self.success = False
        self.failure: str | None = None
        self.failure_detail = ""
        self.lift_steps = 0
        self.hold_steps = 0
        self.free_steps = 0
        self.peak = {"tilt_rad": 0.0, "hand_penetration_m": 0.0, "joint_overshoot_rad": 0.0, "free_steps": 0,
                     "drop_speed_m_s": 0.0}
        self._last = self._measure()
        self.initial_sha = self.state_sha()
        return self.status()

    @property
    def done(self) -> bool:
        return bool(self.success or self.failure)

    def hold_action(self) -> np.ndarray:
        return self.data.ctrl.copy()

    def validate(self, action) -> np.ndarray:
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (self.action_dim,):
            raise ValueError(f"{self.hand} rows must have {self.action_dim} actuator targets; got shape {values.shape}")
        if not np.isfinite(values).all():
            raise ValueError("actuator targets must be finite")
        lo, hi = self.actuator_ranges.T
        tolerance = P["ctrl_range_tolerance"]
        if np.any(values < lo - tolerance) or np.any(values > hi + tolerance):
            bad = int(np.flatnonzero((values < lo - tolerance) | (values > hi + tolerance))[0])
            raise ValueError(f"target {self.actuator_names[bad]}={values[bad]!r} outside {self.actuator_ranges[bad]}")
        return np.clip(values, lo, hi)

    def step(self, action) -> dict:
        """Apply one row for one 2 ms physics step and evaluate the predicate. A no-op once the episode is done."""
        if self.done:
            return self.status()
        values = self.validate(action)
        m, d = self.model, self.data
        d.ctrl[:] = values
        self.actions.append(values.copy())
        mujoco.mj_step(m, d)
        self.steps += 1
        bad = mujoco.mjtWarning
        warnings = (bad.mjWARN_BADQPOS, bad.mjWARN_BADQVEL, bad.mjWARN_BADQACC)
        unstable = any(d.warning[w].number for w in warnings)
        mujoco.mj_forward(m, d)
        if unstable:
            self._fail("unstable_physics", "MuJoCo reported a bad position, velocity or acceleration")
        else:
            self._evaluate()
        if not self.done and self.steps >= self.max_rows:
            self._fail("step_budget", f"no success within {self.max_rows} rows")
        return self.status()

    def replay(self, actions) -> dict:
        """Reset, execute rows until the episode is done or the rows end, and return the verdict."""
        if isinstance(actions, (str, Path)):
            actions, hand, _ = hands.read_trajectory(actions, widths={self.hand: self.action_dim},
                                                     max_rows=self.max_rows, task=self.task)
        rows = np.asarray(actions, dtype=np.float64)
        if rows.ndim != 2 or rows.shape[1] != self.action_dim:
            raise ValueError(f"{self.hand} actions must have shape (T, {self.action_dim})")
        for row in rows:  # validate everything before any physics runs
            self.validate(row)
        self.reset()
        for row in rows:
            if self.done:
                break
            self.step(row)
        return self.status()

    def save_trajectory(self, actions=None, path="/app/output/trajectory.npz") -> Path:
        """Write the deliverable (`actions` + `hand` + `task`); ``save_trajectory(path)`` saves the rows run so far."""
        if isinstance(actions, (str, Path)):
            actions, path = None, actions
        rows = np.asarray(self.actions if actions is None else actions, dtype=np.float64).reshape(-1, self.action_dim)
        hands.write_trajectory(path, rows, hand=self.hand, task=self.task)
        return Path(path)

    # ------------------------------------------------------------------ snapshots
    def snapshot(self) -> dict:
        """Exact copy of the physics state and the predicate's episode state (restore() continues bit for bit)."""
        state = np.empty(mujoco.mj_stateSize(self.model, STATE))
        mujoco.mj_getState(self.model, self.data, state, STATE)
        return {
            "state": state,
            "episode": json.loads(json.dumps(self._episode_state())),
            "actions": [row.copy() for row in self.actions],
            "hand": self.hand,
        }

    def restore(self, snapshot: dict) -> dict:
        if snapshot.get("hand") != self.hand:
            raise ValueError("snapshot belongs to a different hand")
        mujoco.mj_setState(self.model, self.data, np.asarray(snapshot["state"], dtype=np.float64), STATE)
        mujoco.mj_forward(self.model, self.data)
        episode = snapshot["episode"]
        self.steps, self.success, self.failure = episode["steps"], episode["success"], episode["failure"]
        self.failure_detail = episode["failure_detail"]
        self.lift_steps, self.hold_steps, self.free_steps = (
            episode["lift_steps"], episode["hold_steps"], episode["free_steps"])
        self.peak = dict(episode["peak"])
        self.actions = [np.asarray(row, dtype=np.float64).copy() for row in snapshot["actions"]]
        self._last = self._measure()
        return self.status()

    # ------------------------------------------------------------------ predicate
    def _fail(self, reason: str, detail: str) -> None:
        if not self.done:
            self.failure, self.failure_detail = reason, detail

    def _measure(self) -> dict:
        """Contacts (normal force >= contact_force_n counts as a load-bearing contact) and pose of the current state."""
        m, d = self.model, self.data
        n = int(d.ncon)
        result = {
            "touching": False, "hand_contacts": {LEFT: 0, RIGHT: 0}, "hand_load_n": {LEFT: 0.0, RIGHT: 0.0},
            "support": [], "other_pot_contacts": [], "bad": [], "hand_depth_m": 0.0, "pot_contact_geoms": set(),
        }
        if n:
            geoms = np.asarray(d.contact.geom[:n])
            owners = self.geom_owner[geoms]
            wrench = np.zeros(6)
            for i in np.flatnonzero((owners != WORLD).any(axis=1)):
                g1, g2 = int(geoms[i, 0]), int(geoms[i, 1])
                a, b = int(owners[i, 0]), int(owners[i, 1])
                if POT in (a, b):
                    result["touching"] = True
                    result["pot_contact_geoms"].add(g2 if a == POT else g1)
                mujoco.mj_contactForce(m, d, int(i), wrench)
                if wrench[0] < P["contact_force_n"]:
                    continue
                if POT in (a, b):
                    other, other_geom = (b, g2) if a == POT else (a, g1)
                    if other in (LEFT, RIGHT):
                        force = d.contact.frame[i].reshape(3, 3).T @ wrench[:3]
                        force *= -1 if a == POT else 1
                        result["hand_contacts"][other] += 1
                        result["hand_load_n"][other] += float(force[2])
                        result["hand_depth_m"] = max(result["hand_depth_m"], -float(d.contact.dist[i]))
                    elif other == WORLD and other_geom in (self.counter_geom, self.shelf_geom):
                        result["support"].append(other_geom)
                    elif other == WORLD:
                        result["other_pot_contacts"].append(self._geom_name(other_geom))
                    else:
                        result["bad"].append(("pot_robot_link_contact", self._geom_name(other_geom)))
                elif a == b and a in (LEFT, RIGHT):
                    continue  # inherited internal hand self-contact (disclosed, not judged)
                else:
                    result["bad"].append(("robot_collision", f"{self._geom_name(g1)}|{self._geom_name(g2)}"))
        position = d.xpos[self.pot_body].copy()
        velocity = d.qvel[self.pot_dadr:self.pot_dadr + 6]
        result["position"] = position
        result["tilt_rad"] = float(np.arccos(np.clip(d.xmat[self.pot_body, 8], -1.0, 1.0)))
        result["linear_speed"] = float(np.linalg.norm(velocity[:3]))
        result["vertical_velocity"] = float(velocity[2])
        result["angular_speed"] = float(np.linalg.norm(velocity[3:]))
        q = d.qpos[self.limit_qadr]
        result["joint_overshoot_rad"] = float(
            np.max(np.maximum(self.limit_range[:, 0] - q, q - self.limit_range[:, 1]), initial=0.0))
        return result

    def _geom_name(self, geom: int) -> str:
        m = self.model
        return m.geom(geom).name or m.body(int(m.geom_bodyid[geom])).name

    def hand_clearance(self, limit: float | None = None) -> float:
        """Smallest distance between any hand collision geom and any pot collision geom, capped at ``limit``."""
        m, d = self.model, self.data
        limit = float(P["withdrawn_clearance_m"] * 2 if limit is None else limit)
        centers_h, centers_p = d.geom_xpos[self.hand_geoms], d.geom_xpos[self.pot_geoms]
        gap = (np.linalg.norm(centers_h[:, None, :] - centers_p[None, :, :], axis=2)
               - m.geom_rbound[self.hand_geoms][:, None] - m.geom_rbound[self.pot_geoms][None, :])
        best = limit
        fromto = np.zeros(6)
        for i, j in zip(*np.nonzero(gap < best)):
            best = min(best, mujoco.mj_geomDistance(m, d, int(self.hand_geoms[i]), int(self.pot_geoms[j]), best,
                                                     fromto))
        return float(best)

    def pot_extent(self) -> tuple[np.ndarray, np.ndarray]:
        """World axis-aligned bounds of the pot's collision geometry (exact per-geom oriented AABBs)."""
        m, d = self.model, self.data
        geoms = self.pot_geoms
        rotation = d.geom_xmat[geoms].reshape(-1, 3, 3)
        center = d.geom_xpos[geoms] + np.einsum("nij,nj->ni", rotation, m.geom_aabb[geoms, :3])
        half = np.einsum("nij,nj->ni", np.abs(rotation), m.geom_aabb[geoms, 3:])
        return (center - half).min(axis=0), (center + half).max(axis=0)

    def _terminal(self, f: dict) -> tuple[bool, str]:
        """The released-on-shelf state; returns (ok, first unmet condition)."""
        position = f["position"]
        if np.linalg.norm(position[:2] - self.target[:2]) > P["target_xy_tolerance_m"]:
            return False, "pot_not_at_target_xy"
        if abs(position[2] - self.target[2]) > P["target_z_tolerance_m"]:
            return False, "pot_not_at_target_height"
        if f["tilt_rad"] > P["upright_tilt_rad"]:
            return False, "pot_not_upright"
        if f["linear_speed"] > P["linear_speed_m_s"] or f["angular_speed"] > P["angular_speed_rad_s"]:
            return False, "pot_moving"
        radius = P["vessel_radius_m"]
        if np.any(position[:2] - radius < self.board_lo) or np.any(position[:2] + radius > self.board_hi):
            return False, "vessel_not_on_shelf_board"
        if self.shelf_geom not in f["support"] or f["pot_contact_geoms"] - {self.shelf_geom}:
            return False, "pot_not_resting_on_shelf_alone"
        lo, hi = self.pot_extent()
        if (np.any(lo[:2] < self.bay_lo) or np.any(hi[:2] > self.bay_hi) or hi[2] > self.bay_top
                or lo[2] < self.board_top - P["target_z_tolerance_m"]):
            return False, "pot_not_inside_compartment"
        if self.hand_clearance(P["withdrawn_clearance_m"]) < P["withdrawn_clearance_m"]:
            return False, "hands_not_withdrawn"
        return True, ""

    def _evaluate(self) -> None:
        f = self._measure()
        self._last = f
        position = f["position"]
        self.peak["tilt_rad"] = max(self.peak["tilt_rad"], f["tilt_rad"])
        self.peak["hand_penetration_m"] = max(self.peak["hand_penetration_m"], f["hand_depth_m"])
        self.peak["joint_overshoot_rad"] = max(self.peak["joint_overshoot_rad"], f["joint_overshoot_rad"])
        self.free_steps = 0 if f["touching"] else self.free_steps + 1
        self.peak["free_steps"] = max(self.peak["free_steps"], self.free_steps)
        self.peak["drop_speed_m_s"] = max(self.peak["drop_speed_m_s"], -f["vertical_velocity"])
        lo, hi = np.asarray(P["workspace_lo_m"]), np.asarray(P["workspace_hi_m"])
        # ---- fail-fast invariants (the first violation ends the episode as a failure)
        if position[2] < P["fell_below_z_m"]:
            return self._fail("pot_fell", f"pot base at z={position[2]:.4f} m, below {P['fell_below_z_m']} m")
        if np.any(position < lo) or np.any(position > hi):
            return self._fail("pot_left_workspace", f"pot base at {np.round(position, 4).tolist()}")
        if f["tilt_rad"] > P["tipped_tilt_rad"]:
            return self._fail("pot_tipped", f"tilt {f['tilt_rad']:.3f} rad > {P['tipped_tilt_rad']} rad")
        if self.free_steps > P["max_free_steps"]:
            return self._fail("pot_dropped", f"pot touched nothing for {self.free_steps} steps")
        if -f["vertical_velocity"] > P["max_drop_speed_m_s"]:
            return self._fail("pot_dropped", f"pot falling at {-f['vertical_velocity']:.3f} m/s")
        if f["other_pot_contacts"]:
            return self._fail("pot_hit_environment", ", ".join(sorted(set(f["other_pot_contacts"]))))
        if f["bad"]:
            kind, detail = f["bad"][0]
            return self._fail(kind, detail)
        if f["hand_depth_m"] > P["max_hand_penetration_m"]:
            return self._fail("hand_penetration", f"{f['hand_depth_m'] * 1000:.2f} mm hand-pot penetration")
        if f["joint_overshoot_rad"] > P["max_joint_overshoot_rad"]:
            return self._fail("joint_limit", f"joint overshoot {f['joint_overshoot_rad']:.4f} rad")
        # ---- stage 1: bimanual carry (both hands bear upward load, no support contact, pot raised)
        lifted = (position[2] > P["lift_min_z_m"] and not f["support"]
                  and f["hand_load_n"][LEFT] >= P["min_hand_up_load_n"]
                  and f["hand_load_n"][RIGHT] >= P["min_hand_up_load_n"])
        self.lift_steps += int(lifted)
        if self.lift_steps < P["lift_steps"]:
            self.hold_steps = 0
            return None
        # ---- stage 2: released, stable, fully placed on the shelf, hands withdrawn, held for the hold window
        ok, _ = self._terminal(f)
        self.hold_steps = self.hold_steps + 1 if ok else 0
        if self.hold_steps >= P["hold_steps"]:
            self.success = True
        return None

    def _episode_state(self) -> dict:
        return {
            "steps": int(self.steps), "success": bool(self.success), "failure": self.failure,
            "failure_detail": self.failure_detail, "lift_steps": int(self.lift_steps),
            "hold_steps": int(self.hold_steps), "free_steps": int(self.free_steps),
            "peak": {k: float(v) for k, v in self.peak.items()},
        }

    # ------------------------------------------------------------------ observation
    def stage(self) -> int:
        return 2 if self.success else int(self.lift_steps >= P["lift_steps"])

    def status(self) -> dict:
        return {
            "success": bool(self.success),
            "done": self.done,
            "failed": bool(self.failure),
            "reason": "success" if self.success else (self.failure or ""),
            "detail": self.failure_detail,
            "steps": int(self.steps),
            "stage": self.stage(),
            "total_stages": 2,
            "lift_s": self.lift_steps * self.control_dt,
            "hold_s": self.hold_steps * self.control_dt,
            "hand": self.hand,
        }

    def features(self) -> dict:
        """Diagnostics of the current state (all privileged)."""
        f = self._last
        ok, unmet = self._terminal(f) if f["support"] or f["touching"] else (False, "pot_not_resting_on_shelf_alone")
        lo, hi = self.pot_extent()
        return {
            **self.status(),
            "pot_position_m": f["position"].tolist(),
            "pot_quat_wxyz": self.data.xquat[self.pot_body].tolist(),
            "pot_tilt_rad": f["tilt_rad"],
            "pot_linear_speed_m_s": f["linear_speed"],
            "pot_angular_speed_rad_s": f["angular_speed"],
            "pot_extent_m": [lo.tolist(), hi.tolist()],
            "hand_contacts": {"left": f["hand_contacts"][LEFT], "right": f["hand_contacts"][RIGHT]},
            "hand_up_load_n": {"left": f["hand_load_n"][LEFT], "right": f["hand_load_n"][RIGHT]},
            "support": sorted(self._geom_name(g) for g in set(f["support"])),
            "pot_touching": bool(f["touching"]),
            "hand_penetration_m": f["hand_depth_m"],
            "terminal_ok": bool(ok),
            "terminal_unmet": unmet,
            "peak": dict(self.peak),
        }

    def observe(self) -> dict:
        m, d = self.model, self.data
        qadr = m.jnt_qposadr[m.actuator_trnid[:, 0]]
        dadr = m.jnt_dofadr[m.actuator_trnid[:, 0]]
        wrists = {}
        for body in self.tcp_bodies:
            index = m.body(body).id
            wrists[body] = np.concatenate([d.xpos[index], d.xquat[index]]).tolist()
        return {
            "time_s": float(d.time),
            "hand": self.hand,
            "actuator_names": self.actuator_names,
            "joint_positions": d.qpos[qadr].tolist(),
            "joint_velocities": d.qvel[dadr].tolist(),
            "targets": d.ctrl.tolist(),
            "wrist_poses_wxyz": wrists,
            "pot_pose_wxyz": np.concatenate([d.xpos[self.pot_body], d.xquat[self.pot_body]]).tolist(),
            **self.status(),
        }

    def state_sha(self) -> str:
        state = np.empty(mujoco.mj_stateSize(self.model, STATE))
        mujoco.mj_getState(self.model, self.data, state, STATE)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(json.dumps({"episode": self._episode_state(), "hand": self.hand, "task": self.task,
                                  "scene": self.scene_sha256}, sort_keys=True).encode())
        return digest.hexdigest()

    def physics_sha(self) -> str:
        """sha256 of the MuJoCo integration state alone (no predicate or hand label)."""
        state = np.empty(mujoco.mj_stateSize(self.model, STATE))
        mujoco.mj_getState(self.model, self.data, state, STATE)
        return hashlib.sha256(state.astype("<f8").tobytes()).hexdigest()

    # ------------------------------------------------------------------ rendering
    def cameras(self) -> list[str]:
        return list(CONFIG["cameras"])

    def render_frame(self, camera: str = "overview", width: int = 640, height: int = 480, shadows: bool = False):
        """RGB uint8 (height, width, 3). Shadows are off by default: the arm meshes make a shadowed frame about four
        times slower under software rendering (the eai-dexhand image renders with OSMesa)."""
        if camera not in self.cameras():
            raise ValueError(f"unknown camera {camera!r}; choose one of {self.cameras()}")
        if self.renderer is not None and (self.renderer.width != width or self.renderer.height != height):
            self.close()
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=height, width=width)
        self.renderer.update_scene(self.data, camera=camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = shadows
        return self.renderer.render().copy()

    def close(self) -> None:
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
