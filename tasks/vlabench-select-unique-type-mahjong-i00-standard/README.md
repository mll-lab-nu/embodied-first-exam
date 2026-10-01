# vlabench-select-unique-type-mahjong-i00-standard

Standard-mode twin of `vlabench-select-unique-type-mahjong-i00` (see its README): the same instance and success check, served as a robot
service (`environment/sim/server.py` on `rcb_service.py`, protocol `eai-standard/2.1`). The agent sees four cameras
and the robot's own state; no object poses, no reset.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with joint-position targets, and
finish in one episode without a reset, on top of the task's own reasoning (a direct command).

## Reference solution
`solution/`: the privileged oracle's 107 control steps (recorded offline; see its README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at the task's success, replays the recorded episode in a fresh simulator and writes
`/data/final.json`; `tests/grade.py` (separate sandbox, no network) grades it: `success = live_success ∧
replay_success ∧ deterministic`.
