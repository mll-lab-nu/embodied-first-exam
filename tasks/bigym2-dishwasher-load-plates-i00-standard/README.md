# bigym2-dishwasher-load-plates-i00-standard

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `bigym2-dishwasher-load-plates-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `dishwasher-load-plates` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); no positive example yet; human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Take the plates from the dish rack and gently slot them into the dishwasher's lower rack. (BiGym 2.0 `dishwasher_load_plates`; the robot as a service: its three onboard cameras and its proprioception only, one
episode.)

## Difficulty
Two plates moved from a drainer into the dishwasher's low rack and stood on edge; a dropped plate ends the episode. In standard mode the agent sees only the robot's cameras (the head camera looks down at the hands at the
start) and proprioception, acts through the client, and gets one episode with no reset.

## Reference solution
None (as `bigym2-dishwasher-load-plates-i00-privileged`).

## Verification
The sim sidecar judges the live episode with BiGym's own success check (`is_success`: the task's success held for 1 s,
no fall), then replays the recorded episode in a fresh simulator; `tests/grade.py` reads `/data/final.json`: pass iff
the live run and the replay succeed and end in the same state. Success condition: each of the two plates stands on edge in the dishwasher's lower rack: its face toward your left or right (its axis within 20 degrees of the robot's left or right at the start), touching the lower rack, held by neither gripper; both plates at once. A plate touching the floor ends the episode as a failure. No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Service | `environment/sim/server.py` (the BiGym 2.0 adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Observations | three onboard RGB cameras (`RCB_IMAGE_HW`, default 84 px square, as upstream renders them, 60° field of view); upstream's low-dimensional observation (joints, grippers, tracked pelvis pose) |
| Horizon | 3150 control steps (63 s at 50 Hz) |
