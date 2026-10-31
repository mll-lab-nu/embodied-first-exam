# TactileLab

Contact-rich manipulation with tactile sensing: a dual-arm X-Trainer whose right gripper carries two GelSight Mini
sensors, on Isaac Lab 2.3.2 / Isaac Sim 5.1. The tactile image of each gel pad is geometric: a 60 x 80 taxel raycast of
the pad against the touched meshes, rendered to 240 x 320 RGB with a Taxim look-up table.

## Before you run

- **Files.** Every task's Dockerfile copies files from three public files-only images (`tactilelab-files`,
  `tactilelab-assets-files`, `tactilelab-thirdparty-files`, package `efe`), pinned by digest. Two of them hold robot and
  object files whose licence is not yet confirmed (`images/tactilelab-files/ASSET_LICENSES.md`); their source is the public
  Hugging Face dataset `MLL-Lab/embodied-first-exam-public`, pinned by commit and checked by sha256, so each image can also
  be rebuilt byte for byte (`python3 scripts/files_image.py build <name>`).
- **Licence.** The simulator image contains NVIDIA Isaac Sim 5.1 / Isaac Lab 2.3.2 (`images/tactilelab`; like
  every Isaac Sim image here it is in the private package only, and a runner without access builds the same layers from
  the recipe): building it accepts NVIDIA's Isaac Sim terms (the recipe sets `OMNI_KIT_ACCEPT_EULA=YES`).
- **GPU and driver.** An RTX-class NVIDIA GPU (the tasks' `gpu_types`; a 48 GB card for the dough tasks), an L40S
  recommended: the instances were frozen on one. The other models in `gpu_types` are being measured in the first runs;
  on a model that rebuilds a scene to another state hash a run ends as `instance_mismatch`, an infrastructure failure,
  not a result ("Frozen instance" below). Driver 580.x (the instances were frozen with 580.178.04 and CUDA 12.8; from
  driver 595 on, Isaac Sim 5.1's renderer needs a Vulkan layer that clamps one reported limit, "Frozen instance" below),
  Docker with BuildKit and the NVIDIA Container Toolkit. The first build of a task builds the simulator image (31 GB):
  70 GB of free disk.

## Tasks
| Task | Mode | What is asked |
|---|---|---|
| `tactilelab-cable-needle-thread-i00` | privileged, standard | Thread the cable tip through the square hole in the wall. |
| `tactilelab-cable-route-channel-i00` | privileged, standard | Press the cable into the channel along its length and let go. |
| `tactilelab-cable-slack-reduce-i00` | privileged, standard | Pinch the free end of the slack cable and pull it taut. |
| `tactilelab-cloth-edge-feed-i00` | privileged, standard | Pinch the overhanging cloth edge and slide the pinch along it to the corner. |
| `tactilelab-cloth-fold-half-i00` | privileged, standard | Fold the cloth in half over the fold line and let go. |
| `tactilelab-dough-fill-tray-i00` | privileged, standard | Pick the scraper from its rack and spread the dough heap evenly over the tray. |
| `tactilelab-dough-press-thickness-i00` | privileged, standard | Pinch the dough ridge to the target thickness at two places and lift the hand. |
| `tactilelab-dough-target-shape-i00` | privileged, standard | Pinch the dough bar thin at its two outer slots, keep the middle thick, and lift the hand. |
| `tactilelab-drawer-container-i00` | privileged, standard | Slide both containers into the drawer box, each to its back stop. |
| `tactilelab-fem-plug-insert-i00` | privileged, standard | Carry the soft plug from its pick socket into the press-fit hole and seat it. |
| `tactilelab-gear-mesh-i00` | privileged, standard | Slide the medium gear onto the middle post of the gear base so that it meshes with its neighbours. |
| `tactilelab-handover-i00` | privileged, standard | Hand the rod over from the right gripper to the left gripper. |
| `tactilelab-insert-hdmi-i00` | privileged, standard | Pick up the HDMI plug and insert it into the port. |
| `tactilelab-insert-tube-i00` | privileged, standard | Pull the test tube out of its rack and insert it into the inclined bore of the tube slot. |
| `tactilelab-lamp-bulb-i00` | privileged, standard | Seat the bulb in the lamp base's socket and the hood on top. |
| `tactilelab-lift-i00` | privileged, standard | Pick up the lying bottle, set it down on the green pad at its standing height and let go. |
| `tactilelab-nut-thread-i00` | privileged, standard | Turn the M16 nut further down the fixed bolt and let go. |
| `tactilelab-one-leg-i00` | privileged, standard | Insert one square-table leg into a corner bore of the fixed table top and leave it seated. |
| `tactilelab-sleeve-pull-on-forearm-i00` | privileged, standard | Pull the sleeve along the other arm's forearm to the target band. |
| `tactilelab-square-table-i00` | privileged, standard | Insert all four legs into the four corner bores of the fixed table top and leave them seated. |

## Conventions (all tasks)
- Env frame, metres, z up; quaternions WXYZ. Table top z = 1.102, robot base at (-0.5, 0, 1.1) facing +x.
- Action row (22): right / left end-effector targets (7 each), right / left gripper command (0 open, 1 closed), optional
  right / left finger-gap override, optional right finger drive settings (velocity limit, effort limit, stiffness,
  damping); NaN = unused / hold. 60 Hz control. A release of the right gripper is physical (an open command after a close,
  once the fingers have opened 10 mm). The standard twin takes the same row as `ee_pose` (22) with sentinels where the
  privileged row has NaN (the protocol refuses NaN): an all-zero quaternion holds that arm, a negative gap is no override,
  a drive setting <= 0 is unchanged; its recorded trajectory is the privileged format. Both modes refuse the same rows
  (`rcb_tactilelab.rows_problem`: 400 in standard, `bad_trajectory` in privileged): a gripper command other than 0 or 1,
  an arm whose seven numbers are neither all NaN nor all finite, a target outside +-2 m of the robot base on some axis, a
  zero-length quaternion, a drive setting out of its range, a number too large for a float32.
- Finger drive (columns 18-21): the stock drive is 0.2 m/s, 20 N, 200 N/m and 40 N s/m; accepted values are in (0, 0.2],
  (0, 20], (0, 10,000] and (0, 1,000] (NaN, or <= 0 in standard, is unchanged). A value outside these ranges, or any
  number too large for a float32, is refused: 400 in standard, `bad_trajectory` in privileged. A restore of the stock
  drive (the scripted skills' `restore_finger_limits`) is recorded as the explicit stock values. The settings take effect
  in the eight rigid assembly tasks (drawer_container, gear_mesh, insert_hdmi, insert_tube, lamp_bulb, nut_thread,
  one_leg, square_table); in the other twelve they are checked and recorded only, and each instruction says which.
- Cameras: two wrist cameras, 640 x 480 RGB and z-depth, pinhole with square pixels and the principal point at the image
  centre; the default lens is focal 1.277 mm over a 20.955 mm aperture, 166.1 x 161.5 degrees (fx = fy = 39.0 px). A
  render may ask for a narrower horizontal field of view, 30 degrees up to that default: a second camera at the same
  mount (same aperture and resolution, that focal length; fx = fy = 320 / tan(hfov / 2)) renders it, so the wrist
  camera itself never changes; that second camera renders from the first request on (later renders get slightly
  slower). Privileged:
  `s.render_frame("wrist_right_rgb", hfov_deg=90)`, its matrix `s.camera_intrinsics("wrist_right_rgb", hfov_deg=90)`.
  Standard: the camera name `wrist_right@90` (or `wrist_left@<deg>`; one per wrist camera and call) in a call's
  `cameras`; that image, its depth, its extrinsics and (with `calibration_in_obs`) its `intrinsic_cv` come back under
  that name, and `spec.cameras.<cam>.field_of_view` states the default, the range and the rule. Without the parameter
  every image is the default lens's. A render never steps physics or changes the state. The two tactile images
  (240 x 320 RGB) are not pinhole cameras.
- Multi-part tasks judge their grasp and clearance checks on the first part (`JUDGED_PART`); `set_active_part` changes
  only which part the scripted accessors address, never the judgement, so a live run and its replay agree.
- World-frame information: the privileged instructions give the scene (object names, rough positions, annotation files)
  and the tooling reads every pose. The standard texts give no world coordinates of workspace items: only the frame
  conventions, the robot base pose and the items' sizes and masses (docs/protocol/standard_mode.md
  §10).
- Frozen instance (PROTOCOL §2): `instance.json` holds the task, the seed, the physics device and the hash of the full
  scene state after reset (robot, rigid objects, the deformable body's particles). A rebuilt scene must reproduce that
  hash exactly, in both modes; another hash is `instance_mismatch` (infrastructure, no verdict). Physics is PhysX on the
  GPU, as the tasks were developed, and the reset settles on it: the hashes are exact on the GPU model the instances were
  frozen on, an L40S. `gpu_types` lists every RTX-class model on purpose: the first runs measure whether the other
  models rebuild the instances exactly (only the L40S is known to), and a run on one that does not ends as
  `instance_mismatch` (no verdict). `instance.json` records the GPU, driver and CUDA version it was frozen on
  (`frozen_on`); every privileged grade records each replay's (`/logs/verifier/hosts.json`, beside `frozen_on`) and
  every standard episode the service's (`instance_host` in its `final.json`), so the mismatch rate per GPU model and
  driver can be read off the runs. Newer drivers: from the 595 branch on, NVIDIA drivers report
  `maxMemoryAllocationSize` (`VkPhysicalDeviceMaintenance3Properties`) as 2^64 - 1; Isaac Sim 5.1's RTX scene database
  keeps a limit derived from it in 32 bits, which overflows, and Kit crashes while the renderer starts. A Vulkan
  implicit layer that clamps that one reported value to 4,292,870,144 (what driver 580 reports) lets it start; it
  changes no allocation, physics or rendering. Such a layer is not part of NVIDIA's software, the images or this
  benchmark: it is a small implicit layer (a manifest and a library that wraps `vkGetPhysicalDeviceProperties2` and
  lowers that one field) that the maintainers wrote for their own hosts on such drivers; a runner on such a driver
  installs one like it on the host, or uses driver 580.x. With such a layer on a newer driver branch, lift, gear_mesh,
  cloth_fold_half and dough_fill_tray rebuilt their instances exactly on an L40S, and a 30-row hold ended in the same
  state hash as on driver 580.178.04.
- Budget: none but the agent's wall clock. One technical episode cap per task, `rcb_tactilelab.max_control_steps` =
  `max_rows` + the 60-step hold: a trajectory holds at most `max_rows` rows, 30,000, or 4,800 for the tasks with a
  deformable body (they step at 1-4 control steps/s; an 80 s trajectory is about twice the longest reference
  demonstration), and its replay adds the hold. The standard twin's `spec.max_control_steps` is the same number: the
  agent's rows stop after `max_rows` - 60 control steps (holds included), the final hold brings the episode to at most
  `max_control_steps`, and its recorded trajectory (the rows before that final hold, which a replay's settle repeats)
  stays within `max_rows`, so the privileged CLI replays it.
- Modes: privileged and standard. No standard-realtime twins: the tasks are static (nothing moves until the robot moves
  it), and the simulator steps at 1-23 control steps per second, below the 60 Hz control rate a real-time clock would
  need it to keep.

## Grading
- Privileged, the task's declared grading kind (PROTOCOL §2): two fresh-process replays of the trajectory that must both
  succeed and end in the same final-state hash (rigid tasks; cloth, cables and the soft plug: the Newton sidecar runs
  Warp's run-to-run deterministic atomics and sorted contacts). The dough tasks are graded on one fresh-process replay
  (`replays` = 1, `determinism_checked` = 0, as RoboDojo's one-replay tasks): their implicit MPM solver runs without the
  deterministic atomics (they made it far too slow) and is not guaranteed to replay bit for bit.
- Replay time: each replay has `rcb_tactilelab.replay_limit_s(task, rows)` = 1200 s + 2 x the rows over the task's
  slowest measured replay pace (control steps/s, `TASK_LIMITS`), a limit, not a measured time; the grade records the rows
  a replay completed and its pace (`replay_rows_done`, `replay_pace`). The pace is the slower of the oracle's grading replays and a stress replay (the
  oracle's rows with the right wrist 3 cm lower, pressed into the objects and the table, a +-3 cm random walk on both
  wrists and the finger drive at its maxima; four replays sharing two GPUs on a loaded host). The stress replays ran up
  to 2.2 x slower than the oracle's (cloth_edge_feed), so the factor 2 is taken over the slower of the two. The oracle's
  own replays run at 1.7-23 control steps/s (each standard instruction quotes its task's). The verifier's `timeout_sec`
  covers the replays, one retry and the video at the row cap.
- Whose failure a 0 is (privileged, `tests/grade.py`; what the agent's rows cause is a result, never infrastructure,
  docs/protocol/running.md and PROTOCOL H.5). From the first trajectory row on, the agent's 0 at once (`sim_error`): an
  exception the simulator raises or an error the soft-body solver reports, unless it is one of the host's kinds
  (`rcb_tactilelab.HOST_FAULT`: CUDA, Warp, PhysX or torch errors, out of memory, a lost device, an OS error). Those, a
  replay process that dies of its own signal or exits without a verdict (SIGSEGV, SIGABRT, ...; `replay_crashed`,
  `replay_signal`; Isaac Sim's crash handler can catch the signal and leave the process hanging, which then runs out of
  its time), a replay that runs out of its time limit (`replay_timed_out`) and a Newton sidecar that dies or stops
  answering (`sidecar_failed`) are run once more in a fresh process (`replay_retried`, once per trial). Such a failure
  is the agent's 0 (`replay_reproduced`) only when (1) the retry, or a later replay, fails the same way, at about the
  same control step (the kinds may differ); (2) a reference replay of the frozen scene (240 held rows) completes without
  a failure at no less than a quarter of the task's reference pace measured on an L40S (`reference_pace`,
  `reference_ok`, `host_slowdown` = the L40S reference pace / the pace here); (3) for a time-out, the replay's pace
  scaled by `host_slowdown` is below 1.25 x the pace the time limit allows (`replay_norm_pace`; a host that is merely
  slow does not cost the agent its trial); and (4) no other replay of the trajectory got past it (`replay_contradicted`:
  none completed, unless every failure compared is a time-out and that replay was itself that slow, and none failed
  later). Infrastructure, no verdict: a failure before the first row (Isaac start, scene build, the instance check), a
  replay process killed from outside (SIGKILL, SIGTERM: an OOM kill, an operator; `replay_killed`; the verifier cgroup's
  OOM kills are recorded, `replay_oom_kills`), and a retried failure that is not reproduced. A `kill -9 -1` collect hook
  on the agent's container ends every process the agent left before the verifier runs. The video is rendered in one more
  replay after the verdict is written, filmed by a fixed third-person camera that is no observation.
- Standard: graded by the live episode (docs/protocol/standard_mode.md). After every control step at which the task's
  success condition is reached, the last command is held for 60 control steps inside the same call (recorded and
  returned like any other steps) and the task judged: solved ends the episode in success; otherwise the next step at
  which the condition is reached, 60 or more control steps after the last hold, starts another (so a condition that
  flickers, or a latch whose end check fails, never turns most of a call into holds). For the latching tasks (the rigid ones, lift, handover, dough and
  the soft plug) the condition stays reached, so the hold's judgement fails only if the task truncates during it. At the
  time limit and at the episode cap the same 60-step hold runs in full before the judgement; it runs as the pseudo-call
  `/end` when no call is open, so a crash in it counts as inside the agent's last call (docs/protocol/running.md); an
  exception during that hold ends the episode with reason `error`, score 0. A task's own early failure (its truncation) ends the episode, reason `failed`. A call cut
  short (its wall-clock limit, a client disconnect) keeps the targets of the last step it executed. The collect signal
  refuses every later request before the final hold (PROTOCOL H.4). A host fault (a Newton sidecar that dies or stops
  answering, or a GPU or host error of the kinds above raised in a step or reported by the soft-body solver) is the
  host's the first time in an episode, in a call, a hold or a resume: the service closes the call in flight as the
  host's (`host_fault`, so the crash never counts as the agent's `crashed_in_call`), exits non-zero, compose restarts it
  and the episode resumes from its journal. A later one in the same episode is the rows' when the host passes a health
  check (the GPU answers, computes a matrix product and has 2 GiB free): the episode ends with reason `error`
  (`sidecar_error` or `gpu_error`, score 0; during a resume, a give-up with that reason). When the check fails, and for
  a fault during a resume at a step the episode had passed before, it is the host's again: another resume, and a host
  that keeps failing ends the episode as `sim_crashed` (infrastructure). A fault while the scene is built is always the
  host's. The video is filmed live (a fixed third-person camera that is no observation, the two tactile images in its
  corner, every 12 control steps; the privileged video replay films the same camera). Crash
  recovery resumes the episode from its journal: class `exact`, `approx` for the dough tasks.
- Tooling: `rcb_tactilelab.py` and the standard service `sim/` (`embodied_first_exam/benchmarks/tactilelab/`), with the
  `tactilelab_tasks` package as the agent may read it (scripted policies and expert parameters removed); all come from the
  files-only image `tactilelab-files`. The files over 2 MB come from the data-only image `tactilelab-assets-files`, the
  third-party files whose licence is not confirmed from the data-only image `tactilelab-thirdparty-files` (not in git).
  Sources and licences: `images/tactilelab-files/ASSET_LICENSES.md`.

## Budget
3600 s per task, both modes. Every Python process pays about 1 min of Isaac Sim launch and scene build (the Newton
sidecar's first start compiles its GPU kernels, a few minutes once per trial).

Standard service startup (Isaac launch, scene build, sidecar start, the instance check), measured on L40S hosts from
`startups.jsonl` to the episode's start event, six trials sharing two GPUs on a loaded host: 286-478 s over 49 startups
of the 20 families (sleeve_pull_on_forearm the slowest, 419-478 s; the rigid tasks 286-332 s; earlier builds of the same
services up to 508 s). `RCB_STARTUP_TIMEOUT_S` = 1800 s for every task, more than twice the slowest. The collect hook
ends the episode within `RCB_COLLECT_END_TIMEOUT_S` = `rcb_tactilelab.collect_end_s(task)`, the time a grading replay of
the longest episode gets (a resume at collect time replays the journal at the task's pace: 6,819 s for gear_mesh, 10,370
s for sleeve_pull_on_forearm), and the hook's `timeout_sec` adds the video encode (600 s) and 300 s.
