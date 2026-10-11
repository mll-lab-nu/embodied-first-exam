# RoboWits · align_blocks — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Align the three cubes perfectly in a straight line.

The scene objects are the env's entities (`s.objects()`: `first target cube`, `second target cube`, `third target cube`, `long rigid ruler`; see
`/opt/robowits/gs_gym/envs/robowits/01_align_blocks.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful."""
        import numpy as np

        objs_info = self.collect_objs_info()

        TABLE_BOUNDS = {
            "x_min": 0.21,
            "x_max": 1.00,
            "y_min": -0.69,
            "y_max": 0.69,
            "z_surf": 0.76,
        }

        cube_names = [
            "first target cube",
            "second target cube",
            "third target cube",
        ]

        for n in cube_names:
            if n not in objs_info:
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        def get_xy(name):
            p = objs_info[name]["pos"]
            return np.array([p[0], p[1]], dtype=float)

        def pairwise_dists(pts):
            d01 = np.linalg.norm(pts[0] - pts[1])
            d12 = np.linalg.norm(pts[1] - pts[2])
            d02 = np.linalg.norm(pts[0] - pts[2])
            return [(d01, (0, 1)), (d12, (1, 2)), (d02, (0, 2))]

        def point_line_distance(p, a, b):
            v = b - a
            w = p - a
            v_norm = np.linalg.norm(v)
            if v_norm < 1e-9:
                return np.linalg.norm(p - a)
            cross_z = v[0] * w[1] - v[1] * w[0]
            return abs(cross_z) / (v_norm + 1e-12)

        def on_table_surface(name, z_tol=0.025):
            info = objs_info[name]
            b = info.get("bounds", None)
            if b is None:
                return True
            zmin = float(b[0][2])
            return abs(zmin - TABLE_BOUNDS["z_surf"]) <= z_tol

        margin = 0.03
        for name, info in objs_info.items():
            lname = name.lower()
            if "table" in lname or "robot" in lname:
                continue
            pos = info.get("pos", None)
            if pos is None:
                continue
            x, y = float(pos[0]), float(pos[1])
            if (
                x < TABLE_BOUNDS["x_min"] - margin
                or x > TABLE_BOUNDS["x_max"] + margin
                or y < TABLE_BOUNDS["y_min"] - margin
                or y > TABLE_BOUNDS["y_max"] + margin
            ):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        for n in cube_names:
            if not on_table_surface(n, z_tol=0.025):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        pts = [get_xy(n) for n in cube_names]

        dists = pairwise_dists(pts)
        max_pair = max(dists, key=lambda x: x[0])
        max_dist, (i, j) = max_pair
        if max_dist < 0.03:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        k = 3 - i - j
        line_tol = 0.010
        perp_dist = point_line_distance(pts[k], pts[i], pts[j])
        if perp_dist > line_tol:
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

- Every object in the scene except the table and the robot (the ruler included) has its position inside x 0.18-1.03 m,
  |y| <= 0.72 m (the table bounds grown by 3 cm).
- Each of the three cubes rests on the table: the bottom of its bounding box within 2.5 cm of the table top
  (z = 0.76 m).
- Seen from above (x, y), the two cube centres farthest apart are at least 3 cm apart, and the third cube's centre
  lies within 1.0 cm of the straight line through those two.

Not checked: the cubes' orientation, whether they touch, their speed, whether a gripper still holds one, and how the
ruler is used.

Task text vs grader ("Align the three cubes perfectly in a straight line."): "Perfectly in a straight line" means
within 1.0 cm of the line through the two outermost cubes, seen from above. The grader also requires what the text
does not say: the cubes resting on the table, at least 3 cm between the outermost two, and every object over the
table.

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
s = Session("align_blocks", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task align_blocks --instance /app/instance.json --traj /app/output/trajectory.npz`

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
