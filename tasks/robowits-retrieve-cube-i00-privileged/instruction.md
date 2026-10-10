# RoboWits · retrieve_cube — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Retrieve the cube from the container and place it on the green target area.

The scene objects are the env's entities (`s.objects()`: `deep narrow container`, `cube`, `target area`; see
`/opt/robowits/gs_gym/envs/robowits/02_retrieve_cube.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful."""

        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        TABLE_Z = 0.76

        CUBE = "cube"
        TARGET = "target area"
        CONTAINERS = ["deep narrow container", "wide open container"]

        EPS_XY = 1e-2
        Z_TOL_BELOW = 0.01
        Z_TOL_ABOVE = 0.03
        AREA_EPS = 1e-8

        def get_hull_xy(obj_name):
            obj = objs_info.get(obj_name)
            if obj is None:
                return None
            hull = obj.get("convex_hull_2d")
            if hull is not None:
                try:
                    hull = np.asarray(hull, dtype=float)
                    if hull.ndim == 2 and hull.shape[1] == 2 and len(hull) >= 3:
                        return hull
                except Exception:
                    pass
            b = obj.get("bounds")
            if b is None:
                return None
            b = np.asarray(b, dtype=float)
            if b.shape != (2, 3):
                return None
            (x_min, y_min, _), (x_max, y_max, _) = b
            return np.array(
                [
                    [x_min, y_min],
                    [x_max, y_min],
                    [x_max, y_max],
                    [x_min, y_max],
                ],
                dtype=float,
            )

        def get_bounds(obj_name):
            obj = objs_info.get(obj_name)
            if obj is None:
                return None
            b = obj.get("bounds")
            if b is None:
                return None
            b = np.asarray(b, dtype=float)
            if b.shape != (2, 3):
                return None
            return b

        def polygon_signed_area(poly):
            if poly is None or len(poly) < 3:
                return 0.0
            x = poly[:, 0]
            y = poly[:, 1]
            return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

        def polygon_area(poly):
            return abs(polygon_signed_area(poly))

        def ensure_ccw(poly):
            if poly is None or len(poly) < 3:
                return poly
            if polygon_signed_area(poly) < 0:
                return np.flipud(poly.copy())
            return poly

        def sutherland_hodgman(subject_polygon, clip_polygon):
            if subject_polygon is None or clip_polygon is None:
                return np.zeros((0, 2), dtype=float)
            output_list = subject_polygon.tolist()
            if len(output_list) < 3 or len(clip_polygon) < 3:
                return np.zeros((0, 2), dtype=float)

            def is_inside(p, a, b):
                return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0.0

            def compute_intersection(p1, p2, p3, p4):
                x1, y1 = p1
                x2, y2 = p2
                x3, y3 = p3
                x4, y4 = p4
                denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
                if abs(denom) < 1e-12:
                    return [(p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0]
                px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
                py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
                return [px, py]

            clip_pts = clip_polygon.tolist()
            for i in range(len(clip_pts)):
                input_list = output_list
                output_list = []
                if not input_list:
                    break
                A = clip_pts[i]
                B = clip_pts[(i + 1) % len(clip_pts)]
                S = input_list[-1]
                for E in input_list:
                    if is_inside(E, A, B):
                        if not is_inside(S, A, B):
                            output_list.append(compute_intersection(S, E, A, B))
                        output_list.append(E)
                    elif is_inside(S, A, B):
                        output_list.append(compute_intersection(S, E, A, B))
                    S = E
            if not output_list or len(output_list) < 3:
                return np.zeros((0, 2), dtype=float)
            return np.array(output_list, dtype=float)

        def overlap_area(poly1, poly2):
            if poly1 is None or poly2 is None:
                return 0.0
            p1 = ensure_ccw(np.asarray(poly1, dtype=float))
            p2 = ensure_ccw(np.asarray(poly2, dtype=float))
            inter = sutherland_hodgman(p1, p2)
            if inter.size == 0 or len(inter) < 3:
                return 0.0
            return polygon_area(inter)

        def hull_inside_table(hull):
            if hull is None or len(hull) == 0:
                return False
            xs = hull[:, 0]
            ys = hull[:, 1]
            within_x = (xs >= (TABLE_X_MIN - EPS_XY)) & (xs <= (TABLE_X_MAX + EPS_XY))
            within_y = (ys >= (TABLE_Y_MIN - EPS_XY)) & (ys <= (TABLE_Y_MAX + EPS_XY))
            return bool(np.all(within_x & within_y))

        cube_hull = get_hull_xy(CUBE)
        target_hull = get_hull_xy(TARGET)
        cube_bounds = get_bounds(CUBE)

        # Get container hull (try both container types)
        container_hull = None
        for container_name in CONTAINERS:
            container_hull = get_hull_xy(container_name)
            if container_hull is not None:
                break

        if cube_hull is None or target_hull is None or cube_bounds is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        z_min = float(cube_bounds[0, 2])
        if z_min < (TABLE_Z - Z_TOL_BELOW) or z_min > (TABLE_Z + Z_TOL_ABOVE):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not hull_inside_table(cube_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not hull_inside_table(target_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        cube_area = polygon_area(ensure_ccw(cube_hull))
        if cube_area <= AREA_EPS:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        # Check cube is outside container (overlap < 50%)
        if container_hull is not None:
            container_overlap = overlap_area(cube_hull, container_hull)
            container_overlap_ratio = container_overlap / cube_area
            if container_overlap_ratio >= 0.5:
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        # Check cube overlaps target area by at least 50%
        inter_area = overlap_area(cube_hull, target_hull)
        overlap_ratio = inter_area / cube_area

        return torch.tensor([overlap_ratio >= 0.5], dtype=torch.bool, device=self._device)
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success criterion (as graded)
This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the grader
runs). Where the task text says something else, this section and the predicate are what count. It is evaluated once
per replay, on the state right after the last action of your trajectory (no settle steps are added: let things come to
rest inside the trajectory), and must hold after both replays.

- The cube is at table height: the bottom of its bounding box between 1 cm below and 3 cm above the table top (z
  0.75-0.79 m).
- The footprints of the cube and of the target area lie inside the table bounds grown by 1 cm.
- Less than 50 % of the cube's footprint area lies over the container's footprint.
- At least 50 % of the cube's footprint area lies over the target area.

Not checked: whether a gripper still holds the cube, any speed, and where the container ends up.

Task text vs grader ("Retrieve the cube from the container and place it on the green target area."): The text and the
grader agree; the grader makes "out of the container" and "on the target" precise (half of the cube's footprint) and
requires the cube at table height.

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
s = Session("retrieve_cube", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task retrieve_cube --instance /app/instance.json --traj /app/output/trajectory.npz`

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
