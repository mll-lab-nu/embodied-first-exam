# libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-receptacle-relocation-i00-privileged

| | |
|---|---|
| Benchmark | LIBERO-MAX |
| Mode | privileged |
| Twin | `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-receptacle-relocation-i00-standard` |
| Simulator / robot | `robosuite` / `franka-panda` |
| Family / instance | `libero-max/libero_10/receptacle_relocation` / seed 195 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:libero-max-0.1.1` |

## Task
LIBERO-MAX case `pro-initial-pose-position-angle-10-t00-i02-receptacle_relocation-d0-p195`: a Franka Panda arm at a table, instructed **"Put both the alphabet soup and the tomato sauce in the basket."**, on a LIBERO-PRO variant
of a libero_10 task (initial_pose_position_angle). Online event (receptacle relocation): the first time the gripper comes within
0.18 m of `alphabet_soup_1`, LIBERO-MAX changes the scene once (the receptacle `basket_1` is moved 0.06 m, direction (1, 0); it jumps there alone: what already rests in or on it stays where it was, and where it lands on another object the physics pushes the two apart). The deliverable is one
replayable trajectory of LIBERO's OSC control steps (`/app/output/trajectory.npz`, `(T, 7)`, T ≤ 520), graded by
LIBERO's success check at its end.

## Difficulty
Privileged mode: every object's pose, the goal, the simulator, unlimited restarts (one simulator per process) and
self-replay. The task itself is short; what makes it harder than LIBERO is the change mid-task, which a plan made at the
start has to survive. This mode is the control for the standard twin, which removes the privileged state.

## Reference solution
300 control steps on this instance (`solution/oracle.npy`), replayed by `solution/solve.sh`: a scripted
controller with privileged state (not in the image) that re-reads the objects' poses
every step and so follows the change; the event fired at step 11. LIBERO's demonstrations are not in the
image. Re-verified at freeze time: the replay ends with LIBERO's success at its last step.

## Verification
`tests/grade.py` in a separate sandbox without network: two replays, each in a fresh process, from the verifier's own
copy of the instance (`tests/instance.json`; the rebuilt start is checked against its hash on every load); pass iff both
end in the same state (`deterministic`) and LIBERO's success check holds at the last action (actions after it make the
trajectory invalid). Oracle: the replays end in the live state (hash `3a6c18623d12…`) and succeed. `nop`: no trajectory,
reward 0; the instance is not solved at the start.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: verifier 1.6 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); the rest author estimate (robosuite, CPU-only, 256x256 OSMesa cameras)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: the [environment] cap 8 GiB, which every past trial ran under (no samples); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | LIBERO-PRO @ 2b910b5 (MIT; task data `zhouxueyang/LIBERO-Pro` @ c86fc3b, CC-BY-4.0); LIBERO-MAX @ a1e3cef (event runtime and this case's parameters; no licence file upstream); robosuite 1.4.0, MuJoCo 3.2.6 |
| Case | `pro-initial-pose-position-angle-10-t00-i02-receptacle_relocation-d0-p195` (LIBERO-MAX 8,000-case manifest; LIBERO-PRO category `initial_pose_position_angle`, task 0, initial state 2) |
| Event | `receptacle_relocation`: the receptacle `basket_1` is moved 0.06 m, direction (1, 0); it jumps there alone: what already rests in or on it stays where it was, and where it lands on another object the physics pushes the two apart; trigger: gripper within 0.18 m of `alphabet_soup_1` |
| Actions | 7 per control step (1/20 s): OSC hand-target delta (1.0 = 0.05 m, 0.5 rad) and gripper |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Provenance
The case was chosen and frozen in `ghcr.io/mll-lab-nu/efe:libero-max-0.1.1`.

### Change Log
- 2026-10-08: image `efe:libero-max-0.1.1` (`OPENBLAS_CORETYPE=Zen`); the instance, its start-state hash, the reference
  solution and the pass rule are unchanged, so the task keeps its name. With 0.1.0 the start state did not rebuild on
  Intel Xeon 8488C hosts (the Session refused with a hash mismatch): the OpenBLAS 0.3.18 bundled with numpy and scipy
  does not know that CPU and fell back to its generic Prescott kernels, while the instances were frozen with its Zen
  kernels (AMD 7950X). 0.1.1 pins the Zen kernels; same Python packages and sources. The rebuild check
  (start-state hash and reference replay of all 64 instances): 8488C 0/64 with 0.1.0, 64/64 with 0.1.1; 7950X 64/64.
- 2026-10-10: `tests/grade.py` and `lmx_tool.py`; the instance, the reference solution and the pass rule are
  unchanged, so the task keeps its name.
  - `reward.json` always has `infra_error` (0/1). It is 1 (with `grader_error = 1`) when the verifier's host does not
    rebuild the frozen start bit-exactly (a CPU without the frozen numeric kernels: the replay exits with code 3 before
    it executes any action). Before, such a trial read as an agent failure with `grader_error = 1` only.
  - A replay that records a video prints its verdict before it finishes the video, and a failing video no longer fails
    the replay; `video_rendered` is 1 only when the video was finished.
- 2026-10-14: the instruction says that a moved receptacle jumps alone: what rests in or on it stays where it was (LIBERO-MAX moves one entity; a review saw a basket jump through a can already in it). Text only: the instance, the event, the reference solution, LIBERO's success check and the verifier are unchanged, so the task keeps its name.
