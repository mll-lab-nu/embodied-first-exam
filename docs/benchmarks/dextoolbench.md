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
