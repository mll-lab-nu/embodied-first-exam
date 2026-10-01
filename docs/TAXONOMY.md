# Taxonomy (`task.toml` `[metadata]`)

Known values; a new value is added by pull request (CI validation of these vocabularies is part of the migration). See [PROTOCOL.md](PROTOCOL.md) §2.3 for which fields are required.

| Field | Values |
|---|---|
| `author_name` | the author's name (an organization may go in `author_org`) |
| `task_type` | `trajectory` · `policy` |
| `mode` | `privileged` · `standard` (formerly `unlimited` / `limited`) |
| `protocol` | standard mode only: `eai-standard/2.1` (accepted, pending: `eai-standard/2.2`). Legacy spelling during migration: `rcb-limited/2.1` |
| `simulator` | `robosuite` · `robotwin` (RoboTwin 2.0 = SAPIEN 3 + CuRobo) · `mujoco` · `kinder` (KinDER: MuJoCo and PyBullet) |
| `robot` | `franka-panda` · `aloha-agilex` · `aloha-2` · `kuka-iiwa14-sharpa-ha4` · `tidybot-plus-plus` |
| `simulator` | `robosuite` · `robotwin` (RoboTwin 2.0 = SAPIEN 3 + CuRobo) · `mujoco` · `humanoidbench` (HumanoidBench: MuJoCo + dm_control) |
| `robot` | `franka-panda` · `aloha-agilex` · `aloha-2` · `kuka-iiwa14-sharpa-ha4` · `unitree-h1` · `unitree-h1hand` (H1 with two Shadow hands) |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `cube_stack`, `dextoolbench/brush/blue_brush/sweep_forward`) |
| `oracle` | `full` (oracle scores 1) · `partial` (oracle reaches part of the goal) · `none` — see PROTOCOL §2.7 |
| `oracle_evidence` | required unless `oracle = "full"`: where the evidence for solvability is (PR, results folder, upstream record) |
| `expert_time_estimate_hours` | number |
| `instance_seed` | optional, informational |
| `tier` | **deprecated** (`privileged` → `mode = "privileged"`, `perception` → `mode = "standard"`); removed by the migration |

## Task names
- Privileged tasks: `<simulator>-<family-with-dashes>-i<NN>`; benchmarks imported with their own task names keep them:
  `robotwin_2_0_<robotwin_task>`, `dextoolbench_<category>_<object>_<task>`, `mujoco_playground_<env>`.
- Standard tasks: the privileged task's name + `-standard` (legacy: `-limited`).
- `[task].name = "robot-coding-bench/<folder>"`.
- No versions or durations in names; a task's version is its digest in `tasks/dataset.toml`.

## Run ids
`<harness>-<model>-<effort>`, for example `codex-gpt6_luna-xhigh` or `claude_code-fable_5_1-max`.
- `harness`: the Harbor agent name with `-` replaced by `_` (`codex`, `claude_code`).
- `model`: lower case, vendor prefix dropped, characters other than letters and digits replaced by `_`. Reuse the token
  already used for a model in existing results (`gpt6_luna`, `gpt6_astra`, `fable_5_1`).
- `effort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or `default` when the harness sets none.
- Provider, service tier, reset budget and other settings go in the results metadata, not in the id.
