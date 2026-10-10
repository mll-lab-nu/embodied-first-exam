# bigym2-move-two-plates-i00-standard

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `bigym2-move-two-plates-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `move-two-plates` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); no positive example yet; human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Take both plates out of the left dish rack and gently stand them in the right dish rack. (BiGym 2.0 `move_two_plates`; the robot as a service: its three onboard cameras and its proprioception only, one
episode.)

## Difficulty
Bimanual transport of two thin plates between racks, each re-seated upright in a slot within 5 cm and 20 degrees and released; a dropped plate ends the episode. In standard mode the agent sees only the robot's cameras (the head camera looks down at the hands at the
start) and proprioception, acts through the client, and gets one episode with no reset.

## Reference solution
None (as `bigym2-move-two-plates-i00-privileged`).

## Verification
The sim sidecar judges the live episode with BiGym's own success check (`is_success`: the task's success held for 1 s,
no fall), then replays the recorded episode in a fresh simulator; `tests/grade.py` reads `/data/final.json`: pass iff
the live run and the replay succeed and end in the same state. Success condition: each plate stands in a slot of the right-hand rack: its centre within 0.05 m of one of that rack's six slot points, standing on edge with its face toward your right (its axis within 20 degrees of the robot's right at the start, as the plates stand now; a plate turned around does not count), touching the right-hand rack, not touching the table, held by neither gripper; both plates at once. A plate touching the floor ends the episode as a failure. No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Service | `environment/sim/server.py` (the BiGym 2.0 adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Observations | three onboard RGB cameras (`RCB_IMAGE_HW`, default 84 px square, as upstream renders them, 60° field of view); upstream's low-dimensional observation (joints, grippers, tracked pelvis pose) |
| Horizon | 2300 control steps (46 s at 50 Hz) |
