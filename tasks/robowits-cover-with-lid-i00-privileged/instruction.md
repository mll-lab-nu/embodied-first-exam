# RoboWits · cover_with_lid — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Cover the pot precisely using one lid.

The scene objects are the env's entities (`s.objects()`: `pot without lid`, `small lid`, `lid medium`, `lid large`; see
`/opt/robowits/gs_gym/envs/robowits/13_cover_with_lid.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful: exactly one lid covers pot correctly."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        OVERLAP_RATIO_MIN = 0.80
        SIZE_RATIO_MIN = 0.85
        SIZE_RATIO_MAX = 1.40
        Z_ABOVE_EPS = 0.01

        def get_hull(obj):
            hull = obj.get("convex_hull_2d", None)
            if hull is not None and isinstance(hull, np.ndarray) and hull.shape[0] >= 3:
                return hull.copy()
            b = obj.get("bounds", None)
            if b is None:
                return None
            (xmin, ymin, _), (xmax, ymax, _) = b
            return np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]], dtype=float)

        def is_within_table_bounds(hull):
            if hull is None or len(hull) == 0:
                return False
            xs = hull[:, 0]
            ys = hull[:, 1]
            return (
                np.all(xs >= TABLE_X_MIN - 1e-3)
                and np.all(xs <= TABLE_X_MAX + 1e-3)
                and np.all(ys >= TABLE_Y_MIN - 1e-3)
                and np.all(ys <= TABLE_Y_MAX + 1e-3)
            )

        def compute_overlap_ratio(hull1, hull2):
            if hull1 is None or hull2 is None:
                return 0.0
            area1 = self._polygon_area(hull1)
            if area1 <= 1e-9:
                return 0.0
            inter_area = _utils.intersection_area(hull1, hull2)
            return inter_area / area1

        pot = objs_info.get("pot without lid")
        if pot is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pot_hull = get_hull(pot)
        if pot_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not is_within_table_bounds(pot_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pot_area = self._polygon_area(pot_hull)
        if pot_area <= 1e-6:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pot_z = float(pot["pos"][2])

        lid_names = ["small lid", "lid medium", "lid large"]
        valid_candidates = []

        for lname in lid_names:
            lid = objs_info.get(lname)
            if lid is None:
                continue

            lid_hull = get_hull(lid)
            if lid_hull is None:
                continue

            if not is_within_table_bounds(lid_hull):
                continue

            lid_area = self._polygon_area(lid_hull)
            if lid_area <= 1e-6:
                continue

            lid_z = float(lid["pos"][2])
            if not (lid_z > pot_z + Z_ABOVE_EPS):
                continue

            size_ratio = lid_area / pot_area
            if size_ratio < SIZE_RATIO_MIN or size_ratio > SIZE_RATIO_MAX:
                continue

            overlap = compute_overlap_ratio(lid_hull, pot_hull)
            if overlap < OVERLAP_RATIO_MIN - 1e-6:
                continue

            valid_candidates.append(lname)

        return torch.tensor([len(valid_candidates) == 1], dtype=torch.bool, device=self._device)
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success criterion (as graded)
This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the grader
runs). Where the task text says something else, this section and the predicate are what count. It is evaluated once
per replay, on the state right after the last action of your trajectory (no settle steps are added: let things come to
rest inside the trajectory), and must hold after both replays.

- The pot's footprint lies inside the table bounds (1 mm tolerance).
- Exactly one lid qualifies. A lid qualifies when its footprint lies inside the table bounds (1 mm tolerance), its
  position's z is more than 1 cm above the pot's position's z (the origins of their poses: the pot's is at its
  mid-height, z = 0.829 m here; a lid's about 1 cm above its lowest point), its footprint area is 0.85-1.40 times the
  pot's, and at least 80 % of its footprint area lies over the pot's footprint.
- In this scene only `lid large` is inside the size window (area about 1.23 times the pot's; `lid medium` about 0.60,
  `small lid` about 0.25). Its overlap can reach only about 0.81 (the pot's area over the lid's), so it must sit
  within about 1.4 cm of concentric with the pot.

Not checked: contact (whether the lid rests on the pot), any height beyond the one above, whether a gripper holds it,
and where the other two lids are (they never qualify).

Task text vs grader ("Cover the pot precisely using one lid."): "Using one lid" means exactly one qualifying lid: the
wrong-size lids never qualify, so putting them on the pot as well costs nothing. "Cover" does not require the lid to
rest on the pot: the large lid held concentrically above it counts.

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
s = Session("cover_with_lid", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task cover_with_lid --instance /app/instance.json --traj /app/output/trajectory.npz`

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
