# RoboWits · stack_cubes — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Build a stable two-layer stack so the red cube's center is above the green
colored dot.

The scene objects are the env's entities (`s.objects()`: `base cube 1`, `base cube 2`, `apex cube`, `apex target`; see
`/opt/robowits/gs_gym/envs/robowits/14_stack_cubes.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful."""
        objs_info = self.collect_objs_info()

        b1 = objs_info.get("base cube 1")
        b2 = objs_info.get("base cube 2")
        apex = objs_info.get("apex cube")
        target = objs_info.get("apex target")

        if any(x is None for x in [b1, b2, apex, target]):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_on_table_surface(bounds, table_z, tolerance=0.015):
            z_min = float(bounds[0][2])
            return abs(z_min - table_z) <= tolerance

        def objects_touching(b1, b2, tolerance=0.01):
            return all(not (b1[1][i] + tolerance < b2[0][i] or b2[1][i] + tolerance < b1[0][i]) for i in range(3))

        if not is_on_table_surface(b1["bounds"], self.TABLE_Z):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not is_on_table_surface(b2["bounds"], self.TABLE_Z):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not objects_touching(b1["bounds"], b2["bounds"], tolerance=0.01):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        apex_bottom = float(apex["bounds"][0, 2])
        b1_top = float(b1["bounds"][1, 2])
        if apex_bottom < b1_top - 0.01:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        apex_pos = apex["pos"][:2]
        target_pos = target["pos"][:2]
        dist = np.sqrt((apex_pos[0] - target_pos[0]) ** 2 + (apex_pos[1] - target_pos[1]) ** 2)
        if dist > 0.025:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if check_being_held(apex, self._robot):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success criterion (as graded)
This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the grader
runs). Where the task text says something else, this section and the predicate are what count. It is evaluated once
per replay, on the state right after the last action of your trajectory (no settle steps are added: let things come to
rest inside the trajectory), and must hold after both replays.

- Both base cubes rest on the table: the bottom of each bounding box within 1.5 cm of the table top (z = 0.76 m).
- The two base cubes touch: their bounding boxes are at most 1 cm apart along each of the three axes.
- The bottom of the apex cube's bounding box is no lower than 1 cm below the top of `base cube 1`'s bounding box.
- The apex cube's centre (x, y) is within 2.5 cm of the apex target's (the green dot's) centre.
- The apex cube is not held.

Not checked: whether the apex cube rests on both base cubes (only its height against base cube 1 is tested), any
speed, and where the base cubes are relative to the dot.

Task text vs grader ("Build a stable two-layer stack so the red cube's center is above the green colored dot."): "A
stable two-layer stack" is one final-state check of the conditions above, without a speed check: the apex must be high
enough relative to base cube 1 and over the dot, nothing more.

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
s = Session("stack_cubes", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task stack_cubes --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (0, 0, 1.08), table top at z = 0.76, x points away from the robot, y to its left (the left
  arm works at y > 0). Quaternions are **WXYZ**.
- Action (16): right arm 7 joint targets (rad), right gripper width (m, 0 closed .. 0.1 open), left arm 7 joint targets,
  left gripper width; absolute position targets tracked by PD controllers. `s.hold_action()` is the no-op.
- Control runs at 30 Hz (4 physics substeps). There is no step budget; your wall-clock budget is 90 min (5400 s).
- Cubes are 5 cm, grippers open to 10 cm. The gripper tip frame's +z axis is the approach direction and +x the
  finger-closing direction; `p["top_down_quat"](yaw)` builds a vertical-approach orientation whose fingers close along
  `yaw`. `check_being_held` counts a gripper tip inside the apex cube's bounding box (+3 cm): retreat after releasing.
- One `Session` per process (Genesis initialises once). The physics runs on Genesis' bit-deterministic CPU backend at
  ~700 control steps/s; the GPU only renders camera images. Do not call `s.close()` before writing every output.
