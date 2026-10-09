"""LIBERO-MAX tooling: one frozen LIBERO-MAX case (a LIBERO-PRO task variant plus one online event).

Used by the privileged agent (importable as `lmx_tool`), the privileged verifier and the standard-mode sim service.

    import lmx_tool
    s = lmx_tool.Session("/app/instance.json")   # builds the frozen scene; ONE Session per Python process
    st = s.state()                                # privileged state: hand, gripper, joints, every object's pose, goal
    r = s.step([dx, dy, dz, drx, dry, drz, grip]) # one control step (1/20 s) -> {"success", "done", "event_fired", ...}
    s.save_trajectory()                           # the actions so far -> /app/output/trajectory.npz
    lmx_tool.replay_fresh(actions)                # replay in a NEW process (what the verifier does)
    img = s.render("agentview", 256)              # RGB (256, 256, 3), upright, as the standard-mode cameras see it

The event: when the gripper first comes within the case's trigger distance of the trigger object (LIBERO-MAX's own
on_proximity test), LIBERO-MAX applies its frozen change once (an object or receptacle is moved, an obstacle or
distractors appear, the camera shifts, the lighting, colours or sensor noise change). The episode ends when LIBERO's
success check holds (the task's BDDL goal), or at the suite's step limit.

One simulator per process: some LIBERO-PRO variants do not rebuild bit-exactly a second time in the same process, so
a second Session in one process is refused (start a new process to start over; replay_fresh() does that for you).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import mujoco
import numpy as np

INSTANCE_SCHEMA = "eai-libero-max-instance/1"
N = 7
ACTION_NAMES = ["dx", "dy", "dz", "drx", "dry", "drz", "grip"]
DUMMY = [0.0] * 6 + [-1.0]  # LIBERO's no-op (gripper open), used for the warm-up steps before the agent's first action
SUITE_MAX_STEPS = {"libero_spatial": 220, "libero_object": 280, "libero_goal": 300, "libero_10": 520}
CAMERAS = {"agentview": "agentview", "wrist": "robot0_eye_in_hand"}
HORIZON = 1_000_000
OBS_RES = 128  # resolution of LIBERO's own camera observations (only used by LIBERO-MAX's internal render checks)
_BUILT = {"n": 0}


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def load_instance(path) -> dict:
    inst = json.loads(Path(path).read_text())
    if inst.get("schema") != INSTANCE_SCHEMA or inst.get("instance_sha") != sha(inst["case"]):
        raise ValueError(f"{path}: not a valid frozen LIBERO-MAX instance (schema or hash mismatch)")
    return inst


def load_actions(path, max_bytes: int = 2_000_000) -> np.ndarray:
    """Pickle-free, size-limited loader for an agent's trajectory.npz (key `actions`, shape (T, 7))."""
    import zipfile

    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("archive too large")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or len(names) > 16 or any(not n.endswith(".npy") for n in names):
            raise ValueError("expected a plain .npz (unique .npy members)")
    with np.load(path, allow_pickle=False) as d:
        if "actions" not in d.files:
            raise ValueError("no `actions` array")
        return as_actions(d["actions"])


def as_actions(a) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.size == 0:
        return np.zeros((0, N))
    if a.ndim != 2 or a.shape[1] != N:
        raise ValueError(f"actions must have shape (T, {N}), got {list(a.shape)}")
    if not np.all(np.isfinite(a)):
        raise ValueError("actions contain NaN or inf")
    return np.clip(a, -1.0, 1.0)


def _integration_sha(sim) -> str:
    m, d = sim.model._model, sim.data._data
    a = np.empty(mujoco.mj_stateSize(m, mujoco.mjtState.mjSTATE_INTEGRATION))
    mujoco.mj_getState(m, d, a, mujoco.mjtState.mjSTATE_INTEGRATION)
    return hashlib.sha256(a.tobytes()).hexdigest()


def numerics() -> dict:
    """The CPU-dependent numeric kernels this process uses. The frozen hashes were made with OpenBLAS's Zen kernels
    (OPENBLAS_CORETYPE=Zen, set in the image: unpinned, OpenBLAS 0.3.18 picks per CPU, e.g. its generic Prescott
    kernels on Sapphire Rapids) and numpy's AVX-512 math loops, so a CPU without AVX-512 cannot rebuild them."""
    import ctypes

    out = {"OPENBLAS_CORETYPE": os.environ.get("OPENBLAS_CORETYPE")}
    try:
        from numpy.core._multiarray_umath import __cpu_features__ as feats

        out["numpy_avx512_skx"] = bool(feats.get("AVX512_SKX"))
        with open("/proc/self/maps") as f:
            libs = sorted({ln.split()[-1] for ln in f if "libopenblas" in ln})
        for lib in libs:
            dll = ctypes.CDLL(lib)
            get = getattr(dll, "openblas_get_corename64_", None) or dll.openblas_get_corename
            get.restype = ctypes.c_char_p
            out[Path(lib).name.split("-")[0]] = get().decode()
    except Exception as exc:  # noqa: BLE001  (diagnostics only)
        out["error"] = repr(exc)[:200]
    return out


def build(case: dict):
    """LIBERO-MAX's own path: the LIBERO-PRO task variant, its initial state, the PRO substrate and the event runtime.
    Returns (wrapped env, task, robosuite env). Raises if this process already built a simulator."""
    if _BUILT["n"]:
        raise RuntimeError(
            "one simulator per process: some LIBERO-PRO variants do not rebuild bit-exactly in the same process, so "
            "a second Session here could silently differ from the frozen instance. Start a new Python process "
            "(lmx_tool.replay_fresh(actions) replays in one for you)."
        )
    _BUILT["n"] += 1
    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs import OffScreenRenderEnv
    from libero_max.cosmos_integration import CosmosInterventionEnv
    from libero_max.pro_runtime import wrap_case_env
    from libero_max.substrate import load_case_task

    task, init_states = load_case_task(case, benchmark, {})
    bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    seed = int(case["policy_seed"])
    np.random.seed(seed)
    # horizon: robosuite refuses actions after `horizon` steps (LIBERO default 1000); the suite limits and the standard
    # episode cap apply instead. It does not touch the physics.
    env = OffScreenRenderEnv(bddl_file_name=str(bddl), camera_heights=OBS_RES, camera_widths=OBS_RES, horizon=HORIZON)
    env.seed(seed)
    env = wrap_case_env(env, case)
    env.seed(seed)
    wrapped = CosmosInterventionEnv(
        env=env, task_description=task.language, scenario=case["scenario"], arm="intervention",
        trace_path=Path(os.environ.get("LMX_TRACE", "/tmp/lmx-trace.jsonl")),
        original_task_index=case["task_index"], init_state_index=case["init_state_index"],
    )  # fmt: skip
    wrapped.configure_episode(task_suite_name=case["task_suite_name"], policy_seed=seed, query_interval=16,
                              max_policy_steps=SUITE_MAX_STEPS[case["task_suite_name"]])  # fmt: skip
    wrapped.reset()
    wrapped.set_init_state(init_states[case["init_state_index"]])
    for _ in range(wrapped.warmup_steps):
        wrapped.step(DUMMY)
    inner = wrapped  # down to robosuite's BDDL env (vars(): the wrappers delegate attribute lookups)
    for _ in range(8):
        if "parsed_problem" in vars(inner):
            break
        inner = vars(inner).get("_env") or vars(inner).get("env")
    else:
        raise RuntimeError("could not find LIBERO's BDDL environment under the wrappers")
    return wrapped, task, inner


class Session:
    def __init__(self, instance="/app/instance.json", check: bool = True):
        self.inst = load_instance(instance) if isinstance(instance, (str, Path)) else instance
        self.case = self.inst["case"]
        self.wrapped, self.task, self.env = build(self.case)
        self.sim = self.env.sim
        self.initial_state_sha = _integration_sha(self.sim)
        if check and self.initial_state_sha != self.inst.get("initial_state_sha"):
            raise RuntimeError(
                "the frozen instance did not rebuild bit-exactly (different simulator, assets, versions or CPU "
                f"numeric kernels): {self.initial_state_sha[:12]} != {str(self.inst.get('initial_state_sha'))[:12]}; "
                f"numerics here: {canonical(numerics())} (frozen with OpenBLAS Zen kernels and numpy AVX-512 loops)"
            )
        self.max_steps = SUITE_MAX_STEPS[self.case["task_suite_name"]]
        self.actions: list[np.ndarray] = []
        self.targets = np.array(DUMMY)
        self.done = self.success = False
        self.trigger_step = None
        self.instruction = self.task.language

    # -- episode -------------------------------------------------------------------------------------------------
    def step(self, action) -> dict:
        """One control step (1/20 s) with a = [dx, dy, dz, drx, dry, drz, grip], clipped to [-1, 1]."""
        if self.done:
            raise RuntimeError("the episode is over: LIBERO's success check holds (no more actions are accepted)")
        a = as_actions(np.asarray(action, dtype=np.float64).reshape(1, -1))[0]
        _, _, done, _ = self.wrapped.step(a.tolist())
        self.actions.append(a)
        self.targets = a
        if self.wrapped.events and self.trigger_step is None:
            self.trigger_step = len(self.actions)
        if done:
            self.done = self.success = True
        return self.report()

    def report(self) -> dict:
        return {
            "success": bool(self.success),
            "done": bool(self.done),
            "control_steps": len(self.actions),
            "event_fired": self.trigger_step is not None,
            "event_step": self.trigger_step,
            "steps_left": self.max_steps - len(self.actions),
        }

    def check(self) -> bool:
        return bool(self.wrapped.check_success())

    def replay(self, actions) -> dict:
        """Execute `actions` from the frozen start (this Session must be fresh: no action taken yet)."""
        if self.actions:
            raise RuntimeError("replay needs a fresh Session (one per process); use lmx_tool.replay_fresh(actions)")
        a = as_actions(actions)
        for i, row in enumerate(a):
            if self.done:
                return {**self.result(), "invalid": f"{len(a) - i} actions after the episode ended (success)"}
            self.step(row)
        return self.result()

    def result(self) -> dict:
        return {**self.report(), "state_sha": _integration_sha(self.sim), "initial_state_sha": self.initial_state_sha}

    def save_trajectory(self, actions=None, path="/app/output/trajectory.npz", meta: dict | None = None) -> str:
        a = as_actions(self.actions if actions is None else actions)
        if not 1 <= len(a) <= self.max_steps:
            raise ValueError(f"a trajectory has 1..{self.max_steps} actions, got {len(a)}")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=a, meta=np.array(canonical(meta or {})))
        return str(path)

    # -- state ---------------------------------------------------------------------------------------------------
    def state_sha(self) -> str:
        return _integration_sha(self.sim)

    def entity_pose(self, name: str) -> dict:
        b = self.wrapped.backend
        entity, fixture = b._entity(name)
        bid = self.sim.model.body_name2id(entity.root_body)
        return {"pos": self.sim.data.body_xpos[bid].copy(), "quat_wxyz": self.sim.data.body_xquat[bid].copy()}

    def eef(self) -> dict:
        obs = self.env._get_observations()
        x, y, z, w = obs["robot0_eef_quat"]
        return {"pos": np.asarray(obs["robot0_eef_pos"], float), "quat_wxyz": np.array([w, x, y, z])}

    def state(self) -> dict:
        """Privileged state (world frame, metres, quaternions w x y z)."""
        robot = self.env.robots[0]
        objs = {n: self.entity_pose(n) for n in self.env.objects_dict}
        fixtures = {n: self.entity_pose(n) for n in self.env.fixtures_dict}
        return {
            "eef": self.eef(),
            "gripper_qpos": self.sim.data.qpos[robot._ref_gripper_joint_pos_indexes].copy(),
            "joint_pos": self.sim.data.qpos[robot._ref_joint_pos_indexes].copy(),
            "joint_vel": self.sim.data.qvel[robot._ref_joint_vel_indexes].copy(),
            "objects": objs,
            "fixtures": fixtures,
            "articulations": self.articulations(),
            "goal": self.goal(),
            "instruction": self.instruction,
            **self.report(),
        }

    def articulations(self) -> dict:
        """Position of every slide (m) and hinge (rad) joint of the scene that is not the robot's: drawers, doors, knobs."""
        m = self.sim.model
        out = {}
        for j in range(m.njnt):
            name = m.joint_id2name(j) or ""
            if m.jnt_type[j] in (2, 3) and not name.startswith(("robot0_", "gripper0_")):
                out[name] = float(self.sim.data.qpos[m.jnt_qposadr[j]])
        return out

    def goal(self) -> list:
        return [list(g) for g in self.env.parsed_problem["goal_state"]]

    def proprio(self) -> np.ndarray:
        robot = self.env.robots[0]
        e = self.eef()
        return np.concatenate(
            [
                e["pos"],
                e["quat_wxyz"],
                self.sim.data.qpos[robot._ref_gripper_joint_pos_indexes],
                self.sim.data.qpos[robot._ref_joint_pos_indexes],
                self.sim.data.qvel[robot._ref_joint_vel_indexes],
                self.targets,
            ]
        ).astype(np.float32)

    # -- cameras -------------------------------------------------------------------------------------------------
    def calibration(self, camera: str, hw: int) -> dict:
        """Pinhole intrinsics (OpenCV, upright image) and the camera-to-world pose (OpenGL: looks along -z, +y up),
        as the camera is NOW (a camera_shift event moves agentview and changes its field of view)."""
        m, d = self.sim.model, self.sim.data
        cid = m.camera_name2id(CAMERAS[camera])
        fovy = float(m.cam_fovy[cid])
        f = 0.5 * hw / np.tan(np.deg2rad(fovy) / 2)
        pose = np.eye(4)
        pose[:3, :3] = np.asarray(d.cam_xmat[cid]).reshape(3, 3)
        pose[:3, 3] = d.cam_xpos[cid]
        return {"intrinsic_cv": [[f, 0, hw / 2], [0, f, hw / 2], [0, 0, 1]], "cam2world_gl": pose.tolist(),
                "fovy_deg": fovy, "hw": [hw, hw]}  # fmt: skip

    def render(self, camera: str, hw: int = 256, depth: bool = False):
        """Upright RGB (uint8 HxWx3) as the agent's cameras deliver it: LIBERO-PRO's frozen pixel perturbation of the
        variant and, once the event fired, LIBERO-MAX's image change (sensor noise, colour theme) are applied.
        With depth=True also returns metric depth (float32 HxW, metres)."""
        name = CAMERAS[camera]
        out = self.sim.render(camera_name=name, width=hw, height=hw, depth=depth)
        rgb, buf = out if depth else (out, None)
        key = f"{name}_image"
        obs = {key: np.ascontiguousarray(rgb)}
        pro = getattr(self.wrapped, "_env", None)
        if hasattr(pro, "transform_observation"):
            obs = pro.transform_observation(obs)
        if self.wrapped.runtime.applied and hasattr(self.wrapped.backend, "transform_observation"):
            obs = self.wrapped.backend.transform_observation(obs)
        img = np.ascontiguousarray(np.asarray(obs[key])[::-1])
        if not depth:
            return img
        m = self.sim.model
        extent = m.stat.extent
        near, far = m.vis.map.znear * extent, m.vis.map.zfar * extent
        metric = near / (1 - buf * (1 - near / far))
        return img, np.ascontiguousarray(metric[::-1]).astype(np.float32)

    def controller(self) -> dict:
        c = self.env.robots[0].controller
        return {"output_max": np.asarray(c.output_max).tolist(), "output_min": np.asarray(c.output_min).tolist(),
                "input_max": np.asarray(c.input_max).tolist(), "input_min": np.asarray(c.input_min).tolist(),
                "control_freq": float(self.env.control_freq)}  # fmt: skip

    def robot_base(self) -> dict:
        bid = self.sim.model.body_name2id(self.env.robots[0].robot_model.root_body)
        return {"pos": self.sim.data.body_xpos[bid].round(6).tolist(),
                "quat_wxyz": self.sim.data.body_xquat[bid].round(6).tolist()}  # fmt: skip


def replay_fresh(actions, instance="/app/instance.json", video: str | None = None) -> dict:
    """Replay `actions` in a new Python process from the frozen instance (what the verifier does)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "a.npy"
        np.save(p, as_actions(actions))
        args = [sys.executable, os.path.abspath(__file__), "--replay", str(instance), str(p)] + (
            [video] if video else []
        )
        out = subprocess.run(args, check=True, capture_output=True, text=True)
        return json.loads(out.stdout.strip().splitlines()[-1])


def _replay_main(instance, actions_path, video=None) -> None:
    s = Session(instance)
    a = np.load(actions_path)
    frames = []
    if video:
        frames.append(s.render("agentview", 256))
    r = None
    for i, row in enumerate(a):
        if s.done:
            r = {**s.result(), "invalid": f"{len(a) - i} actions after the episode ended (success)"}
            break
        s.step(row)
        if video and (i % 2 == 1 or i == len(a) - 1):
            frames.append(s.render("agentview", 256))
    r = r or s.result()
    if video:
        import imageio.v2 as imageio
        from PIL import Image

        with imageio.get_writer(video, fps=10, codec="libx264", macro_block_size=1) as w:
            for f in frames:
                w.append_data(f)
        Image.fromarray(frames[-1]).save(str(video).removesuffix(".mp4") + ".last.png")
        r["video"] = True
    print(json.dumps(r))


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--replay":
        _replay_main(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
