# DexToolBench

Twenty-one tasks of DexToolBench (SimToolReal, MIT) in plain MuJoCo 3.3.7, in both modes: 42 task directories,
`tasks/dextoolbench_<category>_<object>_<task>-{privileged,standard}`. A KUKA iiwa 14 arm with a 22-joint Sharpa HA4
hand (29 position-controlled joints, 60 Hz control) must pick a tool up from a table and carry it through a human
demonstration's goal poses in order; a goal counts when all 8 corners of the tool's grasp box are within 1.5 cm of the
goal's, and the task passes only when every goal is reached. The scene, tooling (`rcb_dtb.py`) and the oracle rules are
in the privileged tasks' READMEs. Three demonstrations of the 24 are excluded (the top-level README says why).

Generators: `scripts/dtb_mk_task.py` (privileged), `scripts/dtb_mk_oracle.py` (the oracles), `scripts/mj_mk_limited.py`
(the standard twins, which share `images/mujoco/limited/server_mj.py` with the MuJoCo Playground ALOHA and Panda twins;
docs/benchmarks/mujoco-playground.md has that service's change log). None has a check mode:
`ci_checks/check-tooling-identity.sh` holds their copies together.

## Tasks
| category | object | task | goals | oracle |
|---|---|---|---|---|
| brush | blue_brush | sweep_forward | 34 | partial |
| brush | red_brush | sweep_forward | 38 | partial |
| brush | red_brush | sweep_right | 38 | partial |
| eraser | handle_eraser | wipe_c | 31 | partial |
| eraser | handle_eraser | wipe_smile | 29 | full |
| hammer | claw_hammer | swing_down | 37 | full |
| hammer | claw_hammer | swing_side | 40 | partial |
| hammer | mallet_hammer | swing_down | 36 | partial |
| hammer | mallet_hammer | swing_side | 32 | partial |
| marker | sharpie_marker | draw_smile | 36 | full |
| marker | sharpie_marker | write_c | 25 | full |
| marker | staples_marker | draw_smile | 49 | full |
| marker | staples_marker | write_c | 29 | partial |
| screwdriver | long_screwdriver | spin_horizontal | 31 | full |
| screwdriver | long_screwdriver | spin_vertical | 100 | partial |
| screwdriver | short_screwdriver | spin_horizontal | 38 | partial |
| screwdriver | short_screwdriver | spin_vertical | 76 | partial |
| spatula | flat_spatula | flip_over | 45 | partial |
| spatula | flat_spatula | serve_plate | 33 | partial |
| spatula | spoon_spatula | flip_over | 40 | partial |
| spatula | spoon_spatula | serve_plate | 48 | partial |

`partial`: SimToolReal's pretrained policy, replayed in this scene, reaches only some of the goals (each privileged
README gives the count); `full`: it reaches all of them.

## Modes
| mode | the agent gets | resets | per-goal time limit | graded |
|---|---|---|---|---|
| privileged | the tooling (`rcb_dtb.Session`), the full state, free resets | unlimited | 30 s | the handed-in trajectory, replayed from the start |
| standard (`eai-standard/2.1`) | the robot's cameras (RGB-D, calibrated) and proprioception, the current goal pose, through `rcb_client.py` | **20** (owner, 2026-10-13; PROTOCOL §4.5); `RCB_RESET_BUDGET=0`: none | none (episode cap 360,000 control steps) | the last episode, replayed in a fresh simulator |

Both modes give the agent 60 minutes (docs/CUTOFFS.md).

## Resets in standard mode (owner, 2026-10-13)
`POST /reset` (`r.reset()`) abandons the running episode and starts a new one from the frozen start: the robot at its
home pose, the tool at its start pose, goal 1 current (`Session.reset()`). At most 20 times; only the last episode is
graded, a success ends the trial, and once the agent's time is up no reset is accepted. The clock keeps running.
`meta` and `/status` carry `episode`, `resets_left` and `control_steps_total`; `final.json` and the verifier's
`reward.json` record `resets` and `reset_budget`.

Why: until then a trial was one episode, and the first grasp decided it. All 21 of GPT-6 Astra's standard trials
(2026-10-12, run `codex-gpt6_astra-high`) knocked the tool off the table at some point, the one success included; most
of the hour then went into picking the tool up from the floor, and the same task gave unrelated results from one run to
the next (the task that reached 29/37 before the calibration fix reached 0 after it, one that reached 0 succeeded;
board 0098). A dropped tool says little about the controller that would follow, so the owner granted 20 resets.

Checked (2026-10-13, `eai-mujoco:0.1.2`, CPU / OSMesa, `hammer_claw_hammer_swing_down-standard`): after every reset
the state hash, all four cameras' RGB and depth images, the proprioception and the task info equal the start's; three
resets after random sweeps, then the oracle in episode 4: 37/37, deterministic, graded 1 (`resets = 3`); a reset after
the success is refused; episode 1 at 60 % of the oracle, then 20 resets, a 21st refused (409 "reset budget exhausted"),
nothing in the last episode: graded 0. The service's unit tests (`scripts/mujoco-playground/tests/test_standard_2_1_servers.py`)
cover the budget, the 404 without one, crash recovery across resets and the refusal after the time is up.

Results: standard results recorded before 2026-10-13 ran with no reset and are reported separately, never ranked with
the 20-reset ones (PROTOCOL D1, §4.5). Privileged mode is unchanged (it always had free resets).

## Change log
- 2026-10-13 (owner decision, board 0099): standard tasks grant 20 resets (above). `server_mj.py` gained the reset
  capability, the client `reset()`, the compose files `RCB_RESET_BUDGET` (default 20), the instruction its rules. The
  scene, instances, physics, pass rule and oracles are unchanged, so the tasks keep their names; each standard task's
  README has the entry.
- Earlier changes to the standard twins' service (calibration, request checks, crash recovery, intrinsics; 2026-10-10
  to 2026-10-13) are in docs/benchmarks/mujoco-playground.md's change log and each task's README.

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

**MuJoCo service (DexToolBench, MuJoCo Playground manipulation; `eai-standard/2.1`).** Same endpoints and RCB1 frames,
served by `images/mujoco/limited/server_mj.py`. Differences: one action type, `joint_position` with the task's own
actuator layout (DexToolBench 29, ALOHA 14, Panda 8), rows `dt` apart where `dt` is a multiple of `control_dt` (1/60 s
DexToolBench, 1/50 s Playground), hold or linear interpolation per control step. Actions are sent as **float64** (MuJoCo
on CPU replays bit-exactly, and float32 rounding changes a chaotic tool swing). `meta.task` carries the task definition
(DexToolBench: current goal pose and index; Playground: the target) and `meta.cameras` each camera's intrinsics
(`intrinsic_cv` for the returned image; fx = fy for a camera defined by its field of view, fx ≠ fy for one defined by its
sensor size: ALOHA's overhead and wrist cameras, 158.52 and 216.45 px; until 2026-10-13 the service reported
fx = fy = 216.45 for them) and camera-to-world pose: the viewpoint the image is rendered from, in the state the response
ends in (until 2026-10-10 the position was MuJoCo's left-eye camera, 3.4 cm to the side, and the pose was the one at
service start). Cameras carry `moving` (true for ALOHA's wrist cameras). `final.json` is `finalized` as soon as the
replay's verdict is in it; the video is rendered afterwards and sets `video_done`, which is what the collect hook waits
for (the MetaWorld+ service, `images/metaworld/standard/server_mw.py`, follows the same rules). DexToolBench's own eval
gives each goal 10 s; here the standard twins have **no per-goal limit** and **20 resets** (owner, 2026-10-13: the
optional reset capability; until then one episode, no reset) and an episode cap of 360,000 control steps (100 min of
robot time, `spec.max_control_steps`), while the privileged tasks give each goal 30 s (replayed offline, free resets).
DexToolBench episodes end when all goals are reached, at the cap, or when the agent's time is up; Playground episodes
run to the end of the agent phase and the final state is graded. The service journals and resumes like the shared
layer (journal `record.f64`; startup watchdog `RCB_STARTUP_TIMEOUT_S`, default 300 s) and replays the recorded episode
in a fresh simulator at the end (`deterministic`: same final state hash). It implements the optional reset capability.
