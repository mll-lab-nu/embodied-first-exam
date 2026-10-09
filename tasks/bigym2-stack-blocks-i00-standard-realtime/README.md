# bigym2-stack-blocks-i00-standard-realtime

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `bigym2-stack-blocks-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `stack-blocks` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); positive example graded 1 by the separate verifier: bigym2-stack-blocks-i00-privileg__Rz4Pgdi (run codex-gpt6_luna-medium, 2026-10-08, on an earlier text of the privileged task; regraded by its current verifier); human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Move the blocks to the other table and stack them on the green pad. (BiGym 2.0 `stack_blocks`; the robot as a service on a clock that does not stop: its three onboard cameras and
its proprioception only, one episode.)

## Difficulty
Loco-manipulation over the longest horizon (175 s): carry three blocks from one table to a pad on another and stack them within 5 cm; a block on the floor ends the episode. In standard-realtime mode the robot keeps running at 50 Hz while the agent thinks, holding its last
command (standing still), so the agent drives it from a controller program of its own.

## Reference solution
None (as `bigym2-stack-blocks-i00-privileged`).

## Verification
As `bigym2-stack-blocks-i00-standard`: the sidecar judges the live episode with BiGym's own success check and replays the commands the
simulator executed in a fresh simulator; `tests/grade.py` reads `/data/final.json`. Success condition: the three blocks form one stack on the green pad: the lowest touching the pad, each of the others touching the block below it, at least 0.03 m higher and within 0.05 m of it horizontally; no block held by a gripper.
A block touching the floor ends the episode as a failure. No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Service | `environment/sim/rcb_realtime.py` (eai-standard/2.3) with the BiGym 2.0 adapter `server.py`, `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Clock | real time (`RCB_SLOWDOWN`, default 1) from the first `submit` |
| Horizon | 8750 control steps (175 s at 50 Hz) |
