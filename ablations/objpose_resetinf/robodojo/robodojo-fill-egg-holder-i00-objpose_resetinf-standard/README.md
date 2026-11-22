# robodojo-fill-egg-holder-i00-standard

| | |
|---|---|
| Benchmark | RoboDojo |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robodojo-fill-egg-holder-i00-privileged` |
| Simulator / robot | `robodojo` / `arx-x5-bimanual` |
| Family / instance | `fill_egg_holder` / seed 0 |
| Oracle | `none` — no positive example yet; no reference solution (RoboDojo releases no expert, and its training demonstrations carry no initial state); marked unvalidated (PROTOCOL §2 `validated`); human review in PR #142 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:robodojo-0.2.1` |

## Task
Standard-mode twin of `robodojo-fill-egg-holder-i00-privileged` (same frozen layout, RoboDojo's `arx_x5/0/fill_egg_holder_0.json`). Move the four eggs from the egg basket into the egg holder (an articulated tray with a lid), close the lid, and return the arm home. (RoboDojo's `fill_egg_holder`). The agent drives the
robot only through the eai-standard/2.2 client (the simulator runs in the `sim` sidecar), which owns the scene and records
the episode as a (T, 14) trajectory of RoboDojo's own joint action at 25 Hz.

## Difficulty
A RoboDojo Long-Horizon task (mixed (rigid eggs + articulated egg holder with a hinged lid) objects), graded by RoboDojo's own success thresholds (its evaluation gives a policy 700 actions; no step cap here, PROTOCOL §3). Here the agent sees only the three cameras (RGB, optional depth) and the arms' proprioception: no object
poses, no success signal, no reset, one episode (no step cap; RoboDojo's own evaluation gives a policy 700 actions).

## Reference solution
None (see the privileged twin): RoboDojo releases no expert or planner script, and its training demonstrations record no
initial state, so none replays on a frozen layout. The task is marked unvalidated (PROTOCOL §2 `validated`).

## Verification
The sim service ends the episode on RoboDojo's own check (success), a failed check, the runaway guard or the time limit, and
writes `/data/trajectory.npz` and `/data/episode.json` (the live result); the collect hook (`environment/sim/finalize.sh`)
writes `final.json` from them (no replay) and encodes the video the service kept during the episode (`live.mp4`, a frame of
`cam_head` at the actions the agent's calls rendered; a failed encode costs the video only); `tests/grade.py` scores 1 iff
the live episode succeeded: every standard task is graded by its live episode, which the trusted service ran, with no grading replay (since 2026-10-17; before, `success` = `live_success` and the success of one fresh-process replay). Before serving, the service checks the rebuilt layout's state hash against the frozen instance's
(`instance_mismatch`: an infrastructure failure). The collect hook needs no GPU after the service exits. No oracle;
human review in PR #142 (no positive example yet). `nop` (no actions) scores 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 8 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 16 | 25 GiB | 2048 | 16 GiB | — |
| verifier (as `main`) | 2 | 8 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Episode | one episode, no reset: it ends at the first action where RoboDojo's check passes, when a check fails for good, when the agent's time is up, or on a simulator error; no step cap (RoboDojo's evaluation gives a policy 700 actions; a runaway guard at 15000) |
| Action space | `submit` chunks of `joint_position` (14: RoboDojo's own action at 25 Hz, the agent's `dt` a multiple of 1/25 s) or `ee_pose` (16: both arms' link6 targets, IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK of both arms, stateless); binary RCB1 responses |
| Source | RoboDojo @ `cb2a37d` (MIT), its Isaac Lab 2.3 fork @ `afca7b0`, its cuRobo fork @ `d17b54c`; assets from `RoboDojo-Benchmark/RoboDojo` @ `35efbc7` (Apache-2.0) |
| Benchmark notes | tasks/robodojo/README.md |
