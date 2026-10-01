# metaworldplus-assembly-i00-standard

Standard-mode twin of `metaworldplus-assembly-i00` (see its README): the same instance and success check, served as a
robot service (`images/metaworld/standard/server_mw.py`, protocol rcb-limited/2.1 = eai-standard/2.1, tool module
`mw_tool`). The agent sees camera RGB-D, the robot's own state and the target point; no object poses, no reset.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras and finish in one episode without
a reset. Under the earlier two-mode protocol (step-capped, success at any step), Codex with GPT-6 Luna (high) solved
28 of 69 MetaWorld+ standard-mode trials.

## Reference solution
`solution/`: the privileged oracle's 95 actions (Meta-World's scripted policy, recorded offline)
submitted through the client, one row per control step.

## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network)
reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.
