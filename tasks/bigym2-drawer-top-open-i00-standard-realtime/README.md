# bigym2-drawer-top-open-i00-standard-realtime

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `bigym2-drawer-top-open-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `drawer-top-open` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); positive example graded 1 by the separate verifier: bigym2-drawer-top-open-i00-privi__BR52Quk (run codex-gpt6_luna-medium, 2026-10-08, on an earlier text of the privileged task; regraded by its current verifier); human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Open the top drawer of the kitchen cabinet. (BiGym 2.0 `drawer_top_open`; the robot as a service on a clock that does not stop: its three onboard cameras and
its proprioception only, one episode.)

## Difficulty
Grasp a drawer handle and pull the drawer at least 90% open while the controller keeps the robot standing against the pull. In standard-realtime mode the robot keeps running at 50 Hz while the agent thinks, holding its last
command (standing still), so the agent drives it from a controller program of its own.

## Reference solution
None (as `bigym2-drawer-top-open-i00-privileged`).

## Verification
As `bigym2-drawer-top-open-i00-standard`: the sidecar judges the live episode with BiGym's own success check and replays the commands the
simulator executed in a fresh simulator; `tests/grade.py` reads `/data/final.json`. Success condition: the top drawer is out to within 10% of its full travel (within about 0.038 m of fully open).
No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Service | `environment/sim/rcb_realtime.py` (eai-standard/2.3) with the BiGym 2.0 adapter `server.py`, `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Clock | real time (`RCB_SLOWDOWN`, default 1) from the first `submit` |
| Horizon | 1350 control steps (27 s at 50 Hz) |
