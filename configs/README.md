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
  physical, mdp. One per task: swap / onestroke / maze_wall_removal / stacked_plate /
  untangle / cable_routing / peeling.
- `prefab_configs/topogym_prefabs_v1.yaml` — shared modeling props (rope family:
  PBD params, endpoint connector, fixed terminal, routing post, flush port). Referenced
  from task configs via `${prefabs.*}`. Loads as `cfg.prefabs`.
- `recording/` — recording presets (`off`, `default`, `hq`).

The tabletop V1 table depth/height follow the AABB from RoboMME's pinned ManiSkill
`TableSceneBuilder` (oversized 2.418 m side reduced to 1.200 m); the Panda is moved
45 mm forward so Genesis 1.1.0's asymmetric `link0.stl` footprint stays on the table.
The shared builder validates the mount plane is on the tabletop and the footprint stays
inside the table. See `docs/develop/framework/tabletop_baseline_v1_zh.md`.

## Demos

The current demos are the seven formal physical demos (assisted-contact tier), one per
task, each loading its task-frame V1 config:

```bash
python -m prototypes.swap_physical_grasp_demo --viewer --keep-open --verbose
python -m prototypes.onestroke_physical_wall_demo --viewer --keep-open --verbose
python -m prototypes.maze_wall_removal_physical_demo --seed 11 --viewer --keep-open --verbose
python -m prototypes.stacked_plate_physical_rotate_demo --viewer --keep-open --verbose
python -m prototypes.untangle_physical_handle_demo --viewer --keep-open --verbose
python -m prototypes.cable_routing_physical_handle_demo --viewer --keep-open --verbose
python -m prototypes.peeling_physical_demo --run-oracle --viewer --keep-open --verbose
```

Record all seven (multi-camera) via `bash bash_scripts/record_all_tasks.sh` or
`python -m prototypes.record_physical_demos`.

## References

- `configs/GEOMETRY_PARAMETERS_zh.md`: where each 3D size/position parameter lives.
- `docs/develop/framework/genesis_world_coordinates_zh.md`: Genesis world / table / task coordinates.
- `docs/develop/framework/tabletop_baseline_v1_zh.md`: frozen tabletop V1 baseline and validation.
