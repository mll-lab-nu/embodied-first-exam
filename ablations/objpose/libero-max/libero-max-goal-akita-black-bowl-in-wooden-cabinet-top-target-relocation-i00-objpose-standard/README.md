# libero-max-goal-akita-black-bowl-in-wooden-cabinet-top-target-relocation-i00-standard

| | |
|---|---|
| Benchmark | LIBERO-MAX |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `libero-max-goal-akita-black-bowl-in-wooden-cabinet-top-target-relocation-i00-privileged` |
| Simulator / robot | `robosuite` / `franka-panda` |
| Family / instance | `libero-max/libero_goal/target_relocation` / seed 195 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:libero-max-0.1.1` |

## Task
LIBERO-MAX case `pro-initial-pose-position-angle-goal-t03-i09-target_relocation-d0-p195` as a robot service: a Franka Panda arm at a table, instructed **"Open the top layer of the drawer and put the bowl inside."**, on
the same frozen instance as `libero-max-goal-akita-black-bowl-in-wooden-cabinet-top-target-relocation-i00-privileged`, with the same online event (target relocation: `akita_black_bowl_1` is moved 0.06 m across the table, direction (-0.707, -0.707), the
first time the gripper comes within 0.18 m of `akita_black_bowl_1`). The simulator runs in the `sim` sidecar
(`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: two cameras (RGB
256×256, depth on request, calibrated), the robot's own state, and OSC control steps in chunks. One
episode, no reset, no object poses; nothing to hand in. The agent is told that the scene may change once, not how or
when.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with OSC deltas, notice the change
when it happens and adapt, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged oracle's 247 control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
Graded by the live episode (docs/protocol/README.md H.4; owner, 2026-10-17): the sim service ends the episode at
LIBERO's success (or at the 9000-step technical cap, when the agent's time is up, or on a simulator error) and,
once the agent's container is stopped, writes its verdict to `/data/final.json` (`graded_by = "live"`, `replays = 0`,
the event record `event_fired` / `event_step`); `tests/grade.py` (separate sandbox, no network) grades it:
`success = live_success` (LIBERO's success check held in the live episode), with `infra_error = 1` when there is no
finalized verdict. Nothing is replayed to grade it. The frozen start is checked when the episode begins: a scene that
does not start at the instance's recorded state hash is `instance_mismatch` (`infra_error = 1`), before the agent is
served. After the verdict the collect hook replays `trajectory.npz` once in a fresh process for `replay.mp4` (and
`replay.video.json`: whether that replay ended in the live state); it can neither change nor cost the verdict
(`tasks/libero-max/README.md`, "Grading (standard mode)").

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 3 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Actions | `ee_delta` (7, float64): OSC hand-target delta (1.0 = 0.05 m, 0.5 rad per control step) and gripper |
| Episode cap | 9000 control steps (450 s of robot time; `spec.max_control_steps`, docs/protocol/standard_mode.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering); the collect hook: the verdict at once, then one video pass (up to 5,400 s for the longest episode on a busy host) |
