# HumanoidBench

Whole-body humanoid control: locomotion and manipulation on a Unitree H1, scored by a dense reward. No language.

| | |
|---|---|
| upstream | [HumanoidBench](https://humanoid-bench.github.io/) (RSS 2024), pinned at `cb11890`; 32 registered tasks |
| simulator | MuJoCo 3.1.6 + dm_control, CPU |
| robots | `h1`: Unitree H1, 19 actuators · `h1hand`: H1 + two Shadow hands, 61 actuators |
| score | an episode's summed reward (≤ 1000 steps); pass = at least upstream's success bar |
| tasks | 24 × 2 modes: `tasks/humanoidbench-<category>-<task>-i00-privileged` and `-standard` (`eai-standard/2.1`) |
| image | `ghcr.io/mll-lab-nu/eai-humanoidbench:0.1.6` (`images/humanoidbench/`) |
| oracle | `sit_simple` (the fixture): full, both modes; the 23 scored tasks: none, human review (`oracle_evidence` in each task.toml) |

## Tasks: upstream's 32, ours ✅ (23 scored + the `sit_simple` fixture)

| class | task | robot | ours | note |
|---|---|---|---|---|
| C1 flat gait | walk | h1 | ✅ | |
| | run | h1 | ⬜ | walk's reward at running speed |
| | stand | h1 | ⬜ | walk's reward at speed 0 |
| | crawl | h1 | ⬜ | holding still earns 42% of the bar |
| C2 constrained gait | hurdle | h1 | ✅ | |
| | stair | h1 | ✅ | |
| | slide | h1 | ⬜ | stair's reward, byte for byte, easier |
| | pole | h1 | ⬜ | holding still earns 71% of the bar |
| C3 stabilisation | balance_simple | h1 | ✅ | |
| | balance_hard | h1 | ✅ | same reward on a rolling cylinder: far harder |
| | sit_simple | h1 | ✅ | fixture, the pipeline check: holding still earns 62% |
| C4 navigation | door | h1 | ✅ | |
| | maze | h1 | ✅ | |
| C5 whole-body power | powerlift | h1hand | ✅ | |
| | highbar_simple | h1 | ✅ | |
| | highbar_hard | h1strong | ⬜ | highbar's reward on a stronger robot |
| | basketball | h1 | ✅ | |
| C6 bimanual manip. | push | h1 | ✅ | |
| | window | h1hand | ✅ | |
| | spoon | h1hand | ✅ | holding still earns 58%: kept, noted |
| C7 in-hand precision | cube | h1hand | ✅ | |
| | insert_normal | h1hand | ✅ | |
| | insert_small | h1hand | ⬜ | insert_normal's reward, thinner peg |
| C8 mobile manip. | package | h1 | ✅ | |
| | reach | h1 | ✅ | |
| | sit_hard | h1 | ✅ | |
| | room | h1hand | ✅ | |
| C9 long-horizon | bookshelf_simple | h1hand | ✅ | |
| | bookshelf_hard | h1hand | ⬜ | bookshelf_simple's reward, random placement |
| | truck | h1 | ✅ | |
| | cabinet | h1hand | ✅ | |
| | kitchen | h1hand | ✅ | |

Why: one task per reward function, and holding still must earn under 40% of the bar, so passing takes control, not
a pose; the 23 cover 9 capability classes. Source, with the reasoning per task: `scripts/humanoidbench/subset.toml`
(the generator's input).

## Modes

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator and its full state; no reward | unlimited | its `trajectory.npz`, replayed twice in a fresh process |
| standard | head cameras, joint angles/velocities, a pelvis IMU, a fixed room camera; no reward | none (optional capability, reported separately) | the recorded episode, replayed in a fresh simulator |

World-frame information (PROTOCOL D7): privileged mode gives the full state; standard mode gives none -- no root pose,
no object or target pose; the room camera's pose is given in the robot's starting frame.

| standard mode: given (a real H1 has it) | not given |
|---|---|
| the task text: goal, what ends an episode, pass mark, the reward's terms in words (no formula) | the reward and the return |
| two head cameras, RGB 256×256 (cube 512); `room_camera`; depth (`RCB_OBS_DEPTH=1`, off) | the robot's position in the room |
| joint angles and velocities; pelvis IMU: gyro, gravity direction | any object's or target's pose |
| `spec()`: servo ranges, joint axes and positions, link masses and centres of mass, feet boxes, IMU and camera frames, 50 Hz, the episode length (1000 control steps; 500 for basketball, cube, insert_normal, kitchen, push), budget | contact forces, the simulator itself |

## Answer-key leakage

A dense reward is the answer key: with it the task is to invert an expression, not to control a robot. So the image has
every `get_reward()` and the constants only it read deleted (`images/humanoidbench/scrub_oracles.py`, in the same
layer as the clone, `.git` included); each task's own formula ships only where scoring happens -- `tests/` (privileged)
or `environment/sim/` (standard) -- and is patched back there (`shared/rcb_rewards.py`, from `rewards.json`). The agent
reaches the model APIs and nothing else (`[agent]` allowlist, `scripts/set_agent_egress.py`), so it cannot fetch the
public upstream back; instructions describe the scoring in words, with no tolerance or weight
(`scripts/humanoidbench/subset.toml`, "HOW TO WRITE scoring_note"; `gen_tasks.py check` looks for formula fragments).
Known gaps: the 0.1.6 image still holds `_WALK_SPEED` and `_RUN_SPEED`, which a class body references (the move
term's bound for walk, stair and hurdle; the instructions give the same order of magnitude), and a native agent holds
its model-API key in its container, so it could call a search-enabled model through the allowed host.

## Run

```bash
harbor run -c scripts/humanoidbench/configs/codex-openrouter.yaml --env-file .env -p tasks/humanoidbench-loco-walk-i00-standard
harbor run -p tasks/humanoidbench-loco-sit-simple-i00-standard -a oracle      # or -a nop: scores 0
```
`codex-openrouter.yaml` is Harbor's own Codex agent with OpenRouter as its model provider (run id
`codex-gpt6_luna-medium`); `RCB_RESET_BUDGET=50 harbor run ...` turns on the optional reset capability, whose results are
reported separately. Build the image: `docker build -f images/humanoidbench/Dockerfile -t
ghcr.io/mll-lab-nu/eai-humanoidbench:$(cat images/humanoidbench/VERSION) .` (from the
repository root).

## Results

Agent results are not kept in this repository (PROTOCOL D3): per-run READMEs (verdict, cost, what happened),
`reward.json`, the replay's last frame and videos are published on the results site, keyed by run id. Standard-mode
runs with the optional reset capability (50 resets) are reported separately from the standard configuration (no
reset, PROTOCOL D1), and runs recorded before protocol v1.0 are marked as such.
