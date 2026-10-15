# $name

## Task
iSpatialGym `$task` (family `$family`), upstream subtask `$subtask`, instance 0 ($scene): $description The task is given
only as the goal image (`environment/goal.png`, the head camera's view once it is done), as in iSpatialGym's own
evaluation; the instruction names no object.

## Difficulty
The agent has to work out from one picture what differs between the scene and the goal (which object, which relation,
which pose) and then do it with a mobile bimanual robot it only sees through its own cameras and proprioception, within
$max_steps control steps ($max_steps_s s of simulated time, iSpatialGym's policy budget: twice the length of upstream's own
demonstration of this instance, at least 300). Holding still does not succeed (`hold` in
`scripts/ispatialgym/instances/$task/facts.json`).

## Reference solution
None.

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays of the recorded trajectory agree),
computed in the sidecar; success is iSpatialGym's own geometric success as `run_isg --mode policy` judges it (the BDDL goal
and every measured target within the isg-v2 tolerances x 3, at the same control step; settle-eval off).
`live_matches_replay`, upstream's symbolic success and the success step are reported apart, and so are the
crash-recovery fields; `/logs/verifier/replay.mp4`. `infra_error` = 1 (no verdict on the agent) when `final.json` is
missing, unreadable or not finalized, a replay did not run to its result, or the frozen instance did not rebuild.

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2`: RGB + proprioception through the client; no reset, no object poses, no success predicate |
| Action space | `submit` chunks of `joint_position` (23: base velocity command, trunk, both arms, one command per gripper; iSpatialGym's JoyLo action) streamed at the 30 Hz control rate; `observe` frames or a watch window; stateless `/kinematics` |
| Goal | `environment/goal.png` (copied to `/app/goal.png`): upstream's goal image of this instance, the head camera at 1080×1080 |
| Instance | `environment/sim/instance/`: upstream's scene file, template metadata, BDDL problems and start state (with the measured targets: sidecar only); start-state hash $start_sha |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$$RCB_BEHAVIOR_DATA` (a precondition) |
| Crash recovery | `restart: on-failure:6`; the service journals every control step and resumes the same episode after a crash (resume class `approx`) |
