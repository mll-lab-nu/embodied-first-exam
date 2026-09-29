# HumanoidBench

Whole-body humanoid control: locomotion and manipulation on a Unitree H1, scored by a dense reward. No language.

| | |
|---|---|
| upstream | [HumanoidBench](https://humanoid-bench.github.io/) (RSS 2024), pinned at `cb11890`; 32 registered tasks |
| simulator | MuJoCo 3.1.6 + dm_control, CPU |
| robots | `h1`: Unitree H1, 19 actuators · `h1hand`: H1 + two Shadow hands, 61 actuators |
| score | an episode's summed reward (≤ 1000 steps); pass = at least upstream's success bar |
| image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.6` (`images/humanoidbench/`) |

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

## Modes (standard config: Codex via OpenRouter, effort medium, 60 min)

| mode | the agent gets | resets | delivers |
|---|---|---|---|
| limited | head cameras, joint angles/velocities, IMU, room camera; no reward | 50 | the graded episodes themselves |
| full | the simulator and its full state; no reward | unlimited | one replayable trajectory |

Limited mode, what the agent can and cannot access:

| given (a real H1 has it) | not given |
|---|---|
| the task text: goal, what ends an episode, pass mark, the reward's terms in words (no formula) | the reward and the return |
| two head cameras, RGB 256×256 (cube 512); `room_camera` (standard on); depth (optional) | the robot's position in the room |
| joint angles and velocities; pelvis IMU: gyro, gravity direction (standard on) | any object's or target's pose |
| `spec()`: servo ranges, joint axes and positions, link masses and centres of mass, feet boxes, IMU and camera frames, 50 Hz, 1000 steps, reset budget | contact forces, the simulator itself |

## Run

```bash
RCB_RESET_BUDGET=50 RCB_OBS_IMU=1 RCB_OBS_ROOM_CAMERA=1 RCB_MODEL=openrouter/openai/gpt-6-luna \
  scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00-limited --ak reasoning_effort=medium
python3 scripts/results/build.py --add jobs/<job>     # log the run, rebuild the results pages
```

## Latest results (task text 7, 09-28; pass / scored tasks run)

| model | limited | full |
|---|---|---|
| GPT-6 Luna | 0/23 | 3/23 (push, reach, sit_hard) |
| GPT-6 Sol | 1/5 (push) | 1/2 (sit_hard; only walk and sit_hard run) |
| Claude Opus 5.5 | 2/5 (push, sit_hard) | 4/5 (all but cube) |

- limited is stuck at standing, not at information: no run produced a forward gait; more resets or the link masses
  did not change that.
- full wins on state and unlimited retries; Luna's self-made proxy scores mislead it, Opus plans on the full model.

Per task: `results/humanoidbench/README.md`; analysis: `results/humanoidbench/analysis/overview.md`;
limited protocol: `docs/LIMITED_MODE_1_1.md`.
