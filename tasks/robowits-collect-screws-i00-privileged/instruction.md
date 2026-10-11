# RoboWits · collect_screws — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Collect the screw into the container

The scene objects are the env's entities (`s.objects()`: `container`, `dustpan`, `screw`; see
`/opt/robowits/gs_gym/envs/robowits/10_collect_screws.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self, objs_info: dict | None = None) -> torch.Tensor:
        """Check if task is successful: screw in container."""
        if objs_info is None:
            objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        container = objs_info.get("container")

        if container is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        container_bounds = container.get("bounds")
        if container_bounds is None:
            ch = container.get("convex_hull_2d")
            if ch is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            ch = np.array(ch).astype(float)
            x_min, y_min = np.min(ch[:, 0]), np.min(ch[:, 1])
            x_max, y_max = np.max(ch[:, 0]), np.max(ch[:, 1])
            z_min = self.TABLE_Z - 0.02
            z_max = self.TABLE_Z + 1.0
            cmin = np.array([x_min, y_min, z_min])
            cmax = np.array([x_max, y_max, z_max])
        else:
            cb = np.array(container_bounds).astype(float)
            cmin, cmax = cb[0], cb[1]

        eps = 1e-3

        screw = objs_info.get("screw")

        if screw is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        screw_pos = screw.get("pos")
        if screw_pos is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        screw_pos = np.asarray(screw_pos, dtype=float)

        if not (
            (TABLE_X_MIN - 0.02) <= screw_pos[0] <= (TABLE_X_MAX + 0.02)
            and (TABLE_Y_MIN - 0.02) <= screw_pos[1] <= (TABLE_Y_MAX + 0.02)
            and screw_pos[2] >= (self.TABLE_Z - 0.05)
        ):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        inside = (
            (cmin[0] - eps) <= screw_pos[0] <= (cmax[0] + eps)
            and (cmin[1] - eps) <= screw_pos[1] <= (cmax[1] + eps)
            and (cmin[2] - 0.02) <= screw_pos[2] <= (cmax[2] + 0.02)
        )
        return torch.tensor([bool(inside)], dtype=torch.bool, device=self._device)
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success criterion (as graded)
This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the grader
runs). Where the task text says something else, this section and the predicate are what count. It is evaluated once
per replay, on the state right after the last action of your trajectory (no settle steps are added: let things come to
rest inside the trajectory), and must hold after both replays.

- Only one point is tested: the screw's position (the origin of its pose).
- That point is over the table: x 0.19-1.02 m and |y| <= 0.71 m (the table bounds grown by 2 cm), and not below
  z = 0.71 m (5 cm under the table top).
- That point lies inside the container's axis-aligned bounding box grown by 1 mm in x and y, and in z between 2 cm
  below the box's bottom and 2 cm above its top (the container's box spans x 0.529-0.631 m, |y| <= 0.051 m, z
  0.760-0.878 m in this scene, so z <= 0.898 m).

Not checked: the rest of the screw, whether a gripper (or the dustpan) still holds it, the dustpan, and any speed.

Task text vs grader ("Collect the screw into the container"): "Into the container" is a single point inside the
container's box, with 2 cm allowed above the rim and no release check: a screw lying on the rim, or held just above
the opening, also counts.

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
s = Session("collect_screws", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task collect_screws --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (0, 0, 1.08), table top at z = 0.76, x points away from the robot, y to its left (the left
  arm works at y > 0). Quaternions are **WXYZ**.
- Action (16): right arm 7 joint targets (rad), right gripper width (m, 0 closed .. 0.1 open), left arm 7 joint targets,
  left gripper width; absolute position targets tracked by PD controllers. `s.hold_action()` is the no-op.
- Control runs at 30 Hz (4 physics substeps). There is no step budget; your wall-clock budget is 90 min (5400 s).
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
