# LIBERO-MAX · {{suite}} · {{event_words}} — instance {{inst}}

A **Franka Panda** arm (LIBERO on robosuite / MuJoCo) at a table. **Task: {{instruction}}**
The scene is one frozen LIBERO-MAX case: a LIBERO-PRO variant of a {{suite}} task ({{pro_category}}), with one online
event: the first time the gripper comes within {{trigger_m}} m of `{{trigger_object}}`, LIBERO-MAX changes the scene
once ({{event_detail}}). You have the full simulator state, so you can see the change happen (`s.state()["event_fired"]`).

## What you hand in
`/app/output/trajectory.npz` with key `actions`: LIBERO's native control steps, shape `(T, 7)`, 1 ≤ T ≤ {{max_steps}}
(the {{suite}} step limit), one row per control step (1/20 s), starting after LIBERO's 10 warm-up steps (no-ops with the
gripper open, already part of the frozen start). Write it with `s.save_trajectory()` so the format is right. Leave the
script that produced it at `/app/output/gen.py`.

## Success
The verifier replays your actions from the frozen start in a separate sandbox (twice, each in a fresh process; the
event is applied by the same trigger), and applies LIBERO's own success check: the task's goal, all of
{{goal_text}}
The episode ends the moment the check holds, so the trajectory must end there: actions after that make it invalid.
`s.check()` computes exactly this check on the current state.

## Tooling (`/opt/tools/lmx_tool.py`, importable as `lmx_tool`)
```python
import numpy as np, lmx_tool
s = lmx_tool.Session("/app/instance.json")  # builds the frozen scene; ONE Session per Python process
st = s.state()        # eef {pos, quat_wxyz}, gripper_qpos, joint_pos/vel, objects / fixtures {name: pos, quat_wxyz},
                      #   articulations {joint: position} (drawer slides in m, door and knob hinges in rad),
                      #   goal, instruction, success, done, event_fired, event_step, control_steps, steps_left
r = s.step([dx, dy, dz, drx, dry, drz, grip])   # one control step -> {"success", "done", "event_fired", ...}
s.check()             # LIBERO's success check on the current state
s.save_trajectory()   # the actions so far -> /app/output/trajectory.npz
lmx_tool.replay_fresh(A)   # replay A in a NEW process (what the verifier does) -> {"success", "state_sha", ...}
img = s.render("agentview", 256)   # RGB, upright; cameras "agentview" and "wrist"; depth=True adds metric depth
```
- **One simulator per process.** Some LIBERO-PRO variants do not rebuild bit-exactly a second time in the same
  process, so a second `Session` in one process raises an error: to start over, start a new Python process (as many
  times as you like); `replay_fresh` does this for you.
- Action `[dx, dy, dz, drx, dry, drz, grip]`, each clipped to [-1, 1]: LIBERO's operational-space controller (OSC_POSE)
  moves the hand's target by `[dx, dy, dz]` × {{pos_scale}} m and rotates it by `[drx, dry, drz]` × {{rot_scale}} rad
  (axis-angle, world frame) per control step; `grip` +1 closes, -1 opens the gripper.
- World frame: metres; the robot's base is at {{robot_base}} facing +x: x forward (across the table), y to the robot's
  left, z up; quaternions are w x y z.
- Everything in `s.env` (robosuite's LIBERO environment) and `s.sim` is readable (privileged mode).

## Rules
- Write your own controller. Do not use LIBERO's demonstrations, LIBERO-MAX's policies or any published solution.
- Only the actions count: editing the simulator state while debugging changes nothing in the replay.
- Save a working trajectory early, then improve it; do not stop early.
