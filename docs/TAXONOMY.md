# Taxonomy (task.toml `[metadata]`, closed sets — extend by PR)

| Field | Values |
|---|---|
| `simulator` | `robosuite` · `libero` · `behavior` · `maniskill` · `robocasa` · `rlbench` · `metaworld` · `calvin` · `vlabench` · … |
| `robot` | `franka-panda` · `franka` (VLABench native name) · `panda-omron` · `sawyer` · `r1pro` · … |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `cube_stack`) |
| `task_type` | `trajectory` · `policy` |
| `tier` | `privileged` · `perception` |
| `instance_seed` | optional, informational |

Folder slug: `<simulator>-<family-with-dashes>-i<NN>` for instance tasks; `[task].name = "robot-coding-bench/<slug>"`.

### Pinned privileged expansion (24 families)

`benchmark` distinguishes `metaworldplus`, `robocasa365` and `robocasa-gr1` while
`simulator` remains `metaworld` or `robocasa`. These use
`observation_mode = "privileged"`, `tier = "privileged"` and an explicit
`-privileged-iNN` task suffix. `controller_mode` distinguishes RoboCasa OSC 12,
Panda absolute-joint 13 and GR1 MINK 24 input configurations. Actual simulator
commits and per-family source audit are in `suites/robot24-manifest.json`.
A task family and a successfully validated fixed instance are different units;
see `docs/ROBOT24_STATUS.md` before treating staging candidates as accepted tasks.
