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

A third mode, **standard-realtime** (protocol v1.1, `eai-standard/2.3`, PROTOCOL §4b), is standard mode on a clock that does not
stop: once an episode starts, the robot runs in real time and holds its last targets while the agent thinks, so the agent
drives it from a controller program of its own. It is offered where a benchmark's tasks call for it (HumanoidBench, RoboOlympics, BiGym 2.0), as
`<base>-standard-realtime` next to `<base>-privileged` and `<base>-standard`; its results are reported separately.

> **Names.** Protocol v1.0 renamed *unlimited/limited* to *privileged/standard* and `rcb-limited/2.1` to
> `eai-standard/2.1`. Every task directory ends in its mode, `-privileged` or `-standard` (since v1.1 also `-standard-realtime`). Base images are
> `ghcr.io/mll-lab-nu/eai-<name>` (formerly `rcb-<sim>` under several registries), one per benchmark (PROTOCOL D5).

## Benchmarks

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
| LabUtopia (`labutopia-<family>-i00`) | LabUtopia on Isaac Sim 6.1 · Franka Panda; a chemistry laboratory: glassware (pick, place, pour, shake), a heater with a button, an instrument panel, a drying oven's door, a cabinet's drawer | 9 | full (LabUtopia's scripted controllers) |
| BEHAVIOR-1K (`behavior-<activity>-i00`) | OmniGibson / Isaac Sim · Galaxea R1 Pro | 100 | partial on 2, none on 98 (human review; 89 supplementary tasks without a verified positive yet) |
| VLABench (`vlabench-<task>-i00`) | MuJoCo + dm_control · Franka Panda | 36 | full |
| RoboCasa (`robocasa-<task>-i00`) | robosuite · Franka Panda on an Omron mobile base | 29 | full (upstream demonstrations) |
| RoboCasa365 (`robocasa365-<task>-i00`) | robosuite · Franka Panda on an Omron mobile base | 50 | full (upstream demonstrations) |
| RoboCasa-GR1 (`robocasa-gr1-<task>-i00`) | robosuite · Fourier GR1 humanoid | 24 | full (upstream demonstrations) |
| DexJoCo (`dexjoco-<family>-i00`) | MuJoCo 3.4 · Franka Panda + Allegro hand, one or two arms | 11 | full (upstream human demonstrations) |
| AutoBio (`autobio-<family>-i00`) | AutoBio on MuJoCo 3.3 (CPU) · UR5e with a Robotiq 2F-85, ALOHA arms, and a UR5e pair with a pipette-holding dexterous hand; a biology bench: thermal cycler, thermal mixer panel, centrifuge rotor, screw caps, a pipette | 9 | full (AutoBio's scripted experts) |
| MyoSuite (`myosuite-<family>-i00`) | MyoSuite 2.12.2 (MuJoCo 3.6, CPU) · musculoskeletal hand, arm, torso and legs (MyoHand, MyoArm, MyoLegs, with prostheses in two tasks), muscle commands; MyoChallenge and MyoDex tasks | 22 | full on 3 (MyoSuite's NPG baselines), none on 19 (human review) |
| RoboARC (`roboarc-<family>-<NN>-i01`; formerly TopoGym and RoboTangle; the MuJoCo release replaces the Genesis one, 2026-10-13) | MuJoCo 3.14.0 (CPU float64; the blanket cloth on a deterministic CUDA step), Nyx RGB · ALOHA 2 bimanual; Franka Panda + Robotiq 2F-85 | per release ([docs/benchmarks/roboarc.md](docs/benchmarks/roboarc.md)) | full, or none where no reference exists |
| BiGym 2.0 (`bigym2-<family>-i00`) | MuJoCo 3.8.1 + NVIDIA GR00T-WBC (CPU; EGL rendering) · Unitree G1 humanoid with Dex1-1 grippers, legs and waist driven by the whole-body controller | 13 (+ 13 standard-realtime) | none (human review) |
| RoboFunOlympics (`robofunolympics-<family>-i00`) | the RoboOlympics simulator (MuJoCo 3.3.7, CPU, OSMesa) · Unitree G1 (29 joints, with its walking and running policies; 20 families) or the larger Unitree H1-2 (27 joints, walking policy; 30 families), or joint by joint (Unitree LowCmd); 50 single-robot sports at official rule-book sizes judged by a referee of events, geometry and contact rules; the agent may download public tools and controllers | 50 | see [docs/benchmarks/robofunolympics.md](docs/benchmarks/robofunolympics.md): full where a reference controller exists, none elsewhere (human review) |
| RoboOlympics (`roboolympics-<sport>-<format>-i00`) | MuJoCo 3.3.7 (CPU, OSMesa) · Franka Panda with a paddle (table tennis) or with a racket on an x-y base (badminton); KUKA iiwa 14 with a mallet (air hockey) | 3, standard-realtime only (real-time sports against a scripted opponent; S = 10 and no privileged twin, PROTOCOL §4b exceptions) | full (RoboOlympics' reference players, camera images only) |
| LIBERO-MAX (`libero-max-<suite>-<task>-<event>-iNN`) | robosuite 1.4 (MuJoCo 3.2.6, CPU) · Franka Panda; LIBERO tasks with one change in mid-task (a target, receptacle or obstacle moves, the camera, lighting or scene theme changes, sensor noise sets in, distractors appear) | 64 | full |
| ManiGuard (`maniguard-<family>-iNN`) | BEHAVIOR-1K 3.7.2 (OmniGibson on Isaac Sim 4.5) · Franka Panda with long fin-ray fingers; tabletop tasks with a safety specification checked at every control step | 30 (6 families × 5) | full on 14, none on 16 (human review) |
| MolmoSpaces (`molmospaces-<family>-i00`) | Ai2 MolmoSpaces on MuJoCo 3.5 (CPU physics) · Franka FR3 + Robotiq 2F-85 on a fixed base; Rainbow RB-Y1 mobile manipulator | 8 | none (human review) |
| Panda Dynamic Scenes (`pandadyn-<code>-<name>-i00`) | ManiSkill 3 / SAPIEN (CPU PhysX at 1000 Hz) · one or two Franka Panda arms with task tools (a plate, a cup, a paddle, a scoop, ...); multi-stage dynamic tasks: catch, strike, carry, hand over, release objects that move by themselves | 25 (12 one-arm + 13 two-arm) | full (the benchmark's recorded reference rollouts) |

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
- **RoboFunOlympics:** `scripts/robofunolympics/gen_tasks.py` (`render`, `check`) from the families under
  `scripts/robofunolympics/shared/rfo/tasks/`; how to write a family: `scripts/robofunolympics/AUTHORING.md`; notes in
  [docs/benchmarks/robofunolympics.md](docs/benchmarks/robofunolympics.md).
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
- Reference hardware is an RTX 4090. Four RoboTwin instances rebuild to a different state on other GPUs (e.g. L40S) and are then reported as `grader_error` (PROTOCOL §3).
- Disk space for the base images (the RoboTwin image is about 22 GB). Public images can be pulled; `BUILD_ONLY` ones are built on the host.

**Running official results:**
- Use Harbor's native agents through `scripts/run_agent_batch.sh` with `GATEWAY=1`, and with no tool that runs outside the trial's container (PROTOCOL §2.11, D11): the harness's web search off (Codex `--ak web_search=disabled`, Claude Code `--ak disallowed_tools=WebSearch,WebFetch`: the script's default), no account connectors, apps, plugins or image generation. They run at the model provider, so no egress allowlist stops them; the gateway forwards model-API calls only and is, with the package registries, the agent container's only egress.
- Align reasoning effort and the time budget across agents: every task states its cutoff at the end of its instruction (`## Time limit`), and the numbers per benchmark and mode are in one table, [docs/CUTOFFS.md](docs/CUTOFFS.md) (3600 s by default; PROTOCOL §2.12). The token budget (100M input / 10M output tokens per trial) is defined in PROTOCOL §5; it will be applied to Harbor's recorded counts, which is not implemented yet (PROTOCOL §7).

## Integrity

- **Verifier isolation.** Every task is graded in its own sandbox (`[verifier] environment_mode = "separate"`).
  The agent's container is stopped first, and only the declared artifacts are copied across. An agent is root inside
  its container. In Harbor's default shared mode, it could patch the success predicate and score a do-nothing
  trajectory; under the separate sandbox, the same attack scores 0.
- **No reference solutions in reach.** Reference solutions live only in `solution/`, which Harbor mounts for the
  oracle agent alone. Upstream experts are removed from the agent's images.
- **Recorded evidence in standard mode.** The simulator service records the episode, replays it in a fresh simulator,
  and writes the verdict inputs. The agent never holds the simulator.
- **Network policy and external material.** Every task restricts the agent's egress to the model APIs and the package
  registries (PyPI, the Debian / Ubuntu apt archives; `[agent] network_mode = "allowlist"`, one host list in
  `scripts/set_agent_egress.py`), and every instruction states the same honour rule (`## External material`): the agent
  may install the packages it needs and is asked not to look up or download a solution to the task (PROTOCOL §2.11).
  GitHub, Hugging Face and the general web, where the benchmarks' sources, demonstrations and policies are, stay
  closed. Official runs go through the usage gateway, which forwards model-API calls only; the harness's web search,
  account connectors and other provider-side tools are off (they run at the model provider, past any allowlist).
- **Reproducibility.** Base images are pinned by tag (pinning every pip dependency: PROTOCOL §7, open item 2). A task's identity is its digest in `tasks/dataset.toml`,
  and published task inputs never change.

## Repository layout

```
tasks/                 Harbor tasks (one directory per task and mode) and dataset.toml (manifest with digests)
images/<sim>/          simulator base images (simulator installs only)
scripts/               task generators, image build/push, the egress allowlist, results and report tools
ci_checks/             contract checks run on every pull request (ci_checks/run_all.sh)
docs/                  PROTOCOL.md (contract), STANDARD_MODE.md (standard-mode wire protocol),
                       TAXONOMY.md (metadata vocabulary), REVIEWING.md (maintainer guide),
                       RUNNING.md (batches, logs, recordings), LEAKAGE.md (where answer keys survive),
                       benchmarks/ (per-benchmark notes)
third_party/           upstream sources used by the base images (RoboTwin)
```

## Results

Agent results are not stored in this repository: per-task results and batch reports are published on the results
site and the Hugging Face dataset, keyed by run id `<harness>-<model>-<effort>` (for example `codex-gpt6_luna-xhigh`)
(PROTOCOL §5). How to run a batch and read agent logs is described in [docs/RUNNING.md](docs/RUNNING.md).

## Contributing

New benchmarks start with a proposal issue. Task pull requests contain one benchmark each, pass `ci_checks/`, and
include oracle and `nop` evidence. A task without an oracle needs human review. See [CONTRIBUTING.md](CONTRIBUTING.md)
and [docs/REVIEWING.md](docs/REVIEWING.md).

## License

[MIT](LICENSE) for the code in this repository. Third-party simulators, assets, reference solutions derived from
upstream experts, and the contents of the base images keep their own licenses (e.g. RoboTwin: MIT; CuRobo:
NVIDIA license). See the upstream projects in `third_party/` and each benchmark's README.
