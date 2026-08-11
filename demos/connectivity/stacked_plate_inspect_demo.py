"""Stage-A scene inspector for the redesigned stacked_plate task (no motion).

Builds the vertical-disks-on-a-Y-rod scene and holds it in the viewer so the look
can be eyeballed. `run.rotate_to_target=true` snaps all disks to the oracle target
angle to preview the aligned (sectors-overlapping) state. Motion (edge-grab +
rotate) is Stage B; this file is a temporary inspection helper.

Configuration is Hydra (`configs/stacked_plate_inspect.yaml`).

    python -m demos.connectivity.stacked_plate_inspect_demo run.viewer=true run.keep_open=true
    python -m demos.connectivity.stacked_plate_inspect_demo run.rotate_to_target=true run.viewer=true
    python -m demos.connectivity.stacked_plate_inspect_demo --cfg job
"""

from __future__ import annotations

import time

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.supervision import stop_before_physics
from topogym.tasks import StackedPlateSceneBuilder
from topogym.verification import StackedPlatePuzzleEvaluator


@hydra.main(version_base="1.3", config_path="../../configs", config_name="stacked_plate_inspect")
def main(cfg: DictConfig) -> None:
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"stacked_plate_inspect_config -> {resolved}", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)])

    plate_scene = StackedPlateSceneBuilder(
        cfg.env, cfg.task, cfg.robot_control
    ).build(show_viewer=cfg.run.viewer)

    if cfg.run.rotate_to_target:
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

    if stop_before_physics(cfg, plate_scene.scene, "stacked_plate_inspect"):
        return

    if cfg.run.keep_open_no_step:
        while True:
            time.sleep(0.05)
    elif cfg.run.keep_open or cfg.run.viewer:
        while True:
            plate_scene.scene.step()


if __name__ == "__main__":
    main()
