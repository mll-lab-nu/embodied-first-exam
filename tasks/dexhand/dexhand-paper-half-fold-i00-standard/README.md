# dexhand-paper-half-fold-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-paper-half-fold-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `paper_half_fold` / seed 0 |
| Oracle | `full` — solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (620 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Fold the sheet of paper on the table in half: lift its free half over its fixed half, press a permanent crease along the marked center line, take the hand away, and leave the folded sheet lying on the table. The 160 x 100 mm sheet (1.28 g) lies flat on the table top. Its left half is glued to a backing patch next to a dark clamp and cannot move; the right half is free, and its last 25 mm overhang the table edge. Success requires 100 consecutive 50 Hz control samples (2 s) in which no part of the hand touches the paper and all of these hold: fold angle of the free half above 2.6 rad, permanent (plastic) crease on the center line above 2.2 rad on average with at least 90% of its hinges above 2.2 rad, free edge within 18 mm of the fixed edge, stretch below 8%, and the whole sheet over the table top: every paper vertex within the table's extent (x from -0.345 to 0.135 m, y from -0.30 to 0.30 m) and at most 2 mm below the table top (z >= 0.298 m). The episode ends with that success, or fails immediately and permanently if any paper vertex sinks more than 10 mm below the table top (z < 0.29 m, for example bent down over the table edge) or leaves the workspace box (x from -0.03 to 0.19 m, y from -0.09 to 0.09 m, z <= 0.45 m), if the paper stretches by more than 8%, or the simulation becomes unstable. A fold that springs back, a crease that is not permanent, or a hand still touching the paper is not a success. Only the robot's motor targets act on the paper; there are no grasp welds, scripted paper motion or applied forces. The episode allows at most 1500 controls at 50 Hz (30 s).

## Difficulty
Hard. The sheet is thin, light and passive: the free half must be lifted from a flat start (its overhang is the only
easy access), turned over by about 180 degrees, and pressed hard enough at the fold line to exceed the material's
yield, without stretching or tearing the shell, pushing it off the table edge, or ending with any finger on the
paper. A fold that is only held springs back on release, and the crease must be permanent at nearly every hinge of
the fold line. All four stages (fold, permanent crease, release onto the table, 2 s hold) are required.

## Reference solution
`solution/trajectory.npz` holds the 1,108 Sharpa Wave motor-target rows of the accepted physical episode (a held
contact fold, release, a localized low-load crease press with a pre-flexed middle finger, withdrawal and a 2 s
released hold), followed by 250 copies of its last row. The accepted rows replay bit for bit on this frozen scene and
succeed at row 1,108, where the episode ends; the hold rows are a margin for float32 transport (rows rounded to
float32 finish the hold window one control later). The privileged oracle hands the rows in as the deliverable; the
standard oracle submits them through the client, one row per control. The solution is mounted only for the oracle
agent; nothing in the agent's environment or image locates it.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (620 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

## Verification
standard mode. Privileged: the isolated verifier reads only `actions` and `hand` from `/app/output/trajectory.npz`,
rebuilds the frozen scene for that hand and replays the rows twice in fresh processes; reward 1 iff both replays
succeed and their final state hashes are identical. Standard: the trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.

The verdict is computed from simulator state only: fold angle > 2.6 rad, mean plastic crease angle on the fold line
> 2.2 rad with coverage >= 0.9, free-edge to fixed-edge distance < 18 mm, strain < 0.08, every paper vertex over the
table top and not below it, and no hand contact on the paper, all held for 100 consecutive 50 Hz samples. Fail-fast,
permanent failures (checked at every 0.5 ms physics substep): any paper vertex more than 10 mm below the table top,
any vertex outside the workspace box (x -0.03..0.19 m, y -0.09..0.09 m, z <= 0.45 m), strain above 0.08, unstable
physics, or 1,500 controls without success. A trajectory whose width does not match its recorded hand (28 Sharpa,
26 Wuji), with a wrong task or actuator order, out-of-range, non-finite or oversized is rejected (reward 0). The
no-op, a fold without the crease press, an early stop before the 2 s hold and a pull of the sheet over the table edge
all score 0. Wuji Hand 2.2 composes on the same wrist stage and is graded the same way.
Release status is provisional pending human review.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand family of this task. The scene is the
accepted T06 paper-fold scene (its authoring tooling is kept outside the repository): `scene_sharpa.xml` is its frozen
compiled-model XML, whose compiled binary model is byte-identical to the accepted `model.mjb`
(sha256 `665706cd6ef8a63dddba743a9d715e7ca289ccc16f9f0514c4cbcd72693afd51`, checked at every session start), and
`shell.py` is the unchanged elastic/plastic shell. The runtime keeps the original order of operations, so the
accepted controls reproduce every saved control-boundary state exactly; it adds hand selection, fail-fast support
checks, the on-table condition, terminal success and snapshots. Sharpa Wave assets: MuJoCo Menagerie
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0), with the accepted task-local contact geometry (distal shell
colliders on every finger, source elastomer/DP colliders on the middle fingertip). Wuji Hand 2.2:
`wuji-technology/wuji-description` `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted at the same frame.

Modelling scope: a 9 x 5 triangular MuJoCo flex shell (160 x 100 mm, 1.28 g) with a task-local elastic/plastic
bending-memory law; uncalibrated material coefficients; the left half is adhered to a visible backing (pinned
vertices); effective 0.7 mm contact thickness; finite contact compliance. This is a reduced passive-paper model, not a
fibre or adhesive-peel model.
