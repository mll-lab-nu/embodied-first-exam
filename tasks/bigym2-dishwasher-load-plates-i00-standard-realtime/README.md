# bigym2-dishwasher-load-plates-i00-standard-realtime

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `bigym2-dishwasher-load-plates-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `dishwasher-load-plates` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); no positive example yet; human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Take the plates from the dish rack and gently slot them into the dishwasher's lower rack. (BiGym 2.0 `dishwasher_load_plates`; the robot as a service on a clock that does not stop: its three onboard cameras and
its proprioception only, one episode.)

## Difficulty
Two plates moved from a drainer into the dishwasher's low rack and stood on edge; a dropped plate ends the episode. In standard-realtime mode the robot keeps running at 50 Hz while the agent thinks, holding its last
command (standing still), so the agent drives it from a controller program of its own.

## Reference solution
None (as `bigym2-dishwasher-load-plates-i00-privileged`).

## Verification
As `bigym2-dishwasher-load-plates-i00-standard`: the sidecar judges the live episode with BiGym's own success check and replays the commands the
simulator executed in a fresh simulator; `tests/grade.py` reads `/data/final.json`. Success condition: each of the two plates stands on edge in the dishwasher's lower rack: its face toward your left or right (its axis within 20 degrees of the robot's left or right at the start), touching the lower rack, held by neither gripper; both plates at once.
A plate touching the floor ends the episode as a failure. No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Service | `environment/sim/rcb_realtime.py` (eai-standard/2.3) with the BiGym 2.0 adapter `server.py`, `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Clock | real time (`RCB_SLOWDOWN`, default 1) from the first `submit` |
| Horizon | 3150 control steps (63 s at 50 Hz) |
