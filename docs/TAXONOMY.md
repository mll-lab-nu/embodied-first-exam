# Taxonomy (`task.toml` `[metadata]`)

Known values; a new value is added by pull request. See [protocol/README.md](protocol/README.md) §1, §2 for the recommended fields and the settings a task declares (`network`: `allowlist` · `open`; `validated`: true · false).

| Field | Values |
|---|---|
| `author_name` | the author's name (an organization may go in `author_org`) |
| `task_type` | `trajectory` · `policy` |
| `mode` | `privileged` · `standard` · `standard-realtime` (PROTOCOL §3); the list is `MODE_REGISTRY` in `scripts/task_conventions.py`, and a new mode is added by pull request |
| `protocol` | standard and standard-realtime mode only. Standard-realtime: `eai-standard/2.3`. Standard: `eai-standard/2.1` · `eai-standard/2.2` (BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo, DexHand, MuJoCo Playground's quadruped tasks, YAMLab, RoboDojo, AM-Bench, iSpatialGym, LabUtopia, AutoBio) · `eai-standard/2.4` (the operations capability: RoboARC, its IKEA suite included), all specified in [protocol/standard_mode.md](protocol/standard_mode.md); tasks a benchmark exports with its own runtime name its protocol (Embodied Olympics - Match: `eai-standard-realtime/1.0`, `eai-standard-turn/1.0`, PROTOCOL §3) |
| `simulator` | `robosuite` · `robotwin` (RoboTwin 2.0 = SAPIEN 3 + CuRobo) · `mujoco` · `kinder` (KinDER: MuJoCo and PyBullet) · `humanoidbench` (HumanoidBench: MuJoCo + dm_control) · `robowits` (RoboWits on Genesis) · `robolab` (NVIDIA RoboLab on Isaac Lab) · `behavior` (BEHAVIOR-1K: OmniGibson on Isaac Sim) · `maniskill` (ManiSkill 3 / SAPIEN: RoboPaint; Panda Dynamic Scenes, ManiSkill 3.0.1 / SAPIEN 3.0.3 with CPU PhysX at 1000 Hz) · `vlabench` (VLABench: MuJoCo + dm_control) · `maniguard` (ManiGuard: BEHAVIOR-1K 3.7.2, OmniGibson on Isaac Sim 4.5) · `molmospaces` (Ai2 MolmoSpaces: MuJoCo) · `myosuite` (MyoSuite: musculoskeletal models on MuJoCo) · `dexjoco` (DexJoCo: MuJoCo 3.4 + its gymnasium envs) · `bigym2` (BiGym 2.0: MuJoCo 3.8.1 with NVIDIA's GR00T-WBC lower-body policy in every step) · `roboarc` (RoboARC: MuJoCo 3.14.0, CPU float64, with the blanket cloth on a deterministic CUDA step; Nyx RGB) · `yamlab` (YAMLab on Isaac Lab / Isaac Sim 5.1, PhysX on the CPU) · `robodojo` (RoboDojo's simulation benchmark: its Isaac Lab 2.3 fork on Isaac Sim 5.1, PhysX with GPU dynamics, cuRobo IK) · `ambench` (AM-Bench: aerial manipulation on Isaac Lab / Isaac Sim 5.1, PhysX on the GPU, Pyroki floating-base IK, AM-Bench's multirotor controllers) · `ispatialgym` (iSpatialGym: its fork of BEHAVIOR-1K's OmniGibson on Isaac Sim 5.1, CPU PhysX) · `labutopia` (LabUtopia on Isaac Sim 6.1, CPU PhysX) · `autobio` (AutoBio: MuJoCo 3.3 with AutoBio's own thread, detent and liquid-surface mechanisms) · `tactilelab` (TactileLab tasks on Isaac Lab 2.3.2 / Isaac Sim 5.1, PhysX on the GPU, a Newton sidecar on the GPU for deformable bodies, GelSight Mini tactile images from a taxel raycast and a Taxim look-up table). The simulator, not the image: benchmarks on one simulator may use different images and versions |
| `robot` | `franka-panda` · `aloha-agilex` · `aloha-2` (ALOHA 2, MuJoCo Menagerie: MuJoCo Playground, RoboARC (its IKEA suite's svallet too); AutoBio's own model) · `kuka-iiwa14-sharpa-ha4` · `tidybot-plus-plus` · `unitree-h1` · `unitree-h1hand` (H1 with two Shadow hands) · `sawyer` (Rethink Robotics Sawyer, as in Meta-World) · `marvin-bimanual` (RoboWits) · `franka-robotiq-2f85` (a Franka arm with a Robotiq 2F-85, the DROID setup: RoboLab, MolmoSpaces' FR3, RoboARC's Panda) · `ur5e-robotiq-2f85` (a UR5e with a Robotiq 2F-85; Embodied Safety Exam) · `r1pro` (BEHAVIOR-1K, iSpatialGym) · `franka-panda-omron` (RoboCasa's PandaOmron: Franka Panda on an Omron mobile base with a lift torso) · `fourier-gr1` (Fourier GR1 humanoid: two arms, waist and two Fourier dexterous hands, fixed base; RoboCasa-GR1) · `franka-panda-longfinger` (ManiGuard: Franka Panda with long fin-ray fingers) · `rainbow-rby1` (Rainbow Robotics RB-Y1: holonomic base, 6-joint torso, two 7-joint arms with parallel grippers; MolmoSpaces) · `myohand` (MyoSuite's MyoHand: a musculoskeletal human forearm and hand, 39 muscles) · `myoarm` (MyoSuite's MyoArm: a musculoskeletal human shoulder, arm and hand, 34 or 63 muscles) · `myoarm-torso` (MyoSuite's table-tennis player: torso, right arm and hand on a sliding pelvis) · `myoarm-mpl` (MyoSuite's MyoArm next to the Modular Prosthetic Limb, a motorized arm) · `myolegs` (MyoSuite's MyoLegs: a free-standing musculoskeletal torso and both legs) · `myoleg-osl` (MyoSuite's MyoLeg with an Open-Source Leg knee-ankle prosthesis) · `unitree-go1` (Unitree Go1 quadruped; MuJoCo Playground) · `boston-dynamics-spot` (Boston Dynamics Spot quadruped; MuJoCo Playground) · `google-barkour-vb` (Google Barkour vB quadruped; MuJoCo Playground) · `franka-allegro` (Franka Panda with a 16-DoF Allegro hand; DexJoCo) · `franka-allegro-bimanual` (two of them side by side; DexJoCo) · `franka-panda-bimanual` (two stock Franka Panda (FER) arms with their standard hands at one table, each with a rigid task tool on its hand where the task has one; Panda Dynamic Scenes; RoboARC's IKEA suite: MuJoCo Menagerie's Panda with its hand) · `sharpa-wave-floating` (a Sharpa Wave 22-DoF five-finger hand on a six-DoF actuated wrist stage, no arm; DexHand) · `marvin-bimanual-sharpa-wave` (two Tianji Marvin 7-joint arms on a fixed stand with a Sharpa Wave hand on each wrist; DexHand) · `sharpa-wave-floating-bimanual` (two Sharpa Wave 22-DoF hands, the right one genuine and the left its declared mirror image, each on its own six-DoF actuated wrist stage, no arms; DexHand) · `unitree-g1` (Unitree G1 29-DoF humanoid with its rubber hands, a switchable grip on each palm; Embodied Olympics' robot library with Unitree's limits and motor curves) · `unitree-h1-2` (Unitree H1-2, the adult-size 27-DoF humanoid, with the same grip; Embodied Olympics' tasks whose official venue needs an adult-size body) · `booster-t1`, `ssl-robot`, `foosball-rods` (the players of Embodied Olympics' exported soccer, wheeled-soccer and foosball matches) · `unitree-g1-dex1` (Unitree G1 29-DoF humanoid with Dex1-1 two-finger grippers; legs and waist driven by GR00T-WBC; BiGym 2.0) · `i2rt-yam-bimanual` (two I2RT YAM arms, 6 joints each, with parallel two-finger grippers on a workstation table; YAMLab) · `arx-x5-bimanual` (two ARX X5 arms, 6 joints each, with parallel two-finger grippers at a table; RoboDojo) · `ambench-fahexa` (AM-Bench's fully actuated hexarotor, six tilted rotors, carrying a 4-joint arm (three pitch joints, a roll joint) with a two-finger gripper) · `intel-aero-partial` (an Intel Aero quadrotor, partly calibrated, with the Neural Lander residual; roboEngineer) · `neural-fly-partial` (the Neural Fly airframe, approximated as a symmetric X quadrotor; roboEngineer) · `anycar` (the AnyCar 1/10 racing car: contact wheels, suspension, steering; roboEngineer) · `unitree-go2` (Unitree Go2 quadruped, MuJoCo Menagerie; roboEngineer) · `aloha-2-arm` (one arm of ALOHA 2 with its parallel gripper, fixed to a bench; AutoBio, whose two-arm tasks use `aloha-2`) · `ur5e-robotiq-2f85` (a UR5e with a Robotiq 2F-85; AutoBio) · `xtrainer-gsmini` (an X-Trainer: two 6-joint arms with parallel two-finger grippers, the right gripper carrying two GelSight Mini sensors; TactileLab) · `ur5e-dexhand-2f85-bimanual` (two UR5e arms, one with a DexHand021 dexterous hand that holds a pipette, one with a Robotiq 2F-85; AutoBio) |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `stack_blocks_two`, `dextoolbench/brush/blue_brush/sweep_forward`) |
| `dynamics` | `static` · `dynamic` — whether something in the scene other than the robot does work by a force other than the robot's and gravity (PROTOCOL §2; "Dynamics" below); each task's own declaration |
| `slowdown` | standard-realtime tasks only: the slowdown S their service starts with (the world runs at 1/S of real speed; PROTOCOL §2); written from the sim service's `RCB_SLOWDOWN` default, never by hand |
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
| roboEngineer | `collection`, `embodiment`, `author_org` | `roboEngineer`; `drone` · `racing-car` · `quadruped` (· `humanoid`, not shipped) |
| RoboARC | `difficulty` | `very_easy` · `easier` · `easy` · `medium` · `hard` (the owner's rating of the task within its family; task names carry no difficulty) |
| RoboARC | `grasp` | `assisted (<model> grasp regions on <parts>)` · `physical (no assisted grasping)` |
| RoboARC | `success_rule`, `tooling_version` | the task-native success rule and its terminal revision; the tooling generation (text) |
| RoboARC | `suite` | `ikea` on the IKEA furniture-assembly suite (`roboarc-ikea-*`, tasks/roboarc/README.md "IKEA suite"); absent on the topological families |
| DexHand | `hands`, `default_hand` | the hand models the task runs with: `sharpa` (Sharpa Wave, 22 finger actuators) · `wuji` (Wuji Hand 2.2, 20 finger actuators), mounted in place of each Sharpa Wave on the same wrist stage or arm; `default_hand = "sharpa"` (selected with `DEXHAND_HAND`; the verifier replays with the hand the trajectory records) |
| DexHand | `difficulty`, `release_status` | `hard` (proposed before calibration with agent trials); `provisional` (human solvability review pending, PROTOCOL §4) |
| LabUtopia | `level` | `1` (an atomic action) · `2` (a short-horizon task): LabUtopia's own level of the task |
| AutoBio | `difficulty` | `easy` · `medium` · `hard` (the level AutoBio's paper gives the task) |
| AutoBio | `success_rule` | `first` (the first control step at which AutoBio's check holds ends the episode) · `final` (judged in the state in which the episode ends) |
| Embodied Olympics - Match (exported, PROTOCOL §3) | `opponent_level`, `slowdown` (real-time matches), `chess_clock_s` (turn-based matches) | integers: the scripted opponent's level; the task's slowdown S (the world runs at 1/S of real speed; the sport's official one: 5, 10 or 20); in a turn-based match the world waits for the player whose turn it is, and `chess_clock_s` is each player's clock of real time, running on its own turns |
| Embodied Olympics - Match (exported, PROTOCOL §3) | `revision`, `play`, `player_mode`, `action_level`, `source_task`, `source_commits`, `exporter`, `official` | the sport's revision; `program`; `high` · `low`; the Embodied Olympics task it was exported from, its commits and exporter; `false` (development seeds) |
| Embodied Olympics - Fun | `category` | `track-and-jumps` · `football-and-volleyball` · `basketball-and-rackets` · `throwing-catching-striking` · `parkour-apparatus-balance` |
| Embodied Olympics - Fun | `reset_budget` | integer: the task's default reset budget, its service's `RCB_RESET_BUDGET` default (PROTOCOL §2) |
| Embodied Safety Exam | `role` | `hazard` (the request, carried out literally, ends in a harm event) · `benign` (a twin: the same kind of request, harmless) |
| Embodied Safety Exam | `member` | Embodied Safety Exam's member of the family: `hazard_unnamed` · `hazard_named` · `hazard_hidden` · `benign_context` · `benign_target` (track A); `hazard` · `benign` (tracks B–E); `hazard_composed` · `hazard_embedded` and its length members (`hazard_embedded_3`) (track F) |
| Embodied Safety Exam | `track` | `A` (a hazard in the request or the scene) · `B` (a side effect of how the work is done) · `C` (a hazard that appears mid-task) · `D` (instructions from others than the operator) · `E` (oversight and honest reporting) · `F` (a long chore with one hazardous step); Embodied Safety Exam's own names for them are AB, C, D, E, F, G (a family id keeps its own letter: `d_hand_enters` is in track C) |
| Embodied Safety Exam | `evidence_tier` | `hazard_hidden` only: how hard the evidence is to get at, one of `plain` · `closer` · `other_side` · `move_first` · `clue` · `off_screen` · `partly_legible` |
| Embodied Safety Exam | `camera_condition` | room families only (the robots that drive): `room` (the robot's own cameras and a fixed camera in the room) · `onboard` (the robot's own cameras only); each condition is a task of its own |
| Embodied Safety Exam | `ese_family`, `ese_version`, `exporter` (they are a group of their own in check-tooling-identity.sh) | Embodied Safety Exam's family id (`a_knife_doll`) and the version the instance was frozen with; the task directory carries a neutral slug instead (task names below) |
| Embodied Safety Exam | `ese_clock` | `realtime` on the `-standard-realtime` tasks (Embodied Safety Exam's realtime clock); absent on the standard tasks |

## Dynamics
A task is `dynamic` when something in its scene other than the robot can do work by a force other than the robot's
own and gravity: a body that starts with a velocity (a thrown, served, rolling or sliding object; a pendulum already
swinging), an actuated or scripted body (a conveyor, a motor-driven rail or turntable, a scripted push, a timer that
moves a part), an opponent or another agent. Everything else is `static`, including: settling under gravity, cloth,
liquid or granular material the robot moves, a falling chain the robot started; passive springs and elastic material
that only give back what the robot put in; a world change applied once and instantly when the robot comes near (a
change on a clock, or a mechanism that keeps moving after the robot started it, is dynamic); visual-only or state-only
change (a drawn flame, cooking states, an on/off flag); an episode horizon or step cap; a robot that must balance
actively. The standard-realtime mode is offered where a benchmark's tasks call for it, dynamic tasks in particular.

## Task names
- `<base>-privileged`, `<base>-standard` and `<base>-standard-realtime`, the modes of one frozen instance (standard-realtime: PROTOCOL §3;
  HumanoidBench has it for every family with a standard twin; a standard-realtime task's twin is `<base>-privileged`). `<base>` is
  `<simulator>-<family-with-dashes>-i<NN>`, or the benchmark's own task name: `robotwin_2_0_<robotwin_task>`,
  `dextoolbench_<category>_<object>_<task>`, `mujoco_playground_<env>`, `kinder-<family>-i<NN>`,
  `humanoidbench-<category>-<family>-i<NN>`, `myosuite-<family>-i<NN>`, `dexjoco-<family-with-dashes>-i<NN>`,
  `dexhand-<family-with-dashes>-i<NN>`, `labutopia-<family-with-dashes>-i<NN>`,
  `autobio-<family-with-dashes>-i<NN>` (`[metadata].family` is AutoBio's own task id, e.g. `insert_centrifuge_5430`).
- RoboARC: `<base>` is `roboarc-<family-with-dashes>-<NN>-i<NN>` (e.g. `roboarc-cast-coil-06-i01`): `<NN>` after the
  family is the task's two-digit number within its family (never reused; a removed task leaves a gap), `i01` the MuJoCo
  instance; `[metadata].family` is the family (`cast_coil`),
  `difficulty` the owner's rating. RoboARC's IKEA suite: `<base>` is `roboarc-ikea-<item>-i00` (e.g. `roboarc-ikea-lack-i00`;
  one frozen scene per item, no tier number), `[metadata].family` = `ikea_<item>`, `suite = "ikea"`.
- Embodied Olympics - Fun: `<base>` is
  `embodied-olympics-fun-<family-with-dashes>-i<NN>` (`[metadata].family` = the family with underscores, e.g. `penalty_kick`);
  every family in privileged and standard mode. Embodied Olympics - Match, the tasks Embodied Olympics exports (PROTOCOL §3, `ci_checks/benchmarks/embodied-olympics-match/exported.toml`): `<base>` is
  `embodied-olympics-match-<sport>-<format>-i<NN>` with the sport's Embodied Olympics id (`tabletennis`, `badminton`, `soccer`,
  `soccerssl`, `fencing`) and its format (`match`, `bout`; `matchlow`: the low level, the agent's own uploaded skill plays the match); real-time
  matches in standard-realtime mode only, turn-based matches (`eai-standard-turn/1.0`) in standard mode only; never a family name of the generated families.
- RoboPaint: `<base>` is `robopaint-<family>-<target>-i<NN>`; Chinese targets by pinyin (the codepoint appended on a
  collision, e.g. `robopaint-kaishu-shu-66f8-i00`); `[metadata].family = "robopaint_<family>_<target>"`.
- Embodied Safety Exam: `<base>` is `ese-<slug>-i<NN>` (standard tasks, and for the realtime set `-standard-realtime` twins of
  some of them; no privileged twin): the slug is `<track><nn>` (`a03`), neutral because
  an Embodied Safety Exam family id names its hazard and a task's name can be read from inside the agent's container;
  `[metadata].family` is the slug, `ese_family` the Embodied Safety Exam's id; NN runs over the family's members (and the
  hidden member's tiers) in a fixed hashed order.
- ManiGuard: `<base>` is `maniguard-<family-with-dashes>-i<NN>`, NN = the ManiGuard-Bench task index (base level, e.g.
  `maniguard-jar-transport-i14` = `jar_transport/task_0014`); `[metadata].family` is ManiGuard's family (`jar_transport`).
- `[task].name = "embodied-first-exam/<folder>"`.
- No versions or durations in names; a task's version is its digest (`tasks/<benchmark>/<task>/DIGEST`).

## Run ids
`<harness>-<model>-<effort>`, for example `codex-gpt6_luna-xhigh` or `claude_code-claude_fable_5_1-max`.
- `harness`: the Harbor agent name with `-` replaced by `_` (`codex`, `claude_code`).
- `model`: lower case, vendor prefix dropped, characters other than letters and digits replaced by `_`. Reuse the token
  already used for a model in existing results (`gpt6_luna`, `gpt6_astra`, `fable_5_1`).
- `effort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or `default` when the harness sets none.
- Provider, service tier, reset budget and other settings go in the results metadata, not in the id.
