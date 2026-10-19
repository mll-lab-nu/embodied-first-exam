# RoboWits · stand_pages — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Stand the two pages up on the table so that they brace each other. They start
joined like an open book: the stabilizing bar already runs through the eyelets of both pages as a hinge pin, so
nothing has to be inserted.

RoboWits' own text for this task (in its env file) reads "Assemble the two pages using the stabilizing bar to create a standing hinge structure." In this scene that hinge is already assembled, so what is left is the task above; the grading is the success criterion below.

The scene objects are the env's entities (`s.objects()`: `page A with eyelets`, `page B with eyelets`, `stabilizing bar`; see
`/opt/robowits/gs_gym/envs/robowits/07_stand_pages.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful: both pages standing upright."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        def angle_close_to_right_angle(angle_deg: float) -> bool:
            a = angle_deg
            if a < 0:
                a += 360.0
            if a > 360:
                a -= 360.0
            d = min(abs(a), abs(180 - a), abs(360 - a))
            return d <= self.ANGLE_TOL_DEG

        def is_upright(euler) -> bool:
            if euler is None:
                return False
            ex = float(euler[0]) * 180.0 / np.pi
            ey = float(euler[1]) * 180.0 / np.pi
            return angle_close_to_right_angle(ex) and angle_close_to_right_angle(ey)

        def hull_within_table(hull2d) -> bool:
            if hull2d is None:
                return False
            for pt in hull2d:
                x, y = float(pt[0]), float(pt[1])
                if not (TABLE_X_MIN <= x <= TABLE_X_MAX and TABLE_Y_MIN <= y <= TABLE_Y_MAX):
                    return False
            return True

        def is_on_table(bounds) -> bool:
            if bounds is None:
                return False
            z_min = float(bounds[0][2])
            return abs(z_min - self.TABLE_Z) <= self.Z_CONTACT_TOL

        required_pages = ["page A with eyelets", "page B with eyelets"]

        for name in required_pages:
            info = objs_info.get(name)
            if info is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            euler = info.get("euler")
            if not is_upright(euler):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            hull = info.get("convex_hull_2d")
            if not hull_within_table(hull):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            bounds = info.get("bounds")
            if not is_on_table(bounds):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            if _utils.check_being_held(info, self._robot):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success criterion (as graded)
This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the grader
runs) and the release and rest condition the grader adds (the last item). Where the task text says something else,
this section and the code are what count. After the last action of your trajectory the grader holds that action's
command for a settle window: 1 s (30 control steps) with nothing checked, then 2 s (60 control steps) in which every
condition below must hold at every 6th control step and at the last one, with each graded object staying within 2 mm
of where it was when those 2 s began (the *check window*). It must pass in both replays. `s.replay(actions)` runs
exactly this and returns the verdict as `success` (and why in `settle`); `s.status()["success"]` is the same
conditions at one instant, without the window (`predicate`: RoboWits' alone).

- For each of the two pages:
  - its roll and its pitch (the x and y of its XYZ Euler angles) are each within 15 degrees of 0 or of 180 degrees
    (the page meshes stand upright at roll = pitch = 0; any yaw);
  - its footprint lies inside the table bounds (no tolerance);
  - the bottom of its bounding box is within 3 cm of the table top (z = 0.76 m);
  - it is not held.
- Released and at rest: no part of the robot touches either page or the stabilizing bar (holding the bar holds the
  pages up), and each page moves at most 2 mm during the check window.

Not checked: any connection between the pages (the hinge) and where the bar ends up.

Task text vs grader ("Stand the two pages up on the table so that they brace each other."): The hinge is not checked:
two pages standing upright on the table, released and at rest, pass with or without the bar through their eyelets. In
this scene the bar already runs through the eyelets of both pages at the start (they lie open like a book): nothing
has to be inserted.

Terms: a *footprint* is an object's outline seen from above (the 2D convex hull of its collision mesh in the x-y
plane); *not held* means that neither gripper tip (`Gripper_Tip_R` / `Gripper_Tip_L`, the frames of `s.ee_pose`) is
inside the object's axis-aligned bounding box grown by 3 cm on every side; the *table bounds* are the rectangle x
0.21-1.00 m, |y| <= 0.69 m on the table top (z = 0.76 m).

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed after the replay: the settle window of the success criterion above, else 0. Also leave the script that produced it at `/app/output/gen.py`.
Save a trajectory as soon as one replays successfully (you can overwrite it later), and do not stop before you have
one.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_robowits import Session
s = Session("stand_pages", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, euler_xyz, bounds, size, velocity
p["move_ee"]("left", pos, quat_wxyz, linear=3)   # IK (RoboWits' own) to a gripper-tip pose, then joint interpolation
p["move_joints"]("left", q7); p["set_gripper"]("left", 0.0); p["open_gripper"]("left"); p["hold"](10)
s.ee_pose("left"); s.joint_positions(); s.ik("left", pos, quat_wxyz)    # kinematics helpers
s.render_frame("ego")              # RGB uint8 (480, 848, 3) from one camera (s.VIDEO_CAMERAS); s.render_grid()
s.render_depth("ego")              # float32 (480, 848) z-depth in metres (0 = no reading), pixel-aligned with render_frame("ego")
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.robot_spec()                     # joints (position / velocity / effort limits), grippers, PD gains, tool frames Gripper_Tip_R/L
s.kinematics({"op": "fk", "q": q14})   # stateless FK / IK on the robot's model; {"op": "ik", "targets": {"Gripper_Tip_R": pose7}, "seed": q14}
s.joint_velocities(); s.joint_efforts(); s.gripper_width("left")   # measured state: 16-vectors in action layout (efforts: the PD drives')
s.object_pose(name); s.object_bounds(name); s.state_sha()          # one object's pose / AABB; the state hash that replays compare
p["set_joint_targets"](q16, steps=1); p["close_gripper"]("left"); p["gripper_quat"](yaw, approach)   # more thin wrappers: help(p[...])
s.step(action)                     # one low-level action (16 joint targets, below) = one control step (1/30 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 16) actions, one row per control step
s.status()                         # {'success': the conditions hold now, 'predicate', 'touching', 'progress', 'sim_steps', 'resets', 'state_sha'}
s.replay(actions)                  # resets, replays open-loop, then the settle window: the verdict  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

CLI equivalent of the grader:
`python /opt/tools/rcb_robowits.py replay --task stand_pages --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (0, 0, 1.08), table top at z = 0.76, x points away from the robot, y to its left (the left
  arm works at y > 0). Quaternions are **WXYZ**.
- Action (16): right arm 7 joint targets (rad), right gripper width (m, 0 closed .. 0.1 open), left arm 7 joint targets,
  left gripper width; absolute position targets tracked by PD controllers. `s.hold_action()` is the no-op.
- Control runs at 30 Hz (4 physics substeps). There is no step budget: the time limit (`## Time limit`) is your only budget.
  One technical cap: a trajectory, and a `Session` between two resets, has at most 200000 control steps (about
  1.85 h of simulated time). `s.step` returns `True` on the step that reaches it and raises after it until
  `s.reset()`; the grader scores a trajectory with more rows 0 (`bad_trajectory`).
- Grippers open to 10 cm. The gripper tip frame's +z axis is the approach direction and +x the finger-closing
  direction; `p["top_down_quat"](yaw)` builds a vertical-approach orientation whose fingers close along `yaw`.
- One `Session` per process (Genesis initialises once). The physics runs on Genesis' bit-deterministic CPU backend at
  ~700 control steps/s; the GPU only renders camera images. Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **6 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
