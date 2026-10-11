# robotangle-interlocked-claws-medium-i00-standard

| | |
|---|---|
| Benchmark | RoboTangle |
| Mode | standard (`eai-standard/2.4`) |
| Twin | `robotangle-interlocked-claws-medium-i00-privileged` |
| Simulator / robot | `robotangle` / `aloha-2` |
| Family / instance | `interlocked_claws` / seed 0 |
| Oracle | `full` |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robotangle:0.2.22` |

## Task
Standard-mode twin of `robotangle-interlocked-claws-medium-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.4` client
(docs/STANDARD_MODE.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `robotangle-interlocked-claws-medium-i00-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/solve.sh` streams the recorded rows of the author's standard-mode oracle episode (`solution/oracle_qpos.npy`, one `joint_position` row per 25 ms control step, `hold`) through the client (`solution/oracle_replay.py`). That episode scored 1 (live and fresh replay) on merged-v18 (source 5b5677f0, tooling a9d09d66; lab run 20261006T045807-74727). This family's task, geometry and asset files are unchanged from that build to this release; the shared simulator, tooling, graders and sim service changed only in paths that do not act on this family's scene (the cloth particle speed, a constraint solver chosen by name, the generated PBD birth state of dev/jianwen 2dafa5f2b), apart from the new report fields `initial_state_generated` and `initial_state`. The oracle was not re-run on this build (docs/benchmarks/robotangle.md, Evidence).

## Verification
See `tests/grade.py`.

`nop` scored 0 on this base in both modes on the merged-v18 candidate build (lab `align_v18/cand_v18`, the pipeline's Harbor nop checks, 2026-10-05; frozen instance state identical); not yet re-run on this build.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 7 GB | 6 GB |
| GPU memory | 7 GB | 7 GB |

- GPU: required, any NVIDIA GPU; recommended: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).
- Measured: GPU 5.9 GB on L4, 10.3 GB on L40S, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 4.0 GB, privileged container 4.6 GB, verifier p90 3.9 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 21 GiB memory. Limits measured: GPU: 10.3 GiB on a 48 GB card, 5.9 on 24 GB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: no samples of the agent's container; floor 8 GiB (at most the 16 GiB cap); whole trial: + the sim service's 13 GiB (docker peak 8.4 GiB, 47 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details

### Goal
Completely separate the two claw pieces and briefly hold both still.

### Success requirements
- Leave at least 10 mm between the complete pieces, with a plane separating all of their geometry; a gap inside the interlock is insufficient.
- Keep both pieces' linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding both pieces is allowed; release and transport into the green region are not required.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Finger contact with a held movable piece may penetrate at most 2 mm; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand. All other task contacts, including piece-piece, table, arm and gripper-housing contacts, may penetrate at most 1 mm. Exceeding either limit ends the episode in failure.

### Grader details (in addition to the requirements above)
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 412.2 mm x 412.2 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The other claw piece is free to move (its speed is not checked), but no point of it may cross that plane.
- Contact penetration as this benchmark grades it (it replaces the "at most 1 mm / 2 mm" wording above): penetration is recorded, it never ends the episode by itself. A success with deep interpenetration (a task contact deeper than 3 mm, or deeper than 1 mm for at least 0.25 s: 100 consecutive physics ticks; for a finger contact with a held piece 4 mm, or 2 mm for 0.25 s) is not credited automatically but reviewed, with the recorded evidence and frames; a clean success is credited automatically. A task contact deeper than 10 mm is a simulator breakdown (below).
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step). "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active assisted grasp), the other finger is back at the non-held limits in the same tick.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`meta["safety"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a non-finite state or a task contact deeper than 10 mm): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): piece_0: radius 30 mm; piece_1: radius 30 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.4`: `submit` chunks of `joint_position` (14, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; the state hashes are reported, not required (GPU physics is not bit-deterministic; the CPU rigid families' is, on one host); `/logs/verifier/replay.mp4` is rendered during that replay |
| crash recovery | `eai-standard/2.4` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |

### Provenance
- Frozen instance: built by TopoGym source `5b5677f0` (graded package `align_v18/cand_v18b/tasks/topogym-interlocked-claws-medium-i00-privileged` on the lab host); bound to this release's runtime (source `ecb43962`, tooling `c80aa5a9`). An exact-restore preflight on this build is pending (docs/benchmarks/robotangle.md, Pending).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `8ad7ffd309c9`, under `instances/interlocked-claws-medium-i00/` (scripts/robotangle/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/jianwen `2dafa5f2b` (task templates `2dafa5f2b`), image `ghcr.io/mll-lab-nu/eai-robotangle:0.2.22` (images/robotangle/).
- Name: RoboTangle is the published name of TopoGym (2026-10-07). Code identifiers keep the old name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-08: base image 0.2.19 -> 0.2.21, now public. The simulator, the frozen instances and the audited libuipc wheel are unchanged: on compute capability 8.9 and 12.x (e.g. RTX 4090, L40S, RTX PRO 6000) the physics runs the same libuipc code as before. New: the NVIDIA Vulkan ICD and EGL vendor files, and a second libuipc build of the audited recipe for compute capability 8.6 (RTX A6000 class), which the tooling selects at Session start on every other GPU, so knot_untying and rope_threading run there too. The runtime binding names both builds, and the tooling hash changes with the selection. The compose files reserve one GPU without `runtime: nvidia`, which with the image's NVIDIA_VISIBLE_DEVICES=all could expose every GPU (Nyx needs exactly one). The standard grader counts a fresh replay that crashed without writing its verdict (e.g. CUDA out of memory) as a grader error; it counted as instance_mismatch. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-08 (2): the instance now also starts on a CPU of another instruction-set class. The asset generators run on numpy and OpenBLAS, whose SIMD kernels depend on the CPU: on a host without AVX-512 (e.g. AWS L4 / L40S instances) the pinned generator writes the frozen asset files with other bytes (floating-point noise up to 1e-8 m, face order), and the Session refused the instance (IPC and stored PBD states also refused their archive). Such a host now realizes the frozen recipe (`instance_realized`): the same asset files from the generator the runtime binding pins, archives that differ from this scene only in those bytes, and the frozen state, exactly or within the pose tolerance; the live episode and the fresh replay realize it alike. The graders and the sim service record `instance_realized` and `assets_exact`. A host that reproduces the frozen bytes runs exactly as before. The tooling hash changes; the image, scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-08 (3): base image 0.2.21 -> 0.2.22. The image adds, for the eight IPC instances (knot_untying, rope_threading), the rope volume mesh each was frozen with (`instance_assets/frozen_assets/rope_volume.npz`, the sha256 its asset identity records), and the tooling uses it instead of regenerating it: tetgen's interior points depend on the CPU's floating-point rounding, and on CPUs without AVX-512 knot_untying medium and hard got another mesh, which their frozen settled state does not fit. Nothing else in the image changes. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-10 (review fixes): the sim service and its 2.4 layer; the pass rule is unchanged. Malformed request fields (null or non-numeric `dt`, `video_fps`, `seconds`; a non-string `note`; `cameras` that is not a list of names) get a 400 before anything executes; they ended the episode with a 500 booked as an infrastructure error, a bad `note` after its chunk had run. A crash during a call is resumed like any other crash; the restart ended the episode as `call_watchdog` whenever it came back after the call's deadline, and now does so only when the watchdog's own output shows that it fired. After a crash in the first call the tick ledger is cut with the journal. An instance this host cannot reconstruct is `infra_error` 1 (startup record, replay, grader), and the startup record is final at once instead of after the collect hook's timeout. final.json is written as soon as the replay's verdict is committed, before the video is closed and the review frames are rendered. A live failure whose replay crashed is the agent's 0, not a grader error. The instruction's "Time per call" describes 2.4 (`max_call_wall_s`, `r.operation_status()`, 408 / 409), and the 200000-step runaway guard (`step_guard`) is stated there and in `/spec` (`max_control_steps`). The image, scene and frozen instance are unchanged, so the task keeps its name.
- 2026-10-10 (2): `tests/grade.py`: after a live success, a replay process that died without a result (e.g. CUDA out of memory in the collect hook) is `infra_error` 1 together with `grader_error` 1; it was `grader_error` 1 with `infra_error` 0, which a reader of `infra_error` alone (PROTOCOL §2.6) took for the agent's 0. A `final.json` that is not a JSON object is `infra_error` 1 (it left no reward). Reward 0 in both cases, as before; the pass rule is unchanged, so the task keeps its name.
- 2026-10-10 (review round 2): the sim service, the client and the texts; the pass rule is unchanged. A request field holding a JSON integer beyond the float range (`dt`, `video_fps`, `seconds`) gets a 400 and moves nothing; it ended the episode with a 500 booked as an infrastructure error. The proprio group `gripper_opening` is now the measured gap between the finger pads in metres (`Session.gripper_width`); it repeated the gripper's native drive coordinate (the finger rail position, m) under a description that called it an opening. `/spec` now describes the gripper entries of `joint_pos` and `joint_vel` as that drive coordinate. The Rules said that internal measurements are not exposed, while the instruction documents the safety readings of `meta["safety"]`; the sentence now says so (what is exposed is unchanged). The client's `Robot()` waits up to 3600 s for the service (600 s before) and prints its progress, and `cameras="name"` is one camera, not its characters. The image, scene, frozen instance, tooling and grader are unchanged, so the task keeps its name.
- 2026-10-10 (review round 3): the sim service, its 2.4 layer and the client; the pass rule is unchanged. A camera named more than once in `cameras` is rendered and returned once. A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). `/spec`'s description of the proprio group `gripper_opening` says that a gripper closed on cloth reads 0 (it said that a gripper closed on an object stops above 0, which holds for rigid objects only); the values are unchanged. One call returns at most 2000 images (`/spec` `max_frames_per_call`: cameras x frames, a frame with per-frame depth counts 4): a request that would exceed it is a 400 before anything runs, and rows that take longer than planned stop adding frames there (`meta["frames_skipped"]`). Before, a call had no such bound: one long observation at the full frame rate could hold more frames than the sidecar's memory and get the service killed, so a trial that ended `sim_crashed*` or with `resource_service_oom` right after such a request before this date was that. The image, scene, frozen instance, tooling and grader are unchanged, so the task keeps its name.
