# Taxonomy (task.toml `[metadata]`, closed sets — extend by PR)

| Field | Values |
|---|---|
| `simulator` | `robosuite` · `humanoidbench` · `kinder` · `libero` · `behavior` · `maniskill` · … |
| `robot` | `franka-panda` · `unitree-h1` · `unitree-h1hand` (H1 with two Shadow hands) · `tidybot-plus-plus` · `r1pro` · … |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `cube_stack`) |
| `task_type` | `trajectory` · `policy` |
| `tier` | `privileged` · `perception` |
| `instance_seed` | optional, informational |
| `mode`, `protocol` | limited-mode twins only: `limited`, and the service protocol (`rcb-limited/1.1`) |

Folder slug: `<simulator>-<family-with-dashes>-i<NN>` for instance tasks (HumanoidBench inserts upstream's paper
category, `humanoidbench-<loco|manip>-<family>-i<NN>`); a limited-mode twin appends `-limited`;
`[task].name = "robot-coding-bench/<slug>"`.
