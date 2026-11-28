# AutoBio

## Overview
Nine tasks of [AutoBio](https://github.com/autobio-bench/AutoBio) (Lan et al., 2025; the repository's "preliminary
version" of the ICLR 2026 benchmark, [arXiv:2505.14030](https://arxiv.org/abs/2505.14030)) on MuJoCo 3.3.0, CPU only,
in both modes: 18 task directories, `tasks/autobio/autobio-<family>-i00-{privileged,standard}`. `simulator =
"autobio"`. The scene is a biology laboratory bench: a thermal cycler with a lid and a locking lever, a thermal mixer
with a working button panel and display, a centrifuge with a 30-slot rotor, tube racks, tubes with real screw threads,
a pipette. The robots are UR5e arms with a Robotiq 2F-85, ALOHA arms, and a UR5e pair of which one arm holds the
pipette in a dexterous hand.

```bash
harbor run -d embodied-first-exam@all -p tasks/autobio -a codex -m <model>
```
The first task builds the simulator image from public sources; later tasks reuse it.

| | |
|---|---|
| upstream | AutoBio @ `08504213356cbfe9a82bcd33a43cd282945a45df` (no licence stated) |
| simulator | MuJoCo 3.3.0 with AutoBio's thread, detent and liquid-surface plugins; OSMesa rendering; CPU only |
| image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` (`images/autobio/`), never published: built locally |
| host | Linux x86_64, Docker with BuildKit, no GPU; about 1 GB of RAM per simulator process |
| time limit | 3600 s in both modes (`[agent] timeout_sec`) |
| oracle | `full` in every task: AutoBio's own scripted expert, recorded |

**First build.** The image is not on a public registry, so the first task builds it with Docker from AutoBio's public
repository: a few minutes, about 3 GB of free disk, network access to github.com and pypi.org. Every task's Dockerfile
starts with that recipe (`images/autobio/Dockerfile`), so the build runs once per Docker host and later tasks take it
from Docker's build cache. Maintainers who can pull the private image get its layers instead (compose
`build.cache_from`). To build it ahead of a run: `harbor run -p tasks/autobio/autobio-pickup-i00-privileged -a oracle`
(reward 1).

## Upstream and license
[AutoBio](https://github.com/autobio-bench/AutoBio) at commit `08504213356cbfe9a82bcd33a43cd282945a45df`. The
repository has **no LICENSE file and no licence statement** for its code or for its own assets: the digitized
instruments, tubes, racks and pipette, and two binaries without source (`libmjlab.so.3.3.0`, the thread and detent
MuJoCo plugins, and `meshplane.so`, the liquid-surface solver). Building and running the image uses them for research
evaluation on your own machine. No file of AutoBio is in this repository: the tooling imports it from the image, the
instances are a seed and two hashes, and the reference solutions are control sequences recorded by running AutoBio's
experts. The robot models it bundles keep their own licences: UR5e and Robotiq 2F-85 (BSD), ALOHA 2 (BSD),
DexHand021 (Apache-2.0); the display font is under the SIL OFL. `images/autobio/BUILD_ONLY` has the details. A licence
from the authors that allows redistribution would make the image public and change nothing else.

## Changes from upstream
- **Success checks: none.** The verdict is AutoBio's own `check()` of each task module, unchanged. The physics and
  assets are AutoBio's at the pinned commit.
- **Rules of evaluation.** AutoBio's `early_stop` tasks (eight families, rule `first`) end in privileged mode at the
  first step at which `check()` holds, as AutoBio's evaluator scores them. The thermal mixer (rule `final`), whose
  `check()` is a score in [0, 1] that AutoBio reads at the end, succeeds when the score is 1 in the state the episode
  ends in. Standard episodes are agent-ended and judged by rule `final` in every family (Grading).
- **Time limits lifted.** AutoBio's limits (15 to 45 s of simulated time) are replaced by one technical cap: 600,000
  control steps (1200 s of simulated time), stated in the instructions and in `/spec` (`max_control_steps`).
- **Control rate.** One control step = one physics step, 2 ms. AutoBio evaluates policies at 50 Hz (10 physics steps per
  action), but its experts write their targets at arbitrary physics steps, so 2 ms is the rate at which an expert's
  run replays bit for bit. An agent that wants 50 Hz repeats a row ten times.
- **Mixer display.** The tooling uploads the panel drawing itself (`rcb_autobio.PanelTexture`). The helper in
  AutoBio's evaluator (`make_thermal_mixer_extra`) stops redrawing once two frames in a row find the panel unchanged,
  after which every frame shows a stale display; frames rendered here follow the panel.
- **Experts removed.** `images/autobio/strip_experts.py` deletes, from every module of the checkout, each class that
  derives from `Expert`, the `X.Expert = ...` binding and the `__main__` demonstration generator, in the same image
  layer as the clone; the build fails if a class `...Expert` is left. Everything else stays: the agent can read each
  task's scene code and `check()`.
- **Added.** Frozen instances, the privileged tooling (`rcb_autobio.Session`), and the standard-mode service.

## Interface
- **Instance.** One frozen instance per family: AutoBio's own `Task(Task.load())`, then `reset(seed)`, which draws the
  arm's start pose, the tube's rack slot, the target slot, the rotor's angle and slot, the mixer's target settings or
  the liquid volume, depending on the task. `instance.json` records the seed and two hashes, of the compiled MuJoCo
  model and of the start state; every load compares both (`instance_ok`). Each task allows seeds 0, 1 and 2, with the
  other seeds' instances and references under the privileged task's `tests/seeds/<seed>/`.
- **Action.** One position target per controlled actuator, AutoBio's own `action_indices` (the interface its policies
  use): 6 arm joints per arm plus the gripper command (Robotiq: 0 open to 255 closed; ALOHA: the finger position in m)
  or, for the pipette arm, the thumb joint that presses the plunger. Targets are clipped to the actuators' ranges.
- **Privileged mode.** `rcb_autobio.Session` in the agent's container: AutoBio's task object (`s.task`: its scene
  helpers and `check()`), the MuJoCo model and data, reset, step, recording, self-replay, the tool frames, forward and
  inverse kinematics of the arm joints, rendering (RGB and depth, every camera). Deliverable:
  `/app/output/trajectory.npz`, `(T, n)` position targets, one row per control step.
- **Standard mode** (`eai-standard/3.0`), the same adapter `environment/sim/server.py` in all nine families:
  - action types `joint_position` (the action above; rows `dt` apart, a multiple of 2 ms) and `done` (the same as
    `POST /finish`);
  - every camera of the scene at 640 × 480, depth on request: `table_cam_front` and `table_cam_left` (static) and one
    wrist camera per arm. The mixer's display is drawn into the images by AutoBio's own panel code; its digits are
    readable from the wrist camera once the gripper is near the panel. The liquid's surface is drawn by AutoBio's own
    helper;
  - proprioception = the robot's own joints (positions, velocities, efforts), gripper openings, tool-frame poses and
    the targets in effect; never a tube, rack or instrument, and no instrument state;
  - `/kinematics`: the tool frames (the gripper's pinch point; for the pipette arm, the pipette's tip) and the links the
    wrist cameras sit on, and damped-least-squares IK per arm; `robot_spec` with the arms' base poses, joint limits,
    drive gains and gripper commands;
  - one episode, no reset.
- **Looking never changes the physics.** Observations (rendering, camera poses, tool poses) are computed on a scratch
  copy of the state; nothing calls `mj_forward` on the live data. A replay with rendering ends in the same state as one
  without.
- **World-frame information.** The privileged task gives the simulator itself, world heights and MuJoCo names included.
  A standard instruction states the goal with every threshold relative ("more than a hand's width", "near the middle of
  the tube", "the row farther from the robot") and never a world coordinate, an object pose or an instrument state;
  the robot's own base poses are in `/spec` (`robot_spec.base`). `ci_checks/check-world-frame-texts.sh`
  checks the standard texts.
- **Texts.** The instructions describe each check in our own words and point to its source in the image
  (`/opt/AutoBio/autobio/<module>.py`); AutoBio's code is not quoted (no licence).

## Grading
- **The checks** (thresholds are AutoBio's; each task's README states its check exactly):

  | family | success |
  |---|---|
  | `pickup` | the tube's body above 0.925 m (9.5 cm up) while the gripper's left finger touches the cap |
  | `thermal_cycler_close` | lid hinge within 0.01 rad of -1.9 rad and lever within 0.01 rad of -0.94 rad (both start at 0) |
  | `thermal_cycler_open` | lid hinge and lever within 0.003 rad of 0 (they start at -1.9 and -0.94 rad) |
  | `pipette` | in order: plunger pressed (thumb target > 0.70 rad) with the tip within 6.5 mm of the tube's axis and > 5 mm below the liquid surface; plunger released (< 0.45 rad) with the tip still below it; then the tip > 5 cm above the surface |
  | `screw_loose` | cap > 0.15 m above the tube body's origin (screwed on: 0.1197 m), the first arm's left finger on the cap, cap thread and tube thread not in contact |
  | `screw_tighten` | cap < 0.123 m above the tube body's origin, cap axis within 5 mm of the tube's, threads in contact |
  | `insert` | tube within 15 mm (horizontally) of the target slot's centre, its height between 0.829 and 0.831 m |
  | `thermal_mixer` | final panel settings equal to the three targets (seed 0: 30 s, 33 °C, 600 rpm; from 60 s, 25 °C, 900 rpm) |
  | `insert_centrifuge_5430` | tube within 5 mm of its seated position in the slot opposite the loaded one, its height between 0.955 and 0.961 m |

- **Physics warnings.** A MuJoCo physics warning (an unstable state) ends the episode as a failure, as AutoBio's
  evaluator does, also after a success in standard mode. The renderer's own warning (`VGEOMFULL`) is not counted, so
  that looking never changes a verdict.
- **Privileged mode: one replay.** `tests/grade.py`, in a separate sandbox without network, copies the trajectory's rows
  into a clean file and replays them once in a fresh process with its own copy of the tooling and of the instance. Rule
  `first`: the replay ends at the first step at which `check()` holds; rule `final`: it is judged after the last row. A
  deliverable that cannot be read (not an npz, no `actions`, the wrong shape, more than 600,000 rows) is the agent's 0.
  A replay without a result and an instance mismatch are `grader_error` and `infra_error`. The longest episode replays
  in 1000 s in the slowest family; a verdict replay may take 2400 s, and `[verifier] timeout_sec` 5400 covers it, the
  video replay and a margin. A second replay renders `replay.mp4` after the verdict is on disk.
- **Standard mode: the live episode, agent-ended.** The agent never sees a success, and a success never ends the
  episode. The episode ends at `POST /finish` (or `done`), at the end of the agent's session, at the 600,000-step cap,
  on a physics warning (a failure) or on a simulator error (a 0). The service applies `check()` after every control
  step with rule `final` and judges the state the episode ends in. AutoBio's checks are state checks; the pipette's
  latches (the dip, then the release) count as they happened, and the final lift must hold at the end. The collect
  hook (`environment/sim/finalize.sh`) writes `final.json` from the service's record and then, after the verdict is
  on disk, replays the recorded trajectory once to render `replay.mp4`. A live episode that did not start in the
  instance's recorded state (`instance_mismatch`), a missing or unfinished `final.json`, and no `episode.json` are
  `infra_error`, not the agent's 0.

## Tasks
| family (AutoBio's task id) | AutoBio's name | robot (`robot`) | action entries | rule | reference rows (2 ms each) |
|---|---|---|---|---|---|
| `thermal_cycler_close` | Close thermal cycler lid | UR5e + 2F-85 (`ur5e-robotiq-2f85`) | 7 | first | 5068 |
| `thermal_cycler_open` | Open thermal cycler lid | UR5e + 2F-85 | 7 | first | 8251 |
| `pickup` | Pick up centrifuge tube | one ALOHA arm (`aloha-2-arm`) | 7 | first | 3945 |
| `screw_loose` | Unscrew centrifuge tube cap | two ALOHA arms (`aloha-2`) | 14 | first | 13568 |
| `pipette` | Aspirate with pipette | UR5e with a pipette-holding hand + UR5e with a 2F-85 (`ur5e-dexhand-2f85-bimanual`) | 14 | first | 6973 |
| `insert` | Transfer centrifuge tube | UR5e + 2F-85 | 7 | first | 4162 |
| `screw_tighten` | Screw on centrifuge tube cap | two ALOHA arms | 14 | first | 7638 |
| `thermal_mixer` | Operate thermal mixer panel | UR5e + 2F-85 | 7 | final | 8094 |
| `insert_centrifuge_5430` | Load centrifuge rotor | UR5e + 2F-85 | 7 | first | 4582 |

The `rule` column is the task's `[metadata] success_rule`.

- **Selection.** These are the nine tasks AutoBio's paper evaluates, and they are exactly the tasks whose `check()` is
  implemented in the repository. Left out: four task modules whose `check()` is a placeholder (`return True` or
  `return False`): the lids of the three centrifuges (`mani_centrifuge_5430.py`, `mani_centrifuge_5910.py`,
  `mani_centrifuge_mini.py`) and the vortex mixer (`mani_vortex_mixer.py`); and the rest of the paper's 16 tasks, which
  the repository does not contain.
- **Reference solutions.** AutoBio's scripted experts (`class <Task>Expert` in each task module), run from the frozen
  instance in a checkout that still has them: the targets in effect at every physics step, clipped to the actuators'
  ranges, rounded to float32 (what the standard client sends, so both modes execute the same rows) and, for rule
  `first`, cut at the first success: `solution/oracle.npz` in every task. The privileged oracle hands the rows in; the
  standard oracle streams them through the client and ends the episode with `r.finish()`. Replayed through
  `ctrl[action_indices]` alone on a task without its expert, the unrounded rows reproduce the expert's own run bit for
  bit (final state and the whole `check()` timeline), in all nine families.

## Others
### Known limits
- **The pipette task moves no liquid.** AutoBio models the liquid's surface in a container (volume, level, sloshing),
  not its transfer: the check is on the tip's position relative to the surface and on the plunger command.
- **The rotor check holds only while the tube is held, in this instance.** After AutoBio's own expert lets go, the tube
  rests 5.0 to 5.1 mm from the check's reference point, just outside its 5 mm; the check holds for 0.41 s while the
  tube is being lowered. The reference is computed at the episode's start, so a rotor turned by the agent moves the
  slot away from it. Both instructions say the tube must be pushed all the way down.
- **Contact with a named finger.** `pickup` and `screw_loose` look for contact between the cap and the first arm's
  left finger; a grasp between both fingers satisfies it.
- **`check-standard-protocol.py`** (the live conformance test) reports one false positive on the UR5e tasks:
  `placeholder_limits`, because five UR5e joints share a ±2π range. That is their range in AutoBio's model, as on the
  real arm.

### Egress
Agent egress is the model APIs and the package registries, in both modes (`[agent] network_mode = "allowlist"`). The
experts are in AutoBio's public repository and its recorded demonstrations on Hugging Face; a standard-mode agent could
also rebuild the simulator from the repository.
