# RoboWits · gap_retrieve — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Place the lemon on the green target area.

The scene objects are the env's entities (`s.objects()`: `left boundary block`, `right boundary block`, `target area`, `lemon`; see
`/opt/robowits/gs_gym/envs/robowits/03_gap_retrieve.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful: lemon on target with 80% overlap."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        TABLE_Z = 0.76
        Z_TOL = 0.02

        key_name = "lemon"
        target_name = "target area"

        if key_name not in objs_info or target_name not in objs_info:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        key = objs_info[key_name]
        target = objs_info[target_name]

        def get_hull2d(obj):
            hull = obj.get("convex_hull_2d", None)
            if hull is not None and len(hull) >= 3:
                pts = [(float(p[0]), float(p[1])) for p in hull]
                return pts
            b = obj.get("bounds", None)
            if b is None:
                return None
            (xmin, ymin, _), (xmax, ymax, _) = b
            return [
                (float(xmin), float(ymin)),
                (float(xmax), float(ymin)),
                (float(xmax), float(ymax)),
                (float(xmin), float(ymax)),
            ]

        def polygon_area(poly):
            if not poly or len(poly) < 3:
                return 0.0
            area = 0.0
            for i in range(len(poly)):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % len(poly)]
                area += x1 * y2 - x2 * y1
            return abs(area) * 0.5

        def ensure_ccw(poly):
            signed = 0.0
            for i in range(len(poly)):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % len(poly)]
                signed += x1 * y2 - x2 * y1
            if signed < 0:
                return list(reversed(poly))
            return poly

        def point_in_table_xy(p):
            x, y = p
            return (TABLE_X_MIN - 1e-4) <= x <= (TABLE_X_MAX + 1e-4) and (TABLE_Y_MIN - 1e-4) <= y <= (
                TABLE_Y_MAX + 1e-4
            )

        def hull_inside_table(poly):
            if not poly:
                return False
            return all(point_in_table_xy(p) for p in poly)

        def cross(ax, ay, bx, by):
            return ax * by - ay * bx

        def line_intersection(p, r, q, svec):
            rxs = cross(r[0], r[1], svec[0], svec[1])
            if abs(rxs) < 1e-12:
                return None
            qp = (q[0] - p[0], q[1] - p[1])
            t = cross(qp[0], qp[1], svec[0], svec[1]) / rxs
            return (p[0] + t * r[0], p[1] + t * r[1])

        def is_inside(p, a, b):
            return cross(b[0] - a[0], b[1] - a[1], p[0] - a[0], p[1] - a[1]) >= -1e-9

        def sutherland_hodgman(subject, clip):
            if not subject or not clip:
                return []
            output = subject[:]
            for i in range(len(clip)):
                cp1 = clip[i]
                cp2 = clip[(i + 1) % len(clip)]
                input_list = output
                output = []
                if not input_list:
                    break
                s = input_list[-1]
                for e in input_list:
                    if is_inside(e, cp1, cp2):
                        if not is_inside(s, cp1, cp2):
                            inter = line_intersection(
                                s, (e[0] - s[0], e[1] - s[1]), cp1, (cp2[0] - cp1[0], cp2[1] - cp1[1])
                            )
                            if inter is not None:
                                output.append(inter)
                        output.append(e)
                    elif is_inside(s, cp1, cp2):
                        inter = line_intersection(
                            s, (e[0] - s[0], e[1] - s[1]), cp1, (cp2[0] - cp1[0], cp2[1] - cp1[1])
                        )
                        if inter is not None:
                            output.append(inter)
                    s = e
            return output

        key_hull = get_hull2d(key)
        target_hull = get_hull2d(target)
        if key_hull is None or target_hull is None or len(key_hull) < 3 or len(target_hull) < 3:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        key_hull = ensure_ccw(key_hull)
        target_hull = ensure_ccw(target_hull)

        key_bounds = key.get("bounds", None)
        if key_bounds is None:
            kpos = key.get("pos", None)
            if kpos is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            on_table = (kpos[2] - TABLE_Z) <= 0.03
        else:
            z_min = float(key_bounds[0][2])
            on_table = abs(z_min - TABLE_Z) <= Z_TOL

        key_on_table_xy = hull_inside_table(key_hull)
        target_on_table_xy = hull_inside_table(target_hull)
        if not (key_on_table_xy and target_on_table_xy):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        key_area = polygon_area(key_hull)
        if key_area <= 1e-8:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        inter_poly = sutherland_hodgman(key_hull, target_hull)
        overlap_area = polygon_area(inter_poly) if len(inter_poly) >= 3 else 0.0
        overlap_fraction = overlap_area / key_area

        lemon_not_held = not check_being_held(key, self._robot)

        return torch.tensor(
            [on_table and overlap_fraction >= 0.8 and lemon_not_held],
            dtype=torch.bool,
            device=self._device,
        )
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success criterion (as graded)
This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the grader
runs). Where the task text says something else, this section and the predicate are what count. It is evaluated once
per replay, on the state right after the last action of your trajectory (no settle steps are added: let things come to
rest inside the trajectory), and must hold after both replays.

- The lemon rests on the table: the bottom of its bounding box within 2 cm of the table top (z = 0.76 m).
- The footprints of the lemon and of the target area lie inside the table bounds.
- At least 80 % of the lemon's footprint area lies over the target area.
- The lemon is not held.

Not checked: the boundary blocks (where they end up) and any speed.

Task text vs grader ("Place the lemon on the green target area."): The text and the grader agree; the grader adds the
thresholds above (the lemon on the table, 80 % over the target, released).

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
s = Session("gap_retrieve", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task gap_retrieve --instance /app/instance.json --traj /app/output/trajectory.npz`

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

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Installing packages is not cheating (`## External material` above).
