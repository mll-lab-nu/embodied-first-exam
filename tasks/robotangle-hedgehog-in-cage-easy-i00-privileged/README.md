# robotangle-hedgehog-in-cage-easy-i00-privileged

| | |
|---|---|
| Benchmark | RoboTangle |
| Mode | privileged |
| Twin | `robotangle-hedgehog-in-cage-easy-i00-standard` |
| Simulator / robot | `robotangle` / `franka-robotiq-2f85` |
| Family / instance | `hedgehog_in_cage` / seed 0 |
| Oracle | `full` |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robotangle:0.2.22` |

## Task
RoboTangle hedgehog_in_cage (Franka Panda + Robotiq 2F-85, Genesis): produce one replayable trajectory. Separate and place the whole hedgehog ball, including every spike inside the green dashed goal region. Keep all cage components on the puzzle/system side. Frozen scene instance (variation hedgehog_in_cage_easy, seed 0).

## Difficulty
A 7-dof franka panda arm with a robotiq 2f-85 parallel gripper on a fixed base with a 8-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 2 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `27d236d1833d5bcf…`) to `/app/output/`: the trajectory the author's oracle (the RoboTangle planner on dev/jianwen) produced on merged-v18 (source 5b5677f0, tooling a9d09d66; lab run 20261006T034912-3016766), where the verifier scored it 1 in two fresh-process replays. This family's task, geometry and asset files are unchanged from that build to this release; the shared simulator, tooling, graders and sim service changed only in paths that do not act on this family's scene (the cloth particle speed, a constraint solver chosen by name, the generated PBD birth state of dev/jianwen 2dafa5f2b), apart from the new report fields `initial_state_generated` and `initial_state`. The oracle was not re-run on this build (docs/benchmarks/robotangle.md, Evidence).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the frozen instance (`/tests/instance.json`, staged from the image and checked against `tests/runtime_binding.json`) in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the CPU and is bit-deterministic on one host; the final-state hashes
(`deterministic`) are still diagnostic, as for the GPU families; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).
A trajectory may have at most 200000 rows (`RCB_MAX_STEPS`: two replays must fit the verifier's timeout; a longer one is
`bad_trajectory`).

`nop` scored 0 on this base in both modes on the merged-v18 candidate build (lab `align_v18/cand_v18`, the pipeline's Harbor nop checks, 2026-10-05; frozen instance state identical); not yet re-run on this build.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 7 GB | 5 GB |
| GPU memory | 7 GB | 7 GB |

- GPU: required, any NVIDIA GPU; recommended: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).
- Measured: GPU 5.9 GB on L4, 10.3 GB on L40S, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 4.0 GB, privileged container 4.6 GB, verifier p90 3.9 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 16 GiB GPU memory, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 16 GiB memory. Limits measured: GPU: 10.3 GiB on a 48 GB card, 5.9 on 24 GB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: the [environment] cap 16 GiB, which every past trial ran under (docker peak 4.6 GiB over 1 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision hedgehog_placement_v4_grasp_contact_2mm) |

### Goal
Separate and place the whole hedgehog ball, including every spike inside the green dashed goal region. Keep all cage components on the puzzle/system side.

### Success requirements
- Put every part of the whole hedgehog ball, including every spike inside the fixed goal volume, leaving at least 1 mm inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height. It need not touch the table. The goal volume extends 236.877 mm above the tabletop.
- Keep all cage components, and every other remaining puzzle component, entirely on the system side of the fixed separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding the target with the gripper is allowed; release is not required.
- Keep all final conditions satisfied together for at least 2 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Finger contact with a held movable piece may penetrate at most 2 mm; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand. All other task contacts, including piece-piece, table, arm and gripper-housing contacts, may penetrate at most 1 mm. Exceeding either limit ends the episode in failure.

### Grader details (in addition to the requirements above)
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 244.9 mm x 244.9 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The remaining components here are fixed.
- Contact penetration as this benchmark grades it (it replaces the "at most 1 mm / 2 mm" wording above): penetration is recorded, it never ends the episode by itself. A success with deep interpenetration (a task contact deeper than 3 mm, or deeper than 1 mm for at least 0.25 s: 100 consecutive physics ticks; for a finger contact with a held piece 4 mm, or 2 mm for 0.25 s) is not credited automatically but reviewed, with the recorded evidence and frames; a clean success is credited automatically. A task contact deeper than 10 mm is a simulator breakdown (below).
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step). "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active assisted grasp), the other finger is back at the non-held limits in the same tick. The cage is fixed, so finger contact with it is never held (always the non-held limits).
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 6 mm beyond the tool frame (TCP) along its approach axis when open and about 19 mm when closed (the Robotiq fingertips move forward as they close). Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a non-finite state or a task contact deeper than 10 mm): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): hedgehog_ball: radius 89.3 mm, enclosing the whole part. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- A failure is reported in `s.status()["episode_end"]` as "A task body fell below the table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits, and `s.status()["review"]` the deep task contacts that would hold a success for review.

### Provenance
- Frozen instance: built by TopoGym source `5b5677f0` (graded package `align_v18/cand_v18b/tasks/topogym-hedgehog-in-cage-easy-i00-privileged` on the lab host); bound to this release's runtime (source `ecb43962`, tooling `c80aa5a9`). An exact-restore preflight on this build is pending (docs/benchmarks/robotangle.md, Pending).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `8ad7ffd309c9`, under `instances/hedgehog-in-cage-easy-i00/` (scripts/robotangle/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/jianwen `2dafa5f2b` (task templates `2dafa5f2b`), image `ghcr.io/mll-lab-nu/eai-robotangle:0.2.22` (images/robotangle/).
- Name: RoboTangle is the published name of TopoGym (2026-10-07). Code identifiers keep the old name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-08: base image 0.2.19 -> 0.2.21, now public. The simulator, the frozen instances and the audited libuipc wheel are unchanged: on compute capability 8.9 and 12.x (e.g. RTX 4090, L40S, RTX PRO 6000) the physics runs the same libuipc code as before. New: the NVIDIA Vulkan ICD and EGL vendor files, and a second libuipc build of the audited recipe for compute capability 8.6 (RTX A6000 class), which the tooling selects at Session start on every other GPU, so knot_untying and rope_threading run there too. The runtime binding names both builds, and the tooling hash changes with the selection. The compose files reserve one GPU without `runtime: nvidia`, which with the image's NVIDIA_VISIBLE_DEVICES=all could expose every GPU (Nyx needs exactly one). The graders are unchanged. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-08 (2): the instance now also starts on a CPU of another instruction-set class. The asset generators run on numpy and OpenBLAS, whose SIMD kernels depend on the CPU: on a host without AVX-512 (e.g. AWS L4 / L40S instances) the pinned generator writes the frozen asset files with other bytes (floating-point noise up to 1e-8 m, face order), and the Session refused the instance (IPC and stored PBD states also refused their archive). Such a host now realizes the frozen recipe (`instance_realized`): the same asset files from the generator the runtime binding pins, archives that differ from this scene only in those bytes, and the frozen state, exactly or within the pose tolerance; the live episode and the fresh replay realize it alike. The graders record `instance_realized` and `assets_exact`. A host that reproduces the frozen bytes runs exactly as before. The tooling hash changes; the image, scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-08 (3): base image 0.2.21 -> 0.2.22. The image adds, for the eight IPC instances (knot_untying, rope_threading), the rope volume mesh each was frozen with (`instance_assets/frozen_assets/rope_volume.npz`, the sha256 its asset identity records), and the tooling uses it instead of regenerating it: tetgen's interior points depend on the CPU's floating-point rounding, and on CPUs without AVX-512 knot_untying medium and hard got another mesh, which their frozen settled state does not fit. Nothing else in the image changes. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-10 (review fixes): texts and limits; the pass rule is unchanged. For the families graded with a tolerant hold (blanket_flatten, knot_untying, lock_picking, rope_threading) the instruction and this README said that one replay had to reach the goal within the trajectory's own rows; the grader has applied R-hold since tooling v16 (2026-10-05: every replay may confirm within the hold; `strict_goal_reached` is reported, not required), and the texts now say so. New row cap: a trajectory may have at most the number of rows the instruction states (`RCB_MAX_STEPS` in both Dockerfiles; 200000 before, for every task), sized so that the verifier's two replays fit its timeout (by the step time the instruction states; a verifier that runs out of time leaves no reward); a longer trajectory is now `bad_trajectory`. The grader skips the review-frame pass when its time is short (the verdict and the events are committed before it), and an instance this host cannot reconstruct is `infra_error` 1 with `instance_mismatch` (it was a plain 0). The image, scene and frozen instance are unchanged, so the task keeps its name.
- 2026-10-10 (review round 2): text only. The instruction gave the Robotiq gripper's native drive target in metres; it is the driver joint angle in rad (0 = open, 0.8 = closed). Nothing else changes, so the task keeps its name.
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell: the image's simulator package names the address of an upstream demonstration (`reference_scene.json` `source_url`; docs/benchmarks/robotangle.md, Network policy), which one trial downloaded. The image, scene, frozen instance, tooling and pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress and are withdrawn (RoboTangle is run again from scratch).
