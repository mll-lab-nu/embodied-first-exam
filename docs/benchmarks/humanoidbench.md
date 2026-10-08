# HumanoidBench

Whole-body humanoid control: locomotion and manipulation on a Unitree H1, scored by a dense reward. No language.

| | |
|---|---|
| upstream | [HumanoidBench](https://humanoid-bench.github.io/) (RSS 2024), pinned at `cb11890`; 32 registered tasks |
| simulator | MuJoCo 3.1.6 + dm_control, CPU |
| robots | `h1`: Unitree H1, 19 actuators · `h1hand`: H1 + two Shadow hands, 61 actuators |
| score | an episode's summed reward (≤ 1000 steps); pass = at least upstream's success bar |
| tasks | 10 × 2 modes: `tasks/humanoidbench-<category>-<task>-i00-privileged` and `-standard` (`eai-standard/2.1`) |
| image | `ghcr.io/mll-lab-nu/eai-humanoidbench:0.1.6` (`images/humanoidbench/`) |
| oracle | `sit_simple` (the fixture): full, both modes; the 9 scored tasks: none, human review (`oracle_evidence` in each task.toml) |

## Tasks: upstream's 32, ours ✅ (9 scored + the `sit_simple` fixture)

| class | task | robot | ours | note |
|---|---|---|---|---|
| C1 flat gait | walk | h1 | ✅ | the class's only candidate |
| | run | h1 | ⬜ | walk's reward at running speed |
| | stand | h1 | ⬜ | walk's reward at speed 0 |
| | crawl | h1 | ⬜ | holding still earns 42% of the bar |
| C2 constrained gait | hurdle | h1 | ✅ | runs (5 m/s) |
| | stair | h1 | ⬜ | walks (1 m/s) |
| | slide | h1 | ⬜ | stair's reward, byte for byte, easier |
| | pole | h1 | ⬜ | holding still earns 71% of the bar |
| C3 stabilisation | balance_simple | h1 | ⬜ | balance_hard is upstream's hard version |
| | balance_hard | h1 | ✅ | same reward on a rolling cylinder |
| | sit_simple | h1 | ✅ | fixture, the pipeline check: holding still earns 62% |
| C4 navigation | door | h1 | ✅ | moves 1 object (the door) |
| | maze | h1 | ⬜ | moves no object |
| C5 whole-body power | powerlift | h1hand | ✅ | moves 1 object, dexterous hands |
| | highbar_simple | h1 | ⬜ | moves no object |
| | highbar_hard | h1strong | ⬜ | highbar's reward on a stronger robot |
| | basketball | h1 | ⬜ | moves 1 object, no hands |
| C6 bimanual manip. | push | h1 | ⬜ | moves 1 object, no hands |
| | window | h1hand | ✅ | moves 1 object (a wiping tool), dexterous hands |
| | spoon | h1hand | ⬜ | holding still earns 58% of the bar |
| C7 in-hand precision | cube | h1hand | ✅ | the class's only candidate left |
| | insert_normal | h1hand | ⬜ | the bar needs no insertion |
| | insert_small | h1hand | ⬜ | insert_normal's reward, thinner peg |
| C8 mobile manip. | package | h1 | ⬜ | moves 1 object |
| | reach | h1 | ⬜ | moves no object |
| | sit_hard | h1 | ⬜ | moves no object |
| | room | h1hand | ✅ | moves 6 objects |
| C9 long-horizon | bookshelf_simple | h1hand | ✅ | moves 5 objects, dexterous hands |
| | bookshelf_hard | h1hand | ⬜ | bookshelf_simple's reward, random placement |
| | truck | h1 | ⬜ | moves 5 objects, no hands |
| | cabinet | h1hand | ⬜ | the bar cannot be reached |
| | kitchen | h1hand | ⬜ | moves 4 objects |

Why these (no model's results enter the choice):
- **Valid (20):** the bar measures the task and can be reached, and holding still earns under 40% of it: `main`'s 23
  minus spoon, insert_normal and cabinet.
- **One per capability class (9):** within a class, upstream's hard version first, then the task that moves more
  objects, then the dexterous hands (`h1hand`), then the higher speed target.
- Per-task reasons: the table above and `scripts/humanoidbench/subset.toml`.

## Modes

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator and its full state; no reward | unlimited | its `trajectory.npz`, replayed twice in a fresh process |
| standard | head cameras, joint angles/velocities, a pelvis IMU, a fixed room camera; no reward | 50 (below; `RCB_RESET_BUDGET=0`: none) | the last episode, replayed in a fresh simulator |

### Standard mode's reset budget: 50

HumanoidBench's standard configuration grants **50 resets** (`RCB_RESET_BUDGET` defaults to 50 in every
`-standard` task's `environment/docker-compose.yaml`, so `spec()["budget"]["reset"]` is 50), by the owner's decision
of 2026-10-07. Without one, the agent gets a single blind attempt: the H1 falls within 1-3 s of robot time under a
first guess, and in standard mode there is no simulator to practise in. This is a per-benchmark exception to PROTOCOL
D1's default of 0 (§4.5); results state the reset budget they ran under. What a reset does (`rcb_service.py`, the
`eai-standard/2.1` service shared with KinDER and VLABench; `scripts/humanoidbench/shared/standard/`):

- `POST /reset` (`r.reset()`) abandons the running episode, or follows one that has ended (`failed`: a fall or the
  step limit; `error`), and starts a new one from the frozen instance: `Session.reset()` restores the robot, the scene,
  the task state and the model-side goals, the same restore the verifier's fresh replay starts from. Each episode has
  its own `max_control_steps`; the wall clock is the trial's and never restarts. The reply carries the start's images
  and proprioception, `episode` and `resets_left`.
- Refused (409) once an episode has succeeded (a success ends the trial), once the agent's time is up, or when the
  budget is spent; then the running episode is the last one.
- **Only the last episode is graded.** The finalize replays the episode since the last reset in a fresh simulator;
  `trajectory.npz`, `replay.mp4` and `replay.last.png` are that episode. Since a success ends the trial at once, this
  is the same as "the trial passes iff some episode passes and its replay agrees". Every episode stays in the
  evidence: `trajectory_live.f64` journals every control step of the trial, `episode.jsonl` logs each reset (its
  checkpoint's `ep_start` is where the new episode begins in the journal) and `calls/` each call.
- `final.json` and `reward.json` report `reset_budget` (50), `resets` (used), `n_actions` (the graded episode's steps)
  and `sim_steps` (every episode's, the cost); `final.json` also `episodes`.
- A crash resumes the current episode (the one after the last reset), never a reset; the resets used survive it.

`RCB_RESET_BUDGET=0 harbor run ...` runs the single-episode configuration (no `/reset`, 404); any other value N
grants N. Results under a budget other than 50 are reported separately, and HumanoidBench standard-mode results
recorded before this change (budget 0) are a different configuration from today's.

World-frame information (PROTOCOL D7): privileged mode gives the full state; standard mode gives none -- no root pose,
no object or target pose; the room camera's pose is given in the robot's starting frame.

| standard mode: given (a real H1 has it) | not given |
|---|---|
| the task text: goal, what ends an episode, pass mark, the reward's terms in words (no formula) | the reward and the return |
| two head cameras, RGB 256×256 (cube 512); `room_camera`; depth (`RCB_OBS_DEPTH=1`, off) | the robot's position in the room |
| joint angles and velocities; pelvis IMU: gyro, gravity direction | any object's or target's pose |
| `spec()`: servo ranges, joint axes and positions, link masses and centres of mass, feet boxes, IMU and camera frames, 50 Hz, the episode length (1000 control steps; 500 for cube), budget | contact forces, the simulator itself |

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
harbor run -c scripts/humanoidbench/configs/codex-openrouter.yaml --env-file .env -p tasks/humanoidbench-loco-hurdle-i00-standard
harbor run -p tasks/humanoidbench-loco-sit-simple-i00-standard -a oracle      # or -a nop: scores 0
```
`codex-openrouter.yaml` is Harbor's own Codex agent with OpenRouter as its model provider (run id
`codex-gpt6_luna-medium`). Standard tasks run with 50 resets by default; `RCB_RESET_BUDGET=0 harbor run ...` runs them
with none (one episode), whose results are reported separately. Build the image: `docker build -f images/humanoidbench/Dockerfile -t
ghcr.io/mll-lab-nu/eai-humanoidbench:$(cat images/humanoidbench/VERSION) .` (from the
repository root).

## Results

Agent results are not kept in this repository (PROTOCOL D3): per-run READMEs (verdict, cost, what happened),
`reward.json`, the replay's last frame and videos are published on the results site, keyed by run id. Standard-mode
results state their reset budget: the standard configuration is 50 resets (since 2026-10-07); runs with 0 -- every
HumanoidBench standard-mode run recorded before that date -- are reported separately, and runs recorded before
protocol v1.0 are marked as such.
