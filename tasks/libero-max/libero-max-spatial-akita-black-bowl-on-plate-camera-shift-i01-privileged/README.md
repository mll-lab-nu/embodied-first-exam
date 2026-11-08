# libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i01-privileged

| | |
|---|---|
| Benchmark | LIBERO-MAX |
| Mode | privileged |
| Twin | `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i01-standard` |
| Simulator / robot | `robosuite` / `franka-panda` |
| Family / instance | `libero-max/libero_spatial/camera_shift` / seed 195 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:libero-max-0.1.1` |

## Task
LIBERO-MAX case `pro-position-spatial-t07-i01-camera_shift-d0-p195`: a Franka Panda arm at a table, instructed **"Pick the akita black bowl on the stove and place it on the plate."**, on a LIBERO-PRO variant
of a libero_spatial task (position). Online event (camera shift): the first time the gripper comes within
0.18 m of `akita_black_bowl_1`, LIBERO-MAX changes the scene once (the `agentview` camera moves by (0.06, 0, 0.02) m, turns 18° and its field of view changes by +12°). The deliverable is one
replayable trajectory of LIBERO's OSC control steps (`/app/output/trajectory.npz`, `(T, 7)`, T ≤ 220), graded by
LIBERO's success check at its end.

## Difficulty
Privileged mode: every object's pose, the goal, the simulator, unlimited restarts (one simulator per process) and
self-replay. The task itself is short; what makes it harder than LIBERO is the change mid-task, which a plan made at the
start has to survive. This mode is the control for the standard twin, which removes the privileged state.

## Reference solution
119 control steps on this instance (`solution/oracle.npy`), replayed by `solution/solve.sh`: a scripted
controller with privileged state (not in the image) that re-reads the objects' poses
every step and so follows the change; the event fired at step 10. LIBERO's demonstrations are not in the
image. Re-verified at freeze time: the replay ends with LIBERO's success at its last step.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay, in a fresh process, from the verifier's own
copy of the instance (`tests/instance.json`; the rebuilt start is checked against its hash on every load); pass iff
LIBERO's success check holds at the last action (actions after it make the
trajectory invalid). Oracle: the replay ends in the live state (hash `f799d949f47e…`) and succeed. `nop`: no trajectory,
reward 0; the instance is not solved at the start.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | LIBERO-PRO @ 2b910b5 (MIT; task data `zhouxueyang/LIBERO-Pro` @ c86fc3b, CC-BY-4.0); LIBERO-MAX @ a1e3cef (event runtime and this case's parameters; no licence file upstream); robosuite 1.4.0, MuJoCo 3.2.6 |
| Case | `pro-position-spatial-t07-i01-camera_shift-d0-p195` (LIBERO-MAX 8,000-case manifest; LIBERO-PRO category `position`, task 7, initial state 1) |
| Event | `camera_shift`: the `agentview` camera moves by (0.06, 0, 0.02) m, turns 18° and its field of view changes by +12°; trigger: gripper within 0.18 m of `akita_black_bowl_1` |
| Actions | 7 per control step (1/20 s): OSC hand-target delta (1.0 = 0.05 m, 0.5 rad) and gripper |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Provenance
The case was chosen and frozen in `ghcr.io/mll-lab-nu/efe:libero-max-0.1.1`.
