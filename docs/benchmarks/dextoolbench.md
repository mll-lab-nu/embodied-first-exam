# DexToolBench

Twenty-one tasks of DexToolBench (SimToolReal, MIT) in plain MuJoCo 3.3.7, in both modes: 42 task directories,
`tasks/dextoolbench/dextoolbench_<category>_<object>_<task>-{privileged,standard}`. A KUKA iiwa 14 arm with a 22-joint Sharpa HA4
hand (29 position-controlled joints, 60 Hz control) must pick a tool up from a table and carry it through a human
demonstration's goal poses in order; a goal counts when all 8 corners of the tool's grasp box are within 1.5 cm of the
goal's, and the task passes only when every goal is reached. The scene, tooling (`rcb_dtb.py`) and the oracle rules are
in the privileged tasks' READMEs. Three demonstrations of the 24 are excluded, because the reference policy reaches no goal in this scene: `blue_brush/sweep_right`, `flat_eraser/wipe_c` and `flat_eraser/wipe_smile`.

The task directories are the deliverable; the tooling that built them is kept outside this repository. The standard
twins share `images/mujoco/limited/server_mj.py` with the MuJoCo Playground ALOHA and Panda twins
(docs/benchmarks/mujoco-playground.md); `ci_checks/check-tooling-identity.sh` holds the task copies together.

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
| standard (`eai-standard/2.1`) | the robot's cameras (RGB-D, calibrated) and proprioception, the current goal pose, through `rcb_client.py` | **20**; `RCB_RESET_BUDGET=0`: none | none (episode cap 360,000 control steps) | the last episode as it ran (live) |

Both modes give the agent 60 minutes (PROTOCOL §2, docs/protocol/running.md "The agent's time").

## Resets in standard mode
`POST /reset` (`r.reset()`) abandons the running episode and starts a new one from the frozen start: the robot at its
home pose, the tool at its start pose, goal 1 current (`Session.reset()`). At most 20 times; only the last episode is
graded, a success ends the trial, and once the agent's time is up no reset is accepted. The clock keeps running.
`meta` and `/status` carry `episode`, `resets_left` and `control_steps_total`; `final.json` and the verifier's
`reward.json` record `resets` and `reset_budget`. Why 20: with one episode the first grasp decided the trial (a tool
knocked off the table took most of the hour to recover). After every reset the state hash, all four cameras' RGB and
depth images, the proprioception and the task info equal the start's. Results with another reset budget are reported separately.

## Grading in standard mode
The verdict is the live episode's (`graded_by = "live"`, `replays = 0`). `server_mj.py`'s goal tracker
(`rcb_dtb.Session._track`) runs on every control step the service executes: a goal counts when the tool's keypoints are
within 1.5 cm of it (`SUCCESS_TOL_M`), then the next one is current; the episode ends when the last goal is reached
(`reason = "all goals reached"`, success), at the cap, or when the agent's time is up. When it ends, `finalize()` reads
the tracker off the live simulator: success (`reward.txt`) = every goal reached; `progress` in `reward.json` = goals
reached / goals. The privileged verifier's replay runs the same rows through the same tracker with the same thresholds,
so both modes apply one rule (H.7); there is no settle window after the last goal in either mode.
- **Video:** `replay.mp4`, one render pass over the trajectory on the service's own simulator after the verdict
  (`video_pending` while it renders; EGL on the sidecar's GPU). The collect hook waits up to 840 s for the verdict (a
  service that crashed late in a long episode resumes it from the journal first: 400-800 s for 200,000 steps) and until
  1680 s for the video.
- **Start state:** the instances record no state hash, so the compose file carries `RCB_START_SHA`, the hash
  (`Session.state_sha()`, qpos and qvel at the frozen start) every recorded episode of the task started from.
  A fresh episode on another start is refused before the agent is served
  (`instance_mismatch`, `infra_error = 1`). Re-measure the hashes when the tooling, an instance or the image changes.
- **Infrastructure:** a missing, unreadable or unfinalized `final.json`, a give-up after crashes between calls or a
  failed resume (`sim_crashed`, `resume_failed`), `instance_mismatch`, a failure writing the verdict (`finalize_error`).
  Crashes all inside the agent's calls (`sim_crashed_on_call`) and a simulator error from a call (`sim_error`) are the
  agent's 0; a failed video is only a missing video.

## Standard-mode service details

**MuJoCo service (DexToolBench, MuJoCo Playground manipulation; `eai-standard/2.1`).** Same endpoints and RCB1 frames,
served by `images/mujoco/limited/server_mj.py`. Differences: one action type, `joint_position` with the task's own
actuator layout (DexToolBench 29, ALOHA 14, Panda 8), rows `dt` apart where `dt` is a multiple of `control_dt` (1/60 s
DexToolBench, 1/50 s Playground), hold or linear interpolation per control step. Actions are sent as **float64** (MuJoCo
on CPU replays bit-exactly, and float32 rounding changes a chaotic tool swing). `meta.task` carries the task definition
(DexToolBench: current goal pose and index; Playground: the target) and `meta.cameras` each camera's intrinsics
(`intrinsic_cv` for the returned image; fx = fy for a camera defined by its field of view, fx ≠ fy for one defined by its
sensor size: ALOHA's overhead and wrist cameras, 158.52 and 216.45 px) and camera-to-world pose: the viewpoint the
image is rendered from, in the state the response ends in. Cameras carry `moving` (true for ALOHA's wrist cameras).
`final.json` is `finalized` as soon as the live episode's verdict is in it; the video is rendered afterwards and sets
`video_done`, which is what the collect hook waits for (the MetaWorld+ service, `images/metaworld/standard/server_mw.py`,
follows the same rules). DexToolBench's own eval gives each goal 10 s; here the standard twins have **no per-goal
limit** and **20 resets** and an episode cap of 360,000 control steps (100 min of robot time, `spec.max_control_steps`),
while the privileged tasks give each goal 30 s (replayed offline, free resets). DexToolBench episodes end when all goals
are reached, at the cap, or when the agent's time is up; Playground episodes run to the end of the agent phase and the
final state is graded. The service journals and resumes like the shared layer (journal `record.f64`; startup watchdog
`RCB_STARTUP_TIMEOUT_S`, default 300 s), grades the live episode (Grading in standard mode, above) and implements the
optional reset capability.
