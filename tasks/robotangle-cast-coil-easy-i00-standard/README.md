# robotangle-cast-coil-easy-i00-standard

| | |
|---|---|
| Benchmark | RoboTangle |
| Mode | standard (`eai-standard/2.4`) |
| Twin | `robotangle-cast-coil-easy-i00-privileged` |
| Simulator / robot | `robotangle` / `aloha-2` |
| Family / instance | `cast_coil` / seed 0 |
| Oracle | `full` |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robotangle:0.2.21` |

## Task
Standard-mode twin of `robotangle-cast-coil-easy-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.4` client
(docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `robotangle-cast-coil-easy-i00-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/solve.sh` streams the recorded rows of the author's standard-mode oracle episode (`solution/oracle_qpos.npy`, one `joint_position` row per 25 ms control step, `hold`) through the client (`solution/oracle_replay.py`). That episode scored 1 (live and fresh replay) on merged-v18 (source 5b5677f0, tooling a9d09d66; lab run 20261006T043158-3589967). This family's task, geometry and asset files are unchanged from that build to this release; the shared simulator, tooling, graders and sim service changed only in paths that do not act on this family's scene (the cloth particle speed, a constraint solver chosen by name, the generated PBD birth state of dev/jianwen 2dafa5f2b), apart from the new report fields `initial_state_generated` and `initial_state`. The oracle was not re-run on this build (docs/benchmarks/robotangle.md, Evidence).

## Verification
See `tests/grade.py`.

`nop` scored 0 on this base in both modes on the merged-v18 candidate build (lab `align_v18/cand_v18`, the pipeline's Harbor nop checks, 2026-10-05; frozen instance state identical); not yet re-run on this build.

## Details

### Goal
Assemble the gold and silver Cast Coil pieces into their matching interlocking configuration, then release both.

### Success requirements
- Align the pieces' matching assembly frames with relative position error below 1 mm and relative angular error below 0.02 rad.
- The bottom of at least one piece must be within 3 mm of the tabletop. Neither piece may extend more than 1 mm below it, and each piece must overlap the tabletop horizontally.
- Keep both pieces' linear speeds below 1 mm/s and angular speeds below 0.02 rad/s. Merely touching or gripping them is not completion.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm. Each target rigid body's angular speed must be at most 0.02 rad/s and angular drift at most 0.02 rad.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Finger contact with a held movable piece may penetrate at most 2 mm; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand. All other task contacts, including piece-piece, table, arm and gripper-housing contacts, may penetrate at most 1 mm. Exceeding either limit ends the episode in failure.

### Grader details (in addition to the requirements above)
- Contact penetration as this benchmark grades it (it replaces the "at most 1 mm / 2 mm" wording above): penetration is recorded, it never ends the episode by itself. A success with deep interpenetration (a task contact deeper than 3 mm, or deeper than 1 mm for at least 0.25 s: 100 consecutive physics ticks; for a finger contact with a held piece 4 mm, or 2 mm for 0.25 s) is not credited automatically but reviewed, with the recorded evidence and frames; a clean success is credited automatically. A task contact deeper than 10 mm is a simulator breakdown (below).
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step). "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active assisted grasp), the other finger is back at the non-held limits in the same tick.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`meta["safety"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a non-finite state or a task contact deeper than 10 mm): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- The release clearance is measured between axis-aligned bounding boxes: one around each collision geometry of the whole robot (every link of both arms) and one around each collision geometry of the pieces, so the true gap usually has to be larger than 5 mm.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): coil_gold: radius 25 mm; coil_silver: radius 25 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.4`: `submit` chunks of `joint_position` (14, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; the state hashes are reported, not required (GPU physics is not bit-deterministic; the CPU rigid families' is, on one host); `/logs/verifier/replay.mp4` is rendered during that replay |
| crash recovery | `eai-standard/2.4` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |

### Provenance
- Frozen instance: built by TopoGym source `5b5677f0` (graded package `align_v18/cand_v18b/tasks/topogym-cast-coil-easy-i00-privileged` on the lab host); bound to this release's runtime (source `ecb43962`, tooling `976d20c5`). An exact-restore preflight on this build is pending (docs/benchmarks/robotangle.md, Pending).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `08eb48360ce6`, under `instances/cast-coil-easy-i00/` (scripts/robotangle/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/jianwen `2dafa5f2b` (task templates `2dafa5f2b`), image `ghcr.io/mll-lab-nu/eai-robotangle:0.2.21` (images/robotangle/).
- Name: RoboTangle is the published name of TopoGym (2026-10-07). Code identifiers keep the old name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-08: base image 0.2.19 -> 0.2.21, now public. The simulator, the frozen instances and the audited libuipc wheel are unchanged: on compute capability 8.9 and 12.x (e.g. RTX 4090, L40S, RTX PRO 6000) the physics runs the same libuipc code as before. New: the NVIDIA Vulkan ICD and EGL vendor files, and a second libuipc build of the audited recipe for compute capability 8.6 (RTX A6000 class), which the tooling selects at Session start on every other GPU, so knot_untying and rope_threading run there too. The runtime binding names both builds, and the tooling hash changes with the selection. The compose files reserve one GPU without `runtime: nvidia`, which with the image's NVIDIA_VISIBLE_DEVICES=all could expose every GPU (Nyx needs exactly one). The standard grader counts a fresh replay that crashed without writing its verdict (e.g. CUDA out of memory) as a grader error; it counted as instance_mismatch. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-08 (2): the instance now also starts on a CPU of another instruction-set class. The asset generators run on numpy and OpenBLAS, whose SIMD kernels depend on the CPU: on a host without AVX-512 (e.g. AWS L4 / L40S instances) the pinned generator writes the frozen asset files with other bytes (floating-point noise up to 1e-8 m, face order), and the Session refused the instance (IPC and stored PBD states also refused their archive). Such a host now realizes the frozen recipe (`instance_realized`): the same asset files from the generator the runtime binding pins, archives that differ from this scene only in those bytes, and the frozen state, exactly or within the pose tolerance; the live episode and the fresh replay realize it alike. The graders and the sim service record `instance_realized` and `assets_exact`. A host that reproduces the frozen bytes runs exactly as before. The tooling hash changes; the image, scene, frozen instance and pass rule are unchanged, so the task keeps its name.
