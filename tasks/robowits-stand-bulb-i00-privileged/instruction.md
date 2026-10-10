# RoboWits · stand_bulb — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Stand the tall object with curved bottom stably within the green target area.

The scene objects are the env's entities (`s.objects()`: `target patch`, `stabilizing ring`, `tall object with curved bottom`; see
`/opt/robowits/gs_gym/envs/robowits/16_stand_bulb.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful: tall object on target, upright, stable."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        VEL_THRESHOLD = 0.05
        OVERLAP_RATIO_REQ = 0.80
        TABLE_MARGIN = 1e-3

        def get_hull(obj):
            hull = obj.get("convex_hull_2d", None)
            if hull is not None and isinstance(hull, np.ndarray) and hull.shape[0] >= 3:
                return hull.copy()
            b = obj.get("bounds", None)
            if b is None:
                return None
            (xmin, ymin, _), (xmax, ymax, _) = b
            return np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]], dtype=float)

        def poly_area(poly):
            if poly is None or len(poly) < 3:
                return 0.0
            x = poly[:, 0]
            y = poly[:, 1]
            return 0.5 * float(np.abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))

        def ensure_ccw(poly):
            if poly is None or len(poly) < 3:
                return poly
            area_signed = 0.5 * float(
                np.dot(poly[:, 0], np.roll(poly[:, 1], -1)) - np.dot(poly[:, 1], np.roll(poly[:, 0], -1))
            )
            if area_signed < 0:
                return poly[::-1].copy()
            return poly

        def line_intersection(p1, p2, p3, p4):
            x1, y1 = p1
            x2, y2 = p2
            x3, y3 = p3
            x4, y4 = p4
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(denom) < 1e-12:
                return p2
            px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
            py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
            return np.array([px, py], dtype=float)

        def is_left(a, b, p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])

        def convex_polygon_intersection(subject, clip):
            if subject is None or clip is None or len(subject) < 3 or len(clip) < 3:
                return np.zeros((0, 2), dtype=float)
            output = subject.copy()
            clip = ensure_ccw(clip)
            for i in range(len(clip)):
                c1 = clip[i]
                c2 = clip[(i + 1) % len(clip)]
                input_list = output
                output = []
                if len(input_list) == 0:
                    return np.zeros((0, 2), dtype=float)
                S = input_list[-1]
                for E in input_list:
                    inside_E = is_left(c1, c2, E) >= 0
                    inside_S = is_left(c1, c2, S) >= 0
                    if inside_E:
                        if not inside_S:
                            inter_pt = line_intersection(S, E, c1, c2)
                            output.append(inter_pt)
                        output.append(E)
                    elif inside_S:
                        inter_pt = line_intersection(S, E, c1, c2)
                        output.append(inter_pt)
                    S = E
                if len(output) == 0:
                    return np.zeros((0, 2), dtype=float)
                output = np.array(output, dtype=float)
            return output

        def hull_within_table(hull):
            if hull is None or len(hull) == 0:
                return False
            xs = hull[:, 0]
            ys = hull[:, 1]
            return (
                np.all(xs >= TABLE_X_MIN - TABLE_MARGIN)
                and np.all(xs <= TABLE_X_MAX + TABLE_MARGIN)
                and np.all(ys >= TABLE_Y_MIN - TABLE_MARGIN)
                and np.all(ys <= TABLE_Y_MAX + TABLE_MARGIN)
            )

        tall_name = "tall object with curved bottom"
        patch_name = "target patch"
        if tall_name not in objs_info or patch_name not in objs_info:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        tall = objs_info[tall_name]
        patch = objs_info[patch_name]

        tall_hull = get_hull(tall)
        patch_hull = get_hull(patch)
        if tall_hull is None or patch_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not hull_within_table(tall_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not hull_within_table(patch_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        b = tall.get("bounds", None)
        is_upright = False
        if b is not None:
            (xmin, ymin, zmin), (xmax, ymax, zmax) = b
            z_ext = zmax - zmin
            xy_max = max(xmax - xmin, ymax - ymin)
            is_upright = z_ext > xy_max

        v = tall.get("vel", None)
        is_still = True
        if v is not None and isinstance(v, np.ndarray) and v.shape == (3,):
            is_still = float(np.linalg.norm(v)) <= VEL_THRESHOLD

        if not (is_upright and is_still):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        tall_hull = ensure_ccw(tall_hull)
        patch_hull = ensure_ccw(patch_hull)
        inter_poly = convex_polygon_intersection(tall_hull, patch_hull)
        inter_area = poly_area(inter_poly)
        tall_area = poly_area(tall_hull)
        if tall_area <= 1e-9:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        overlap_ratio = inter_area / tall_area

        if overlap_ratio + 1e-6 < OVERLAP_RATIO_REQ:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if check_being_held(tall, self._robot):
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

- The footprints of the tall object and of the target patch lie inside the table bounds (1 mm tolerance).
- The tall object is "upright": its axis-aligned bounding box is taller than it is wide (its z extent exceeds both its
  x and its y extent).
- The tall object is still: its speed is at most 0.05 m/s.
- At least 80 % of the tall object's footprint area lies over the target patch.
- The tall object is not held.

Not checked: the stabilizing ring, any tilt the bounding-box test lets through (for this 21.6 x 12 cm object, tilts up
to roughly 45 degrees can pass), and how long it stands.

Task text vs grader ("Stand the tall object with curved bottom stably within the green target area."): "Stand ...
stably" means the bounding-box test above and one speed sample at the end (at most 5 cm/s).

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
s = Session("stand_bulb", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task stand_bulb --instance /app/instance.json --traj /app/output/trajectory.npz`

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

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **6 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.
