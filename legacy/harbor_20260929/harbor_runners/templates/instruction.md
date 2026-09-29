# Task

{{TASK_INSTRUCTION}}

# Observation access

{{OBSERVATION_ACCESS}}

# Rollout procedure

This instruction is the task description. `/rollout/spec.json` describes the
action and observation interfaces, units, timing and permissions; it does not
describe the task goal. Policy observations do not repeat this task description.

You control one continuous TopoGym session. The environment has already reset.
The manager recorded `segment_0` while holding the robot's current control targets
for the configured initial observation steps. These are real simulation steps;
your first policy starts at segment_0's final state, with no reset or time reset.
If the session is already terminal, inspect its result and report it without submitting a policy.

Read `/rollout/session.json` and `/rollout/spec.json`. Each published segment has
`/rollout/segments/segment_N/result.json`, full videos and per-step JSONL logs.
All previously published segments remain available in `/rollout/history.json`.
The result JSON contains the summary, termination reason, feedback and file
descriptors/paths; it does NOT contain the individual steps. Read `steps.jsonl`
for one initial state followed by every saved physics tick. Each row identifies
the control step, physical time, robot measurements and applied action.
`events.jsonl` records action requests, completions, failures and segment end.
Limited mode exposes measured robot state and permitted feedback; explicitly
authorized privileged fields (such as object/world poses) appear under `privileged`.
Video cameras and history fields obey the same observation permissions as policies.

Start by inspecting the initial video and logs:

```bash
topogym-rollout history
topogym-rollout logs --segment 0 --kind steps --start 0 --limit 20
topogym-rollout video --segment 0 --camera combined
topogym-rollout frames --segment 0 --camera combined --output /workspace/segment_0_frames
```

`video` returns the readable MP4 path. If your tools accept video, open that path.
Otherwise `frames` uses ffmpeg to extract up to six evenly spaced frames,
including the first and last, into the new output directory. **Open the returned
PNG paths with your image tool**; reading the paths or JSON alone does not show
the images to your model. These are on-demand video extracts, not separate stored
initial/final observations. Use `--camera NAME` for an authorized individual view.
Use `--frame-index 0 1` to inspect particular video frames. The output directory
must be new; choose a fresh name when repeating an extraction.

After every submission, inspect that segment's result, video and step logs before
choosing the next action. For example, after segment_1:

```bash
topogym-rollout logs --segment 1 --kind steps --start 0 --limit 20
topogym-rollout logs --segment 1 --kind events --start 0 --limit 20
topogym-rollout logs --segment 1 --kind frames --start 0 --limit 20
topogym-rollout frames --segment 1 --camera combined --output /workspace/segment_1_frames
```

Follow `next_start` to read subsequent log pages. Video frames and physics ticks
have different rates; frame-map rows give `video_frame_index`, `source_state_id`,
`physics_step` and `source_sim_time_s`. Match these to the step records instead of
assuming one video frame per step. In explicit no-RGB experiments video commands
are unavailable; the step logs and results still exist.

Write the first policy to `/workspace/segment_1.py`. Export
`create_policy(**parameters)`, returning an object with `act(obs)`; optional
`initialize(context)` and `on_segment_end(obs, result)` must return None.
`act` returns one low-level action mapping or None to finish this segment.
An empty mapping `{}` executes one hold control step; it does not finish a segment.
The existing simulator performs IK for EE actions. Use the units, group names,
gripper field and control mode in `context['action_spec']`; no hardcoded robot schema.

Policy `obs` contains RGB arrays, measured robot proprioception,
state references and execution receipts. Arrays and mappings are read-only.
For example, robot groups are under `obs['robot'][group]` and contain
`tcp_position_world_m`, `tcp_orientation_wxyz`, `joint_position_rad` and measured
finger positions. `obs['execution_state']['control_steps']` counts this segment's
steps. Only an explicitly privileged experiment includes `obs['privileged']`.

Example, to exercise two hold steps (not a solution):

```python
from topogym.planning.base import ActionSequencePolicy

def create_policy():
    return ActionSequencePolicy([{}, {}])
```

```bash
topogym-rollout submit /workspace/segment_1.py --request-id first --wait
topogym-rollout status
```

The returned `result_path` points to a sealed segment JSON with `reason`,
`feedback`, `media`, state references and evidence completeness. Inspect that
result, video and step logs before designing segment_2.py. Repeat
until the task is terminal or your trial ends. This never resets between segments.
Results and artifact mappings appear atomically after recording completes;
`finished` means a result is available, not that the puzzle is solved.

Optional parameters: `submit FILE --params parameters.json --request-id ID --wait`.
Submission freezes this single source file plus JSON parameters. Imports from
installed libraries work; imports of other workspace scripts are not supported.
The policy runs as a separate user with no API credentials, worker access or
network. It must return actions through `act`; it cannot create/reset/step Env.

If a CLI wait times out, use `topogym-rollout result --request-id ID --wait`.
Reusing the same ID and source is idempotent; changed contents require a new ID.
Only one submission can run at a time. CLI exit 0 means a valid receipt, exit 2
means rejection, exit 1 a transport/internal error, and exit 3 a wait timeout.
Never alter `/rollout`, reward files, private evidence or instance configuration.

When the experiment enables token budgets, `/rollout/budget.json` shows the
confirmed input/output totals, limits and pending requests. Unknown or in-flight
usage is not zero. Each trial has its own cumulative budget; new segments and
rewinds do not reset it. The manager stops the agent and policy on budget failure,
and a physically solved task still receives reward 0 if its budget fails.
Only report success when the simulator reports `task_success: true`. If evaluation
is unavailable or the session ends without success, report the observed outcome
with evidence; do not infer success from a finished segment or appearance alone.
The outer Harbor trial also has a wall time limit. Stop when `task_terminated` is true, the time limit is reached, or the
session reports terminal/faulted/closed; do not try to create another episode.
