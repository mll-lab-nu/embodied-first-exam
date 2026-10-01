# RoboWits · ball_onto_tower — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Place the ball stably on top of the tower.

The scene objects are the env's entities (`s.objects()`: `tower base`, `large ring`, `medium ring`, `small ring`, `ball`; see
`/opt/robowits/gs_gym/envs/robowits/17_ball_onto_tower.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful: ball on top of tower, stable, not held."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        TABLE_TOL = 1e-3

        base = objs_info.get("tower base")
        ball = objs_info.get("ball")

        if base is None or ball is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def in_table_xy(obj):
            hull = obj.get("convex_hull_2d")
            if hull is not None:
                for pt in hull:
                    x, y = float(pt[0]), float(pt[1])
                    if not (TABLE_X_MIN - TABLE_TOL <= x <= TABLE_X_MAX + TABLE_TOL):
                        return False
                    if not (TABLE_Y_MIN - TABLE_TOL <= y <= TABLE_Y_MAX + TABLE_TOL):
                        return False
                return True
            pos = obj.get("pos")
            if pos is None:
                return False
            x, y = float(pos[0]), float(pos[1])
            return (TABLE_X_MIN - TABLE_TOL <= x <= TABLE_X_MAX + TABLE_TOL) and (
                TABLE_Y_MIN - TABLE_TOL <= y <= TABLE_Y_MAX + TABLE_TOL
            )

        if not in_table_xy(base) or not in_table_xy(ball):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        vel = ball.get("vel")
        if vel is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        speed = math.sqrt(float(vel[0]) ** 2 + float(vel[1]) ** 2 + float(vel[2]) ** 2)
        stable_linear = speed < 0.05
        stable_vertical = abs(float(vel[2])) < 0.03
        stability_ok = stable_linear and stable_vertical

        base_bounds = base.get("bounds")
        ball_pos = ball.get("pos")
        if base_bounds is None or ball_pos is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        base_top_z = float(base_bounds[1][2])
        ball_center_z = float(ball_pos[2])
        height_ok = ball_center_z > base_top_z + 0.005

        base_hull = base.get("convex_hull_2d")
        ball_xy = (float(ball_pos[0]), float(ball_pos[1]))

        def point_in_polygon(pt, poly):
            x, y = pt
            inside = False
            n = len(poly)
            if n < 3:
                return False
            for i in range(n):
                x1, y1 = float(poly[i][0]), float(poly[i][1])
                x2, y2 = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
                if (y1 > y) != (y2 > y):
                    xinters = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1
                    if x < xinters + 1e-12:
                        inside = not inside
            return inside

        if base_hull is not None and len(base_hull) >= 3:
            on_top_ok = point_in_polygon(ball_xy, base_hull)
        else:
            x_min, y_min = float(base_bounds[0][0]) - 0.005, float(base_bounds[0][1]) - 0.005
            x_max, y_max = float(base_bounds[1][0]) + 0.005, float(base_bounds[1][1]) + 0.005
            on_top_ok = (x_min <= ball_xy[0] <= x_max) and (y_min <= ball_xy[1] <= y_max)

        # Check ball is not being held by either gripper
        not_held = not check_being_held(ball, self._robot)

        return torch.tensor(
            [stability_ok and height_ok and on_top_ok and not_held], dtype=torch.bool, device=self._device
        )
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success criterion (as graded)
This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the grader
runs). Where the task text says something else, this section and the predicate are what count. It is evaluated once
per replay, on the state right after the last action of your trajectory (no settle steps are added: let things come to
rest inside the trajectory), and must hold after both replays.

- The footprints of the tower base and of the ball lie inside the table bounds (1 mm tolerance).
- The ball is still: its speed is below 0.05 m/s and its vertical speed below 0.03 m/s.
- The ball's centre is more than 5 mm above the top of the tower base's bounding box (the base's box ends at
  z = 0.868 m in this scene, so the centre must be above z = 0.873 m), and its (x, y) lies inside the tower base's
  footprint.
- The ball is not held.

Not checked: the rings (where they are, whether they are on the tower) and how long the ball stays.

Task text vs grader ("Place the ball stably on top of the tower."): "The tower" is the tower base alone: the rings are
not referenced. "Stably" is one speed sample at the end.

Terms: a *footprint* is an object's outline seen from above (the 2D convex hull of its collision mesh in the x-y
plane); *not held* means that neither gripper tip (`Gripper_Tip_R` / `Gripper_Tip_L`, the frames of `s.ee_pose`) is
inside the object's axis-aligned bounding box grown by 3 cm on every side; the *table bounds* are the rectangle x
0.21-1.00 m, |y| <= 0.69 m on the table top (z = 0.76 m).

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.
Your wall-clock budget is 90 min (5400 s): save a trajectory as soon as one replays successfully (you can overwrite
it later), and do not stop before you have one.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_robowits import Session
s = Session("ball_onto_tower", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task ball_onto_tower --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (0, 0, 1.08), table top at z = 0.76, x points away from the robot, y to its left (the left
  arm works at y > 0). Quaternions are **WXYZ**.
- Action (16): right arm 7 joint targets (rad), right gripper width (m, 0 closed .. 0.1 open), left arm 7 joint targets,
  left gripper width; absolute position targets tracked by PD controllers. `s.hold_action()` is the no-op.
- Control runs at 30 Hz (4 physics substeps). There is no step budget; your wall-clock budget is 90 min (5400 s).
- Grippers open to 10 cm. The gripper tip frame's +z axis is the approach direction and +x the finger-closing
  direction; `p["top_down_quat"](yaw)` builds a vertical-approach orientation whose fingers close along `yaw`.
- One `Session` per process (Genesis initialises once). The physics runs on Genesis' bit-deterministic CPU backend at
  ~700 control steps/s; the GPU only renders camera images. Do not call `s.close()` before writing every output.
