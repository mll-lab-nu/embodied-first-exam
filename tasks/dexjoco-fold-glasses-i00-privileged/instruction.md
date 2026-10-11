# DexJoCo · fold_glasses — frozen instance

You control a Franka Panda arm with a 16-DoF Allegro hand (DexJoCo on MuJoCo 3.4) via Python. **Task:** Fold both temples of the glasses and put the glasses into the open case. Success: both temple hinges past 1.1 rad AND the glasses' centre inside the case (within 0.145 m of the case centre in x and y, between 0.045 m below and 0.0275 m above it), held for 50 consecutive control steps.

Open glasses lie on the table; the open case is next to them. Each temple is a hinge (`temple_0`, `temple_1`). `s.objects()` gives the live poses of the task objects (`glasses`, `temple_0`, `temple_1`, `case`, `table_top`). DexJoCo's success code (from
`/opt/dexjoco/dexjoco/dexjoco/sim/envs/panda_fold_glasses_env.py`; `step()` ends the episode on success or on a task failure):
```python
def _compute_success(self):
    # Read the glass position in world coordinates
    glass_pos_world = np.array(self._data.sensor("glass_pos").data, dtype=np.float64)

    glass_body_id = self._model.body("glass").id
    glass_pos_world_2 = np.array(self._model.body_pos[glass_body_id], dtype=np.float64)
    # print("Debug: glass_pos_world (sensor):", glass_pos_world)
    glass_quat_world = np.array(self._data.sensor("glass_quat").data, dtype=np.float64)
    # print("Debug: glass_quat_world (sensor):", glass_quat_world)

    # Read the world position of the open_box (assuming no rotation)
    box_pos_world = None
    body_id = self._model.body("open_box").id
    box_pos_world = np.array(self._model.body_pos[body_id], dtype=np.float64)

    # Transform from world coordinates to box-local coordinates
    glass_local = glass_pos_world - box_pos_world

    # Inner cavity bounds of the box (derived from the XML, assuming `size` is half-extent)
    x_half = 0.145    # = 0.1475 - 0.0025
    y_half = 0.145
    z_min = -0.045
    z_max =  0.0475
    inside_x = (-x_half <= glass_local[0] <= x_half)
    inside_y = (-y_half <= glass_local[1] <= y_half)
    inside_z = (z_min  <= glass_local[2] <= z_max - 0.02)

    # Original joint angle conditions
    glass_joint_0_pos = self._data.sensor("glass_joint_0_pos").data
    glass_joint_1_pos = self._data.sensor("glass_joint_1_pos").data
    j0 = float(glass_joint_0_pos[0])
    j1 = float(glass_joint_1_pos[0])

    if j0 > 1.1 and j1 > 1.1:
        pass
        # print("-----Glass folded!-----")
    trigger_active = (
        (j0 > 1.1)
        and (j1 > 1.1)
        and inside_x
        and inside_y
        and inside_z
    )

    if trigger_active:
        # Increment counter if the condition is met
        self._success_trigger_count += 1
    else:
        # Reset counter if the condition is not met
        self._success_trigger_count = 0

    # Return success if the condition has been met 10 times consecutively
    return self._success_trigger_count >= self._success_trigger_target
```

This is a *fixed scene instance*: object poses, the table height and the robot's start pose never change between
resets. You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a
general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in a fresh process and scored 1 if its episode ends in success, else 0. Also
leave the script that produced it at `/app/output/gen.py`. A trajectory may have at most 50,000 rows
(1000 s of robot time): `save_trajectory` refuses a longer one and the verifier scores it 0. You have
90 minutes of wall clock: save a first trajectory early, improve it, and do not stop before the task is solved.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_dexjoco import Session
s = Session("fold_glasses", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
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
`python /opt/tools/rcb_dexjoco.py replay --task fold_glasses --instance /app/instance.npz --traj /app/output/trajectory.npz`

## Conventions
- World frame, metres; z up; the robot stands at low x and reaches towards +x. The table top is at z = 0.962. Arm base (`link0`): link0 [-0.75, 0.0, 0.924]. Quaternions are **WXYZ**.
- Action (23): tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro
  joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
  target and stops where contact blocks it); the hand joints are position-controlled. `s.hold_action()` is the no-op.
  At the start the tcp target is [-0.443, -0.0, 1.517] / [0.0, 1.0, 0.0, 0.0].
- Allegro joint order: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger =
  spread, 1-3 = flexion from the knuckle out; thumb 12 = opposition).
  Target ranges (rad, same for every finger slot, thumb last): low [-0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, 0.26, -0.1, -0.19, -0.16], high [0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 1.4, 1.16, 1.64, 1.72]; the simulator clamps
  targets to them.
- Control runs at 50 Hz (10 physics substeps of 2 ms). DexJoCo's own episode cap and real-time pacing are lifted: your
  sessions have no step budget, your wall-clock time is the limit (~380 control steps/s here); only the
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
