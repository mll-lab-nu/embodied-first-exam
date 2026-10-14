# DexJoCo · click_mouse — frozen instance

You control a Franka Panda arm with a 16-DoF Allegro hand (DexJoCo on MuJoCo 3.4) via Python. **Task:** Put the computer mouse on the magenta mousepad and click its button. Success: the mouse is on the pad (its centre within the pad's 0.15 m radius horizontally and within 0.05 m of the pad's height), the button has been pressed while the mouse was on the pad (button joint more than 0.001 rad past its rest angle), which turns the monitor blue, and the mouse then stays on the pad for 10 consecutive control steps. A click while the mouse is off the pad does nothing.

The mouse lies on the table in front of the monitor; the round magenta mousepad is next to it at lower y. The button is a hinge on the mouse's front half. `s.objects()` gives the live poses of the task objects (`mouse`, `mouse_button`, `mousepad`, `monitor`, `table_top`). DexJoCo's success code (from
`/opt/dexjoco/dexjoco/dexjoco/sim/envs/panda_click_mouse_env.py`; `step()` ends the episode on success or on a task failure):
```python
def _compute_success(self) -> bool:
    # print("mouse_in_mousepad", self._mouse_in_mousepad())
    trigger_active = self._mouse_in_mousepad() and self._display_blue

    if trigger_active:
        self._success_trigger_count += 1
    else:
        self._success_trigger_count = 0

    return self._success_trigger_count >= self._success_trigger_target

def _mouse_in_mousepad(self) -> bool:
    try:
        mouse_pos = self._data.sensor("mouse_pos").data
    except Exception:
        return False
    if self._mousepad_geom_id < 0 or self._mousepad_radius is None:
        return False
    pad_center = self._data.geom_xpos[self._mousepad_geom_id]
    dx, dy, dz = mouse_pos - pad_center
    in_xy = (dx * dx + dy * dy) <= (self._mousepad_radius * self._mousepad_radius)
    in_z = abs(dz) <= _MOUSEPAD_Z_TOL
    return in_xy and in_z

def _detect_click(self) -> bool:
    try:
        joint0 = float(self._data.sensor("mouse_joint0_pos").data)
    except Exception:
        return False
    return (joint0 - self._mouse_joint0_init) > _CLICK_THRESHOLD
```

This is a *fixed scene instance*: object poses, the table height and the robot's start pose never change between
resets. You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a
general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in a fresh process and scored 1 if its episode ends in success, else 0. Also
leave the script that produced it at `/app/output/gen.py`. A trajectory may have at most 50,000 rows
(1000 s of robot time): `save_trajectory` refuses a longer one and the verifier scores it 0. Save a
first trajectory early, improve it, and do not stop before the task is solved.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_dexjoco import Session
s = Session("click_mouse", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact snapshot restore)
s.objects()                        # live task objects: name -> pos, quat_wxyz (bodies) / pos (sites) / qpos (joints)
s.state()                          # DexJoCo's state dict: tcp_pose, gripper_pose (hand joints), INITIAL object poses, table height
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
p["move_ee"]("right", pos, quat_wxyz)      # straight-line + slerp motion of an arm's tcp target, then settle
p["set_hand"]("right", q16)                # interpolate the 16 Allegro joint targets
p["hold"](10); p["set_targets"](row, steps)            # keep every target / send one raw action row
p["get_ee_pose"]("right"); p["get_ee_target"]("right"); p["get_hand"]("right"); p["get_body_pose"](name)
s.render_frame("front")            # RGB uint8 (480, 640, 3); cameras: ['front', 'back', 'left', 'right', 'top0', 'handcam_rgb']; s.render_grid()
s.step(action)                     # one control step (23 values, below) = 1/50 s; returns False once the episode is over
s.record_start(); ...; actions = s.record_stop()   # (T, 23) actions, one row per control step
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'state_sha', 'info'}
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4", cameras=["front"])   # replays from the frozen state into a video
```
The primitives are deliberately thin (tcp target moves, hand joint targets, hold): grasping, pressing, striking and
every other skill are yours to build from them. `s.bodies()` lists every MuJoCo body for `p["get_body_pose"]`.

CLI equivalent of the grader:
`python /opt/tools/rcb_dexjoco.py replay --task click_mouse --instance /app/instance.npz --traj /app/output/trajectory.npz`

## Conventions
- World frame, metres; z up; the robot stands at low x and reaches towards +x. The table top is at z = 0.927. Arm base (`link0`): link0 [-0.75, 0.0, 0.924]. Quaternions are **WXYZ**.
- Action (23): tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro
  joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
  target and stops where contact blocks it); the hand joints are position-controlled. `s.hold_action()` is the no-op.
  At the start the tcp target is [-0.443, -0.0, 1.517] / [0.0, 1.0, 0.0, 0.0].
- Allegro joint order: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger =
  spread, 1-3 = flexion from the knuckle out; thumb 12 = opposition).
  Target ranges (rad, same for every finger slot, thumb last): low [-0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, 0.26, -0.1, -0.19, -0.16], high [0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 1.4, 1.16, 1.64, 1.72]; the simulator clamps
  targets to them.
- Control runs at 50 Hz (10 physics substeps of 2 ms). DexJoCo's own episode cap and real-time pacing are lifted: your
  sessions have no step budget, your wall-clock time is the limit (~330 control steps/s here); only the
  trajectory you hand in is capped (50,000 rows). An episode ends at the first success or task failure; `s.step`
  then refuses further actions until `s.reset()`.
- The simulation repeats bit for bit, for one OpenBLAS thread count: the controller's linear algebra gives slightly
  different results on 1, on 2-3 and on 4 or more threads. This container sets `OPENBLAS_NUM_THREADS=4`, as the verifier's
  does; leave it as it is, or your replays will not match the verifier's. (OpenBLAS runs no more threads than the CPUs
  a process may use: if the tooling warns that it runs fewer than 4, your replays here are not the verifier's.)

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
