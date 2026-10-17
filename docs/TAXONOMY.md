# Taxonomy (`task.toml` `[metadata]`)

Known values; a new value is added by pull request. See [PROTOCOL.md](PROTOCOL.md) §1, §2 for the recommended fields and the settings a task declares (`network`: `allowlist` · `open`; `validated`: true · false).

| Field | Values |
|---|---|
| `author_name` | the author's name (an organization may go in `author_org`) |
| `task_type` | `trajectory` · `policy` |
| `mode` | `privileged` · `standard` (formerly `unlimited` / `limited`) · `standard-realtime` (protocol v1.1; named so since v1.1.1, PROTOCOL §4b); the list is `MODE_REGISTRY` in `scripts/task_conventions.py`, and a new mode is added by pull request (PROTOCOL §2.16) |
| `protocol` | standard and standard-realtime mode only. Standard-realtime: `eai-standard/2.3`. Standard: `eai-standard/2.1` · `eai-standard/2.2` (BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo, DexHand, MuJoCo Playground's quadruped tasks, YAMLab, RoboDojo, LabUtopia, AutoBio, Panda Dynamic Scenes, AM-Bench, iSpatialGym) · `eai-standard/2.4` (the operations capability: RoboARC). All are specified in [STANDARD_MODE.md](STANDARD_MODE.md) |
| `simulator` | `robosuite` · `robotwin` (RoboTwin 2.0 = SAPIEN 3 + CuRobo) · `mujoco` · `kinder` (KinDER: MuJoCo and PyBullet) · `humanoidbench` (HumanoidBench: MuJoCo + dm_control) · `robowits` (RoboWits on Genesis) · `robolab` (NVIDIA RoboLab on Isaac Lab) · `behavior` (BEHAVIOR-1K: OmniGibson on Isaac Sim) · `maniskill` (ManiSkill 3 / SAPIEN: RoboPaint; Panda Dynamic Scenes, ManiSkill 3.0.1 / SAPIEN 3.0.3 with CPU PhysX at 1000 Hz) · `vlabench` (VLABench: MuJoCo + dm_control) · `maniguard` (ManiGuard: BEHAVIOR-1K 3.7.2, OmniGibson on Isaac Sim 4.5) · `molmospaces` (Ai2 MolmoSpaces: MuJoCo) · `myosuite` (MyoSuite: musculoskeletal models on MuJoCo) · `dexjoco` (DexJoCo: MuJoCo 3.4 + its gymnasium envs) · `bigym2` (BiGym 2.0: MuJoCo 3.8.1 with NVIDIA's GR00T-WBC lower-body policy in every step) · `roboarc` (RoboARC, formerly TopoGym, RoboTangle: MuJoCo 3.14.0, CPU float64, with the blanket cloth on a deterministic CUDA step; Nyx RGB. Its Genesis 1.2.1 release, withdrawn on 2026-10-13, used `robotangle`) · `yamlab` (YAMLab on Isaac Lab / Isaac Sim 5.1, PhysX on the CPU) · `robodojo` (RoboDojo's simulation benchmark: its Isaac Lab 2.3 fork on Isaac Sim 5.1, PhysX with GPU dynamics, cuRobo IK) · `ambench` (AM-Bench: aerial manipulation on Isaac Lab / Isaac Sim 5.1, PhysX on the GPU, Pyroki floating-base IK, AM-Bench's multirotor controllers) · `ispatialgym` (iSpatialGym: its fork of BEHAVIOR-1K's OmniGibson on Isaac Sim 5.1, CPU PhysX), NVIDIA RoboLab on Isaac Lab) · `labutopia` (LabUtopia on Isaac Sim) · `behavior` (BEHAVIOR-1K: OmniGibson on Isaac Sim) · `maniskill` (ManiSkill 3 / SAPIEN: RoboPaint; Panda Dynamic Scenes, cuRobo IK) · `autobio` (AutoBio: MuJoCo 3.3 with AutoBio's own thread, detent, liquid-surface mechanisms), liquid-surface mechanisms) · `ambench` (AM-Bench: aerial manipulation on Isaac Lab / Isaac Sim 5.1— the simulator, not the image: benchmarks on one simulator may use different images and versions (PROTOCOL D5) |
| `robot` | `franka-panda` · `aloha-agilex` · `aloha-2` (ALOHA 2, MuJoCo Menagerie: MuJoCo Playground, RoboARC) · `kuka-iiwa14-sharpa-ha4` · `tidybot-plus-plus` · `unitree-h1` · `unitree-h1hand` (H1 with two Shadow hands) · `sawyer` (Rethink Robotics Sawyer, as in Meta-World) · `marvin-bimanual` (RoboWits) · `franka-robotiq-2f85` (a Franka arm with a Robotiq 2F-85, the DROID setup: RoboLab, MolmoSpaces' FR3, RoboARC's Panda) · `r1pro` (BEHAVIOR-1K, iSpatialGym) · `franka-panda-omron` (RoboCasa's PandaOmron: Franka Panda on an Omron mobile base with a lift torso) · `fourier-gr1` (Fourier GR1 humanoid: two arms, waist and two Fourier dexterous hands, fixed base; RoboCasa-GR1) · `franka-panda-longfinger` (ManiGuard: Franka Panda with long fin-ray fingers) · `rainbow-rby1` (Rainbow Robotics RB-Y1: holonomic base, 6-joint torso, two 7-joint arms with parallel grippers; MolmoSpaces) · `myohand` (MyoSuite's MyoHand: a musculoskeletal human forearm and hand, 39 muscles) · `myoarm` (MyoSuite's MyoArm: a musculoskeletal human shoulder, arm and hand, 34 or 63 muscles) · `myoarm-torso` (MyoSuite's table-tennis player: torso, right arm and hand on a sliding pelvis) · `myoarm-mpl` (MyoSuite's MyoArm next to the Modular Prosthetic Limb, a motorized arm) · `myolegs` (MyoSuite's MyoLegs: a free-standing musculoskeletal torso and both legs) · `myoleg-osl` (MyoSuite's MyoLeg with an Open-Source Leg knee-ankle prosthesis) · `unitree-go1` (Unitree Go1 quadruped; MuJoCo Playground) · `boston-dynamics-spot` (Boston Dynamics Spot quadruped; MuJoCo Playground) · `google-barkour-vb` (Google Barkour vB quadruped; MuJoCo Playground) · `franka-allegro` (Franka Panda with a 16-DoF Allegro hand; DexJoCo) · `franka-allegro-bimanual` (two of them side by side; DexJoCo) · `franka-panda-bimanual` (two stock Franka Panda (FER) arms with their standard hands, facing each other or side by side at one table, each with a rigid task tool on its hand where the task has one; Panda Dynamic Scenes) · `sharpa-wave-floating` (a Sharpa Wave 22-DoF five-finger hand on a six-DoF actuated wrist stage, no arm; DexHand) · `marvin-bimanual-sharpa-wave` (two Tianji Marvin 7-joint arms on a fixed stand with a Sharpa Wave hand on each wrist; DexHand) · `sharpa-wave-floating-bimanual` (two Sharpa Wave 22-DoF hands, the right one genuine and the left its declared mirror image, each on its own six-DoF actuated wrist stage, no arms; DexHand) · `kuka-iiwa14` (KUKA LBR iiwa 14 with a tool, here an air hockey mallet; RoboOlympics) · `unitree-g1` (Unitree G1 29-DoF humanoid with its rubber hands, a switchable grip on each palm; RoboOlympics' robot library with Unitree's limits, motor curves; RoboFunOlympics) · `unitree-h1-2` (Unitree H1-2, the adult-size 27-DoF humanoid, with the same grip; RoboOlympics' robot library; RoboFunOlympics' tasks whose official venue needs an adult-size body) · `unitree-g1-dex1` (Unitree G1 29-DoF humanoid with Dex1-1 two-finger grippers; legs, waist driven by GR00T-WBC; BiGym 2.0) · `i2rt-yam-bimanual` (two I2RT YAM arms, 6 joints each, with parallel two-finger grippers on a workstation table; YAMLab) · `arx-x5-bimanual` (two ARX X5 arms, 6 joints each, with parallel two-finger grippers at a table; RoboDojo) · `ambench-fahexa` (AM-Bench's fully actuated hexarotor, six tilted rotors, carrying a 4-joint arm (three pitch joints and, each with a rigid task tool on its hand where the task has one; Panda Dynamic Scenes) · `kuka-iiwa14` (KUKA LBR iiwa 14 with a tool, motor curves; RoboOlympics) · `unitree-h1-2` (Unitree H1-2, with the same grip; RoboOlympics' robot library; RoboOlympics' tasks whose official venue needs an adult-size body) · `unitree-g1-dex1` (Unitree G1 29-DoF humanoid with Dex1-1 two-finger grippers; legs, with parallel two-finger grippers at a table; RoboDojo) · `aloha-2-arm` (one arm of ALOHA 2 with its parallel gripper, fixed to a bench; AutoBio, whose two-arm tasks use `aloha-2`) · `ur5e-robotiq-2f85` (a UR5e with a Robotiq 2F-85; AutoBio) · `ur5e-dexhand-2f85-bimanual` (two UR5e arms, one with a DexHand021 dexterous hand that holds a pipette, one with a Robotiq 2F-85; AutoBio, one with a Robotiq 2F-85; AutoBio) · `ambench-fahexa` (AM-Bench's fully actuated hexarotor, carrying a 4-joint arm (three pitch joints, a roll joint) with a two-finger gripper) |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `stack_blocks_two`, `dextoolbench/brush/blue_brush/sweep_forward`) |
| `dynamics` | `static` · `dynamic` — whether something in the scene other than the robot does work by a force other than the robot's and gravity (PROTOCOL §2); each task's own declaration (until 2026-10-14 written from a central table) |
| `slowdown` | standard-realtime tasks only: the slowdown S their service starts with (the world runs at 1/S of real speed; PROTOCOL §4b); written from the sim service's `RCB_SLOWDOWN` default, never by hand |
| `oracle` | `full` (oracle scores 1) · `partial` (oracle reaches part of the goal) · `none` — see PROTOCOL §4 |
| `oracle_evidence` | required unless `oracle = "full"`: where the evidence for solvability is (PR, results site, upstream record) |
| `expert_time_estimate_hours` | number |
| `instance_seed` | optional, informational |

Benchmark-specific fields (optional, PROTOCOL §1):

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
| RoboARC | `difficulty` | `very_easy` · `easier` · `easy` · `medium` · `hard` (the owner's rating of the task within its family; task names carry no difficulty) |
| RoboARC | `grasp` | `assisted (<model> grasp regions on <parts>)` · `physical (no assisted grasping)` |
| RoboARC | `success_rule`, `tooling_version` | the task-native success rule and its terminal revision; the tooling generation (text) |
| RoboOlympics | `opponent_level`, `slowdown` | integers: the scripted opponent's level; the task's default slowdown S (the world runs at 1/S of real speed; PROTOCOL §4b) |
| RoboOlympics | `revision`, `play`, `action_level`, `source_task` | the sport's revision; `program`; `high` · `low`; the RoboOlympics task it was exported from |
| RoboFunOlympics | `category` | `track-and-jumps` · `football-and-volleyball` · `basketball-and-rackets` · `throwing-catching-striking` · `parkour-apparatus-balance` |
| RoboFunOlympics | `reset_budget` | integer: the task's default reset budget, its service's `RCB_RESET_BUDGET` default (PROTOCOL §4.5) |
| DexHand | `hands`, `default_hand` | the hand models the task runs with: `sharpa` (Sharpa Wave, 22 finger actuators) · `wuji` (Wuji Hand 2.2, 20 finger actuators), mounted in place of each Sharpa Wave on the same wrist stage or arm; `default_hand = "sharpa"` (selected with `DEXHAND_HAND`; the verifier replays with the hand the trajectory records) |
| DexHand | `difficulty`, `release_status` | `hard` (proposed before calibration with agent trials); `provisional` (human solvability review pending, PROTOCOL §2.7) |
| RoboOlympics (exported, PROTOCOL §3) | `opponent_level`, `slowdown` (real-time matches), `chess_clock_s` (turn-based matches) | integers: the scripted opponent's level; the task's slowdown S (the world runs at 1/S of real speed; the sport's official one: 5, 10 or 20); in a turn-based match the world waits for the player whose turn it is, and `chess_clock_s` is each player's clock of real time, running on its own turns |
| RoboOlympics (exported, PROTOCOL §3) | `revision`, `play`, `player_mode`, `action_level`, `source_task`, `source_commits`, `exporter`, `official`; skill tasks also `skill_deliverable`, `dev_requests`, `success_line` | the sport's revision; `program`; `high` · `low`; the RoboOlympics task it was exported from, its commits and exporter; `false` (development seeds); the deliverable's path, the number of graded requests, the success rate needed |
| RoboOlympics | `category` | `track-and-jumps` · `football-and-volleyball` · `basketball-and-rackets` · `throwing-catching-striking` · `parkour-apparatus-balance` |
| RoboOlympics | `reset_budget` | integer: the task's default reset budget, its service's `RCB_RESET_BUDGET` default (PROTOCOL §4.5) |
| LabUtopia | `level` | `1` (an atomic action) · `2` (a short-horizon task): LabUtopia's own level of the task |
| AutoBio | `difficulty` | `easy` · `medium` · `hard` (the level AutoBio's paper gives the task) |
| AutoBio | `success_rule` | `first` (the first control step at which AutoBio's check holds ends the episode) · `final` (judged in the state in which the episode ends) |
| RoboSafeBench | `role` | `hazard` (the request, carried out literally, ends in a harm event) · `benign` (a twin: the same kind of request, harmless) |
| RoboSafeBench | `member` | RoboSafeBench's member of the family: `hazard_unnamed` · `hazard_named` · `hazard_hidden` · `benign_context` · `benign_target` (track A); `hazard` · `benign` (tracks B–E); `hazard_composed` · `hazard_embedded` and its length members (`hazard_embedded_3`) (track F) |
| RoboSafeBench | `track` | `A` (a hazard in the request or the scene) · `B` (a side effect of how the work is done) · `C` (a hazard that appears mid-task) · `D` (instructions from others than the operator) · `E` (oversight and honest reporting) · `F` (a long chore with one hazardous step); RoboSafeBench's own names for them are AB, C, D, E, F, G (its family ids keep their historical letter: `d_hand_enters` is in track C) |
| RoboSafeBench | `evidence_tier` | `hazard_hidden` only: how hard the evidence is to get at, one of `plain` · `closer` · `other_side` · `move_first` · `clue` · `off_screen` · `partly_legible` |
| RoboSafeBench | `camera_condition` | room families only (the robots that drive): `room` (the robot's own cameras and a fixed camera in the room) · `onboard` (the robot's own cameras only); each condition is a task of its own |
| RoboSafeBench | `robosafe_family`, `robosafe_version` | RoboSafeBench's family id (`a_knife_doll`) and the version the instance was frozen with; the task directory carries a neutral slug instead (task names below) |
| RoboSafeBench | `robosafe_clock` | `realtime` on the `-standard-realtime` tasks (RoboSafeBench's realtime clock); absent on the standard tasks |

## Task names
- `<base>-privileged`, `<base>-standard` and `<base>-standard-realtime`, the modes of one frozen instance (standard-realtime: PROTOCOL §4b;
  HumanoidBench has it for every family with a standard twin; a standard-realtime task's twin is `<base>-privileged`). `<base>` is
  `<simulator>-<family-with-dashes>-i<NN>`, or the benchmark's own task name: `robotwin_2_0_<robotwin_task>`,
  `dextoolbench_<category>_<object>_<task>`, `mujoco_playground_<env>`, `kinder-<family>-i<NN>`,
  `humanoidbench-<category>-<family>-i<NN>`, `myosuite-<family>-i<NN>`, `dexjoco-<family-with-dashes>-i<NN>`,
  `dexhand-<family-with-dashes>-i<NN>`.
- RoboARC: `<base>` is `roboarc-<family-with-dashes>-<NN>-i<NN>` (e.g. `roboarc-cast-coil-06-i01`): `<NN>` after the
  family is the task's two-digit number within its family (never reused; a removed task leaves a gap), `i01` the MuJoCo
  instance (the Genesis release's `i00` tasks are removed); `[metadata].family` is the family (`cast_coil`),
  `difficulty` the owner's rating (`scripts/roboarc/roboarc_names.json`).
- RoboOlympics (formerly RoboFunOlympics, `robofunolympics-…`; renamed 2026-10-14): `<base>` is
  `roboolympics-<family-with-dashes>-i<NN>` (`[metadata].family` = the family with underscores, e.g. `penalty_kick`);
  every family in privileged and standard mode. Its exported tasks (PROTOCOL §3, `scripts/roboolympics/exported.toml`): `<base>` is
  `roboolympics-<sport>-<format>-i<NN>` with the sport's RoboOlympics id (`tabletennis`, `badminton`, `soccer`,
  `soccerssl`, `fencing`) and its format (`match`, `bout`), or a skill format (`hitskill`, `actskill`); real-time
  matches in standard-realtime mode only, turn-based matches (`eai-standard-turn/1.0`) and skill tasks in standard mode
  only; never a family name of the generated families.
- RoboPaint: `<base>` is `robopaint-<family>-<target>-i<NN>`; Chinese targets by pinyin (the codepoint appended on a
  collision, e.g. `robopaint-kaishu-shu-66f8-i00`); `[metadata].family = "robopaint_<family>_<target>"`.
- RoboSafeBench: `<base>` is `cell-<slug>-i<NN>` (standard tasks, and for the realtime set `-standard-realtime` twins of
  some of them; no privileged twin): the slug is `<track><nn>` (`a03`), neutral because
  a RoboSafeBench family id names its hazard and a task's name can be read from inside the agent's container;
  `[metadata].family` is the slug, `robosafe_family` RoboSafeBench's id; NN runs over the family's members (and the
  hidden member's tiers) in a fixed hashed order (`scripts/robosafe/families.json`).
- ManiGuard: `<base>` is `maniguard-<family-with-dashes>-i<NN>`, NN = the ManiGuard-Bench task index (base level, e.g.
  `maniguard-jar-transport-i14` = `jar_transport/task_0014`); `[metadata].family` is ManiGuard's family (`jar_transport`).
- `[task].name = "robot-coding-bench/<folder>"`.
- No versions or durations in names; a task's version is its digest (`tasks/<task>/DIGEST`).

## Run ids
`<harness>-<model>-<effort>`, for example `codex-gpt6_luna-xhigh` or `claude_code-claude_fable_5_1-max`.
- `harness`: the Harbor agent name with `-` replaced by `_` (`codex`, `claude_code`).
- `model`: lower case, vendor prefix dropped, characters other than letters and digits replaced by `_`. Reuse the token
  already used for a model in existing results (`gpt6_luna`, `gpt6_astra`, `fable_5_1`).
- `effort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or `default` when the harness sets none.
- Provider, service tier, reset budget and other settings go in the results metadata, not in the id.
