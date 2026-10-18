# dexhand-paper-half-fold-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-paper-half-fold-i00-standard` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `paper_half_fold` |
| Oracle | `full` — solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (620 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

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

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (620 rows of motor targets, physical contact only). With `DEXHAND_HAND=wuji` set for the oracle, `solve.sh` hands it in instead of the Sharpa Wave rows; the verifier replays it with the Wuji Hand 2.2.

## Verification
privileged mode. Privileged: the isolated verifier reads only `actions` and `hand` from `/app/output/trajectory.npz`,
rebuilds the frozen scene for that hand and replays the rows twice in fresh processes; reward 1 iff both replays
succeed and their final state hashes are identical. Standard: the trusted simulator service journals every executed
row; its collect hook replays the episode twice in fresh processes, and the isolated verifier grades only those
service artifacts (live success, both replay successes, identical hashes, replay hash equal to the live hash).

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

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: 30 Harbor 0.23 trials of the six essential families (12 oracle, 12 nop, 6 Wuji smoke; rcb_monitor samples every 5 s, eai-dexhand:0.2.0, CPU-only, 2026-10-14) plus the hamburger and paper oracle/nop trials: agent container peak <= 0.03 GiB; one fresh replay process 0.25-0.32 GiB max RSS (os.wait4; paper 0.31 GiB, hamburger 0.28 GiB), the privileged verifier runs two at once (<= 0.65 GiB); standard sim service peak 0.65 GiB (VmHWM, held_joystick oracle episode), paper 0.51 GiB; one core per replay process; x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3 GiB each)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: 8 GiB lets an agent run about twenty 0.3 GiB simulator sessions (pot/sweep: three or four 2 GiB sessions) next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details

### Notes
Source: `scripts/dexhand/families/paper_half_fold/` (generated by `scripts/dexhand/generate.py`). The scene is the
accepted T06 paper-fold scene (`scripts/scene_expansion/repairs/paper_recovery/`): `scene_sharpa.xml` is its frozen
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

### Change Log
- 2026-10-16 (board 0136, video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The verdict, the replays and `reward.json` are unchanged; earlier results stay valid.
