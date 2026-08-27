# TopoGym Configs

Reusable OmegaConf YAML for shared manipulation geometry, scene, robot, task, and
prefab settings. Keep them Hydra-friendly: small composable sections, no Python
expressions, explicit numeric lists for vectors/gains.

All task layouts use the **TopoGym tabletop V1** baseline in the **task frame**
(`coordinate_frame: task`; origin at table center, `z=0` = tabletop surface). The
world/physics layer stays in world coordinates. Conversion happens at build time via
each task layout's `world_z()` (`world_z = task_z + 0.9196429`).

## Layout

- `common_configs/manipulation_space_tabletop_v1.yaml` — shared manipulation-space profile
  (board footprint, EE workspace, Franka mount, home pose), task frame. Loads as `cfg.common`.
- `env_configs/world_tabletop_v1.yaml` — Genesis world (table rigid body, physics,
  frames, cameras, robot mount). World coordinates.
- `robot_control_configs/` — robot assets, joints, home pose, controllers, IK, gripper.
- `task_configs/<task>_topogym_tabletop_v1.yaml` — per-task layout, objects, oracle,
  physical, mdp. Mainline: untangle / untangle_continuous / band_untwist / stacked_plate /
  cable_routing / bar_through_hole. The swap / onestroke / maze_wall_removal / peeling
  configs stay for the RL env shells in `topogym/envs/`, though their demos were deleted.
- `prefab_configs/topogym_prefabs_v1.yaml` — shared modeling props (rope family:
  PBD params, endpoint connector, fixed terminal, routing post, flush port). Referenced
  from task configs via `${prefabs.*}`. Loads as `cfg.prefabs`.
- `recording/` — recording presets (`off`, `default`, `hq`).
- `run_configs/` — per-run parameters (seed, viewer, diagnostics). Loads as `cfg.run`.
- `hydra/` — Hydra behaviour presets (`job_logging/quiet`).
- `<demo>.yaml` — one primary config per demo, composed from `config.yaml`.

The tabletop V1 table depth/height follow the AABB from RoboMME's pinned ManiSkill
`TableSceneBuilder` (oversized 2.418 m side reduced to 1.200 m); the Panda is moved
45 mm forward so Genesis 1.1.0's asymmetric `link0.stl` footprint stays on the table.
The shared builder validates the mount plane is on the tabletop and the footprint stays
inside the table. See `docs/develop/framework/tabletop_baseline_v1_zh.md`.

## Hydra composition

`config.yaml` is the Hydra base config: it names one option from each group above and
maps it onto the package the reading code expects (`cfg.env`, `cfg.task`, `cfg.prefabs`,
...). Each migrated demo has its own primary config `configs/<demo>.yaml` that starts
from `config.yaml` and overrides only the groups it needs. `run_configs/` holds the
"how to run this once" parameters (seed, viewer, diagnostics); `configs/hydra/` holds
logging presets. See `configs/config.yaml` for the override syntax and
`docs/develop/framework/demo_cli_and_config_zh.md` for why Hydra was introduced.

## Demos

Every demo takes Hydra overrides. The argparse config path was deleted on 2026-08-10
along with `demos/legacy/`, so there is only one syntax:

```bash
python -m demos.entangle.untangle_continuous_physical_pinch_demo run.viewer=true run.keep_open=true
python -m demos.entangle.untangle_physical_handle_demo run.viewer=true run.keep_open=true run.verbose=true
python -m demos.connectivity.stacked_plate_physical_rotate_demo run.viewer=true run.keep_open=true
python -m demos.routing.cable_routing_physical_handle_demo run.viewer=true run.allow_target_lag=true
python -m demos.routing.bar_through_hole_physical_insert_demo run.viewer=true run.verbose=true
```

Full list and per-demo primary configs: `demos/README.md`.
Record every task (multi-camera) via `bash bash_scripts/recordings/record_all_tasks.sh`.

## Checks

```bash
python tests/check_configs_compose.py   # every config composes, every ${...} resolves
python tests/check_demo_configs.py      # demo-side wiring; stdlib + PyYAML only
```

All checks live in `tests/`; `scripts/` holds only the tools that produce an
artifact. See `tests/README.md`.

## References

- `configs/GEOMETRY_PARAMETERS_zh.md`: where each 3D size/position parameter lives.
- `docs/develop/framework/genesis_world_coordinates_zh.md`: Genesis world / table / task coordinates.
- `docs/develop/framework/tabletop_baseline_v1_zh.md`: frozen tabletop V1 baseline and validation.
