# Taxonomy (task.toml `[metadata]`, closed sets — extend by PR)

| Field | Values |
|---|---|
| `simulator` | `robosuite` · `libero` · `robotwin` (RoboTwin 2.0 = SAPIEN 3 + CuRobo) · `behavior` · `maniskill` · … |
| `robot` | `franka-panda` · `aloha-agilex` · `r1pro` · … |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `cube_stack`) |
| `task_type` | `trajectory` · `policy` |
| `tier` | `privileged` · `perception` |
| `instance_seed` | optional, informational |

Folder slug: `<simulator>-<family-with-dashes>-i<NN>` for instance tasks (RoboTwin tasks: `robotwin_2_0_<robotwin_task_name>`,
keeping RoboTwin's own task name); `[task].name = "robot-coding-bench/<slug>"`.
