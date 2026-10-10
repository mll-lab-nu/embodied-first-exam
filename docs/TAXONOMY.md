# Taxonomy (`task.toml` `[metadata]`)

Known values; a new value is added by pull request. See [PROTOCOL.md](PROTOCOL.md) §2.3 for which fields are required.

| Field | Values |
|---|---|
| `author_name` | the author's name (an organization may go in `author_org`) |
| `task_type` | `trajectory` · `policy` |
| `mode` | `privileged` · `standard` (formerly `unlimited` / `limited`) · `standard-realtime` (protocol v1.1; named so since v1.1.1, PROTOCOL §4b) |
| `protocol` | standard and standard-realtime mode only. Standard-realtime: `eai-standard/2.3`. Standard: `eai-standard/2.1` · `eai-standard/2.2` (BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo, MuJoCo Playground's quadruped tasks, YAMLab, LabUtopia, AutoBio) · `eai-standard/2.4` (the operations capability: RoboTangle). All are specified in [STANDARD_MODE.md](STANDARD_MODE.md) |
| `simulator` | `robosuite` · `robotwin` (RoboTwin 2.0 = SAPIEN 3 + CuRobo) · `mujoco` · `kinder` (KinDER: MuJoCo and PyBullet) · `humanoidbench` (HumanoidBench: MuJoCo + dm_control) · `robowits` (RoboWits on Genesis) · `robolab` (NVIDIA RoboLab on Isaac Lab) · `labutopia` (LabUtopia on Isaac Sim) · `behavior` (BEHAVIOR-1K: OmniGibson on Isaac Sim) · `maniskill` (ManiSkill 3 / SAPIEN: RoboPaint) · `vlabench` (VLABench: MuJoCo + dm_control) · `maniguard` (ManiGuard: BEHAVIOR-1K 3.7.2, OmniGibson on Isaac Sim 4.5) · `molmospaces` (Ai2 MolmoSpaces: MuJoCo) · `myosuite` (MyoSuite: musculoskeletal models on MuJoCo) · `dexjoco` (DexJoCo: MuJoCo 3.4 + its gymnasium envs) · `bigym2` (BiGym 2.0: MuJoCo 3.8.1 with NVIDIA's GR00T-WBC lower-body policy in every step) · `robotangle` (RoboTangle, formerly TopoGym: Genesis 1.2.1 rigid bodies and libuipc IPC / PBD deformables, Nyx RGB) · `yamlab` (YAMLab on Isaac Lab / Isaac Sim 5.1, PhysX on the CPU) · `autobio` (AutoBio: MuJoCo 3.3 with AutoBio's own thread, detent and liquid-surface mechanisms) — the simulator, not the image: benchmarks on one simulator may use different images and versions (PROTOCOL D5) |
| `robot` | `franka-panda` · `aloha-agilex` · `aloha-2` (ALOHA 2, MuJoCo Menagerie: MuJoCo Playground, RoboTangle) · `kuka-iiwa14-sharpa-ha4` · `tidybot-plus-plus` · `unitree-h1` · `unitree-h1hand` (H1 with two Shadow hands) · `sawyer` (Rethink Robotics Sawyer, as in Meta-World) · `marvin-bimanual` (RoboWits) · `franka-robotiq-2f85` (a Franka arm with a Robotiq 2F-85, the DROID setup: RoboLab, MolmoSpaces' FR3, RoboTangle's Panda) · `r1pro` (BEHAVIOR-1K) · `franka-panda-omron` (RoboCasa's PandaOmron: Franka Panda on an Omron mobile base with a lift torso) · `fourier-gr1` (Fourier GR1 humanoid: two arms, waist and two Fourier dexterous hands, fixed base; RoboCasa-GR1) · `franka-panda-longfinger` (ManiGuard: Franka Panda with long fin-ray fingers) · `rainbow-rby1` (Rainbow Robotics RB-Y1: holonomic base, 6-joint torso, two 7-joint arms with parallel grippers; MolmoSpaces) · `myohand` (MyoSuite's MyoHand: a musculoskeletal human forearm and hand, 39 muscles) · `myoarm` (MyoSuite's MyoArm: a musculoskeletal human shoulder, arm and hand, 34 or 63 muscles) · `myoarm-torso` (MyoSuite's table-tennis player: torso, right arm and hand on a sliding pelvis) · `myoarm-mpl` (MyoSuite's MyoArm next to the Modular Prosthetic Limb, a motorized arm) · `myolegs` (MyoSuite's MyoLegs: a free-standing musculoskeletal torso and both legs) · `myoleg-osl` (MyoSuite's MyoLeg with an Open-Source Leg knee-ankle prosthesis) · `unitree-go1` (Unitree Go1 quadruped; MuJoCo Playground) · `boston-dynamics-spot` (Boston Dynamics Spot quadruped; MuJoCo Playground) · `google-barkour-vb` (Google Barkour vB quadruped; MuJoCo Playground) · `franka-allegro` (Franka Panda with a 16-DoF Allegro hand; DexJoCo) · `franka-allegro-bimanual` (two of them side by side; DexJoCo) · `kuka-iiwa14` (KUKA LBR iiwa 14 with a tool, here an air hockey mallet; RoboOlympics) · `unitree-g1-dex1` (Unitree G1 29-DoF humanoid with Dex1-1 two-finger grippers; legs and waist driven by GR00T-WBC; BiGym 2.0) · `i2rt-yam-bimanual` (two I2RT YAM arms, 6 joints each, with parallel two-finger grippers on a workstation table; YAMLab) · `aloha-2-arm` (one arm of ALOHA 2 with its parallel gripper, fixed to a bench; AutoBio, whose two-arm tasks use `aloha-2`) · `ur5e-robotiq-2f85` (a UR5e with a Robotiq 2F-85; AutoBio) · `ur5e-dexhand-2f85-bimanual` (two UR5e arms, one with a DexHand021 dexterous hand that holds a pipette, one with a Robotiq 2F-85; AutoBio) |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `stack_blocks_two`, `dextoolbench/brush/blue_brush/sweep_forward`) |
| `oracle` | `full` (oracle scores 1) · `partial` (oracle reaches part of the goal) · `none` — see PROTOCOL §2.7 |
| `oracle_evidence` | required unless `oracle = "full"`: where the evidence for solvability is (PR, results site, upstream record) |
| `expert_time_estimate_hours` | number |
| `instance_seed` | optional, informational |

Benchmark-specific fields (MAY, PROTOCOL §2.3):

| Benchmark | Field | Values |
|---|---|---|
| RoboPaint | `difficulty` | `easy` · `medium` · `hard` · `extreme` |
| RoboPaint | `medium` | `calligraphy` · `broad_nib` · `pointed_pen` · `mypaint` (the brush model) |
| RoboPaint | `stroke_count`, `characters` | integers (the stroke cap; the characters of a calligraphy work) |
| RoboPaint | `structure` | `single` · `left-right` · `top-bottom` · `enclosure` · `work` (calligraphy) · `word` · `line` (lettering) |
| RoboWits | `host_cpu_vendor` | optional: the `/proc/cpuinfo` `vendor_id` (`GenuineIntel`) of the only hosts on which the task's frozen instance is rebuilt within tolerance; a scheduler runs the task there only (elsewhere the trial ends as `infra_error = 1`). Absent: any vendor |
| ManiGuard | `maniguard_task` | the ManiGuard-Bench task, `<family>/task_NNNN` (its base level) |
| ManiGuard | `constraint_class` | `spatial` (an invariant: upright, not dropped, no contact) · `ordering` (one thing before another) |
| ManiGuard | `skill` | `pick_and_place` · `articulated` · `long_horizon` (ManiGuard's family classes) |
| ManiGuard | `grasping` | `assisted` · `sticky` (the grasping mode ManiGuard's evaluator uses for the family) |
| RoboTangle | `difficulty` | `very_easy` · `easier` · `easy` · `medium` · `hard` (the tier: different puzzle geometry of one family) |
| RoboTangle | `grasp` | `assisted (<model> grasp regions on <parts>)` · `physical (no assisted grasping)` |
| RoboTangle | `success_rule`, `tooling_version` | the task-native success rule and its terminal revision; the tooling generation (text) |
| RoboOlympics | `opponent_level`, `slowdown` | integers: the scripted opponent's level; the task's default slowdown S (the world runs at 1/S of real speed; PROTOCOL §4b exception: 10) |
| RoboOlympics | `revision`, `play`, `action_level`, `source_task` | the sport's revision; `program`; `high` · `low`; the RoboOlympics task it was exported from |
| LabUtopia | `level` | `1` (an atomic action) · `2` (a short-horizon task): LabUtopia's own level of the task |
| AutoBio | `difficulty` | `easy` · `medium` · `hard` (the level AutoBio's paper gives the task) |
| AutoBio | `success_rule` | `first` (the first control step at which AutoBio's check holds ends the episode) · `final` (judged in the state in which the episode ends) |

## Task names
- `<base>-privileged`, `<base>-standard` and `<base>-standard-realtime`, the modes of one frozen instance (standard-realtime: PROTOCOL §4b;
  HumanoidBench has it for every family with a standard twin; a standard-realtime task's twin is `<base>-privileged`). `<base>` is
  `<simulator>-<family-with-dashes>-i<NN>`, or the benchmark's own task name: `robotwin_2_0_<robotwin_task>`,
  `dextoolbench_<category>_<object>_<task>`, `mujoco_playground_<env>`, `kinder-<family>-i<NN>`,
  `humanoidbench-<category>-<family>-i<NN>`, `myosuite-<family>-i<NN>`, `dexjoco-<family-with-dashes>-i<NN>`,
  `labutopia-<family-with-dashes>-i<NN>`,
  `autobio-<family-with-dashes>-i<NN>` (`[metadata].family` is AutoBio's own task id, e.g. `insert_centrifuge_5430`).
- RoboTangle: `<base>` is `robotangle-<family-with-dashes>-<tier-with-dashes>-i<NN>` (e.g. `robotangle-cast-coil-very-easy-i00`);
  `[metadata].family` is the family (`cast_coil`), `difficulty` the tier.
- RoboOlympics: `<base>` is `roboolympics-<sport>-<format>-i<NN>` (`[metadata].family` = `<sport>_<format>`), standard-realtime only (no
  privileged twin: a PROTOCOL §4b exception).
- RoboPaint: `<base>` is `robopaint-<family>-<target>-i<NN>`; Chinese targets by pinyin (the codepoint appended on a
  collision, e.g. `robopaint-kaishu-shu-66f8-i00`); `[metadata].family = "robopaint_<family>_<target>"`.
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
