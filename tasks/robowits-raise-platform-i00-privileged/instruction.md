# RoboWits · raise_platform — frozen instance

You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis
0.4.7 physics) via Python. **Task:** Place the book on the cup supports.

The scene objects are the env's entities (`s.objects()`: `heavy book`, `cup support 1`, `cup support 2`, `support cube 1`, `support cube 2`; see
`/opt/robowits/gs_gym/envs/robowits/24_raise_platform.py`). RoboWits' success predicate is `_check_success` in that file:
```python
def _check_success(self) -> torch.Tensor:
        """Check if task is successful: book resting on cup supports."""
        objs_info = self.collect_objs_info()

        ELEV_CLEARANCE = 0.005
        CONTACT_TOL = 0.035
        SUPPORT_HORIZ_TOL = 0.05
        FALL_BELOW_TOL = 0.05

        cup1 = objs_info.get("cup support 1")
        cup2 = objs_info.get("cup support 2")
        book = objs_info.get("heavy book")

        if cup1 is None or cup2 is None or book is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if cup1.get("bounds") is None or cup2.get("bounds") is None or book.get("bounds") is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def get_poly(obj):
            hull = obj.get("convex_hull_2d")
            if hull is not None and len(hull) >= 3:
                return [(float(p[0]), float(p[1])) for p in hull]
            b = obj.get("bounds")
            if b is None:
                return None
            xmin, ymin = b[0][0], b[0][1]
            xmax, ymax = b[1][0], b[1][1]
            return [
                (float(xmin), float(ymin)),
                (float(xmax), float(ymin)),
                (float(xmax), float(ymax)),
                (float(xmin), float(ymax)),
            ]

        def obj_center_xy(obj):
            p = obj.get("pos")
            if p is None:
                return None
            if len(p) < 2:
                return None
            return (float(p[0]), float(p[1]))

        def point_in_poly(pt, poly):
            if pt is None or poly is None or len(poly) < 3:
                return False
            x, y = pt
            inside = False
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                if (y1 > y) != (y2 > y):
                    xinters = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
                    if x < xinters:
                        inside = not inside
            return inside

        def point_to_poly_dist(pt, poly):
            if pt is None or poly is None or len(poly) < 2:
                return float("inf")
            x, y = pt
            min_d = float("inf")
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                dx, dy = x2 - x1, y2 - y1
                seg_len2 = dx * dx + dy * dy
                if seg_len2 == 0:
                    d = math.hypot(x - x1, y - y1)
                else:
                    t = ((x - x1) * dx + (y - y1) * dy) / seg_len2
                    t = max(0.0, min(1.0, t))
                    projx = x1 + t * dx
                    projy = y1 + t * dy
                    d = math.hypot(x - projx, y - projy)
                if d < min_d:
                    min_d = d
            return min_d

        book_poly = get_poly(book)
        cup1_center = obj_center_xy(cup1)
        cup2_center = obj_center_xy(cup2)

        cup1_zmax = float(cup1["bounds"][1][2])
        cup2_zmax = float(cup2["bounds"][1][2])
        book_zmin = float(book["bounds"][0][2])

        for obj in (cup1, cup2, book):
            if float(obj["bounds"][0][2]) < (self.TABLE_Z - FALL_BELOW_TOL):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        if (book_zmin - self.TABLE_Z) <= ELEV_CLEARANCE:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_cup_under_book(cup_center, _book_poly=book_poly):
            if _book_poly is None or cup_center is None:
                return False
            if point_in_poly(cup_center, _book_poly):
                return True
            return point_to_poly_dist(cup_center, _book_poly) <= SUPPORT_HORIZ_TOL

        if not (is_cup_under_book(cup1_center) and is_cup_under_book(cup2_center)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_in_contact_vert(book_bottom, support_top):
            return abs(book_bottom - support_top) <= CONTACT_TOL and (book_bottom >= support_top - CONTACT_TOL)

        if not (is_in_contact_vert(book_zmin, cup1_zmax) and is_in_contact_vert(book_zmin, cup2_zmax)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if _utils.check_being_held(book, self._robot):
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

- None of the book and the two cup supports has the bottom of its bounding box more than 5 cm below the table top (z <
  0.71 m fails).
- The book is raised: the bottom of its bounding box is more than 5 mm above the table top (z > 0.765 m).
- Each cup support's position (x, y) lies inside the book's footprint or within 5 cm of its outline.
- The bottom of the book's bounding box is within 3.5 cm of the top of each cup support's bounding box (the cup
  supports are fixed and their boxes end at z = 0.856 m, so the book's bottom must be at z 0.821-0.891 m).
- The book is not held.
- Released and at rest: no part of the robot touches the book, and it moves at most 2 mm during the check window.

Not checked: the support cubes, contact or load (the book may rest on anything at the right height), and the table
bounds.

Task text vs grader ("Place the book on the cup supports."): "On the cup supports" means the book's bottom within
3.5 cm of both cups' tops, with both cups under (or within 5 cm of) its outline; the cups need not carry it.

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
s = Session("raise_platform", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
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
`python /opt/tools/rcb_robowits.py replay --task raise_platform --instance /app/instance.json --traj /app/output/trajectory.npz`

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
Limits for the whole trial, all its processes together (every simulator you start and the `blenderkit` service included): at most **6 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
