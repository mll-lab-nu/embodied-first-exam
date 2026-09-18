# Taxonomy (task.toml `[metadata]`, closed sets — extend by PR)

| Field | Values |
|---|---|
| `simulator` | `robosuite` · `libero` · `behavior` · `maniskill` · … |
| `robot` | `franka-panda` · `r1pro` · … |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `cube_stack`) |
| `task_type` | `trajectory` · `policy` |
| `tier` | `privileged` · `perception` |
| `instance_seed` | optional, informational |

Folder slug: `<simulator>-<family-with-dashes>-i<NN>` for instance tasks; `[task].name = "robot-coding-bench/<slug>"`.
