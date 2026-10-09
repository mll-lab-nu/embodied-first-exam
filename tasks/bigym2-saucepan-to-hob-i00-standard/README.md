# bigym2-saucepan-to-hob-i00-standard

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `bigym2-saucepan-to-hob-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `saucepan-to-hob` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); no positive example yet; human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Take the saucepan out of the cabinet and gently set it on the hob. (BiGym 2.0 `saucepan_to_hob`; the robot as a service: its three onboard cameras and its proprioception only, one
episode.)

## Difficulty
Two stages low and high: open the cabinet under the counter, take the saucepan out, set it on the hob, released. In standard mode the agent sees only the robot's cameras (the head camera looks down at the hands at the
start) and proprioception, acts through the client, and gets one episode with no reset.

## Reference solution
None (as `bigym2-saucepan-to-hob-i00-privileged`).

## Verification
The sim sidecar judges the live episode with BiGym's own success check (`is_success`: the task's success held for 1 s,
no fall), then replays the recorded episode in a fresh simulator; `tests/grade.py` reads `/data/final.json`: pass iff
the live run and the replay succeed and end in the same state. Success condition: the saucepan touches the hob and is held by neither gripper (it starts inside the closed cabinet under the counter). No oracle; human review in PR #123 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| Service | `environment/sim/server.py` (the BiGym 2.0 adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Observations | three onboard RGB cameras (`RCB_IMAGE_HW`, default 84 px square, as upstream renders them, 60° field of view); upstream's low-dimensional observation (joints, grippers, tracked pelvis pose) |
| Horizon | 4650 control steps (93 s at 50 Hz) |
