"""Paper half-fold: frozen accepted Sharpa paper scene, selectable hand, strict released-crease predicate.

Physics is the accepted T06 episode's: the frozen compiled scene (`scene_sharpa.xml`, byte-identical compiled
model), the unchanged passive elastic/plastic shell (`shell.py`), 0.5 ms implicitfast integration and 40 substeps
per 20 ms control. The order of operations in `step` is the original runtime's, so recorded controls reproduce the
accepted episode bit for bit. Added on top, without touching physics: hand selection, fail-fast support checks, an
explicit on-table condition in the released predicate, terminal success, snapshots and trajectory metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

import hands
from shell import PaperShell

HERE = Path(__file__).resolve().parent
TASK_ID = "paper_half_fold"
STATE = mujoco.mjtState.mjSTATE_INTEGRATION
STAGES = ("folded", "creased", "released_on_table", "held")


def load_spec(instance=None) -> dict:
    """The frozen instance: `instance.json` in a task directory, `task.json` in the authoring folder."""
    if instance is None:
        instance = HERE / "instance.json" if (HERE / "instance.json").is_file() else HERE / "task.json"
    spec = json.loads(Path(instance).read_text())
    if spec.get("id") != TASK_ID:
        raise ValueError("Unknown task specification")
    return spec


def compiled_digest(model) -> str:
    """SHA256 of the compiled binary model (mj_saveModel): the frozen-physics identity of the Sharpa scene."""
    buffer = np.empty(mujoco.mj_sizeModel(model), dtype=np.uint8)
    mujoco.mj_saveModel(model, None, buffer)
    return hashlib.sha256(buffer.tobytes()).hexdigest()


def array_digest(model) -> str:
    """SHA256 of every compiled model array except the mesh file-path table (Wuji meshes use absolute paths)."""
    digest = hashlib.sha256()
    for name in sorted(dir(model)):
        if name.startswith("_") or name == "paths" or name.endswith("pathadr"):
            continue
        try:
            value = getattr(model, name)
        except Exception:  # noqa: BLE001 - some attributes are not readable arrays
            continue
        if isinstance(value, np.ndarray):
            digest.update(f"{name}:{value.dtype.str}:{value.shape}".encode())
            digest.update(np.ascontiguousarray(value).tobytes())
    return digest.hexdigest()


def build(spec: dict, hand: str):
    """Compile the frozen scene for one hand and apply the original post-compile settings.

    Sharpa compiles the frozen accepted XML as is (only its mesh folder is filled in). Wuji replaces the Sharpa hand
    subtree with the manufacturer's model on the same wrist-stage mount (shared `hands.replace_wave_hands`).
    """
    meshdir = str((hands.sharpa_dir() / "assets/right").resolve())
    xml = (HERE / spec["scene_xml"]).read_text().replace("${DEXHAND_SHARPA_MESHDIR}", meshdir)
    if hand == "sharpa":
        record = {"hand": "sharpa", "root_body": "right_hand_C_MC"}
    else:
        root = ET.fromstring(xml)
        record = hands.replace_wave_hands(root, hand)[0]
        # Drop the Sharpa mesh assets no element references any more. Unused meshes cannot act on physics, but
        # MuJoCo's process-wide mesh cache would make their compiled polygon data depend on what was compiled
        # earlier in the process, and with them the model identity hash.
        used = {item.get("mesh") for item in root.iter() if item.tag != "mesh" and item.get("mesh")}
        assets = root.find("asset")
        for mesh in list(assets.findall("mesh")):
            if mesh.get("name") not in used:
                assets.remove(mesh)
        root.set("model", "paper_half_fold / " + hand)
        xml = ET.tostring(root, encoding="unicode")
    model = mujoco.MjModel.from_xml_string(xml)
    config = spec["config"]
    # Original scene.build: paper edge-constraint compliance and vertex damping (set after compilation).
    flex_eq = model.eq_type == mujoco.mjtEq.mjEQ_FLEX
    model.eq_solref[flex_eq] = (config["edge_timeconst_s"], 1)
    model.eq_solimp[flex_eq] = (0.9999, 0.9999, 0.0001, 0.5, 2)
    for body in model.flex_vertbodyid:
        start = int(model.body_dofadr[body])
        count = int(model.body_dofnum[body])
        if count:
            model.dof_damping[start : start + count] = 0.00006
    return model, xml, record


class Session:
    """Privileged session. All state (model, data, paper shell) is readable; only motor targets act."""

    def __init__(self, task=TASK_ID, hand=None, instance=None):
        if task != TASK_ID:
            raise ValueError("Unknown task: " + str(task))
        self.spec = load_spec(instance)
        self.config = self.spec["config"]
        self.support = self.spec["support"]
        self.hand = hands.selected(hand)
        self.model, self.xml, self.hand_record = build(self.spec, self.hand)
        self.model_sha256 = compiled_digest(self.model) if self.hand == "sharpa" else array_digest(self.model)
        expected = self.spec.get("model_sha256", {}).get(self.hand)
        if expected and expected != self.model_sha256:
            raise RuntimeError(f"Compiled {self.hand} scene differs from the frozen model; check the image assets")
        self.data = mujoco.MjData(self.model)
        self.jids = self.model.actuator_trnid[:, 0]
        self.qadr = self.model.jnt_qposadr[self.jids]
        self.vadr = self.model.jnt_dofadr[self.jids]
        self.action_dim = self.model.nu
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.joint_names = [self.model.joint(int(j)).name for j in self.jids]
        self.control_dt = self.config["control_dt"]
        self.substeps = int(round(self.control_dt / self.config["physics_dt"]))
        self.max_control_steps = int(self.config["max_steps"])  # technical episode cap (PROTOCOL 4.5)
        if not np.isclose(self.substeps * self.config["physics_dt"], self.control_dt, rtol=0, atol=1e-12):
            raise ValueError("Control dt must be an integer multiple of physics dt")
        if self.model.nflex != 1 or self.model.nflexvert != self.config["grid"][0] * self.config["grid"][1]:
            raise RuntimeError("Unexpected paper topology")
        self.shell = PaperShell(self.model, self.data, self.config)
        self.renderer = None
        self.reset()

    # ----------------------------------------------------------------- episode
    def initial_targets(self) -> np.ndarray:
        """Sharpa: the accepted pregrasp. Wuji: the same six wrist targets and a collision-free curled pregrasp."""
        lo, hi = self.model.actuator_ctrlrange.T
        if self.hand == "sharpa":
            initial = np.asarray(self.config["initial_hand"], dtype=float)
        else:
            initial = np.r_[self.config["initial_hand"][:6], self.spec["wuji_initial_fingers"]].astype(float)
        return np.clip(initial, lo, hi)

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        initial = self.initial_targets()
        self.data.qpos[self.qadr] = initial
        self.data.ctrl[:] = self.data.qpos[self.qadr]
        self.shell.reset()
        self.steps = 0
        self.failure = None
        self.actions = []
        self.max_contact_force = 0.0
        self.min_contact_distance = 0.0
        self.released_hold = 0
        self.success = False
        self.peak_stage = 0
        mujoco.mj_forward(self.model, self.data)
        self.initial_sha = self.state_sha()
        return self.status()

    def hold_action(self) -> np.ndarray:
        return self.data.ctrl.copy()

    @property
    def done(self) -> bool:
        return bool(self.success or self.failure)

    def step(self, action):
        action = np.asarray(action, dtype=np.float64)
        if action.shape != (self.action_dim,) or not np.isfinite(action).all():
            raise ValueError(f"Expected {self.action_dim} finite actuator targets for hand {self.hand}")
        lo, hi = self.model.actuator_ctrlrange.T
        if np.any(action < lo - 1e-7) or np.any(action > hi + 1e-7):
            raise ValueError("Actuator target outside the declared limits")
        if self.done:
            # Failure is fail-fast and success is terminal: later rows are not executed.
            return self.features()
        self.data.ctrl[:] = np.clip(action, lo, hi)
        self.actions.append(self.data.ctrl.copy())
        for _ in range(self.substeps):
            self.shell.apply()
            mujoco.mj_step(self.model, self.data)
            if any(
                self.data.warning[w].number
                for w in (
                    mujoco.mjtWarning.mjWARN_BADQPOS,
                    mujoco.mjtWarning.mjWARN_BADQVEL,
                    mujoco.mjtWarning.mjWARN_BADQACC,
                )
            ):
                self.failure = "unstable_physics"
                break
            if self.shell.max_strain > self.config["max_strain"]:
                self.failure = "excessive_stretch"
                break
            # Read-only support check of the latest vertex positions (every 0.5 ms substep).
            self.failure = self.support_failure(self.data.flexvert_xpos)
            if self.failure:
                break
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        if not self.failure:
            self.failure = self.support_failure(self.data.flexvert_xpos)
        features = self.features()
        terminal = self.released_goal(features)
        self.released_hold = self.released_hold + 1 if terminal and not self.failure else 0
        self.success = self.released_hold >= self.config["goal_hold_steps"] and not self.failure
        if self.steps >= self.config["max_steps"] and not self.success and not self.failure:
            self.failure = "episode_budget"
        features = self.features()
        self.peak_stage = max(self.peak_stage, features["stage"])
        return features

    # --------------------------------------------------------------- predicate
    def support_failure(self, x) -> str | None:
        """Fail-fast: the sheet may not hang below the table top or leave the workspace (any vertex)."""
        s = self.support
        if float(x[:, 2].min()) < s["table_top_z_m"] - s["below_table_tolerance_m"]:
            return "paper_fell_below_table"
        if (
            float(x[:, 0].min()) < s["workspace_x_m"][0]
            or float(x[:, 0].max()) > s["workspace_x_m"][1]
            or float(x[:, 1].min()) < s["workspace_y_m"][0]
            or float(x[:, 1].max()) > s["workspace_y_m"][1]
            or float(x[:, 2].max()) > s["workspace_z_max_m"]
        ):
            return "paper_left_workspace"
        return None

    def on_table(self, x) -> bool:
        """Every vertex lies over the table top (no overhang) and not below it."""
        s = self.support
        return bool(
            float(x[:, 0].min()) >= s["table_x_m"][0]
            and float(x[:, 0].max()) <= s["table_x_m"][1]
            and float(x[:, 1].min()) >= s["table_y_m"][0]
            and float(x[:, 1].max()) <= s["table_y_m"][1]
            and float(x[:, 2].min()) >= s["table_top_z_m"] - s["released_on_table_tolerance_m"]
        )

    def folded(self, f) -> bool:
        return f["fold_angle_rad"] > self.config["goal_fold_angle_rad"] and f["edge_alignment_m"] < self.config["goal_alignment_m"]

    def creased(self, f) -> bool:
        return (
            f["crease_angle_rad"] > self.config["goal_crease_angle_rad"]
            and f["crease_coverage"] >= self.config["goal_crease_coverage"]
        )

    def released_goal(self, f) -> bool:
        """The original released predicate plus the explicit on-table condition."""
        return bool(
            self.folded(f)
            and self.creased(f)
            and f["hand_contacts"] == 0
            and f["max_strain"] < self.config["max_strain"]
            and f["on_table"]
        )

    def features(self) -> dict:
        nx, ny = self.config["grid"]
        x = self.data.flexvert_xpos.reshape(nx, ny, 3)
        origin = x[nx // 2].mean(axis=0)
        end = x[-1].mean(axis=0)
        direction = end - origin
        fold_angle = float(np.arctan2(max(direction[2], 0.0), direction[0]))
        hinge_x = self.shell.reference_positions[self.shell.hinges[:, :2], 0]
        center = np.isclose(hinge_x, self.config["length_m"] / 2, atol=1e-6).all(axis=1)
        rest = np.abs(self.shell.rest_angles[center])
        hand_contacts = 0
        finger_contacts = set()
        peak = 0.0
        wrench = np.zeros(6)
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            if 0 not in c.flex:
                continue
            self.min_contact_distance = min(self.min_contact_distance, float(c.dist))
            for g in (int(c.geom1), int(c.geom2)):
                if g < 0:
                    continue
                if int(self.model.geom_bodyid[g]) > 0:
                    hand_contacts += 1
                    name = self.model.geom(g).name or ""
                    for finger in ("thumb", "index", "middle", "ring", "pinky"):
                        if finger in name:
                            finger_contacts.add(finger)
                    mujoco.mj_contactForce(self.model, self.data, i, wrench)
                    peak = max(peak, float(np.linalg.norm(wrench[:3])))
        self.max_contact_force = max(self.max_contact_force, peak)
        flat = self.data.flexvert_xpos
        f = {
            "fold_angle_rad": fold_angle,
            "crease_angle_rad": float(np.mean(rest)) if len(rest) else 0.0,
            "crease_coverage": float(np.mean(rest > self.config["goal_crease_angle_rad"])) if len(rest) else 0.0,
            "edge_alignment_m": float(np.linalg.norm(x[-1] - x[0], axis=1).mean()),
            "tip_position": end.tolist(),
            "hand_contacts": hand_contacts,
            "finger_contacts": sorted(finger_contacts),
            "max_strain": self.shell.max_strain,
            "min_contact_distance_m": self.min_contact_distance,
            "peak_contact_force_n": self.max_contact_force,
            "plastic_work_j": float(self.shell.plastic_work.sum()),
            "paper_min_z_m": float(flat[:, 2].min()),
            "paper_max_x_m": float(flat[:, 0].max()),
            "on_table": self.on_table(flat),
            "released_hold_steps": self.released_hold,
            "success": self.success,
            "failure": self.failure,
            "steps": self.steps,
        }
        stage = 0
        if self.folded(f):
            stage = 1
            if self.creased(f):
                stage = 2
                if f["hand_contacts"] == 0 and f["on_table"] and f["max_strain"] < self.config["max_strain"]:
                    stage = 3
                    if self.success:
                        stage = 4
        f["stage"] = stage
        return f

    @property
    def reason(self) -> str:
        return "success" if self.success else (self.failure or "")

    def status(self) -> dict:
        f = self.features()
        return {
            "task": TASK_ID,
            "hand": self.hand,
            "success": bool(self.success),
            "done": self.done,
            "reason": self.reason,
            "failed": bool(self.failure),
            "failure": self.failure,
            "steps": self.steps,
            "released_hold_steps": self.released_hold,
            "stage": f["stage"],
            "peak_stage": self.peak_stage,
            "total_stages": len(STAGES),
            "stages": list(STAGES),
            "state_sha": self.state_sha(),
        }

    # ------------------------------------------------------------ privileged io
    def state_sha(self) -> str:
        state = np.empty(mujoco.mj_stateSize(self.model, STATE))
        mujoco.mj_getState(self.model, self.data, state, STATE)
        digest = hashlib.sha256(state.astype("<f8").tobytes())
        digest.update(self.shell.rest_angles.astype("<f8").tobytes())
        digest.update(self.shell.plastic_work.astype("<f8").tobytes())
        digest.update(self.shell.plastic_strain.astype("<f8").tobytes())
        digest.update(
            json.dumps(
                {
                    "task": TASK_ID,
                    "hand": self.hand,
                    "model": self.model_sha256,
                    "config": self.config,
                    "support": self.support,
                    "steps": self.steps,
                    "hold": self.released_hold,
                    "success": self.success,
                    "failure": self.failure,
                    "max_strain": self.shell.max_strain,
                },
                sort_keys=True,
            ).encode()
        )
        return digest.hexdigest()

    def snapshot(self) -> dict:
        """Complete restorable episode state (physics, paper material memory, counters)."""
        state = np.empty(mujoco.mj_stateSize(self.model, STATE))
        mujoco.mj_getState(self.model, self.data, state, STATE)
        return {
            "hand": self.hand,
            "state": state,
            "rest_angles": self.shell.rest_angles.copy(),
            "plastic_strain": self.shell.plastic_strain.copy(),
            "plastic_work": self.shell.plastic_work.copy(),
            "max_strain": self.shell.max_strain,
            "steps": self.steps,
            "failure": self.failure,
            "released_hold": self.released_hold,
            "success": self.success,
            "peak_stage": self.peak_stage,
            "actions": [a.copy() for a in self.actions],
            "max_contact_force": self.max_contact_force,
            "min_contact_distance": self.min_contact_distance,
        }

    def restore(self, snap: dict):
        if snap.get("hand") != self.hand:
            raise ValueError("Snapshot belongs to another hand")
        mujoco.mj_setState(self.model, self.data, np.asarray(snap["state"], dtype=np.float64), STATE)
        self.shell.rest_angles = np.asarray(snap["rest_angles"], dtype=np.float64).copy()
        self.shell.plastic_strain = np.asarray(snap["plastic_strain"], dtype=np.float64).copy()
        self.shell.plastic_work = np.asarray(snap["plastic_work"], dtype=np.float64).copy()
        self.shell.max_strain = float(snap["max_strain"])
        self.steps = int(snap["steps"])
        self.failure = snap["failure"]
        self.released_hold = int(snap["released_hold"])
        self.success = bool(snap["success"])
        self.peak_stage = int(snap["peak_stage"])
        self.actions = [np.asarray(a, dtype=np.float64).copy() for a in snap["actions"]]
        self.max_contact_force = float(snap["max_contact_force"])
        self.min_contact_distance = float(snap["min_contact_distance"])
        mujoco.mj_forward(self.model, self.data)
        return self.status()

    def save_trajectory(self, actions=None, path="/app/output/trajectory.npz"):
        """Write `actions` (default: the rows executed since reset) plus `hand`, `task` and `actuator_names`.

        The verifier replays only the rows, on the recorded hand. `save_trajectory(path)` also works.
        """
        if isinstance(actions, (str, Path)):
            actions, path = None, actions
        rows = np.asarray(self.actions if actions is None else actions, dtype=np.float64)
        if rows.ndim != 2 or rows.shape[1] != self.action_dim:
            raise ValueError(f"Expected a (T, {self.action_dim}) array for hand {self.hand}")
        hands.write_trajectory(path, rows, hand=self.hand, task=TASK_ID, actuator_names=self.actuator_names)
        return Path(path)

    def replay(self, actions) -> dict:
        """Reset, execute rows (an array or a saved trajectory path) and return the status."""
        if isinstance(actions, (str, Path)):
            from replay import read

            actions, hand, _names = read(actions)
            if hand != self.hand:
                raise ValueError(f"Trajectory is for hand {hand}; this session uses {self.hand}")
        self.reset()
        for row in np.asarray(actions, dtype=np.float64):
            self.step(row)
            if self.done:
                break
        return self.status()

    def observe(self, camera=None, width=640, height=480) -> dict:
        obs = {
            "time_s": float(self.data.time),
            "joint_names": self.joint_names,
            "joint_positions": self.data.qpos[self.qadr].copy(),
            "joint_velocities": self.data.qvel[self.vadr].copy(),
            "joint_targets": self.data.ctrl.copy(),
            "paper_vertices": self.data.flexvert_xpos.copy(),
            "paper_rest_angles": self.shell.rest_angles.copy(),
            "features": self.features(),
        }
        if camera is not None:
            obs["rgb"] = self.render_frame(camera, width, height)
        return obs

    def cameras(self):
        return ["overview", "side"]

    def render_frame(self, camera="overview", width=640, height=480, shadows=True):
        if self.renderer is not None and (self.renderer.width != width or self.renderer.height != height):
            self.close()
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=height, width=width)
        self.renderer.update_scene(self.data, camera=camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = shadows
        return self.renderer.render().copy()

    def close(self):
        if self.renderer:
            self.renderer.close()
            self.renderer = None
