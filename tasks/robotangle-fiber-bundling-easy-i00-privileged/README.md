# robotangle-fiber-bundling-easy-i00-privileged

| | |
|---|---|
| Benchmark | RoboTangle |
| Mode | privileged |
| Twin | `robotangle-fiber-bundling-easy-i00-standard` |
| Simulator / robot | `robotangle` / `franka-robotiq-2f85` |
| Family / instance | `fiber_bundling` / seed 0 |
| Oracle | `full` |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robotangle:0.2.21` |

## Task
RoboTangle fiber_bundling (Franka Panda + Robotiq 2F-85, Genesis): produce one replayable trajectory. Manipulate the thick sheath to pass every fine fiber and the front sheath through the fixed copper ring; keep the rear terminal anchored. Frozen scene instance (variation fiber_bundling_easy, seed 0).

## Difficulty
A 7-dof franka panda arm with a robotiq 2f-85 parallel gripper on a fixed base with a 8-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `72269a5c94bf8e5a…`) to `/app/output/`: the trajectory the author's oracle (the RoboTangle planner on dev/jianwen) produced on merged-v18 (source 5b5677f0, tooling a9d09d66; lab run 20261006T022802-1716501), where the verifier scored it 1 in two fresh-process replays. This family's task, geometry and asset files are unchanged from that build to this release; the shared simulator, tooling, graders and sim service changed only in paths that do not act on this family's scene (the cloth particle speed, a constraint solver chosen by name, the generated PBD birth state of dev/jianwen 2dafa5f2b), apart from the new report fields `initial_state_generated` and `initial_state`. The oracle was not re-run on this build (docs/benchmarks/robotangle.md, Evidence).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the frozen instance (`/tests/instance.json`, staged from the image and checked against `tests/runtime_binding.json`) in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the CPU and is bit-deterministic on one host; the final-state hashes
(`deterministic`) are still diagnostic, as for the GPU families; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).

`nop` scored 0 on this base in both modes on the merged-v18 candidate build (lab `align_v18/cand_v18`, the pipeline's Harbor nop checks, 2026-10-05; frozen instance state identical); not yet re-run on this build.

## Details
| | |
|---|---|
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision terminal_v4_fiber_ring_plane) |

### Goal
Manipulate the thick sheath to pass every fine fiber and the front sheath through the fixed copper ring; keep the rear terminal anchored.

### Success requirements
- Pass every fiber tip first, then successive material points through to its root. The actual crossing history must be observed; placing fibers on the far side or passing only the tips is not completion.
- All fiber points must finish beyond the exit side of the ring tube, allowing for fiber thickness. The branching face of the front sheath must also pass through and clear the tube with its full thickness. The fixed rear terminal must remain anchored and does not pass through.
- Keep the angle between every pair of adjacent fiber segments at most 60 degrees in the final configuration.
- Touch and grasp only the thick sheath with the gripper. Keep the completed passage valid through confirmation; holding is allowed, with no separate release or speed threshold.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Any gripper touch of a fine fiber at any time ends the episode in failure, including a brief or zero-force touch.
- A fiber link falling more than 100 mm below the tabletop ends the episode in failure.

### Grader details (in addition to the requirements above)
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 6 mm beyond the tool frame (TCP) along its approach axis when open and about 19 mm when closed (the Robotiq fingertips move forward as they close). Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Sizes: ring inner radius 13.5 mm, ring tube radius 4 mm; 4 fibers of radius 1.2 mm; sheath radius 12 mm.
- Each fiber is tracked at 11 points from tip to root. A point counts when it crosses the ring's plane less than 17.48 mm from the ring's axis, in tip-to-root order; a crossing out of order or outside that radius resets that point and every point behind it, and crossing back loses the credit.
- At the end every fiber point must be more than 5.2 mm past the ring's plane (tube + fiber radius) and the centre of the sheath's front face more than 16 mm past it (tube + sheath radius). The exit side is the side opposite to where the fibers start.
- The failure counts contact between a fine fiber and the gripper (fingers and hand, housing included); arm links touching a fiber do not count. Contact is sampled at all 4 solver substeps of every tick; if any tick since the start had incomplete contact coverage (a simulator-side condition), the episode can no longer succeed.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): fiber_bundle: radius 25 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- A failure is reported in `s.status()["episode_end"]` as "fiber_gripper_contact", "Fiber below table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

### Provenance
- Frozen instance: built by TopoGym source `5b5677f0` (graded package `align_v18/cand_v18b/tasks/topogym-fiber-bundling-easy-i00-privileged` on the lab host); bound to this release's runtime (source `ecb43962`, tooling `976d20c5`). An exact-restore preflight on this build is pending (docs/benchmarks/robotangle.md, Pending).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `08eb48360ce6`, under `instances/fiber-bundling-easy-i00/` (scripts/robotangle/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/jianwen `2dafa5f2b` (task templates `2dafa5f2b`), image `ghcr.io/mll-lab-nu/eai-robotangle:0.2.21` (images/robotangle/).
- Name: RoboTangle is the published name of TopoGym (2026-10-07). Code identifiers keep the old name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-08: base image 0.2.19 -> 0.2.21, now public. The simulator, the frozen instances and the audited libuipc wheel are unchanged: on compute capability 8.9 and 12.x (e.g. RTX 4090, L40S, RTX PRO 6000) the physics runs the same libuipc code as before. New: the NVIDIA Vulkan ICD and EGL vendor files, and a second libuipc build of the audited recipe for compute capability 8.6 (RTX A6000 class), which the tooling selects at Session start on every other GPU, so knot_untying and rope_threading run there too. The runtime binding names both builds, and the tooling hash changes with the selection. The compose files reserve one GPU without `runtime: nvidia`, which with the image's NVIDIA_VISIBLE_DEVICES=all could expose every GPU (Nyx needs exactly one). The graders are unchanged. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-08 (2): the instance now also starts on a CPU of another instruction-set class. The asset generators run on numpy and OpenBLAS, whose SIMD kernels depend on the CPU: on a host without AVX-512 (e.g. AWS L4 / L40S instances) the pinned generator writes the frozen asset files with other bytes (floating-point noise up to 1e-8 m, face order), and the Session refused the instance (IPC and stored PBD states also refused their archive). Such a host now realizes the frozen recipe (`instance_realized`): the same asset files from the generator the runtime binding pins, archives that differ from this scene only in those bytes, and the frozen state, exactly or within the pose tolerance; the live episode and the fresh replay realize it alike. The graders record `instance_realized` and `assets_exact`. A host that reproduces the frozen bytes runs exactly as before. The tooling hash changes; the image, scene, frozen instance and pass rule are unchanged, so the task keeps its name.
