"""Replay a recorded episode dataset back into the sim to self-check it.

Rebuilds the environment from the H5's task/seed, feeds the recorded absolute
end-effector-pose + gripper actions open-loop, and checks that the replayed eef
trajectory faithfully tracks the recorded one (hard gate). Runs headless (no
rendering), so it is far faster than recording.

Task success handling differs by task:
- swap (rigid): success IS evaluated (`SwapPuzzleEvaluator`) and reported; a hard
  gate only with ``require_success``.
- untangle / cable_routing (PBD): success is NOT evaluated. Open-loop ee-pose
  replay drives only the arm; the rope/connector manipulation (latch + attachment
  + primitive callbacks) cannot be reproduced from ee poses, so a success verdict
  would be meaningless. Only ee-trajectory tracking is checked. Rope behaviour is
  validated by the recorded images + inspect_dataset value checks instead.

    python -m topogym.data.replay runs/dataset_tests/<ts>/<task>_seed0.h5
"""

from __future__ import annotations

import argparse
import types
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"
_COMMON = CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml"
_ENV = CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml"
_ROBOT = CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik.yaml"


@dataclass(frozen=True)
class ReplayReport:
    """Outcome of replaying one recorded episode."""

    task_id: str
    seed: int
    frames: int
    steps_per_target: int
    max_pos_err: float
    max_pos_err_frame: int
    mean_pos_err: float
    p99_pos_err: float
    final_pos_err: float
    pos_tol: float
    tracking_ok: bool
    success: bool | None  # None = not evaluated (PBD tasks)
    recorded_success: bool
    require_success: bool

    @property
    def passed(self) -> bool:
        if not self.tracking_ok:
            return False
        if self.require_success:
            return self.success is True
        return True

    def summary(self) -> str:
        success = "n/a" if self.success is None else self.success
        return (
            f"task={self.task_id} seed={self.seed} frames={self.frames} "
            f"steps_per_target={self.steps_per_target} "
            f"p99_pos_err={self.p99_pos_err:.4f} mean_pos_err={self.mean_pos_err:.4f} "
            f"max_pos_err={self.max_pos_err:.4f}@frame{self.max_pos_err_frame} "
            f"final_pos_err={self.final_pos_err:.4f} pos_tol={self.pos_tol:.4f} "
            f"tracking_ok={self.tracking_ok} success={success} "
            f"recorded_success={self.recorded_success} "
            f"require_success={self.require_success} passed={self.passed}"
        )


def _read_episode(h5_path):
    import h5py

    with h5py.File(h5_path, "r") as f:
        ep = f["episode_0"]
        setup = ep["setup"]
        task_id = setup.attrs["task_id"]
        task_id = task_id.decode() if isinstance(task_id, bytes) else str(task_id)
        seed = int(setup.attrs["seed"])
        recorded_success = bool(setup.attrs.get("success", False))
        ts = sorted(
            (k for k in ep if k.startswith("timestep_")),
            key=lambda x: int(x.split("_")[1]),
        )
        eef = np.stack([ep[k]["obs/eef_state"][:] for k in ts]).astype(np.float64)
        actions = np.stack([ep[k]["action/ee_pose_action"][:] for k in ts]).astype(np.float64)
        gripper = np.stack([ep[k]["obs/gripper_state"][:] for k in ts]).astype(np.float64)
    return {
        "task_id": task_id,
        "seed": seed,
        "recorded_success": recorded_success,
        "eef": eef,
        "actions": actions,
        "gripper": gripper,
    }


def _gs_init(cfg):
    import genesis as gs

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[cfg.env.genesis.backend],
        precision=cfg.env.genesis.precision,
        logging_level=cfg.env.genesis.logging_level,
    )


def _replay_ee_trajectory(controller, actions, gripper, steps_per_target):
    """Open-loop drive the arm to each recorded (ee-pose, gripper) target.

    Each target gets a real convergence budget ``steps_per_target`` (NOT the
    recording stride): open-loop, the arm re-converges to each target from rest.
    Returns the achieved eef positions, one per driven target.
    """
    achieved = np.zeros((len(actions) - 1, 3), dtype=np.float64)
    for t in range(len(actions) - 1):
        controller.set_gripper(float(np.mean(gripper[t + 1])))
        controller.move_ee_to(
            pos=actions[t][:3], quat=actions[t][3:7], steps=steps_per_target
        )
        achieved[t] = np.asarray(controller.hand_pos(), dtype=np.float64)
    return achieved


# --- per-task environment reconstruction -----------------------------------
# Each returns (cfg, controller, success_fn). success_fn is None for PBD tasks
# (ee-tracking only). The PBD setups reuse the demo's own ``load_configs`` so the
# rebuilt scene matches what recording used (same rope/handle overrides), rather
# than duplicating that logic here.


def _setup_swap(backend):
    from omegaconf import OmegaConf

    from topogym.core import load_topogym_configs
    from topogym.primitives import configure_gripper_contact_friction
    from topogym.tasks import SwapPuzzleEvaluator, SwapSceneBuilder
    from topogym.utils import initialize_franka_controller

    task_config = CONFIG_ROOT / "task_configs" / "swap_topogym_tabletop_v1.yaml"
    cfg = load_topogym_configs(
        common_config=_COMMON, env_config=_ENV, robot_config=_ROBOT, task_config=task_config
    )
    cfg = OmegaConf.merge(cfg, {"env": {"genesis": {"backend": backend}}})
    physical = cfg.task.physical
    _gs_init(cfg)

    import genesis as gs

    scene = SwapSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        rigid_options=gs.options.RigidOptions(
            noslip_iterations=int(physical.noslip_iterations)
        ),
    ).build(show_viewer=False)
    controller = initialize_franka_controller(
        scene=scene.scene,
        manifest=scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(physical.settle_steps),
    )
    configure_gripper_contact_friction(
        entities=[scene.manifest.get(n) for n in scene.layout.block_names()],
        robot=controller.robot,
        finger_links=physical.finger_links,
        object_friction=float(physical.block_friction),
        finger_friction=float(physical.finger_friction),
    )

    def success_fn():
        return bool(
            SwapPuzzleEvaluator(tolerance_xy=float(cfg.task.task.success_tolerance_xy))
            .classify(scene)
            .is_terminal
        )

    return cfg, controller, success_fn


def _setup_untangle(backend):
    from prototypes import untangle_physical_handle_demo as demo
    from topogym.tasks import UntangleSceneBuilder
    from topogym.utils import initialize_franka_controller

    args = types.SimpleNamespace(
        common_config=demo.DEFAULT_COMMON_CONFIG,
        env_config=demo.DEFAULT_ENV_CONFIG,
        robot_config=demo.DEFAULT_ROBOT_CONFIG,
        task_config=demo.DEFAULT_TASK_CONFIG,
        backend=backend,
        lite=False,
    )
    cfg = demo.load_configs(args)
    _gs_init(cfg)
    scene = UntangleSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=False, include_robot=True
    )
    controller = initialize_franka_controller(
        scene=scene.scene,
        manifest=scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    return cfg, controller, None  # PBD: success not evaluated (ee-tracking only)


def _setup_cable_routing(backend):
    from prototypes import cable_routing_physical_handle_demo as demo
    from topogym.tasks import CableRoutingSceneBuilder
    from topogym.utils import initialize_franka_controller

    args = types.SimpleNamespace(
        common_config=demo.DEFAULT_COMMON_CONFIG,
        env_config=demo.DEFAULT_ENV_CONFIG,
        robot_config=demo.DEFAULT_ROBOT_CONFIG,
        task_config=demo.DEFAULT_TASK_CONFIG,
        backend=backend,
        lite=False,
        grasp_yaw=None,
    )
    cfg = demo.load_configs(args)
    _gs_init(cfg)
    scene = CableRoutingSceneBuilder(
        cfg.env, cfg.task, cfg.robot_control, route_mode="initial"
    ).build(show_viewer=False, include_robot=True)
    controller = initialize_franka_controller(
        scene=scene.scene,
        manifest=scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    return cfg, controller, None  # PBD: success not evaluated (ee-tracking only)


_SETUP = {
    "swap": _setup_swap,
    "untangle": _setup_untangle,
    "cable_routing": _setup_cable_routing,
}


def replay_episode(
    h5_path,
    *,
    pos_tol: float = 0.03,
    require_success: bool = False,
    steps_per_target: int | None = None,
    backend: str = "gpu",
) -> ReplayReport:
    """Rebuild the task env from the H5 and open-loop replay its actions."""
    data = _read_episode(h5_path)
    task = data["task_id"]
    if task not in _SETUP:
        raise ValueError(
            f"No replay setup for task {task!r}; available: {sorted(_SETUP)}."
        )
    if len(data["actions"]) < 2:
        raise ValueError("Need at least 2 recorded frames to replay.")

    cfg, controller, success_fn = _SETUP[task](backend)
    if steps_per_target is None:
        steps_per_target = int(cfg.robot_control.control_loop.steps_per_action)
    steps_per_target = max(1, int(steps_per_target))

    achieved = _replay_ee_trajectory(
        controller, data["actions"], data["gripper"], steps_per_target
    )
    pos_err = np.linalg.norm(achieved - data["eef"][1:, :3], axis=1)
    # Gate on the 99th percentile, not max: a recorded trajectory can contain a
    # teleport (reset_home uses set_dofs_position), and that single frame's
    # ``ee_pose_action`` is a huge jump no open-loop drive can reproduce. p99
    # tolerates a few such outlier frames while still catching systematic lag.
    p99_err = float(np.percentile(pos_err, 99))

    success = success_fn() if success_fn is not None else None

    return ReplayReport(
        task_id=task,
        seed=data["seed"],
        frames=len(data["actions"]),
        steps_per_target=int(steps_per_target),
        max_pos_err=float(pos_err.max()),
        max_pos_err_frame=int(pos_err.argmax()),
        mean_pos_err=float(pos_err.mean()),
        p99_pos_err=p99_err,
        final_pos_err=float(pos_err[-1]),
        pos_tol=float(pos_tol),
        tracking_ok=p99_err < float(pos_tol),
        success=success,
        recorded_success=data["recorded_success"],
        require_success=bool(require_success),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay a recorded episode dataset to self-check it (dispatches by task_id)."
    )
    parser.add_argument("h5_path", type=Path, help="Path to a recorded episode .h5")
    parser.add_argument("--pos-tol", type=float, default=0.03, help="Max eef tracking error (m).")
    parser.add_argument(
        "--require-success",
        action="store_true",
        help="Make task success a hard gate (swap only; PBD tasks don't evaluate success).",
    )
    parser.add_argument(
        "--steps-per-target",
        type=int,
        default=None,
        help="Physics steps to converge to each recorded pose (default: robot steps_per_action).",
    )
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default="gpu")
    args = parser.parse_args()

    report = replay_episode(
        args.h5_path,
        pos_tol=args.pos_tol,
        require_success=args.require_success,
        steps_per_target=args.steps_per_target,
        backend=args.backend,
    )
    print(f"dataset_replay {report.summary()}")
    if report.passed:
        print(f"[ok] replay self-check passed: {args.h5_path}")
    else:
        reason = "tracking" if not report.tracking_ok else "success"
        print(f"[fail] replay self-check failed ({reason} gate): {args.h5_path}")
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
