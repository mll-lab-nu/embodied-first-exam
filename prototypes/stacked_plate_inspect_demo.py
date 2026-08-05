"""Stage-A scene inspector for the redesigned stacked_plate task (no motion).

Builds the vertical-disks-on-a-Y-rod scene and holds it in the viewer so the look
can be eyeballed. `--rotate-to-target` snaps all disks to the oracle target angle
to preview the aligned (sectors-overlapping) state. Motion (edge-grab + rotate) is
Stage B; this file is a temporary inspection helper.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import load_topogym_configs
from topogym.tasks import StackedPlateSceneBuilder
from topogym.verification import StackedPlatePuzzleEvaluator

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the redesigned stacked_plate scene (no motion).")
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default="gpu")
    parser.add_argument("--viewer", action="store_true", help="Open the Genesis viewer.")
    parser.add_argument("--keep-open", action="store_true", help="Step forever (interactive; robot may settle).")
    parser.add_argument("--keep-open-no-step", action="store_true", help="Hold the static built scene (no physics step).")
    parser.add_argument(
        "--rotate-to-target",
        action="store_true",
        help="Snap every disk to oracle.target_angle_deg to preview the aligned state.",
    )
    args = parser.parse_args()

    cfg = load_topogym_configs(
        common_config=CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml",
        env_config=CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml",
        # 与正式 demo 一致的 stacked_plate 专用抬高 home，避免 base home 在对称盘阵里穿模。
        robot_config=CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik_stacked_plate_raised_home.yaml",
        task_config=CONFIG_ROOT / "task_configs" / "stacked_plate_topogym_tabletop_v1.yaml",
    )
    cfg = OmegaConf.merge(cfg, {"env": {"genesis": {"backend": args.backend}}})
    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[cfg.env.genesis.backend])

    plate_scene = StackedPlateSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(show_viewer=args.viewer)

    if args.rotate_to_target:
        target = plate_scene.layout.target_angle()
        for name, entity in plate_scene.articulated_plate_entities.items():
            dof = plate_scene.plate_joint_dofs[name]
            entity.set_dofs_position([target], dofs_idx_local=[dof], zero_velocity=True)

    state = StackedPlatePuzzleEvaluator().classify(plate_scene)
    print(
        "stacked_plate_inspect aligned=%s spread_deg=%.1f angles_deg=%s"
        % (
            state.is_terminal,
            float(np.rad2deg(state.alignment_spread)),
            {k: round(float(np.rad2deg(v)), 1) for k, v in plate_scene.plate_yaws.items()},
        )
    )

    if args.keep_open_no_step:
        while True:
            time.sleep(0.05)
    elif args.keep_open or args.viewer:
        while True:
            plate_scene.scene.step()


if __name__ == "__main__":
    main()
