# Taxonomy (`task.toml` `[metadata]`)

Known values; a new value is added by pull request (CI validation of these vocabularies is part of the migration). See [PROTOCOL.md](PROTOCOL.md) §2.3 for which fields are required.

| Field | Values |
|---|---|
| `author_name` | the author's name (an organization may go in `author_org`) |
| `task_type` | `trajectory` · `policy` |
| `mode` | `privileged` · `standard` (formerly `unlimited` / `limited`) |
| `protocol` | standard mode only: `eai-standard/2.1` · `eai-standard/2.2` (BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, MyoSuite; [STANDARD_MODE_2_2.md](STANDARD_MODE_2_2.md)) |
| `simulator` | `robosuite` · `robotwin` (RoboTwin 2.0 = SAPIEN 3 + CuRobo) · `mujoco` · `kinder` (KinDER: MuJoCo and PyBullet) · `humanoidbench` (HumanoidBench: MuJoCo + dm_control) · `robowits` (RoboWits on Genesis) · `robolab` (NVIDIA RoboLab on Isaac Lab) · `behavior` (BEHAVIOR-1K: OmniGibson on Isaac Sim) · `maniskill` (ManiSkill 3 / SAPIEN: RoboPaint) · `vlabench` (VLABench: MuJoCo + dm_control) · `maniguard` (ManiGuard: BEHAVIOR-1K 3.7.2, OmniGibson on Isaac Sim 4.5) · `molmospaces` (Ai2 MolmoSpaces: MuJoCo) · `myosuite` (MyoSuite: musculoskeletal models on MuJoCo) — the simulator, not the image: benchmarks on one simulator may use different images and versions (PROTOCOL D5) |
| `robot` | `franka-panda` · `aloha-agilex` · `aloha-2` · `kuka-iiwa14-sharpa-ha4` · `tidybot-plus-plus` · `unitree-h1` · `unitree-h1hand` (H1 with two Shadow hands) · `sawyer` (Rethink Robotics Sawyer, as in Meta-World) · `marvin-bimanual` (RoboWits) · `franka-robotiq-2f85` (a Franka arm with a Robotiq 2F-85, the DROID setup: RoboLab, MolmoSpaces' FR3) · `r1pro` (BEHAVIOR-1K) · `franka-panda-omron` (RoboCasa's PandaOmron: Franka Panda on an Omron mobile base with a lift torso) · `fourier-gr1` (Fourier GR1 humanoid: two arms, waist and two Fourier dexterous hands, fixed base; RoboCasa-GR1) · `franka-panda-longfinger` (ManiGuard: Franka Panda with long fin-ray fingers) · `rainbow-rby1` (Rainbow Robotics RB-Y1: holonomic base, 6-joint torso, two 7-joint arms with parallel grippers; MolmoSpaces) · `myohand` (MyoSuite's MyoHand: a musculoskeletal human forearm and hand, 39 muscles) · `myoarm` (MyoSuite's MyoArm: a musculoskeletal human shoulder, arm and hand, 34 or 63 muscles) · `myoarm-torso` (MyoSuite's table-tennis player: torso, right arm and hand on a sliding pelvis) · `myoarm-mpl` (MyoSuite's MyoArm next to the Modular Prosthetic Limb, a motorized arm) · `myolegs` (MyoSuite's MyoLegs: a free-standing musculoskeletal torso and both legs) · `myoleg-osl` (MyoSuite's MyoLeg with an Open-Source Leg knee-ankle prosthesis) |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `cube_stack`, `dextoolbench/brush/blue_brush/sweep_forward`) |
| `oracle` | `full` (oracle scores 1) · `partial` (oracle reaches part of the goal) · `none` — see PROTOCOL §2.7 |
| `oracle_evidence` | required unless `oracle = "full"`: where the evidence for solvability is (PR, results site, upstream record) |
| `expert_time_estimate_hours` | number |
| `instance_seed` | optional, informational |
| `tier` | **deprecated** (`privileged` → `mode = "privileged"`, `perception` → `mode = "standard"`); removed by the migration |

Benchmark-specific fields (MAY, PROTOCOL §2.3):

| Benchmark | Field | Values |
|---|---|---|
| RoboPaint | `difficulty` | `easy` · `medium` · `hard` · `extreme` |
| RoboPaint | `medium` | `calligraphy` · `broad_nib` · `pointed_pen` · `mypaint` (the brush model) |
| RoboPaint | `stroke_count`, `characters` | integers (the stroke cap; the characters of a calligraphy work) |
| RoboPaint | `structure` | `single` · `left-right` · `top-bottom` · `enclosure` · `work` |
| ManiGuard | `maniguard_task` | the ManiGuard-Bench task, `<family>/task_NNNN` (its base level) |
| ManiGuard | `constraint_class` | `spatial` (an invariant: upright, not dropped, no contact) · `ordering` (one thing before another) |
| ManiGuard | `skill` | `pick_and_place` · `articulated` · `long_horizon` (ManiGuard's family classes) |
| ManiGuard | `grasping` | `assisted` · `sticky` (the grasping mode ManiGuard's evaluator uses for the family) |

## Task names
- `<base>-privileged` and `<base>-standard`, the two modes of one frozen instance. `<base>` is
  `<simulator>-<family-with-dashes>-i<NN>`, or the benchmark's own task name: `robotwin_2_0_<robotwin_task>`,
  `dextoolbench_<category>_<object>_<task>`, `mujoco_playground_<env>`, `kinder-<family>-i<NN>`,
  `humanoidbench-<category>-<family>-i<NN>`, `myosuite-<family>-i<NN>`.
- RoboPaint: `<base>` is `robopaint-<family>-<target>-i<NN>`; Chinese targets by pinyin (the codepoint appended on a
  collision, e.g. `robopaint-kaishu-shu-66f8-i00`); `[metadata].family = "robopaint_<family>_<target>"`.
- RoboPaint-strict: `<base>` is `robopaint-strict-<family>-<target>-i<NN>` (RoboPaint's pair with process rules);
  `[metadata].family = "robopaint_strict_<family>_<target>"`; RoboPaint's benchmark-specific fields apply.
- ManiGuard: `<base>` is `maniguard-<family-with-dashes>-i<NN>`, NN = the ManiGuard-Bench task index (base level, e.g.
  `maniguard-jar-transport-i14` = `jar_transport/task_0014`); `[metadata].family` is ManiGuard's family (`jar_transport`).
- `[task].name = "robot-coding-bench/<folder>"`.
- No versions or durations in names; a task's version is its digest in `tasks/dataset.toml`.

## Run ids
`<harness>-<model>-<effort>`, for example `codex-gpt6_luna-xhigh` or `claude_code-claude_fable_5_1-max`.
- `harness`: the Harbor agent name with `-` replaced by `_` (`codex`, `claude_code`).
- `model`: lower case, vendor prefix dropped, characters other than letters and digits replaced by `_`. Reuse the token
  already used for a model in existing results (`gpt6_luna`, `gpt6_astra`, `fable_5_1`).
- `effort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or `default` when the harness sets none.
- Provider, service tier, reset budget and other settings go in the results metadata, not in the id.
