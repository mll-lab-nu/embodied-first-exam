# AutoBio

Nine tasks of [AutoBio](https://github.com/autobio-bench/AutoBio) (commit `0850421`, the "preliminary version" of the
ICLR 2026 benchmark, [arXiv:2505.14030](https://arxiv.org/abs/2505.14030)) on MuJoCo 3.3.0, CPU only, in both modes: 18
task directories, `tasks/autobio/autobio-<family>-i00-{privileged,standard}`. `simulator = "autobio"`. The scene is a
biology laboratory bench: a thermal cycler with a lid and a locking lever, a thermal mixer with a working button panel
and display, a centrifuge with a 30-slot rotor, tube racks, tubes with real screw threads, a pipette. The robots are
UR5e arms with a Robotiq 2F-85, ALOHA arms, and a UR5e pair of which one arm holds the pipette in a dexterous hand.
The tasks are in the `all` set only (not in `docs/core_set.toml`). Results are attributed by DIGEST (PROTOCOL H.8).

AutoBio's repository states **no licence** for its code or its own assets. Nothing of it is in this repository, and its
image is never published (below, "Before you run").

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/autobio -a codex -m openai/gpt-6-astra
```
The first task builds the simulator image from public sources (below); later tasks reuse it.

## Before you run

- **Licence.** AutoBio's repository has no LICENSE file and no licence statement for its code or for its own assets
  (the digitized instruments, tubes, racks and pipette, and two binaries without source: `libmjlab.so.3.3.0`, the
  thread and detent MuJoCo plugins, and `meshplane.so`, the liquid-surface solver). Building and running the image uses
  them for research evaluation on your own machine. The robot models it bundles keep their own licences (UR5e and
  Robotiq 2F-85: BSD; ALOHA 2: BSD; DexHand021: Apache-2.0; the display font: SIL OFL). `images/autobio/BUILD_ONLY` has
  the details. No account, login or token is needed.
- **Host.** Linux x86_64 and Docker with BuildKit. No GPU: MuJoCo physics and OSMesa rendering run on the CPU. About
  1 GB of RAM per simulator process.
- **First build.** The image is not on a public registry, so the first task builds it with Docker from AutoBio's
  public repository: a few minutes, about 3 GB of free disk, network access to github.com and pypi.org. Every task's
  Dockerfile starts with that recipe (`images/autobio/Dockerfile`), so the build runs once per Docker host and later
  tasks take it from Docker's build cache. Maintainers who can pull `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` get
  its layers instead (compose `build.cache_from`). To build it ahead of the run:
  `harbor run -p tasks/autobio/autobio-pickup-i00-privileged -a oracle` (reward 1).

## Tasks
| family (AutoBio's task id) | AutoBio's name and level | robot (`robot`) | action entries | rule | reference rows (2 ms each) |
|---|---|---|---|---|---|
| `thermal_cycler_close` | Close thermal cycler lid, easy | UR5e + 2F-85 (`ur5e-robotiq-2f85`) | 7 | first | 5068 |
| `thermal_cycler_open` | Open thermal cycler lid, easy | UR5e + 2F-85 | 7 | first | 8251 |
| `pickup` | Pick up centrifuge tube, easy | one ALOHA arm (`aloha-2-arm`) | 7 | first | 3945 |
| `screw_loose` | Unscrew centrifuge tube cap, medium | two ALOHA arms (`aloha-2`) | 14 | first | 13568 |
| `pipette` | Aspirate with pipette, medium | UR5e with a pipette-holding hand + UR5e with a 2F-85 (`ur5e-dexhand-2f85-bimanual`) | 14 | first | 6973 |
| `insert` | Transfer centrifuge tube, medium | UR5e + 2F-85 | 7 | first | 4162 |
| `screw_tighten` | Screw on centrifuge tube cap, hard | two ALOHA arms | 14 | first | 7638 |
| `thermal_mixer` | Operate thermal mixer panel, hard | UR5e + 2F-85 | 7 | final | 8094 |
| `insert_centrifuge_5430` | Load centrifuge rotor, hard | UR5e + 2F-85 | 7 | first | 4582 |

Every family has `oracle = "full"`: AutoBio's own scripted expert. The benchmark's own fields: `difficulty` (`easy` ·
`medium` · `hard`, the level AutoBio's paper gives the task) and `success_rule` (below).

## Selection
These are the nine tasks AutoBio's paper evaluates (its Table 3), and they are exactly the tasks whose `check()` is
implemented in the repository. Left out:
- four task modules whose `check()` is a placeholder (`return True` or `return False`): the lids of the three centrifuges
  (`mani_centrifuge_5430.py`, `mani_centrifuge_5910.py`, `mani_centrifuge_mini.py`) and the vortex mixer
  (`mani_vortex_mixer.py`). They have experts, so they could come in with a success rule of ours and human review;
- the rest of the paper's 16 tasks, which the repository does not contain (its `task.py` registry names six modules
  that are not there).

For orientation, the paper's vision-language-action policies trained on 100 demonstrations per task reach (Table 3,
success in % of 100 episodes, pi0 / RDT): close lid 99.7 / 100.0, open lid 96.0 / 99.0, pick up 53.7 / 57.7, unscrew
21.3 / 2.7, aspirate 42.7 / 0.3, transfer 40.7 / 2.0, screw on 2.0 / 8.3, mixer panel 7.5 / 1.6 (AutoBio's score, not a
success rate), load rotor 14.7 / 1.0.

## Task definition
- **Instance.** One frozen instance per family: AutoBio's own `Task(Task.load())` then `reset(seed=0)`, which draws the
  arm's start pose, the tube's rack slot, the target slot, the rotor's angle and slot, the mixer's target settings or
  the liquid volume, depending on the task. The task's `instance.json` records the seed and two hashes: of the compiled
  MuJoCo model and of the start state. Every load compares both (`instance_ok`); a mismatch is an infrastructure
  failure, never a silent change. Nothing else is stored: the scene is rebuilt from AutoBio in the image.
- **Action.** One position target per controlled actuator, AutoBio's own `action_indices` (the interface its policies
  use): 6 arm joints per arm plus the gripper command (Robotiq: 0 open .. 255 closed; ALOHA: the finger position in m)
  or, for the pipette arm, the thumb joint that presses the plunger. Targets are clipped to the actuators' ranges.
- **Control step = one physics step, 2 ms.** AutoBio evaluates policies at 50 Hz (10 physics steps per action), but its
  experts write their targets at arbitrary physics steps (every 25 steps, with offsets), so 2 ms is the rate at which
  an expert's run replays bit for bit. An agent that wants 50 Hz repeats a row ten times (privileged: `s.step(a, n=10)`;
  standard: `dt=0.02`).
- **Success** is AutoBio's own `check()`, evaluated after every control step (the upstream's rule stays):
  - rule `first`, AutoBio's `early_stop` tasks (eight families): the first step at which it holds ends the episode in
    success. This is "success at any step": it is how AutoBio's evaluator scores these tasks.
  - rule `final`, the thermal mixer: `check()` is a score in [0, 1] (0.5 x temperature + 0.3 x time + 0.2 x speed, each
    the fraction of the way from the initial to the target setting), and AutoBio scores the state at the end. Here:
    success iff the score is 1 in the state in which the episode ends (privileged: after the last row; standard: at the
    agent's `done`, or when its time is over); the score is reported as `progress`.
  - AutoBio's time limits (15 to 45 s of simulated time) are lifted: the wall clock is the budget. One technical cap
    bounds an episode: it ends after 600000 control steps (1200 s of simulated time), stated in the instructions and in
    `/spec` (`max_control_steps`).
  - A MuJoCo physics warning (an unstable state) ends the episode as a failure, as AutoBio's evaluator does. The
    renderer's own warning (`VGEOMFULL`) is not counted, so that looking never changes a verdict.
- **The checks, in words** (thresholds are AutoBio's):

  | family | success |
  |---|---|
  | `pickup` | the tube's body above 0.925 m (9.5 cm up) while the gripper's left finger touches the cap |
  | `thermal_cycler_close` | lid hinge within 0.01 rad of -1.9 rad and lever within 0.01 rad of -0.94 rad (both start at 0) |
  | `thermal_cycler_open` | lid hinge and lever within 0.003 rad of 0 (they start at -1.9 and -0.94 rad) |
  | `pipette` | in order: plunger pressed (thumb target > 0.70 rad) with the tip within 6.5 mm of the tube's axis and > 5 mm below the liquid surface; plunger released (< 0.45 rad) with the tip still below it; then the tip > 5 cm above the surface |
  | `screw_loose` | cap > 0.15 m above the tube body's origin (screwed on: 0.1197 m), the first arm's left finger on the cap, cap thread and tube thread not in contact |
  | `screw_tighten` | cap < 0.123 m above the tube body's origin, cap axis within 5 mm of the tube's, threads in contact |
  | `insert` | tube within 15 mm (horizontally) of the target slot's centre, its height between 0.829 and 0.831 m |
  | `thermal_mixer` | final panel settings equal to the three targets (30 s, 33 °C, 600 rpm; from 60 s, 25 °C, 900 rpm) |
  | `insert_centrifuge_5430` | tube within 5 mm of its seated position in the slot opposite the loaded one, its height between 0.955 and 0.961 m |

- **World-frame information.** A privileged instruction gives AutoBio's thresholds as they are in its code, world
  heights and MuJoCo names included: that mode reads the simulator anyway. A standard instruction states the same goal
  with every threshold relative ("lift it at least 9.5 cm", "within 15 mm of the slot's centre", "the row farther from
  the robot's base"), and never a world coordinate, an object pose or an instrument state; the robot's own base poses
  are in `/spec` (`robot_spec.base`). `ci_checks/benchmarks/autobio/advisory-world-frame.sh` checks the standard texts.
- **Texts.** The instructions describe each check in our own words and point to its source in the image
  (`/opt/AutoBio/autobio/<module>.py`); AutoBio's code is not quoted (no licence).
- **Budget: 3600 s**, both modes (each task's `[agent] timeout_sec`, stated in its instruction's closing
  `## Time limit` section).

## Modes
- **Privileged:** `rcb_autobio.Session` in the agent's container: AutoBio's task object (`s.task`: its scene helpers and
  `check()`), the MuJoCo model and data, reset, step, recording, self-replay, the tool frames, forward and inverse
  kinematics of the arm joints, rendering (RGB and depth, every camera). Deliverable `/app/output/trajectory.npz`,
  `(T, n)` position targets, one row per control step. AutoBio's code other than the experts is in the image (inverse
  kinematics, path timing, scene helpers). The verifier replays the rows in two fresh processes in its own sandbox: both
  must succeed and end in the same state.
- **Standard (`eai-standard/2.2`):** the shared layer of `embodied_first_exam/standard/` and the adapter
  `environment/sim/server.py`, the same in all nine families:
  - action types `joint_position` (the action above; rows `dt` apart, a multiple of 2 ms, `linear` or `hold`; clipped
    values reported) and `done` (ends the episode in its current state: how the thermal mixer's episode is handed in);
  - every camera of the scene, 640 x 480, depth on request: `table_cam_front` and `table_cam_left` (static) and one
    wrist camera per arm (mounted on the arm's last link). The mixer's display is rendered into the images, drawn by
    AutoBio's own panel code: at 640 x 480 its digits are readable from the wrist camera once the gripper is near the
    panel. The tooling uploads the drawing itself (`rcb_autobio.PanelTexture`): the helper in AutoBio's evaluator
    (`make_thermal_mixer_extra`) stops redrawing for good once two frames in a row find the panel unchanged, after which
    every frame shows a stale display. The liquid's surface is drawn by AutoBio's own helper;
  - proprioception = the robot's own joints (`q_`, `qd_`, `effort_`), gripper openings, tool-frame poses and the targets
    in effect (`cmd_`); never a tube, rack or instrument;
  - `/kinematics` = the tool frames (the gripper's pinch point; for the pipette arm, the pipette's tip) and the links
    the wrist cameras sit on, for arm joint positions, and damped-least-squares IK per arm; `robot_spec` with the arms'
    base poses, joint limits, drive gains and gripper commands;
  - crash recovery with resume class `exact` (MuJoCo on the CPU is bit-exact in a fresh process);
  - a request is checked in full before anything is executed: a malformed field (null or a wrong type for `dt`,
    `seconds`, `cameras`, `note`, `video`, `interpolate`, `depth`; a `dt` that is not finite or not a whole multiple of
    2 ms) is a 400 and the episode goes on. Null for `dt`, `seconds`, `video_fps`, `cameras` or `note` means the
    default.
- **Grading, standard mode.** The trial is graded by its live episode (docs/protocol/README.md H.4): `success` = the
  live episode's success, judged by the sim service on the episode the agent ran, with no grading replay; an
  episode that ended in a simulator error scores 0. The collect
  hook (`environment/sim/finalize.sh`) ends the episode, writes `final.json` from the service's record and then, after
  the verdict is on disk, replays the recorded trajectory once to render `replay.mp4` (a failed video replay costs the
  video only). Its `timeout_sec` is 3000 = 900 (the episode's end, through a resume) + the video replay (at most
  1800 s) + 300 s.
- **Time limits, privileged mode.** The longest episode, 600000 rows, replays in 1000 s in the slowest family
  (`insert_centrifuge_5430`, 600 control steps/s); a verdict replay may take 2400 s and is killed at that limit.
  `[verifier] timeout_sec` 5400 = 2 x 2400 + the video replay (what is left, at most 1800 s; skipped under 120 s) +
  300 s, so `tests/grade.py` always writes a reward before Harbor's timeout.
- **What is not the agent's 0** (`infra_error = 1` in `reward.json`, PROTOCOL §4). Standard: `final.json` missing
  (the service writes it as soon as its scene is up), unreadable, or not finalized (the collect hook was killed before
  it wrote the verdict); the service never ending its episode for the hook; a give-up after crashes between calls or a
  failed resume; a live episode that did not start in the instance's recorded state (`instance_mismatch`); no
  `episode.json`. A crash inside a call (`sim_crashed_on_call`) stays the agent's failure. `final.json` is written
  whole (temporary file, then rename). Privileged: a replay without a result and an instance mismatch set
  `grader_error` and `infra_error`; a deliverable that cannot be read (not an npz, no `actions`, object arrays, the
  wrong shape, more than 600000 rows) is the agent's 0 (`bad_trajectory`), never a grader error.
- **Looking never changes the physics.** Observations (rendering, camera poses, tool poses) are computed on a scratch
  copy of the state; nothing calls `mj_forward` on the live data (that would change the solver's warm start and with
  it the trajectory). A replay with rendering ends in the same state as one without.

## Reference solutions
AutoBio's scripted experts (`class <Task>Expert` in each task module), run from the frozen instance in a checkout that
still has them: the targets in effect at every physics step, clipped to the actuators' ranges, rounded to float32 (what
the standard client sends, so both modes execute the same rows) and, for rule `first`, cut at the first success:
`solution/oracle.npz` in every task. The privileged oracle hands the rows in; the standard oracle streams them through
the client (and ends the mixer's episode with `done`). Replayed through `ctrl[action_indices]` alone on a task without
its expert, the unrounded rows reproduce the expert's own run bit for bit (final state and the whole `check()`
timeline), in all nine families; rounded to float32 they still succeed (the success step moves by at most 22 control
steps).

## Integrity
- **Experts removed.** `images/autobio/strip_experts.py` deletes, from every module of the checkout, each class that
  derives from `Expert`, the `X.Expert = ...` binding and the `__main__` demonstration generator, in the same image
  layer as the clone (no layer holds them); the build fails if a class `...Expert` is left. Everything else stays as it
  is: the agent can read each task's scene code and `check()`.
- **Agent egress is the model APIs and the package registries, in both modes.** The experts are in AutoBio's public
  repository and its recorded demonstrations on Hugging Face; a standard-mode agent could also rebuild the simulator
  from the repository.
- **Only rows cross to the verifier.** The privileged grader copies the trajectory's rows into a clean file and replays
  them with its own copy of the tooling and of the instance, in a sandbox the agent never saw.
- **No file of AutoBio is in this repository:** the tooling imports it from the image; the instances are a seed and two
  hashes; the reference solutions are control sequences recorded by running AutoBio's experts (data produced by the
  program, like the demonstrations its authors publish under MIT).

## Known limits
- **The pipette task moves no liquid.** AutoBio models the liquid's surface in a container (volume, level, sloshing),
  not its transfer: the check is on the tip's position relative to the surface and on the plunger command.
- **The rotor check holds only while the tube is held, in this instance.** After AutoBio's own expert lets go, the tube
  rests 5.0 to 5.1 mm from the check's reference point, just outside its 5 mm; the check holds for 0.41 s while the
  tube is being lowered. Under rule `first` that moment is the success. Both instructions state this, with the height
  window (0.955-0.961 m) and the fact that the reference is computed at the episode's start (a rotor turned by the
  agent moves the slot away from it).
- **Contact with a named finger.** `pickup` and `screw_loose` look for contact between the cap and the first arm's
  left finger; a grasp between both fingers satisfies it, and the instructions say so.
- **AutoBio's own evaluator shows a frozen mixer display** after its first two frames (the helper described under
  Modes); frames rendered here follow the panel. Worth knowing when comparing with AutoBio's numbers for that task.
- **`check-standard-protocol.py`** (the live conformance test) reports one false positive on the UR5e tasks:
  `placeholder_limits`, because five UR5e joints share a +-2 pi range. That is their range in AutoBio's model, as on the
  real arm.
- **No licence upstream**, hence a private image; a licence from the authors that allows redistribution would change
  that and nothing else.

## Verification
On the image built locally (Intel Xeon Platinum 8559C, 8 vCPUs, no GPU): `harbor run -a oracle` scored 1 on all 18
task directories (both fresh-process replays and, in standard mode, the live episode ending in the reference's
recorded state) and `harbor run -a nop` scored 0 on all 18. The standard tasks have since moved to live grading (the
verdict = the live episode's, which those runs also checked); they were not run again after that change.

## Files
Every task directory is self-contained: `environment/rcb_autobio.py` (privileged; the verifier's own copy in `tests/`)
or `environment/sim/` (standard: the adapter `server.py`, `rcb_autobio.py`, the collect hook),
`instance.json`, `solution/oracle.npz`; the standard tasks take the shared 2.2 layer and the agent's client
(`rcb_limited.py`, `run.sh`, `rcb1.py`, `rcb_client.py`) from the pinned `standard-files` image. `images/autobio/` has the image recipe (Dockerfile, VERSION, BUILD_ONLY,
requirements.txt, strip_experts.py).
