# Robot Coding Bench

**Can a coding agent program a robot?** Robot Coding Bench is a benchmark of robot-manipulation tasks for coding
agents such as Claude Code and Codex, built on the [Harbor](https://github.com/harbor-framework/harbor) task format.
In each task, an agent works in a container with a robot simulator and a Python interface. It must produce a deliverable
that a verifier checks in a separate sandbox, by replaying it in a fresh process. A program decides pass or fail (no
learned judge) and reports numeric diagnostics (for example DexToolBench's goal progress).

The benchmark contract is [docs/PROTOCOL.md](docs/PROTOCOL.md) (the version is stated there). Contributions follow
[CONTRIBUTING.md](CONTRIBUTING.md).

## Evaluation modes

Every task instance is offered in two modes that share the same frozen scene.

| | **Privileged mode** | **Standard mode** ("robot as a service") |
|---|---|---|
| Simulator | in the agent's container | in a sidecar container the agent cannot open |
| What the agent observes | full simulator state, task source, planning primitives | camera images (optionally depth, calibration) and proprioception |
| Resets | unlimited | none — one trial is one episode |
| Actions | the simulator's Python API | action chunks via a client (`eai-standard/2.x`: `/submit`, `/observe`) |
| Deliverable | a replayable trajectory saved by the agent | the trajectory recorded by the service |
| Verification | separate sandbox, two fresh replays with matching state hashes | separate sandbox, fresh replay of the recorded episode |

Privileged mode measures whether an agent can program a robot when it has full access to the simulator. Standard mode
measures the same thing under real-robot constraints. The standard-mode wire protocol is specified in
[docs/STANDARD_MODE.md](docs/STANDARD_MODE.md).

A third mode, **standard-realtime** (protocol v1.1, `eai-standard/2.3`, PROTOCOL §3), is standard mode on a clock that does not
stop: once an episode starts, the robot runs in real time and holds its last targets while the agent thinks, so the agent
drives it from a controller program of its own. It is offered where a benchmark's tasks call for it (HumanoidBench, BiGym 2.0; RoboOlympics' exported matches serve its own `eai-standard-realtime/1.0`, PROTOCOL §4c, RoboOlympics, BiGym 2.0, RoboSafeBench), as
`<base>-standard-realtime` next to `<base>-privileged` and `<base>-standard`; its results are reported separately.

> **Names.** Protocol v1.0 renamed *unlimited/limited* to *privileged/standard* and `rcb-limited/2.1` to
> `eai-standard/2.1`. Every task directory ends in its mode, `-privileged` or `-standard` (since v1.1 also `-standard-realtime`). Base images are
> `ghcr.io/mll-lab-nu/eai-<name>` (formerly `rcb-<sim>` under several registries), one per benchmark (PROTOCOL §1).

## Benchmarks

The current list of tasks, with each task's mode, cutoff, oracle and digest and the counts per benchmark, is generated
after every merge: [`TASKS.md` on the branch `task-list`](../../blob/task-list/TASKS.md) (`tasks.json`, `dataset.toml` next to it).

| Benchmark | Simulator / robot | Tasks (per mode) | Oracle |
|---|---|---|---|
| RoboTwin 2.0 (`robotwin_2_0_<task>`) | SAPIEN 3 + CuRobo · ALOHA-AgileX dual arm | 47 of 50 | full (upstream expert) |
| DexToolBench (`dextoolbench_<cat>_<obj>_<task>`) | MuJoCo 3.3.7 · KUKA iiwa14 + Sharpa HA4 hand | 21 of 24 | full on 6, partial on 15 |
| MuJoCo Playground (`mujoco_playground_<env>`) | MuJoCo · ALOHA, Franka Panda; quadrupeds: Unitree Go1, Boston Dynamics Spot, Google Barkour vB | 4 manipulation + 9 quadruped | full (manipulation: scripted IK; quadrupeds: Playground's Go1 policy or policies trained on its rewards) |
| KinDER (`kinder-<family>-i00`) | MuJoCo 3.3 / PyBullet · TidyBot++ mobile manipulator | 5 | full on 1, none on 4 (human review) |
| HumanoidBench (`humanoidbench-<family>-i00`) | MuJoCo · Unitree H1 humanoid | 10 (+ 10 standard-realtime, `-standard-realtime`: time does not stop) | full on 1, none on 9 (human review), in each mode |
| MetaWorld+ (`metaworldplus-<env>-i00`) | MuJoCo (Meta-World v3) · Rethink Sawyer | 50 | full |
| RoboWits (`robowits-<family>-i00`) | Genesis · Marvin bimanual | 15 | partial on 2, none on 13 (human review) |
| RoboPaint (`robopaint-<style>-<target>-i<NN>`) | ManiSkill 3 / SAPIEN + libmypaint · Franka Panda with a brush; the picture is written or painted with strokes, not coloured in (process rules) | 43 | partial |
| RoboLab (`robolab-<family>-i00`) | Isaac Lab / Isaac Sim · Franka + Robotiq 2F-85 | 53 | full on 2 (standard mode: partial), none on 51 (human review) |
| YAMLab (`yamlab-<family>-iNN`) | Isaac Lab / Isaac Sim (YAMLab) · two I2RT YAM arms with parallel grippers | 10 (2 families × 5 object pairs) | full (upstream human demonstrations) |
| RoboDojo (`robodojo-<task>-i00`) | Isaac Lab / Isaac Sim (RoboDojo) · two ARX X5 arms with parallel grippers | 54 (RoboDojo's 42 tasks + its 12 randomised variants, one evaluation layout each); privileged 48: the 6 whose physics does not replay bit for bit are standard only, graded by the live episode | none (human review; RoboDojo releases no expert) |
| BEHAVIOR-1K (`behavior-<activity>-i00`) | OmniGibson / Isaac Sim · Galaxea R1 Pro | 100 | partial on 2, none on 98 (human review; 89 supplementary tasks without a verified positive yet) |
| VLABench (`vlabench-<task>-i00`) | MuJoCo + dm_control · Franka Panda | 36 | full |
| RoboCasa (`robocasa-<task>-i00`) | robosuite · Franka Panda on an Omron mobile base | 29 | full (upstream demonstrations) |
| RoboCasa365 (`robocasa365-<task>-i00`) | robosuite · Franka Panda on an Omron mobile base | 50 | full (upstream demonstrations) |
| RoboCasa-GR1 (`robocasa-gr1-<task>-i00`) | robosuite · Fourier GR1 humanoid | 24 | full (upstream demonstrations) |
| DexJoCo (`dexjoco-<family>-i00`) | MuJoCo 3.4 · Franka Panda + Allegro hand, one or two arms | 11 | full (upstream human demonstrations) |
| DexHand (`dexhand-<family>-i00`) | MuJoCo 3.4.0 (CPU) · Sharpa Wave 22-DoF hand on a six-DoF wrist stage (thirteen families; the six essential families lock the wrist), two Sharpa Wave hands on two six-DoF wrist stages (carrying a tray with two filled glasses, holding a handheld vacuum while reseating its dust bin), or two fixed Tianji Marvin 7-DoF arms with a Sharpa Wave hand on each (fifteen families, e.g. sweeping debris into a held dustpan, carrying a pot into a shelf, hanging a framed picture, turning a board-book page; a one-hand task parks the other arm); every family also runs with the Wuji Hand 2.2 (20 DoF) in place of each Sharpa Wave; immediate failure when an object drops or leaves its support | 30 | full (recorded physical Sharpa episodes) |
| MyoSuite (`myosuite-<family>-i00`) | MyoSuite 2.12.2 (MuJoCo 3.6, CPU) · musculoskeletal hand, arm, torso and legs (MyoHand, MyoArm, MyoLegs, with prostheses in two tasks), muscle commands; MyoChallenge and MyoDex tasks | 22 | full on 3 (MyoSuite's NPG baselines), none on 19 (human review) |
| RoboARC (`roboarc-<family>-<NN>-i01`; formerly TopoGym and RoboTangle; the MuJoCo release replaces the Genesis one, 2026-10-13) | MuJoCo 3.14.0 (CPU float64; the blanket cloth on a deterministic CUDA step), Nyx RGB · ALOHA 2 bimanual; Franka Panda + Robotiq 2F-85 | per release ([docs/benchmarks/roboarc.md](docs/benchmarks/roboarc.md)) | full, or none where no reference exists |
| BiGym 2.0 (`bigym2-<family>-i00`) | MuJoCo 3.8.1 + NVIDIA GR00T-WBC (CPU; EGL rendering) · Unitree G1 humanoid with Dex1-1 grippers, legs and waist driven by the whole-body controller | 13 (+ 13 standard-realtime) | none (human review) |
| RoboOlympics (`roboolympics-<family>-i00`, formerly RoboFunOlympics; and RoboOlympics' exported `roboolympics-<sport>-<format>-iNN`) | the RoboOlympics simulator (MuJoCo 3.3.7, CPU, OSMesa) · Unitree G1 (29 joints, with its walking and running policies; 20 families) or the larger Unitree H1-2 (27 joints, walking policy; 30 families), or joint by joint (Unitree LowCmd); 50 single-robot sports at official rule-book sizes judged by a referee of events, geometry and contact rules; the agent may download public tools and controllers; plus 15 tasks RoboOlympics exports with its own service (PROTOCOL §4c): table tennis, badminton, humanoid soccer (2 Booster T1), wheeled soccer (5 v 5) and foosball matches against a scripted opponent (wheeled soccer i01: a learned team; table tennis and badminton duelrl: a learned player), and two turn-based fencing bouts | 100 (50 × 2) + 15 exported (13 standard-realtime, 2 standard) | see [docs/benchmarks/roboolympics.md](docs/benchmarks/roboolympics.md): full where a reference controller exists, none elsewhere (human review); exported: the reference player or skill |
| LIBERO-MAX (`libero-max-<suite>-<task>-<event>-iNN`) | robosuite 1.4 (MuJoCo 3.2.6, CPU) · Franka Panda; LIBERO tasks with one change in mid-task (a target, receptacle or obstacle moves, the camera, lighting or scene theme changes, sensor noise sets in, distractors appear) | 64 | full |
| ManiGuard (`maniguard-<family>-iNN`) | BEHAVIOR-1K 3.7.2 (OmniGibson on Isaac Sim 4.5) · Franka Panda with long fin-ray fingers; tabletop tasks with a safety specification checked at every control step | 30 (6 families × 5) | full on 14, none on 16 (human review) |
| MolmoSpaces (`molmospaces-<family>-i00`) | Ai2 MolmoSpaces on MuJoCo 3.5 (CPU physics) · Franka FR3 + Robotiq 2F-85 on a fixed base; Rainbow RB-Y1 mobile manipulator | 8 | none (human review) |
| RoboSafeBench (`rsb-<slug>-i<NN>`, `cell-` until 0.5.3: docs/benchmarks/robosafe.md) | RoboSafeBench on MuJoCo 3.8.1 (CPU, OSMesa) · a UR5e with a Robotiq 2F-85, two I2RT YAM arms (i2rt-yam-bimanual) and a Franka FR3 with a Robotiq 2F-85 at a work table, a TidyBot++ and a Unitree G1 in a room, driven by joint targets or hand poses at 50 Hz; requests from an operator, some of which would harm someone or something and each with harmless twins, judged on what physically happened and on how the episode ended (an exit, a question or a report to the operator) | 566: the 0.5.4 core set of 84 (78 standard, 6 standard-realtime, `-standard-realtime`: time does not stop) and 482 kept at 0.5.3, 481 of them in the easy set (`docs/easy_set.toml`; `rsb-c04-i00-standard` stays in the core set with its 0.5.4 realtime twin); no privileged twin (a privileged agent would read the hazard state) | full (RoboSafeBench's scripted references compiled into rows) |
| Panda Dynamic Scenes (`pandadyn-<code>-<name>-i00`) | ManiSkill 3 / SAPIEN (CPU PhysX at 1000 Hz) · one or two Franka Panda arms with task tools (a plate, a cup, a paddle, a scoop, ...); multi-stage dynamic tasks: catch, strike, carry, hand over, release objects that move by themselves | 25 (12 one-arm + 13 two-arm) | full (the benchmark's recorded reference rollouts) |
| AM-Bench (`ambench-<task>-fahexa-i<NN>`) | AM-Bench on Isaac Lab / Isaac Sim 5.1 · a fully actuated hexarotor with a 4-joint arm and a two-finger gripper (aerial manipulation: the arm moves the base it hangs from) | 17 (8 tasks × 2 modes, and PullLever in standard mode only, graded by its live episode; the benchmark has 12) | full (AM-Bench's scripted experts, recorded) |
| iSpatialGym (`ispatialgym-<task>-i00-<mode>`) | iSpatialGym eval v1.0 (BEHAVIOR-1K's OmniGibson on Isaac Sim 5.1, its fork) · R1Pro mobile bimanual robot; spatial-intelligence tasks given only as a goal image (alignment, camera relocalization, configuration matching, object relations, mental rotation, object scaling) | 24 (12 × privileged, standard) | none |
| IKEA MuJoCo (`ikea-<task>-i00-<mode>`) | MuJoCo 3.14.0 (CPU float64, an EPA-patched wheel), Nyx RGB in standard mode · two Franka Panda arms with Menagerie Panda hands, or two ViperX 300 s arms (ALOHA 2); IKEA furniture assembly with physical grasps: dowels, latches, snaps, screws driven by hand or with a tool, each scene with its own mechanism and the source assembly grader | 16 (8 × privileged, standard) | full (closed-loop or speed-limited demo references) |

Each task directory carries a README in one layout: a key table (benchmark, mode, twin, simulator and robot, family and
instance, oracle, budget, image), then Task, Difficulty, Reference solution, Verification and Details.

**Excluded tasks:**
- **RoboTwin:** `click_bell` is excluded because its success is a transient contact that a replay does not reproduce. `click_alarmclock` and `put_object_cabinet` are excluded because the upstream expert failed on every seed we swept.
- **DexToolBench:** `blue_brush/sweep_right`, `flat_eraser/wipe_c` and `flat_eraser/wipe_smile` are excluded because the reference policy reaches no goal in this scene.
- **VLABench:** `select_fruit_semantic` is excluded as a duplicate of `select_fruit_common_sense` (same scene, reference and check); `select_book_semantic` and `set_study_table` because their upstream instruction has a literal "..." where the target should be named (`scripts/vlabench/tasks.json`, `dropped`).

**Tooling:**
- **RoboTwin generators:** `scripts/robotwin_expert_sweep.py`, `robotwin_mk_task.py`, `robotwin_mk_limited.py`.
- **DexToolBench generators:** `scripts/dtb_mk_task.py`, `dtb_mk_oracle.py`.
- **MuJoCo standard-mode twins:** generated by `scripts/mj_mk_limited.py`.
- **KinDER, HumanoidBench:** both modes (HumanoidBench: also standard-realtime) rendered by `scripts/kinder/gen_tasks.py` and `scripts/humanoidbench/gen_tasks.py` (`render`, `check`).
- **Other benchmarks:** each has its generator under `scripts/<bench>/` (RoboWits, RoboLab, BEHAVIOR-1K, RoboARC, YAMLab, RoboDojo, ManiGuard, MolmoSpaces, Panda Dynamic Scenes: `mk_tasks.py --check`; VLABench, RoboCasa, RoboCasa365, RoboCasa-GR1, LIBERO-MAX, DexJoCo, MuJoCo Playground's quadrupeds: `generate.py --check`; BiGym 2.0: `gen_tasks.py check`; MyoSuite: `scripts/myosuite/generate.py --check`; LabUtopia: `scripts/labutopia/generate.py --check`; AutoBio: `scripts/autobio/generate.py --check`; MetaWorld+: `generate.py`; RoboPaint: `scripts/robopaint_strict/mk_tasks.py --check`, which runs `scripts/robopaint_brush_mk_task.py --refresh` and adds the process rules). CI runs every check mode (`ci_checks/check-generated-tasks.sh`). Per-benchmark notes: [docs/benchmarks/](docs/benchmarks/).
- **RoboOlympics:** `scripts/roboolympics/gen_tasks.py` (`render`, `check`) from the families under
  `scripts/roboolympics/shared/rfo/tasks/`; how to write a family: `scripts/roboolympics/AUTHORING.md`; notes in
  [docs/benchmarks/roboolympics.md](docs/benchmarks/roboolympics.md). Its exported tasks are written by RoboOlympics'
  own exporter and listed in `scripts/roboolympics/exported.toml` (the generator skips them).
- **Other benchmarks:** each has its generator under `scripts/<bench>/` (RoboWits, RoboLab, BEHAVIOR-1K, RoboARC, YAMLab, RoboDojo, ManiGuard, MolmoSpaces, Panda Dynamic Scenes, AM-Bench, iSpatialGym: `mk_tasks.py --check`; IKEA MuJoCo: `scripts/ikea_mujoco/mk_tasks.py --check` and `mk_standard_tasks.py --check`; VLABench, RoboCasa, RoboCasa365, RoboCasa-GR1, LIBERO-MAX, DexJoCo, MuJoCo Playground's quadrupeds: `generate.py --check`; DexHand: `scripts/dexhand/generate.py --check --release` (the families of `scripts/dexhand/release.json`); BiGym 2.0: `gen_tasks.py check`; MyoSuite: `scripts/myosuite/generate.py --check`; MetaWorld+: `generate.py`; RoboPaint: `scripts/robopaint_strict/mk_tasks.py --check`, which runs `scripts/robopaint_brush_mk_task.py --refresh` and adds the process rules). CI runs every check mode (`ci_checks/check-generated-tasks.sh`). Per-benchmark notes: [docs/benchmarks/](docs/benchmarks/).
- **RoboFunOlympics:** `scripts/robofunolympics/gen_tasks.py` (`render`, `check`) from the families under
  `scripts/robofunolympics/shared/rfo/tasks/`; how to write a family: `scripts/robofunolympics/AUTHORING.md`; notes in
  [docs/benchmarks/robofunolympics.md](docs/benchmarks/robofunolympics.md).
- **RoboSafeBench:** a frozen release, `scripts/robosafe/release.json` (`check_release.py check`): the 0.5.3 tasks
  from `scripts/robosafe/gen_tasks.py` and the instances frozen by `scripts/robosafe/make_instances.py`, the 0.5.4 tasks
  exported by RoboSafeBench's release tooling; how they are made: `scripts/robosafe/AUTHORING.md`; notes in
  [docs/benchmarks/robosafe.md](docs/benchmarks/robosafe.md).
- **RoboOlympics:** `scripts/roboolympics/gen_tasks.py` (`render`, `check`) from RoboOlympics' simulator code
  (`scripts/roboolympics/shared/`); notes in [docs/benchmarks/roboolympics.md](docs/benchmarks/roboolympics.md).
- **Conventions:** every generator ends with `scripts/task_conventions.py` (`--check` reports a task it would change).
- **MuJoCo base image:** run `images/mujoco/prepare_assets.sh` before building it.

## Quick start

```bash
uv tool install harbor==0.23.0
git submodule update --init --recursive          # third_party/ sources used by the base images
images/mujoco/prepare_assets.sh                  # MuJoCo assets (pinned upstream commits)
scripts/build_images.sh                          # every eai-* base image (the public ones can be pulled instead)
cp .env.example .env                             # API keys, or a Claude / ChatGPT subscription login

# one task, locally
harbor run -p tasks -i robotwin_2_0_stack_blocks_two-privileged -a codex -m openai/gpt-6-luna
harbor run -p tasks -i robotwin_2_0_stack_blocks_two-standard -a claude-code -m anthropic/claude-fable-5-1

# reference checks: the oracle scores 1, the nop agent scores 0
harbor run -p tasks -i robotwin_2_0_stack_blocks_two-privileged -a oracle
harbor run -p tasks -i robotwin_2_0_stack_blocks_two-privileged -a nop
harbor view jobs
```

**Requirements:**
- Docker.
- An NVIDIA GPU with `nvidia-container-toolkit` for RoboTwin (CuRobo, Vulkan) and for MuJoCo rendering. KinDER's physics runs on CPU.
- GPUs are passed through by `environment/docker-compose.yaml`, because Harbor's local Docker sandbox does not support `[environment].gpus`.
- Reference hardware is an RTX 4090. Four RoboTwin instances rebuild to a different state on other GPUs (e.g. L40S) and are then reported as `grader_error` (PROTOCOL §4).
- Disk space for the base images (the RoboTwin image is about 22 GB). Public images can be pulled; `BUILD_ONLY` ones are built on the host.

**Running official results:**
- Use Harbor's native agents through `scripts/run_agent_batch.sh` with `GATEWAY=1`, and with no tool that runs outside the trial's container (docs/RUNNING.md "Official runs"): the harness's web search off (Codex `--ak web_search=disabled`, Claude Code `--ak disallowed_tools=WebSearch,WebFetch`: the script's default), no account connectors, apps, plugins or image generation. They run at the model provider, so no egress allowlist stops them; the gateway forwards model-API calls only and is, with the package registries, the agent container's only egress.
- Align reasoning effort and the time budget across agents: every task states its cutoff at the end of its instruction (`## Time limit`), each task sets its own (3600 s by default; PROTOCOL §2; history in [docs/CUTOFFS.md](docs/CUTOFFS.md)). The token budget (100M input / 10M output tokens per trial) is enforced by the usage gateway (docs/RUNNING.md "Official runs"). Results are ranked only within one comparable configuration (mode, cutoff, reset budget, S, network); validated and unvalidated tasks are ranked together; tasks of the easy set ([docs/easy_set.toml](docs/easy_set.toml)) are kept and run but reported apart, outside the main table (docs/RUNNING.md "Results").

## Integrity

Eight invariants bind every task and every run ([PROTOCOL Appendix H](docs/PROTOCOL.md#appendix-h-invariants-binding));
no task setting overrides them, and the required CI job `invariants` fails a pull request that breaks one. Everything
else in the protocol is a recommended convention, reported by the job `advisories` as a warning.

- **Verifier isolation.** Every task is graded in its own sandbox (`[verifier] environment_mode = "separate"`).
  The agent's container is stopped first, and only the declared artifacts are copied across. An agent is root inside
  its container. In Harbor's default shared mode, it could patch the success predicate and score a do-nothing
  trajectory; under the separate sandbox, the same attack scores 0.
- **No reference solutions in reach.** Reference solutions live only in `solution/`, which Harbor mounts for the
  oracle agent alone. Upstream experts are removed from the agent's images.
- **Recorded evidence in standard mode.** The simulator service records the episode, replays it in a fresh simulator,
  and writes the verdict inputs. The agent never holds the simulator.
- **Infrastructure retry.** An infrastructure failure allows at most one full retry with the same instance, seed and
  configuration; a normal task failure is never retried (H.5).
- **Network policy and external material.** By default a task restricts the agent's egress to the model APIs and the package
  registries (PyPI, the Debian / Ubuntu apt archives; `[agent] network_mode = "allowlist"`, one host list in
  `scripts/set_agent_egress.py`), and every instruction states the same honour rule (`## External material`): the agent
  may install the packages it needs and read whatever is installed in its container (the benchmark's own source
  included), and is asked not to search the web for, or download, a ready-made solution to the task (PROTOCOL §5, H.6; a task whose author chooses open egress declares
  `[metadata] network = "open"`, and its results are ranked apart).
  GitHub, Hugging Face and the general web, where the benchmarks' sources, demonstrations and policies are, stay
  closed. Official runs go through the usage gateway, which forwards model-API calls only; the harness's web search,
  account connectors and other provider-side tools are off (they run at the model provider, past any allowlist).
- **Reproducibility.** Base images are pinned by tag (pinning every pip dependency: open, PROTOCOL_HISTORY.md v1 §7 item 2). A task's identity is its digest (`tasks/<task>/DIGEST`; the release manifest `tasks/dataset.toml` is generated from them),
  and published task inputs never change.

## Repository layout

```
tasks/                 Harbor tasks (one directory per task and mode, each with its content DIGEST)
images/<sim>/          simulator base images (simulator installs only)
scripts/               task generators, image build/push, the egress allowlist, results and report tools
ci_checks/             checks run on every pull request: run_invariants.sh (required: PROTOCOL Appendix H) and
                       run_all.sh (both tiers; the advisory ones only warn); scoped by ci_scope.py
docs/                  PROTOCOL.md (conventions + the binding invariants), STANDARD_MODE.md (standard-mode wire protocol),
                       TAXONOMY.md (metadata vocabulary), REVIEWING.md (maintainer guide),
                       RUNNING.md (official runs, seeds, retries, results, batches), LEAKAGE.md (where answer keys survive),
                       benchmarks/ (per-benchmark notes)
third_party/           upstream sources used by the base images (RoboTwin)
```

## Results

Agent results are not stored in this repository: per-task results and batch reports are published on the results
site and the Hugging Face dataset, keyed by run id `<harness>-<model>-<effort>` (for example `codex-gpt6_luna-xhigh`)
(PROTOCOL §4); each result records its effective configuration (docs/RUNNING.md "Results"). How to run a batch and read agent logs is described in [docs/RUNNING.md](docs/RUNNING.md).

## Contributing

New benchmarks start with a proposal issue. Task pull requests contain one benchmark each, pass the required check
`invariants` (`ci_checks/run_invariants.sh`), and
include oracle and `nop` evidence. A task without an oracle needs human review. See [CONTRIBUTING.md](CONTRIBUTING.md)
and [docs/REVIEWING.md](docs/REVIEWING.md).

## License

[MIT](LICENSE) for the code in this repository. Third-party simulators, assets, reference solutions derived from
upstream experts, and the contents of the base images keep their own licenses (e.g. RoboTwin: MIT; CuRobo:
NVIDIA license). See the upstream projects in `third_party/` and each benchmark's README.
