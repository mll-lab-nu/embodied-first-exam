# $name

## Task
iSpatialGym `$task` (family `$family`), upstream subtask `$subtask`, instance 0 ($scene): $description The task is given
only as the goal image (`environment/goal.png`, the head camera's view once it is done), as in iSpatialGym's own
evaluation; the instruction names no object.

## Difficulty
The agent has the simulator and every object's state, but nothing says which object, relation or pose the picture asks
for: it has to work that out from one image, then deliver one open-loop trajectory of at most $max_steps control steps
($max_steps_s s of simulated time, iSpatialGym's policy budget) that does it from the frozen start. Holding still does not
succeed (`hold` in `scripts/ispatialgym/instances/$task/facts.json`).

## Reference solution
None.

## Verification
The verifier restores this task's `goal.json` onto the frozen start (`tests/instance.json`, byte-identical to the
agent's `environment/instance.json` and to the standard twin's), checks the result against upstream's own TRO by
sha256, and replays `/app/output/trajectory.npz` in two fresh processes: `success` = both replays reach iSpatialGym's
geometric success as `run_isg --mode policy` judges it (the BDDL goal and every measured target within the isg-v2
tolerances x 3, held over the last $settle_steps control steps with the task's objects and the robot at rest: upstream's settle-eval) and end in the same state. `bad_trajectory` (unreadable, not
`(T, 23)` finite, more than $max_steps rows) scores 0; a replay that dies or times out, a failed restore or a start that
does not rebuild is `infra_error` + `grader_error`. `/logs/verifier/replay.mp4`.

## Details
| | |
|---|---|
| Agent's container | eai-ispatialgym with every BDDL problem, the eval data's repository id and folder names, the project URLs, tests and docs removed at build; the build fails if any is left or if a scripted expert, sampler, task spec or eval-data file is in the image (the public release ships none) (`environment/scrub/scrub.sh`); this task's start-only BDDL problem is written from the image's own copy |
| Action space | `s.step(a)`: 23 floats (base velocity command, trunk, both arms, one command per gripper; iSpatialGym's JoyLo action), one 30 Hz control step |
| Goal | `environment/goal.png` (copied to `/app/goal.png`): upstream's goal image of this instance, the head camera at 1080×1080 |
| Instance | `environment/instance.json` = `tests/instance.json`: the start only (scene, template keys the loader reads, start-only TRO, objects without upstream's role names); start-state hash $start_sha |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$$RCB_BEHAVIOR_DATA` (a precondition) |
