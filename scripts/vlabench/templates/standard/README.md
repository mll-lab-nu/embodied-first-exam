# vlabench-{{dash}}-i00-standard

## Task
VLABench's `{{task}}` as a robot service: a Franka Panda arm at a table, instructed **"{{instruction}}"**
({{instruction_kind}}), on the same frozen instance as `vlabench-{{dash}}-i00-privileged`. The simulator runs in the
`sim` sidecar (`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: four cameras
(RGB 320×320, depth on request, calibrated), the robot's own state, and joint-position chunks. One episode, no reset,
no object poses; nothing to hand in.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with joint-position targets, and
finish in one episode without a reset, on top of the task's own reasoning ({{instruction_kind}}).

## Reference solution
`solution/`: the privileged oracle's {{n_actions}} control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at the task's success (or at the {{max_steps}}-step technical cap, when the agent's
time is up, or on a simulator error) and writes that live verdict to `/data/final.json` (`graded_by = "live"`);
nothing is replayed to grade it (owner, 2026-10-17, board 0151). The scene is checked against the frozen instance (its
initial state and compiled model hashes) when it is built, and its start state when the episode begins (a mismatch is
`instance_mismatch`, infrastructure). `tests/grade.py` (separate sandbox, no network) grades `final.json`:
`success = live_success`. The video (`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and
never changes it.

## Details
| | |
|---|---|
| Actions | `joint_position` (9, float64): absolute targets for the 7 arm joints (rad) and the 2 fingers (m), 0.1 s per control step |
| Episode cap | {{max_steps}} control steps ({{robot_seconds}} s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |{{instruction_row}}

## Change Log
- 2026-10-16 (board 0136): the sim collect hook waits for the replay video until 2880 s after the episode ends (was 1470 s; `timeout_sec` 1500 -> 2910); the verdict keeps its 1440 s bound. The video replays the graded episode once more after the verdict, so a slow verdict left it no time. Video only: the verdict, the physics and the pass rule are unchanged, so results from before this date stay valid.
- 2026-10-17 (owner, board 0150/0151): graded by the live episode: `success` = VLABench's own success check reached in the episode the sim service ran (the same rule, judged as it ran), and no grading replay runs (no `replay_success` / `deterministic` any more; `final.json` has `graded_by = "live"`, `replays = 0`, `reward.json` `graded_by_live = 1`). The video is one render pass over the trajectory after the verdict, as before. The scene's start is checked when the episode begins: a scene that does not rebuild the frozen instance gives up as infrastructure (`instance_mismatch`). The scene, instance, pass rule, step cap and the agent's interface are unchanged, so the task keeps its name; archived verdicts are the same under the live rule, except 5 trials whose old video render ran out of time (recorded `infra_error`), which the live rule grades (all 0).
