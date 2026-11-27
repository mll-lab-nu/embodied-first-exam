# HumanoidBench

## Overview

Whole-body humanoid control: locomotion and manipulation on a Unitree H1, scored by a dense reward. No language.

| | |
|---|---|
| upstream | [HumanoidBench](https://humanoid-bench.github.io/) (Sferrazza et al., RSS 2024), pinned at `cb11890`; 32 registered tasks |
| simulator | MuJoCo 3.3.7 + dm_control, CPU (upstream pins 3.1.6; see Changes from upstream) |
| robots | `h1`: Unitree H1, 19 actuators · `h1hand`: H1 + two Shadow hands, 61 actuators |
| score | an episode's summed reward (≤ 1000 steps; cube ≤ 500); pass = at least upstream's success bar |
| tasks | 10 families × 3 modes = 30 tasks: `tasks/humanoidbench/humanoidbench-<category>-<task>-i00-privileged`, `-standard` (the standard protocol) and `-realtime` (standard mode on a clock that does not stop, below) |
| image | `ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0` (`images/humanoidbench/`) |
| oracle | `sit_simple` (the fixture): full, all three modes; the 9 scored tasks: none, human review (`oracle_evidence` in each task.toml) |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/humanoidbench -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator and its full state; no reward | unlimited | its `trajectory.npz`, replayed once in a fresh process |
| standard | head cameras, joint angles/velocities, a pelvis IMU, a fixed room camera; no reward | 50 (below; `RCB_RESET_BUDGET=0`: none) | the last episode, as it ran (live; nothing replayed) |
| realtime | the same as standard, but time does not stop: the robot runs at 50 Hz in real time while the agent thinks (below) | 50 (as in standard: HumanoidBench's choice, PROTOCOL §2; the realtime template's default is 0) | the last episode, as it ran (live; nothing replayed) |

## Upstream and license

HumanoidBench (Sferrazza et al., 2024; <https://github.com/carlosferrazza/humanoid-bench>, pinned at `cb11890`) is
MIT-licensed, copyright (c) 2024 Robot Learning Lab, UC Berkeley; the notice is
`images/humanoidbench/LICENSE.humanoid-bench`. `rewards.json`, `no-torch.patch` and `upstream-fixes.patch` in
`images/humanoidbench/`, and the `rewards.json` copies in `tasks/humanoidbench/`, carry upstream code under it. The
robot models come with upstream: the Unitree H1 (BSD 3-Clause, Unitree Robotics) and the Shadow Hand from MuJoCo
Menagerie (Apache License 2.0). No non-commercial terms apply.

## Changes from upstream

### Physics: fixes to upstream (image 0.2.0)

Rewards, success bars and terminations are upstream's; the physics is fixed where it was measurably wrong (the image
build fails unless each fix holds). Every task runs upstream's model (HumanoidBench cb11890) on MuJoCo 3.3.7, not the
3.1.6 upstream pins, whose convex collision reported wrong contacts; results on image 0.1.6 or earlier are other
physics and are reported apart.

| scope | upstream bug | fix | measured |
|---|---|---|---|
| every task | MuJoCo 3.1.6 collides general convex shapes (mesh, cylinder) through libccd's MPR, which now and then reports a depth and normal unrelated to the geometry | MuJoCo 3.3.7 (native convex collision) and the matching dm_control's array-size table | hip self-contact normal off > 20° in 64% of 1008 logged contacts (up to 66°, kN forces) → p90 0.6°; forearm-door depth over-reported by up to 98 mm → never; flat ground statistically unchanged |
| `balance_hard` (and `stair`, `balance_simple`, not shipped; `h1` and `h1hand`) | a mesh foot on a box gets one contact point: on 3.1.6 wrong depths (a robot with every joint locked slid off a stair tread in 9 of 10 placements), on 3.3.7 it never comes to rest | feet = four boxes that follow the hull, sole exact (`box_feet.py`) | locked robot on 9 stair placements: still (< 1 mm/s); foot-box depth exact in all 75,406 contacts of our logged episodes |
| `room` | the reset loops over 7 objects in a scene of 6 and writes the 7th's x/y into the right little finger's two joints (`rh_LFJ2`/`rh_LFJ1`; it started bent through its own fingertip, 1.4 kN on it); headphones and a package start 5-8 cm inside the floor | write the 6 objects only (same draws, same placement); lift objects onto the floor (`upstream-fixes.patch`); the frozen instance was redrawn with the fix | finger in range, no self-contact; objects on the floor |
| `powerlift` | the plates' `density="500"` sits on geoms whose class sets `mass="0"`, so it never applied | the density on the visual plates (`upstream-fixes.patch`) | dumbbell 104.0 kg → 53.7 kg |

None is comparable with the paper's numbers. The instances were drawn on MuJoCo 3.1.6 and load identically on 0.2.0, room's redrawn with its fix.
Known and not fixed: masses where upstream set no density (room's packages 24 and 40 kg) or chose one (the door, 160 kg at
`density="600"`), the ±0.01 start noise on every `qpos` (feet start up to 18 mm in the floor), `sit_simple`'s chair box
overlapping the heels by 19 mm (its mesh feet touch that box; it is a fixture), and `hurdle`'s hurdles, which its reward
never reads: each is one collision box 37.5 cm high across the track (`generated_xml_hurdles.xml`; the bars drawn on it,
about 40 cm tall, have no collision geometry of their own), so the robot has to get over it; the task text says so.

### Answer-key leakage: the reward is scrubbed

A dense reward is the answer key: with it the task is to invert an expression, not to control a robot. So the image has
every `get_reward()` and the constants only it read deleted (`images/humanoidbench/scrub_oracles.py`, in the same
layer as the clone, `.git` included); `get_terminated` stays (dynamics, not scoring). Each task's own formula ships only
where scoring happens -- `tests/` (privileged) or `environment/sim/` (standard and realtime) -- and is patched back
there (`rcb_rewards.py`, from `rewards.json`). In the agent's container `s.scored` is False, `s.step()` returns `None`
for the reward and `s.status()` reports no return. The agent reaches the model APIs and the package registries
(`[agent]` allowlist, `scripts/set_agent_egress.py`), so it cannot fetch the public upstream back; instructions
describe the scoring in words, with no tolerance or weight.
Known gaps: the image still holds `_WALK_SPEED` and `_RUN_SPEED`, which a class body references (the move
term's bound for walk, stair and hurdle; the instructions give the same order of magnitude), and a native agent holds
its model-API key in its container, so it could call a search-enabled model through the allowed host.

### Added

The standard and realtime modes (a sim sidecar with HumanoidBench's own `image` and `proprio` sensors, a pelvis IMU, a
room camera and depth, below), frozen instances, and agent-ended episodes; upstream has only the privileged setting.

## Interface

**Privileged.** `/opt/tools/rcb_hb.py` (`from rcb_hb import Session`): the full simulator on the frozen instance,
`s.obs()` (qpos and, for most tasks, qvel, plus this task's goal where it has one), `s.low.model` / `s.low.data`,
unlimited `s.reset()`, `s.recording()`, `s.replay()`, `s.save_trajectory()`. An action is one control step (50 Hz):
normalised joint-position targets in [-1, 1], one per actuator (19 for `h1`, 61 for `h1hand`), -1 and +1 the two ends
of the servo's range; no reward. CPU MuJoCo repeats bit for bit, so actions recorded from a feedback controller
reproduce when replayed open-loop.

**Standard and realtime.** The robot is a service in the `sim` sidecar (wire protocol `eai-standard/3.0`; `environment/docker-compose.yaml`, GPU on the
sidecar for rendering), reached through `environment/rcb_client.py` (installed as `/opt/tools/rcb_client.py`; its
docstring is the reference; `instruction.md` lists the endpoints) or the `efe-robot` MCP tools. One action type,
`joint_position`: HumanoidBench's own normalised position targets, 50 Hz, sent in chunks (realtime: streamed one row
at a time or in chunks of up to 10 s).

World-frame information (PROTOCOL §5): privileged mode gives the full state; standard mode gives none -- no root pose,
no object or target pose; the room camera's pose is given in the robot's starting frame.

| standard mode: given (a real H1 has it) | not given |
|---|---|
| the task text: goal, what ends an episode, pass mark, the reward's terms in words (no formula) | the reward and the return |
| two head cameras, RGB 256×256 (cube 512); `room_camera`; depth (`RCB_OBS_DEPTH=1`, off) | the robot's position in the room |
| joint angles and velocities; pelvis IMU: gyro, gravity direction | any object's or target's pose |
| `spec()`: servo ranges, joint axes and positions, link masses and centres of mass, feet boxes, IMU and camera frames, 50 Hz, the episode length (1000 control steps; 500 for cube), budget | contact forces, the simulator itself |

Knobs (compose env): `RCB_RESET_BUDGET` (50), `RCB_OBS_PROPRIO` (1), `RCB_OBS_IMU` (1), `RCB_OBS_ROOM_CAMERA` (1),
`RCB_OBS_DEPTH` (0), and in realtime `RCB_SLOWDOWN` (1: real time; S: one control step every S × 0.02 s). The defaults
are the tasks' configuration; a run that changes one is reported separately, and `episode.jsonl` records the `/spec`
it ran under.

What the cameras see (`RCB_ROOM_CAMERA_POSE` in the compose file places `room_camera`; where it is unset, the camera is
the task's recording camera frozen at its starting pose):

| family | head cameras | `room_camera` |
|---|---|---|
| walk | flat floor and the horizon (nothing else in the scene) | behind and above the start, down the course: the robot in frame from x = 0 to 20 m |
| hurdle | the walled track and the line of hurdles ahead | behind and above the start, down the course: the robot in frame from x = 0 to 20 m |
| sit_simple | floor and horizon; the chair is behind the robot | frozen recording camera: the robot and the chair |
| balance_hard | floor and horizon; the board and roller never enter view | frozen recording camera: the robot on the board from outside |
| door | the door right in front of the robot | the doorway from the side: robot, door and the floor beyond in frame from x = -0.5 to 4 m |
| powerlift | floor and horizon; the dumbbell at the feet is out of view | frozen recording camera: the robot and the dumbbell |
| window | the window | frozen recording camera: the window, the wiping tool and the robot |
| cube | the cube above one palm | close on the hands: both cubes and, above them, the goal orientation (upstream's `target_cube`); legs out of frame; every camera at 512×512 |
| room | a bookshelf and a table | looking down on the whole room: all six objects and the robot |
| bookshelf_simple | the inside of one shelf | the shelves from behind the robot's right shoulder: the bookshelf, the objects' places and the robot |

### Realtime mode: time does not stop

In standard mode the robot waits, frozen, between the agent's calls: a model that thinks for a minute between two
chunks loses nothing. A real H1 does not wait. The realtime mode (PROTOCOL §3;
`tasks/humanoidbench/humanoidbench-*-i00-realtime`, 10 tasks, one per family, `mode = "realtime"`) is standard mode with the same
instance, sensors, success rule, reset budget (50), wall clock (each task's own `[agent] timeout_sec`, stated by the Time line of every instruction's closing `## Limits`, PROTOCOL §2) and client, on a
clock that does not stop (each task's `environment/sim/rcb_realtime.py`, which extends `rcb_service.py`; the
wire protocol is the standard protocol's realtime capability, docs/protocol/standard_mode.md "Realtime mode"):

- **Clock.** An episode starts paused at the frozen start, its servos holding their starting targets. Its clock starts
  at its first `submit` and runs one control step every 20 ms of wall time
  (`RCB_SLOWDOWN` = S: every S × 20 ms; 1 by default, other values reported separately) until the episode ends. Each
  episode after a reset starts paused again; so does an episode resumed after a crash.
- **Actions.** The service keeps a plan, one target row per coming control step. `submit` expands its chunk exactly as
  in standard mode (rows `dt` apart, `linear` or `hold`) and writes it into the plan from control step `at` (default: the next
  one), replacing what was planned from there, and answers at once with the robot as it is now. A row whose step has
  already run when the request arrives is dropped (`late_steps`). When the plan runs out, the last target is held
  (zero-order hold): a slow agent's robot keeps its last servo targets, as a position-controlled H1 would. (The layer
  is shared with BiGym 2.0 and Embodied Olympics - Fun, whose plans mix action types: rows of different types are never combined.)
- **Observations.** `get_obs()` is the robot now; `get_obs(last_s=n)` returns at once what the recorder
  recorded over the last n seconds, without touching the plan (observe never waits). `cameras=[]` returns proprioception only (the controller's call).
- **Timing guarantees.** The simulator thread runs a due control step before any waiting request; HumanoidBench's
  physics takes 0.4–2.1 ms per control step and a head-camera image about 0.5 ms on the
  sidecar's GPU, against a 20 ms step. A service that falls behind runs the missed steps back to back; more than
  0.5 s behind, it drops the debt (a stall) instead of fast-forwarding the robot. Requests cannot slow the clock: a request is read, decoded and checked off the simulator's thread (large
  JSON bodies by a child process), waiting requests are served once the clock has caught up, and the cameras are
  rendered once per control step for everyone who asks (`docs/protocol/standard_mode.md`, "What a request can cost the
  clock").

**What makes it a meaningful task.** A model's turn takes seconds; the H1 falls within 1-3 s of robot time without
active balance; a whole episode is 20 s (cube: 10 s). An agent that answers each observation with a model call cannot
keep the robot up, so the instruction says so and tells it to write a controller: a Python loop in its own container
that reads proprioception and streams targets at the control rate through the client (a one-row call with
`cameras=[]` costs a few ms over the shared network namespace), run in the background, and improved between episodes.
The agent's code still runs only in its own container, never next to the simulator (standard mode's isolation is
kept); the 50 resets are what make that loop of writing, running and revising a controller possible at all, which is
why HumanoidBench's realtime tasks default to 50 resets rather than the mode's 0 (PROTOCOL §2).

## Grading

**Privileged: replay.** In its own container, built from `tests/Dockerfile` (no network): the agent's container is
gone by then, and only `/app/output/` crosses over. `tests/grade.py` restores this task's reward (`rcb_rewards.py`),
then replays `/app/output/trajectory.npz` open-loop from `tests/instance.npz` in a fresh process, once; pass iff the
replay's episode return reaches `success_bar`. With one replay `deterministic` is written as 1 with
`determinism_checked` = 0 and `replays` = 1 (`--repeat N` is the old bit-exact determinism check, kept for a
measurement by hand). A missing file (`missing_trajectory`), another task's file (`wrong_family`) or not a (T, nu)
array of finite values with T at most the episode limit (`bad_trajectory`) is the agent's 0; an exception in the
grader is `grader_error` (infrastructure). `tests/grade.py` also writes `/logs/verifier/replay.mp4` and
`replay.last.png`, and, because Harbor promotes every `reward.json` key to a leaderboard metric, keeps the per-task
numbers (`episode_return`, `success_bar`, `state_sha`, timings) in `/logs/verifier/diagnostics.json`. `nop` scores 0.

### Grading in the standard modes: the live episode

The standard and realtime verdict is the live episode's: the sim sidecar holds the reward, judges the episode it runs
with HumanoidBench's own rule (the episode's return reaches the pass mark; `step()` in
`embodied_first_exam/benchmarks/humanoidbench/sim/server.py`, each standard task's `environment/sim/server.py`), and
`rcb_service.py` writes that verdict (`graded_by = "live"`, `replays = 0`) once the agent's container is stopped; the
rule has no settle or hold window. The verifier grades the sidecar's record in a container of its own
(`tests/Dockerfile`, no network): `tests/grade.py` reads `/data/final.json` and copies the evidence to
`/logs/verifier/` (`trajectory.npz`, the deliverable, replayable, and `replay.mp4`). The frozen start is checked on the
live simulator: `start_sha` is the state `instance.npz` records (the hash of the snapshot `Session` restores), and the
instance file's own digest must match its contents; a fresh trial that does not start there gives up as
infrastructure (`instance_mismatch`, `infra_error = 1`), and so does the service at once when a reset does not return
there. The video is one render pass over `trajectory.npz` after the verdict (`render_video`: CPU physics, EGL
rendering on the sidecar's GPU; median 19 s a trial); it never changes the verdict. In both service modes
`final.json` is `finalized` the moment the verdict is written, before the video is rendered (`video_pending` while it
renders); the collect hook waits for the verdict and then, as long as its timeout allows, for the video, so a slow,
hung or killed render costs the video and never the verdict. `nop` scores 0.

**Infrastructure vs agent failures.** `infra_error = 1` only for no or an unfinalized `final.json`, a give-up after
crashes not all inside the agent's calls (`sim_crashed`, `resume_failed`), a reset whose scene does not rebuild, and
`instance_mismatch`. Crashes inside the agent's calls (`sim_crashed_on_call`), simulator errors raised by its calls,
timeouts and failures are the agent's 0. In realtime: once the agent's first command has run (the first control step
of a row the agent sent, `first_command` in `episode.jsonl`), a simulator error raised by a control step is the
agent's 0 (`sim_error = 1`, no `infra_error`), and so is a simulator crash inside a control step (a death whose
fatal-signal record in `crash.log` -- SIGSEGV, SIGBUS, SIGFPE, SIGILL, SIGABRT -- shows the crashing thread in the
step; past `RCB_MAX_RESUMES` such crashes the trial ends `sim_crashed_on_call`); a crash outside a step (building the
scene, resuming, resetting, rendering, finalizing), anything before the first command, a failed reset rebuild, a kill
(SIGKILL, SIGTERM, the OOM killer; no record) and a failed resume are infrastructure (`sim_crashed`, `infra_error = 1`).
Standard mode keeps its rule: a crash is the agent's only inside its call (`fatal_signal` is logged as evidence).

### Agent-ended episodes

Every standard and realtime task runs with `RCB_AGENT_END=1` (PROTOCOL §3, agent-ended episodes): reaching the pass mark
no longer ends the episode or the trial and no reply shows it. The episode ends at the agent's `POST /finish`, at one of
the task's own terminations (a fall, a dropped tool, cube or book, a forbidden contact: a failure), at the episode's
length or bookshelf's own end once all five objects are placed (reason `step_limit`), or at the end of the session.
Judgement is by events (`end_judgement = "events"`): the summed reward reaching the pass mark counts once reached, and
an event that happened stands: a fall or another failure rule after the pass mark ends the episode (reason `failed`)
but the episode is a success (the standard protocol, PROTOCOL §3: on a goal judged as events a later failure does not
take an event back; `rcb_service.py`). A failure before the pass mark is reached is 0; a simulator error or a reset
gives 0 whatever was reached. Resets stay available after a success, and the last episode is graded.

### Standard mode's reset budget: 50

HumanoidBench's standard configuration grants **50 resets** (`RCB_RESET_BUDGET` defaults to 50 in every
`-standard` task's `environment/docker-compose.yaml`, so `spec()["budget"]["reset"]` is 50). Without them, the agent gets a single blind attempt: the H1 falls within 1-3 s of robot time under a
first guess, and in standard mode there is no simulator to practise in. This is HumanoidBench's own choice of budget
(PROTOCOL §2: each task declares its budget; the standard template's default is 0); results state the reset budget they ran under. What a reset does (`rcb_service.py`, the
standard-protocol service shared with KinDER and VLABench; each standard task's `environment/sim/`):

- `POST /reset` (`r.reset()`) abandons the running episode, or follows one that has ended (`failed`: a fall or the
  step limit; `error`), and starts a new one from the frozen instance: `Session.reset()` restores the robot, the scene,
  the task state and the model-side goals, the same restore every episode starts from. Each episode has
  its own `max_control_steps`; the wall clock is the trial's and never restarts. The reply carries the start's images
  and proprioception, `episode` and `resets_left`.
- Refused (409) after `/finish`, once the agent's time is up, or when the budget is spent; then the running episode is
  the last one.
- **Only the last episode is graded.** The finalize grades the episode since the last reset as it ran;
  `trajectory.npz`, `replay.mp4` and `replay.last.png` are that episode. Every episode stays in the
  evidence: `trajectory_live.f64` journals every control step of the trial, `episode.jsonl` logs each reset (its
  checkpoint's `ep_start` is where the new episode begins in the journal) and `calls/` each call.
- `final.json` and `reward.json` report `reset_budget` (50), `resets` (used), `n_actions` (the graded episode's steps)
  and `sim_steps` (every episode's, the cost); `final.json` also `episodes`.
- A crash resumes the current episode (the one after the last reset), never a reset; the resets used survive it.

`RCB_RESET_BUDGET=0 harbor run ...` runs the single-episode configuration (no `/reset`, 404); any other value N
grants N. Results under a budget other than 50 are reported separately.

### Realtime evidence

The live episode is graded as in standard mode (above). The journal (`trajectory_live.f64`) holds the sim row the
simulator applied at every control step, whatever was submitted, so the trajectory reproduces the live run however
late or early the agent was. Evidence beside it: `ticks.f64` (each step's wall time and the call that planned it; -1 =
held), `calls.jsonl`, `submitted.f64` (every row as sent), and in `final.json` `max_lag_s`, `stalls`, `held_steps`,
`late_steps` (over the whole trial, across crash-resumes), with `clock_s`, `stalled_s` and `stalled_share` (the wall
time the clock ran, the time its stalls dropped, and their ratio), `requests_refused` and `request_busy_s`;
`reward.json` repeats them. They are evidence: a stalled trial is flagged, not failed.

## Tasks

### Upstream's 32, ours ✅ (9 scored + the `sit_simple` fixture)

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
| | balance_hard | h1 | ✅ | same reward on a rolling sphere |
| | sit_simple | h1 | ✅ | fixture, the pipeline check: holding still earns 77% |
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
- Per-task reasons: the table above. `bookshelf_hard` is the same class as `bookshelf_simple` with its five
  destinations permuted (`fixed = False`); its completion rate and give-away are within noise of `bookshelf_simple`'s,
  so it would spend a slot on the same problem.
- **`sit_simple` is the fixture**, not part of the scored subset: a static seated pose is easy to reason out, and an
  all-zero action already scores about 80% of its bar. It proves the pipeline end to end with a solvable target, is the
  template the other tasks are generated from, and is the CI fixture that tells "the agent is broken" apart from "the
  task is hard".

## Others

### Instances

Every task runs one frozen instance, seed 0 (`[metadata] instance_seed`): `environment/instance.npz` with byte copies
in `tests/` (privileged) or `environment/sim/` (standard, realtime). An instance holds the MuJoCo state (qpos, qvel,
time, qacc_warmstart) plus the task state that lives outside it -- goals drawn at reset, subtask counters, and the model
arrays a task writes its target into (cube's goal orientation is `model.body_quat[-1]`, drawn from the global
`np.random` that `reset(seed=)` does not reach) -- so agent and grader face the same scene. Upstream forces
`randomness = 0` for `bookshelf_*`, `cube` and `kitchen`: one instance per family.

### GPU (privileged)

Optional, and passing never depends on it: MuJoCo physics is CPU-only, so a GPU only speeds up the agent's own
offscreen rendering (osmesa ~130 ms/frame, egl ~0.4 ms). Hand one to the agent's container with
`--extra-docker-compose environment/gpu.docker-compose.yaml`; `rcb_hb.py` then picks EGL by itself unless `MUJOCO_GL`
says otherwise. The overlay is not named `docker-compose.yaml` because Harbor would load that on every machine, and a
device reservation the host cannot satisfy stops the container from starting. Standard and realtime tasks hold a GPU
in the `sim` sidecar for rendering.

### Run

```bash
harbor run -p tasks/humanoidbench/humanoidbench-loco-hurdle-i00-standard -a codex -m openai/gpt-6-astra --env-file .env
harbor run -p tasks/humanoidbench/humanoidbench-loco-sit-simple-i00-standard -a oracle      # or -a nop: scores 0
harbor run -p tasks/humanoidbench/humanoidbench-loco-walk-i00-realtime -a codex -m openai/gpt-6-astra --env-file .env
harbor run -p tasks/humanoidbench/humanoidbench-loco-sit-simple-i00-realtime -a oracle   # streams the same 999 rows
```
Agent, provider and effort settings: docs/protocol/running.md. Standard tasks run with 50 resets by default; `RCB_RESET_BUDGET=0 harbor run ...` runs them
with none (one episode), whose results are reported separately. Build the image: `docker build -f images/humanoidbench/Dockerfile -t
ghcr.io/mll-lab-nu/efe:humanoidbench-$(cat images/humanoidbench/VERSION) .` (from the
repository root).

### Results

Agent results are not kept in this repository: they are published on the results site, keyed by run id. Standard-mode
results state their reset budget (the configuration is 50; runs with another budget are reported separately).
Realtime results are their own mode and are never pooled with standard ones; they state the reset budget and
`slowdown`. Official runs use `slowdown` 1 (the default); results with `RCB_SLOWDOWN` ≠ 1 are reported separately.

### Standard-mode service details

**KinDER and HumanoidBench service (the standard protocol).** Same endpoints, RCB1 frames and crash recovery, served by one
shared service (`rcb_service.py`, one source in `embodied_first_exam/standard/sidecar/`, from the files-only image `standard-files`) with a per-benchmark
simulator adapter (`server.py`). Actions are delta or joint-position rows at the task's control rate (KinDER 10 Hz,
PyBullet tasks kinematic: a refused move comes back `blocked` and stops the chunk; HumanoidBench 50 Hz); the step
counters are `rows` and `control_steps`. No world coordinates are given (odometry and camera poses are in the robot's
starting frame). A request body over 64 MB gets 413 before it is decoded. The service implements the optional reset
capability (`RCB_RESET_BUDGET`).
