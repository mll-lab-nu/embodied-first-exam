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
`success` = the live episode's success, judged by the sim sidecar at every control step the episode runs; nothing
replays it (2026-10-17). Success is iSpatialGym's own geometric success as `run_isg --mode policy` judges it (the BDDL goal
and every measured target within the isg-v2 tolerances x 3, held over the last $settle_steps control steps with the task's objects and the robot at rest: upstream's settle-eval).
Upstream's symbolic success and the success step are reported apart, and so are the crash-recovery fields; the video
(`/logs/verifier/live.mp4`, the head camera) is recorded during the episode (a video-only render, `replay.mp4`, only
when it is missing) and never decides anything. The frozen start
is checked when the sidecar builds the scene, before the agent is served. `infra_error` = 1 (no verdict on the agent) when
`final.json` is missing, unreadable or not finalized, the service never ended the episode, it gave up after crashes not
all inside the agent's calls, or the frozen start did not rebuild (`instance_mismatch`).

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2`: RGB + proprioception through the client; no reset, no object poses, no success predicate |
| Action space | `submit` chunks of `joint_position` (23: base velocity command, trunk, both arms, one command per gripper; iSpatialGym's JoyLo action) streamed at the 30 Hz control rate; `observe` frames or a watch window; stateless `/kinematics` |
| Goal | `environment/goal.png` (copied to `/app/goal.png`): upstream's goal image of this instance, the head camera at 1080×1080 |
| Instance | `environment/sim/instance.json`, byte-identical to the privileged twin's: the start only (scene, template keys the loader reads, start-only TRO, objects without upstream's role names); `environment/sim/goal.json` (sidecar only) restores upstream's targets onto it, checked by sha256; start-state hash $start_sha |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$$RCB_BEHAVIOR_DATA` (a precondition) |
| Crash recovery | `restart: on-failure:6`; the service journals every control step and resumes the same episode after a crash (resume class `approx`) |
