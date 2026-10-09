# bigym2-dishwasher-close-i00-standard

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `bigym2-dishwasher-close-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `dishwasher-close` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); positive example graded 1 by the separate verifier: bigym2-dishwasher-close-i00-priv__BtaZZZZ (run codex-gpt6_luna-medium, 2026-10-08, on an earlier text of the privileged task; regraded by its current verifier); human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Push the dishwasher racks in and close the door. (BiGym 2.0 `dishwasher_close`; the robot as a service: its three onboard cameras and its proprioception only, one
episode.)

## Difficulty
Three articulated joints low in front of the robot (two racks and a door), pushed fully closed to within 5% of their travel, which takes squatting and leaning. In standard mode the agent sees only the robot's cameras (the head camera looks down at the hands at the
start) and proprioception, acts through the client, and gets one episode with no reset.

## Reference solution
None (as `bigym2-dishwasher-close-i00-privileged`).

## Verification
The sim sidecar judges the live episode with BiGym's own success check (`is_success`: the task's success held for 1 s,
no fall), then replays the recorded episode in a fresh simulator; `tests/grade.py` reads `/data/final.json`: pass iff
the live run and the replay succeed and end in the same state. Success condition: the door and both racks are closed to within 5% of their travel: the door within about 4.5 degrees of shut, the lower rack within 0.025 m and the upper rack within 0.0225 m of fully in. No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Service | `environment/sim/server.py` (the BiGym 2.0 adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Observations | three onboard RGB cameras (`RCB_IMAGE_HW`, default 84 px square, as upstream renders them, 60° field of view); upstream's low-dimensional observation (joints, grippers, tracked pelvis pose) |
| Horizon | 4650 control steps (93 s at 50 Hz) |
