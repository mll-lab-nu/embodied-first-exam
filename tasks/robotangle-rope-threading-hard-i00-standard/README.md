# robotangle-rope-threading-hard-i00-standard

| | |
|---|---|
| Benchmark | RoboTangle |
| Mode | standard (`eai-standard/2.4`) |
| Twin | `robotangle-rope-threading-hard-i00-privileged` |
| Simulator / robot | `robotangle` / `aloha-2` |
| Family / instance | `rope_threading` / seed 0 |
| Oracle | `full` |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robotangle:0.2.22` |

## Task
Standard-mode twin of `robotangle-rope-threading-hard-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.4` client
(docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `robotangle-rope-threading-hard-i00-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/solve.sh` streams the recorded rows of the author's standard-mode oracle episode (`solution/oracle_qpos.npy`, one `joint_position` row per 25 ms control step, `hold`) through the client (`solution/oracle_replay.py`). That episode scored 1 (live and fresh replay) on merged-v18 (source cadc53a3, tooling a9d09d66; lab run 20261005T213419-1023476). Between that build and merged-v18: graded on the merged-v18 build before its rebase; frozen instance state and simulator configuration identical; the rope oracle code is unchanged at 8d7d16489 (same document). After merged-v18, the shared simulator, tooling, graders and sim service changed only in paths that do not act on this family's scene (the cloth particle speed, a constraint solver chosen by name, the generated PBD birth state of dev/jianwen 2dafa5f2b), apart from the new report fields `initial_state_generated` and `initial_state`. The oracle was not re-run on this build (docs/benchmarks/robotangle.md, Evidence).

## Verification
See `tests/grade.py`.

`nop` scored 0 on this base in both modes on the merged-v18 candidate build (lab `align_v18/cand_v18`, the pipeline's Harbor nop checks, 2026-10-05; frozen instance state identical); not yet re-run on this build.

## Details

### Goal
Thread the rope through the cyan ring (R1) then green ring (R2) then purple ring (R3), in that order along the rope from material start to material end.

### Success requirements
- Required directions along that material order: cyan ring (R1): cross toward the side containing the green ring (R2); green ring (R2): cross away from the side containing the cyan ring (R1); purple ring (R3): cross away from the side containing the green ring (R2). Do not reverse the crossing directions.
- Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. Keep the full rope thickness clear of the rim, with an additional 0.1 mm radial margin; the passage must clear both sides of each ring's thickness, not just its middle plane.
- Keep every rope point at or below 10 mm/s. Holding is allowed; release is not required.
- Keep the rope intact; collapsed or inverted rope volume is not accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Invalid rope volume ends the episode in failure.

### Grader details (in addition to the requirements above)
- The rope's Young's modulus is 5000 kPa. Gripper pressure can deform it. A crushed rope volume (an inverted volume element) ends the episode only once it has lasted at least 0.25 s (7 consecutive physics ticks; while it lasts, the goal cannot be confirmed); an invalid soft-body solver state is a simulator breakdown (below). Close to about half the rope's diameter and slow down in the last centimetre.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`meta["safety"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (an invalid soft-body solver state): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- Sizes (rope radius 4 mm): R1: inner radius 50 mm, tube radius 6 mm, centreline passage radius 46.9 mm on the middle plane and 49.2 mm on the two tube-offset planes; R2: inner radius 50 mm, tube radius 6 mm, centreline passage radius 46.9 mm on the middle plane and 49.2 mm on the two tube-offset planes; R3: inner radius 50 mm, tube radius 6 mm, centreline passage radius 46.9 mm on the middle plane and 49.2 mm on the two tube-offset planes.
- Aperture check: round_ring, compression allowance 1 mm. This allowance changes the geometric passage test; the collision geometry stays as declared.
- The material start is the rope end that is farther from the rings at the start.
- Only the grippers' fingers collide with the rope and the rings: every other robot part (palms, wrists, arm links, bases) passes through them without contact, so only the fingers can push, pinch or hold the rope.
- Soft grasp patches: rope: spatial radius 14 mm, material radius 18 mm, finger proximity 6 mm, maximum material strain ratio 2, exposed patch not required. Both fingers must be near the same material patch; penetration and native constraint health checks still apply. Two hands may hold disjoint patches of one object. Material bounds, when present, restrict the admissible region.
- Grading: success needs the live episode to succeed (with the thresholds above) AND one fresh-process replay of its rows to succeed; a live failure is final whatever the replay shows. This family's physics runs on the GPU, which is not bit-deterministic, so that replay can differ slightly from the live episode: it runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (50 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in the live episode can still complete; the hold uses the thresholds above too (no tolerance for this family). Nothing else changes.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.4`: `submit` chunks of `joint_position` (14, streamed at the 25 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; the state hashes are reported, not required (GPU physics is not bit-deterministic; the CPU rigid families' is, on one host); `/logs/verifier/replay.mp4` is rendered during that replay; after a live success it is a grading replay (tooling v18): if this GPU family's episode has not ended after the last live row, the final targets are held for up to 2 s with the replay tolerances of the grader details; a live failure is final |
| crash recovery | `eai-standard/2.4` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |

### Provenance
- Frozen instance: built by TopoGym source `5b5677f0` (graded package `align_v18/cand_v18b/tasks/topogym-rope-threading-hard-i00-privileged` on the lab host); bound to this release's runtime (source `ecb43962`, tooling `c80aa5a9`). An exact-restore preflight on this build is pending (docs/benchmarks/robotangle.md, Pending).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `8ad7ffd309c9`, under `instances/rope-threading-hard-i00/` (scripts/robotangle/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/jianwen `2dafa5f2b` (task templates `2dafa5f2b`), image `ghcr.io/mll-lab-nu/eai-robotangle:0.2.22` (images/robotangle/).
- Name: RoboTangle is the published name of TopoGym (2026-10-07). Code identifiers keep the old name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-08: base image 0.2.19 -> 0.2.21, now public. The simulator, the frozen instances and the audited libuipc wheel are unchanged: on compute capability 8.9 and 12.x (e.g. RTX 4090, L40S, RTX PRO 6000) the physics runs the same libuipc code as before. New: the NVIDIA Vulkan ICD and EGL vendor files, and a second libuipc build of the audited recipe for compute capability 8.6 (RTX A6000 class), which the tooling selects at Session start on every other GPU, so knot_untying and rope_threading run there too. The runtime binding names both builds, and the tooling hash changes with the selection. The compose files reserve one GPU without `runtime: nvidia`, which with the image's NVIDIA_VISIBLE_DEVICES=all could expose every GPU (Nyx needs exactly one). The standard grader counts a fresh replay that crashed without writing its verdict (e.g. CUDA out of memory) as a grader error; it counted as instance_mismatch. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-08 (2): the instance now also starts on a CPU of another instruction-set class. The asset generators run on numpy and OpenBLAS, whose SIMD kernels depend on the CPU: on a host without AVX-512 (e.g. AWS L4 / L40S instances) the pinned generator writes the frozen asset files with other bytes (floating-point noise up to 1e-8 m, face order), and the Session refused the instance (IPC and stored PBD states also refused their archive). Such a host now realizes the frozen recipe (`instance_realized`): the same asset files from the generator the runtime binding pins, archives that differ from this scene only in those bytes, and the frozen state, exactly or within the pose tolerance; the live episode and the fresh replay realize it alike. The graders and the sim service record `instance_realized` and `assets_exact`. A host that reproduces the frozen bytes runs exactly as before. The tooling hash changes; the image, scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-08 (3): base image 0.2.21 -> 0.2.22. The image adds, for the eight IPC instances (knot_untying, rope_threading), the rope volume mesh each was frozen with (`instance_assets/frozen_assets/rope_volume.npz`, the sha256 its asset identity records), and the tooling uses it instead of regenerating it: tetgen's interior points depend on the CPU's floating-point rounding, and on CPUs without AVX-512 knot_untying medium and hard got another mesh, which their frozen settled state does not fit. Nothing else in the image changes. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
