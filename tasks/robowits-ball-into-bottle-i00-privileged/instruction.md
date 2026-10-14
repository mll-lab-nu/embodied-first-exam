# RoboWits · ball_into_bottle — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Transfer the ball from the blue container into the red bottle.

The red bottle's base is thin in the simulator (its collision shape is about 3.5 mm thick, and the bottle is fixed to the table): a ball that falls fast down the bottle can pass through the base onto the table, which fails the task. In one measured case about half of the pours did (16 replays of one pouring trajectory with tiny noise, 9 balls through the base): let the ball in slowly.

The scene objects are the env's entities (`s.objects()`: `red bottle`, `funnel`, `ball container`, `small ball`; see
`/opt/robowits/gs_gym/envs/robowits/12_ball_into_bottle.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful: ball inside bottle."""
        objs_info = self.collect_objs_info()

        if not isinstance(objs_info, dict):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        ball = objs_info.get("small ball")
        bottle = objs_info.get("red bottle")
        if ball is None or bottle is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        table_z = 0.76
        safe_margin = 0.002
        top_margin = 0.11

        def f(v):
            try:
                return float(v)
            except Exception:
                return None

        def point_in_polygon(px, py, poly):
            n = len(poly)
            if n < 3:
                return False
            inside = False
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                if (y1 > py) != (y2 > py):
                    x_int = (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1
                    if px < x_int:
                        inside = not inside
            return inside

        def not_fallen(obj):
            b = obj.get("bounds")
            if b is not None:
                zmin = f(b[0][2])
            else:
                pos = obj.get("pos")
                zmin = f(pos[2]) if pos is not None else None
            if zmin is None:
                return False
            return zmin >= (table_z - 0.05)

        ball_pos = ball.get("pos")
        if ball_pos is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        bx, by, bz = f(ball_pos[0]), f(ball_pos[1]), f(ball_pos[2])
        if bx is None or by is None or bz is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        ball_bounds = ball.get("bounds")
        ball_radius = None
        if ball_bounds is not None:
            try:
                dx = f(ball_bounds[1][0]) - f(ball_bounds[0][0])
                dy = f(ball_bounds[1][1]) - f(ball_bounds[0][1])
                dz = f(ball_bounds[1][2]) - f(ball_bounds[0][2])
                ball_radius = 0.5 * min(abs(dx), abs(dy), abs(dz))
            except Exception:
                ball_radius = None
        if ball_radius is None or ball_radius <= 0:
            ball_radius = 0.01

        ball_bottom_z = bz - ball_radius
        if ball_bottom_z <= (table_z + safe_margin):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        bottle_poly = bottle.get("convex_hull_2d")
        if bottle_poly is not None:
            poly = [(f(p[0]), f(p[1])) for p in bottle_poly]
            poly = [(x, y) for (x, y) in poly if x is not None and y is not None]
        else:
            bnd = bottle.get("bounds")
            if bnd is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            x0, y0 = f(bnd[0][0]), f(bnd[0][1])
            x1, y1 = f(bnd[1][0]), f(bnd[1][1])
            if None in (x0, y0, x1, y1):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            poly = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

        bottle_bounds = bottle.get("bounds")
        if bottle_bounds is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        bottle_zmin = f(bottle_bounds[0][2])
        bottle_zmax = f(bottle_bounds[1][2])
        if bottle_zmin is None or bottle_zmax is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        inside_xy = point_in_polygon(bx, by, poly)

        ball_top_z = bz + ball_radius
        fully_below_mouth = ball_top_z < (bottle_zmax - top_margin)
        above_bottle_base = ball_bottom_z > (bottle_zmin + safe_margin)

        if not (not_fallen(ball) and not_fallen(bottle)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor(
            [inside_xy and fully_below_mouth and above_bottle_base], dtype=torch.bool, device=self._device
        )
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success criterion (as graded)
This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the grader
runs). Where the task text says something else, this section and the predicate are what count. It is evaluated once
per replay, on the state right after the last action of your trajectory (no settle steps are added: let things come to
rest inside the trajectory), and must hold after both replays.

- The ball's centre (x, y) lies inside the red bottle's footprint.
- The ball is deep in the bottle: its top (centre z + r, r = half the smallest extent of its bounding box: 5 mm for
  this 1 cm ball) is more than 11 cm below the top of the bottle's bounding box. In this scene the bottle's box spans
  z 0.767-0.994 m, so the ball's top must be below z = 0.884 m.
- The ball's bottom (centre z - r) is more than 2 mm above the table top (z = 0.762 m) and more than 2 mm above the
  bottom of the bottle's bounding box (z = 0.769 m here).
- Neither the ball nor the bottle has fallen: the bottom of each bounding box is no lower than 5 cm below the table
  top (z >= 0.71 m).

Not checked: how the ball got there (the blue container and the funnel are not referenced), whether a gripper holds
anything, and any speed.

Task text vs grader ("Transfer the ball from the blue container into the red bottle."): "Into the red bottle" means
deep inside it: seen from above inside the bottle's outline, with the ball's top more than 11 cm below the bottle's
top and the ball off the bottle's base. "From the blue container" is not checked.

Terms: a *footprint* is an object's outline seen from above (the 2D convex hull of its collision mesh in the x-y
plane); *not held* means that neither gripper tip (`Gripper_Tip_R` / `Gripper_Tip_L`, the frames of `s.ee_pose`) is
inside the object's axis-aligned bounding box grown by 3 cm on every side; the *table bounds* are the rectangle x
0.21-1.00 m, |y| <= 0.69 m on the table top (z = 0.76 m).

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.
Save a trajectory as soon as one replays successfully (you can overwrite it later), and do not stop before you have
one.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_robowits import Session
s = Session("ball_into_bottle", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
s.status()                         # {'success': bool, 'progress': float, 'sim_steps': int, 'resets': int, 'state_sha': str}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

CLI equivalent of the grader:
`python /opt/tools/rcb_robowits.py replay --task ball_into_bottle --instance /app/instance.json --traj /app/output/trajectory.npz`

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
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **6 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
