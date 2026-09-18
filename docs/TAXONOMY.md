# Taxonomy (task.toml `[metadata]`)

| Field | Values (closed set, extend by PR) |
|---|---|
| `simulator` | `robosuite` · `libero` · `behavior` (planned) |
| `robot` | `franka-panda` · `r1pro` (planned) |
| `family` | adapter registry key, e.g. `cube_stack`, `cube_lifting`, `peg_insertion`, `spill_wipe`, `two_arm_lift` |
| `task_type` | `trajectory` · `policy` |
| `tier` | `privileged` · `perception` |
| `image` | key under `images/` (`robosuite`, …) |

Task folder slug: `<simulator>-<family-with-dashes>-i<NN>`; `[task].name = "robot-coding-bench/<slug>"`.
