# libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i01-standard

| | |
|---|---|
| Benchmark | LIBERO-MAX |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i01-privileged` |
| Simulator / robot | `robosuite` / `franka-panda` |
| Family / instance | `libero-max/libero_spatial/camera_shift` / seed 195 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-libero-max:0.1.1` |

## Task
LIBERO-MAX case `pro-position-spatial-t07-i01-camera_shift-d0-p195` as a robot service: a Franka Panda arm at a table, instructed **"Pick the akita black bowl on the stove and place it on the plate."**, on
the same frozen instance as `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i01-privileged`, with the same online event (camera shift: the `agentview` camera moves by (0.06, 0, 0.02) m, turns 18° and its field of view changes by +12°, the
first time the gripper comes within 0.18 m of `akita_black_bowl_1`). The simulator runs in the `sim` sidecar
(`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: two cameras (RGB
256×256, depth on request, calibrated), the robot's own state, and OSC control steps in chunks. One
episode, no reset, no object poses; nothing to hand in. The agent is told that the scene may change once, not how or
when.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with OSC deltas, notice the change
when it happens and adapt, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged oracle's 119 control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at LIBERO's success (or at the 9000-step technical cap, when the agent's time
is up, or on a simulator error), replays the recorded episode in a fresh process and writes `/data/final.json`;
`tests/grade.py` (separate sandbox, no network) grades it: `success = live_success ∧ replay_success ∧ deterministic`.

## Details
| | |
|---|---|
| Actions | `ee_delta` (7, float64): OSC hand-target delta (1.0 = 0.05 m, 0.5 rad per control step) and gripper |
| Episode cap | 9000 control steps (450 s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Change Log
- 2026-10-08: image `eai-libero-max:0.1.1` (`OPENBLAS_CORETYPE=Zen`); the instance, its start-state hash, the reference
  solution and the pass rule are unchanged, so the task keeps its name. With 0.1.0 the start state did not rebuild on
  Intel Xeon 8488C hosts (the Session refused with a hash mismatch): the OpenBLAS 0.3.18 bundled with numpy and scipy
  does not know that CPU and fell back to its generic Prescott kernels, while the instances were frozen with its Zen
  kernels (AMD 7950X). 0.1.1 pins the Zen kernels; same Python packages and sources. `scripts/libero-max/rebuild_check.sh`
  (start-state hash and reference replay of all 64 instances): 8488C 0/64 with 0.1.0, 64/64 with 0.1.1; 7950X 64/64.
