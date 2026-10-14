"""Privileged session of the DexHand `sweep_dustpan` task: fixed dual-arm robot, pre-held broom and dustpan.

The scene is the frozen model `assets/sweep_sharpa.xml` (mesh paths tokenized, four fixed cameras) and its exact
reset `assets/reset.npz` (Wuji Hand 2.2: `assets/reset_wuji.npz`, same arm/tool/debris state, Wuji fingers closed on
the shafts). One control row sets every motor target for one native 0.5 ms physics step (2000 Hz); nothing
else acts on the simulator. The predicate (`checker.py`) is evaluated after every physics step.
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
from checker import SweepChecker

HERE = Path(__file__).resolve().parent
TASK_ID = "sweep_dustpan"
CONFIG_PATH = HERE / "task.json"
ACTION_DIM = {"sharpa": 58, "wuji": 54}  # the hands this task accepts and their row widths
# Wuji Hand 2.2 composes at the same flanges (54 actuators: 14 arm + 20 left + 20 right) and starts from its own
# declared pre-grasp (assets/reset_wuji.npz): every arm, tool, debris and bristle coordinate of the frozen reset with the
# Wuji finger joints closed on the same shafts (README.md "Hands").
UNSUPPORTED_WIDTH = {}
WUJI_RESET = "assets/reset_wuji.npz"
RANGE_TOLERANCE = 1e-9
UNSTABLE = (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL, mujoco.mjtWarning.mjWARN_BADQACC)


def _config(instance=None) -> dict:
    path = Path(instance) if instance else CONFIG_PATH
    if not path.is_file():
        path = HERE / "instance.json"
    return json.loads(path.read_text())


def tianji_dir() -> Path:
    """TIANJI_ASSET_DIR, else the image path, else the repository asset folders next to the Sharpa assets."""
    if os.environ.get("TIANJI_ASSET_DIR"):
        return Path(os.environ["TIANJI_ASSET_DIR"])
    sharpa = hands.sharpa_dir()
    for candidate in (
        Path("/opt/dexhand/tianji"),
        sharpa.parent / "tianji",
        sharpa.parents[2] / "everyday_dexterity/assets/tianji",
    ):
        if (candidate / "converted_collision").is_dir():
            return candidate
    raise FileNotFoundError("Tianji Marvin arm meshes not found (set TIANJI_ASSET_DIR or use the eai-dexhand image)")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_VERIFIED: dict = {}


def scene_xml(config: dict) -> str:
    """The frozen Sharpa scene with every asset hash checked and the path tokens resolved."""
    manifest = json.loads((HERE / "assets/manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if _sha((HERE / "assets" / name).read_bytes()) != digest:
            raise ValueError(f"frozen task asset changed: assets/{name}")
    roots = {"DEXHAND_ASSET_DIR": hands.sharpa_dir(), "TIANJI_ASSET_DIR": tianji_dir()}
    key = tuple(str(v.resolve()) for v in roots.values())
    if key not in _VERIFIED:
        for item in json.loads((HERE / config["external_assets"]).read_text())["files"]:
            data = (roots[item["token"]] / item["path"]).read_bytes()
            if len(data) != item["bytes"] or _sha(data) != item["sha256"]:
                raise ValueError(f"mesh integrity failure: {item['token']}/{item['path']}")
        _VERIFIED[key] = True
    xml = (HERE / config["scene_xml"]).read_text()
    for token, root in roots.items():
        xml = xml.replace("${" + token + "}", str(root))
    return xml


class Session:
    """Simulator session; `step(row)` executes one 0.5 ms physics step with the given motor targets."""

    control_hz = 2000
    substeps = 1

    def __init__(self, task: str = TASK_ID, hand: str | None = None, instance=None, allow_unsupported_hand=False):
        if task != TASK_ID:
            raise ValueError(f"Unknown task: {task!r}")
        self.task = task
        self.hand = hands.selected(hand)
        if self.hand not in ACTION_DIM and not allow_unsupported_hand:
            raise ValueError(f"{TASK_ID} supports only {sorted(ACTION_DIM)}; {self.hand!r} is not available in this task")
        self.config = _config(instance)
        self.spec = self.config
        xml = scene_xml(self.config)
        self.hand_records = None
        if self.hand != "sharpa":
            root = ET.fromstring(xml)
            self.hand_records = hands.replace_wave_hands(root, self.hand)
            xml = ET.tostring(root, encoding="unicode")
        self.xml = xml
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)
        width = {**ACTION_DIM, **UNSUPPORTED_WIDTH}[self.hand]
        if self.model.nu != width:
            raise ValueError(f"{self.hand} scene has {self.model.nu} actuators, expected {width}")
        self.action_dim = int(self.model.nu)
        self.actuator_names = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.joint_names = [self.model.joint(int(j)).name for j in self.model.actuator_trnid[:, 0]]
        self.ctrl_range = self.model.actuator_ctrlrange.copy()
        self._lo, self._hi = self.ctrl_range[:, 0].copy(), self.ctrl_range[:, 1].copy()
        self.control_dt = float(self.model.opt.timestep)
        self.robot = "marvin-bimanual-" + ("sharpa-wave" if self.hand == "sharpa" else "wuji-hand-2.2")
        self.tcp_bodies = ["l_hand_palm", "r_hand_palm"]
        self.max_rows = int(self.config["max_rows"])
        self.max_control_steps = self.max_rows  # published by the standard service; the episode horizon
        self._structure_check()
        with np.load(HERE / self.config["reset"], allow_pickle=False) as saved:
            self._reset = {key: saved[key].copy() for key in saved.files}
        self._reset_hand = None
        if self.hand == "wuji" and not allow_unsupported_hand:  # authoring (build_wuji_reset.py): neutral fingers
            with np.load(HERE / WUJI_RESET, allow_pickle=False) as saved:
                self._reset_hand = {key: saved[key].copy() for key in saved.files}
            self._check_hand_reset()
        self.scene_sha256 = _sha(json.dumps({"xml": xml, "hand": self.hand}, sort_keys=True).encode())
        self.renderer = None
        self.reset()

    # ----------------------------------------------------------------------------------------- setup
    def _structure_check(self) -> None:
        """Robot-only actuation, free tools/debris, no welds, mocap, gravity compensation or disabled gravity."""
        m = self.model
        robot = set()
        base = m.body(self.config["predicate"]["robot_root"]).id
        for body in range(m.nbody):
            if body == base or int(m.body_parentid[body]) in robot:
                robot.add(body)
        problems = []
        for i in range(m.nu):
            joint = int(m.actuator_trnid[i, 0])
            if m.actuator_trntype[i] != mujoco.mjtTrn.mjTRN_JOINT or int(m.jnt_bodyid[joint]) not in robot:
                problems.append("non-robot actuator " + m.actuator(i).name)
        for name in ["broom", "dustpan", *self.config["predicate"]["debris"]]:
            body = m.body(name).id
            joint = int(m.body_jntadr[body])
            if m.body_jntnum[body] != 1 or m.jnt_type[joint] != mujoco.mjtJoint.mjJNT_FREE:
                problems.append(name + " is not a free body")
        if m.neq or m.nmocap or np.any(m.body_gravcomp) or m.opt.disableflags & mujoco.mjtDisableBit.mjDSBL_GRAVITY:
            problems.append("equality, mocap, gravity compensation or disabled gravity")
        if not np.allclose(m.opt.gravity, [0, 0, -9.81], atol=0, rtol=0):
            problems.append("gravity changed")
        if any(m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE and int(m.jnt_bodyid[j]) in robot for j in range(m.njnt)):
            problems.append("floating robot")
        if problems:
            raise ValueError("scene structure check failed: " + "; ".join(problems))

    def _check_hand_reset(self) -> None:
        """The declared Wuji start must describe exactly this model (joint layout and actuator order) and keep every
        non-finger coordinate of the frozen reset bit for bit."""
        m, saved, frozen = self.model, self._reset_hand, self._reset
        names = [m.joint(j).name for j in range(m.njnt)]
        if list(saved["joint_names"]) != names or list(saved["actuator_names"]) != self.actuator_names:
            raise ValueError("assets/reset_wuji.npz does not match the Wuji scene")
        if saved["initial_qpos"].shape != (m.nq,) or saved["initial_ctrl"].shape != (m.nu,):
            raise ValueError("assets/reset_wuji.npz has the wrong size")
        for name, adr, dim in zip(frozen["joint_names"], frozen["joint_qposadr"], frozen["joint_qposdim"]):
            name = str(name)
            if name in names:
                j = names.index(name)
                ours = saved["initial_qpos"][int(m.jnt_qposadr[j]):int(m.jnt_qposadr[j]) + int(dim)]
                if not np.array_equal(ours, frozen["initial_qpos"][int(adr):int(adr) + int(dim)]):
                    raise ValueError(f"assets/reset_wuji.npz changes the frozen coordinate {name}")
        known = {str(n): float(v) for n, v in zip(frozen["actuator_names"], frozen["initial_ctrl"])}
        for i, name in enumerate(self.actuator_names):
            if name in known and saved["initial_ctrl"][i] != known[name]:
                raise ValueError(f"assets/reset_wuji.npz changes the frozen target {name}")

    def reset(self) -> dict:
        m, d, saved = self.model, self.data, self._reset
        mujoco.mj_resetData(m, d)
        if self.hand == "sharpa":
            d.qpos[:] = saved["initial_qpos"]
        elif self._reset_hand is not None:
            d.qpos[:] = self._reset_hand["initial_qpos"]
        else:
            by_name = {
                str(name): saved["initial_qpos"][int(adr) : int(adr) + int(dim)]
                for name, adr, dim in zip(saved["joint_names"], saved["joint_qposadr"], saved["joint_qposdim"])
            }
            # Arm, tool, debris and bristle joints keep the frozen values; Wuji finger joints stay at zero (neutral).
            for j in range(m.njnt):
                name = m.joint(j).name
                adr = int(m.jnt_qposadr[j])
                if name in by_name:
                    d.qpos[adr : adr + len(by_name[name])] = by_name[name]
        # Forward with reset controls, then assign the holding targets (this order fixes the solver warm start).
        mujoco.mj_forward(m, d)
        d.ctrl[:] = self._initial_ctrl()
        self.checker = SweepChecker(m, d, self.config)
        self.actions = []
        self.steps = 0
        self.initial_sha = self.state_sha()
        return self.status()

    def _initial_ctrl(self) -> np.ndarray:
        saved = self._reset
        if self.hand == "sharpa":
            return saved["initial_ctrl"].copy()
        if self._reset_hand is not None:
            return self._reset_hand["initial_ctrl"].copy()
        known = {str(n): float(v) for n, v in zip(saved["actuator_names"], saved["initial_ctrl"])}
        ctrl = np.empty(self.model.nu)
        for i, name in enumerate(self.actuator_names):
            if name in known:
                ctrl[i] = known[name]
            else:
                joint = int(self.model.actuator_trnid[i, 0])
                ctrl[i] = np.clip(self.data.qpos[self.model.jnt_qposadr[joint]], *self.ctrl_range[i])
        return ctrl

    # ----------------------------------------------------------------------------------------- control
    def hold_action(self) -> np.ndarray:
        return self.data.ctrl.copy()

    def validate(self, rows) -> np.ndarray:
        values = np.asarray(rows, dtype=np.float64)
        if values.ndim == 1:
            values = values[None, :]
        if values.ndim != 2 or values.shape[1] != self.action_dim:
            raise ValueError(f"{self.hand} actions need {self.action_dim} targets per row; got shape {np.shape(rows)}")
        if not np.isfinite(values).all():
            raise ValueError("actions must be finite")
        lo, hi = self.ctrl_range.T
        if np.any(values < lo - RANGE_TOLERANCE) or np.any(values > hi + RANGE_TOLERANCE):
            raise ValueError("actuator targets outside model.actuator_ctrlrange")
        return values

    def _advance(self, values: np.ndarray) -> None:
        """Execute one validated row: set the targets, run one native physics step, update the predicate."""
        np.clip(values, self._lo, self._hi, out=self.data.ctrl)
        mujoco.mj_step(self.model, self.data)
        self.actions.append(self.data.ctrl.copy())
        self.steps += 1
        self.checker.observe(self.steps - 1)
        if any(self.data.warning[w].number for w in UNSTABLE) or not np.isfinite(self.data.qacc).all():
            self.checker.fail("unstable_physics")
        if self.steps >= self.max_rows and not self.checker.done:
            self.checker.fail("episode_budget")

    def step(self, row) -> dict:
        """One 0.5 ms physics step. A no-op once the episode is done (success or failure)."""
        if not self.checker.done:
            self._advance(self.validate(row)[0])
        return self.status()

    def step_many(self, rows) -> dict:
        """Execute rows until they end or the episode is done; returns status()."""
        for row in self.validate(rows):
            if self.checker.done:
                break
            self._advance(row)
        return self.status()

    def hold(self, steps: int) -> dict:
        """Keep the current targets for `steps` physics steps."""
        target = self.hold_action()
        for _ in range(int(steps)):
            if self.checker.done:
                break
            self._advance(target)
        return self.status()

    # ----------------------------------------------------------------------------------------- reports
    def status(self) -> dict:
        c = self.checker.state
        success = bool(c["success"])
        failure = c["failure"]
        return {
            "success": success,
            "done": bool(success or failure),
            "failed": bool(failure),
            "reason": "success" if success else failure,
            "steps": self.steps,
            "time_s": self.steps * self.control_dt,
            "stage": self.checker.in_pan() + int(success),
            "total_stages": len(self.config["predicate"]["debris"]) + 1,
            "in_pan": self.checker.in_pan(),
            "terminal_run": c["terminal_run"],
            "hand": self.hand,
        }

    def features(self) -> dict:
        return {**self.checker.features(), "hand": self.hand, "time_s": self.steps * self.control_dt}

    def observe(self) -> dict:
        """Privileged observation: robot joints, targets, tool and debris poses and the predicate diagnostics."""
        d, m = self.data, self.model
        qadr = m.jnt_qposadr[m.actuator_trnid[:, 0]]
        vadr = m.jnt_dofadr[m.actuator_trnid[:, 0]]

        def pose(name):
            body = d.body(name)
            return {"position": body.xpos.tolist(), "quaternion_wxyz": body.xquat.tolist()}

        return {
            "time_s": float(d.time),
            "hand": self.hand,
            "actuator_names": self.actuator_names,
            "joint_positions": d.qpos[qadr].tolist(),
            "joint_velocities": d.qvel[vadr].tolist(),
            "targets": d.ctrl.tolist(),
            "palms": {side: pose(f"{side}_hand_palm") for side in ("l", "r")},
            "broom": pose("broom"),
            "dustpan": pose("dustpan"),
            "debris": {name: pose(name) for name in self.config["predicate"]["debris"]},
            "status": self.status(),
            "features": self.checker.features(),
        }

    def state_sha(self) -> str:
        """sha256 of the native integration state, the predicate state, the hand and the frozen instance."""
        digest = hashlib.sha256(self.physics_state().astype("<f8").tobytes())
        digest.update(json.dumps(self.checker.summary(), sort_keys=True).encode())
        digest.update(self.hand.encode())
        digest.update(json.dumps(self.config, sort_keys=True).encode())
        return digest.hexdigest()

    def physics_state(self) -> np.ndarray:
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        return state

    def physics_sha(self) -> str:
        """sha256 of the raw integration state only (no predicate state)."""
        return _sha(self.physics_state().tobytes())

    # ----------------------------------------------------------------------------------------- tools
    def snapshot(self) -> dict:
        """The complete integration state (what the next physics step depends on) plus the predicate state."""
        return {"state": self.physics_state(), "checker": self.checker.snapshot(), "steps": self.steps,
                "rows": len(self.actions)}

    def restore(self, snapshot: dict) -> dict:
        """Return exactly to a snapshot of this session (subsequent steps are bit-identical)."""
        mujoco.mj_setState(self.model, self.data, snapshot["state"], mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(self.model, self.data)  # derived quantities for features/rendering; state unchanged
        self.checker.restore(snapshot["checker"])
        self.steps = snapshot["steps"]
        del self.actions[snapshot["rows"] :]
        return self.status()

    def executed_actions(self) -> np.ndarray:
        return np.asarray(self.actions, dtype=np.float64).reshape(-1, self.action_dim)

    def save_trajectory(self, actions=None, path="/app/output/trajectory.npz") -> None:
        rows = self.executed_actions() if actions is None else np.asarray(actions, dtype=np.float64)
        hands.write_trajectory(path, rows, hand=self.hand, task=self.task, actuator_names=self.actuator_names)

    def replay(self, actions) -> dict:
        """Reset, then execute the rows until they end or the episode is done (the verifier's semantics)."""
        rows = self.validate(actions)
        self.reset()
        for row in rows:
            if self.checker.done:
                break
            self._advance(row)
        return self.status()

    def cameras(self) -> list[str]:
        return [self.model.camera(i).name for i in range(self.model.ncam)]

    def render_frame(self, camera: str = "overview", width: int = 640, height: int = 480, shadows: bool = False):
        """RGB uint8 (height, width, 3). The scene has 1.6 M mesh faces; software rendering (osmesa) takes about a
        second per frame without shadows or multisampling and several seconds with shadows, so both are off by
        default. Rendering reads the state only."""
        if self.renderer is not None and (self.renderer.width != width or self.renderer.height != height):
            self.close()
        if self.renderer is None:
            samples = int(self.model.vis.quality.offsamples)
            try:
                self.model.vis.quality.offsamples = 0  # framebuffer setting only; restored at once
                self.renderer = mujoco.Renderer(self.model, height=height, width=width)
            finally:
                self.model.vis.quality.offsamples = samples
        self.renderer.update_scene(self.data, camera=camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = shadows
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
        return self.renderer.render().copy()

    def close(self) -> None:
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
