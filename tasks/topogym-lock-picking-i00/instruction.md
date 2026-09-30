# TopoGym · lock_picking — frozen instance

You control a simulated robot (**a 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base**; TopoGym on Genesis 1.2.1 physics, Nyx rendering) via Python.
**Task:** Insert the tabbed key through the lock plates. Rotate and translate the key to negotiate the rotor slots until its leading tab clears the final plate and the shaft reaches the insertion goal. Keep the key aligned with the bores; the rotor pins must remain constrained by their physical slots. Do not force the key or tabs through solid plates. Hold the completed configuration still.

The scene objects are the task's entities (`s.objects()`: `lock_base` (fixed), `lock_disc_0` (fixed), `lock_frame_0` (fixed), `lock_disc_1` (fixed), `lock_frame_1` (fixed), `lock_disc_2` (fixed), `lock_frame_2` (fixed), `key_tray` (fixed), `key_tray_post_0` (fixed), `key_cradle_0_0` (fixed), `key_cradle_0_1` (fixed), `key_tray_post_1` (fixed), `key_cradle_1_0` (fixed), `key_cradle_1_1` (fixed), `lock_goal_post` (fixed), `lock_goal` (fixed), `lock_key`). The success predicate is
`LockPickingMediumTask.evaluate_state` (module `topogym.tasks.lock_picking.lock_picking_medium`); the task succeeds once it holds continuously for
0.5 s:
```python
    def evaluate_state(self, state):
        p = np.asarray(state["bodies"]["lock_key"]["position_m"])
        if not np.isfinite(p).all():
            return False, "Non-finite key state", {}
        if p[2] < self.table_height_m - 0.1:
            return False, "Key fell below table", {}
        cfg, g = self.config["terminal"], self.layout
        angles = []
        for i, stop in enumerate(self.config["rotor_stops"]):
            value = np.asarray(state["articulations"][f"lock_disc_{i}"]["joints"]["disc_hinge"]["position"], float)
            if value.size != 1 or not np.isfinite(value).all():
                raise ValueError("Expected one finite rotor angle")
            angle = float(np.degrees(value.item()))
            angles.append(angle)
            lo, hi = stop["bounds_deg"]
            if hi-lo < 360-1e-8 and not lo-cfg["rotor_tolerance_deg"] <= angle <= hi+cfg["rotor_tolerance_deg"]:
                return False, "rotor_limit_exceeded", dict(rotor=i, angle_deg=angle)
        q = np.asarray(state["bodies"]["lock_key"]["quaternion_wxyz"], float)
        if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
            raise ValueError("Invalid key orientation")
        rotation = Rotation.from_quat(q[[1, 2, 3, 0]])
        axis = rotation.apply([1., 0, 0])
        tilt = float(np.degrees(np.arccos(np.clip(axis[0], -1, 1))))
        radial = rotation.apply([0., 0, 1.])
        angle = float(np.degrees(np.arctan2(radial[1], radial[2])))
        depth = (p[0]-g.first_x)/g.pitch+1
        aligned = tilt <= cfg["maximum_tilt_deg"]
        offsets = []
        shaft_in_goal = False
        if aligned:
            for i in range(4):
                x = g.disc_x(i)
                for face in (x-g.disc_thickness/2, x+g.disc_thickness/2):
                    at = p+axis*((face-p[0])/axis[0])
                    offsets.append(float(np.linalg.norm(at[1:]-[g.center_y, g.axis_z])))
            aligned &= max(offsets) + g.shaft_radius/axis[0] + cfg["shaft_clearance_m"] < g.bore_radius
            goal_faces = [(g.disc_x(3)+side*g.disc_thickness/2-p[0])/axis[0] for side in (-1,1)]
            shaft_in_goal = min(goal_faces) >= -g.grip_offset-.02 and max(goal_faces) <= .015
        # Conservative x extent of the leading tab under small residual tilt.
        tab_back = p[0]-g.tab_thickness/2*abs(axis[0])-g.tab_radius*np.linalg.norm(rotation.as_matrix()[0, 1:])
        inserted = tab_back >= g.disc_x(3)+g.disc_thickness/2+cfg["insertion_margin_m"]
        issues = g.clearance(depth, angle, angles)
        # Expand slab tests for tilt and angular tests for the allowed offset.
        radial_error = max(offsets, default=g.bore_radius)
        angular_allowance = np.degrees(np.arcsin(min(1., radial_error/g.tab_radius)))+tilt
        for tab in range(3):
            tab_center = p+rotation.apply([-tab*g.pitch, 0, 0])
            extent = g.tab_thickness/2*abs(axis[0])+g.tab_radius*np.linalg.norm(rotation.as_matrix()[0, 1:])
            for i in range(4):
                if abs(tab_center[0]-g.disc_x(i)) <= extent+g.disc_thickness/2:
                    margin = (g.slot_margin(angle, angles[i], i) if i < 3 else
                              g.slot_half_deg-g.tab_half_deg-abs((angle-g.endpoint_deg+180)%360-180))
                    if margin < angular_allowance:
                        issues.append(f"tab{tab}/plate{i}/pose_clearance")
        return bool(inserted and shaft_in_goal and aligned and not issues), None, dict(
            disc_angles_deg=angles, key_depth=depth, key_tilt_deg=tilt,
            coaxial=bool(aligned), shaft_in_goal=bool(shaft_in_goal), leading_tab_inserted=bool(inserted), clearance_issues=issues,
            physical_rotor_frames=True, rotor_mechanism_runtime_verified=False,
            evaluation_status="available", thresholds_calibrated=False, goal_evaluation_complete=False)
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Startup and long-running commands

- Scene initialization and kernel compilation can take minutes. Actual time depends on the task, hardware, and load.
  Quiet logs during initialization do not by themselves mean failure. Use `python -u` for unbuffered script output.
- A command tool's wait/yield interval (for example, `yield_time_ms=30000`) is not the command's lifetime.
  When a command is still running, retain its process/session identifier and continue waiting for that same command.
  With Codex's `exec_command`, expose the complete result, including `session_id` and `exit_code`, rather than only
  `output` (for example, `text(r)` instead of only `text(r.output)`). Continue it with `write_stdin` using the returned
  `session_id` and no input. An outer JavaScript wrapper saying `Script completed` does not prove Python has exited.
  Use the corresponding wait/status operation if another command tool is provided.
- Do not rerun a command just because its first wait returned partial logs. Confirm the original process has exited
  before starting a replacement; if cancellation is necessary, stop only your own identified process and confirm exit.
- Keep the task's simulator and sensor configuration. Waiting does not extend the actual agent wall-clock budget.
- Keep at most one live simulator process in this trial at a time. A new Python process calling `Session(...)`
  creates another scene and consumes more GPU memory; separate replay/render CLI commands also create scenes.
- Reuse the initialized Session for observations, actions, reset, and replay. Avoid separate initialization-only probes:
  put the first useful actions and trajectory save in the same script that initializes the simulator.
- Initialization consumes the agent budget. Save a real trajectory as soon as practical and keep saving progress.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_topogym import Session
s = Session("lock_picking", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
s.reset()                          # back to the frozen initial state (unlimited; a restore of the first recorded state)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, euler_xyz, bounds, size, velocity
p["move_ee"]("arm", pos, quat_wxyz, linear=3)   # IK on the robot's model to a TCP pose, then joint interpolation
p["move_joints"]("arm", q_arm); p["set_gripper"]("arm", 0.0); p["open_gripper"]("arm"); p["hold"](10)
s.ee_pose("arm"); s.joint_positions(); s.ik("arm", pos, quat_wxyz)    # kinematics helpers (arms: ['arm'])
s.render_frame("agentview")         # RGB uint8 (480, 848, 3) from one camera (s.VIDEO_CAMERAS); s.render_grid()
s.render_depth("agentview")         # float32 (480, 848) z-depth in metres (0 = no reading), pixel-aligned with render_frame
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.robot_spec()                     # joints (limits), grippers (the grasping rule), PD gains, tool frames ['arm_tcp']
s.kinematics({"op": "fk", "q": q})   # stateless FK / IK on the robot's model; {"op": "ik", "targets": {"arm_tcp": pose7}, "seed": q}
s.joint_velocities(); s.joint_efforts(); s.gripper_width("arm")   # measured state in action layout (efforts: the PD drives')
s.object_pose(name); s.object_bounds(name); s.state_sha()          # one object's pose / AABB; the state hash that replays compare
p["object_in_hand"]("arm"); p["set_joint_targets"](row, steps=1); p["gripper_quat"](yaw, approach)   # help(p[...])
s.step(action)                     # one low-level action (8 entries, below) = one control step (1/40 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 8) actions, one row per control step
s.status()                         # {'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end'}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

CLI equivalent of the grader:
`python /opt/tools/rcb_topogym.py replay --task lock_picking --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (-0.570, 0.000, 0.920), table top at z = 0.920, +z up. Quaternions are **WXYZ**.
- Action (8): arm `arm`: 7 joint targets (rad), then `arm_gripper` = opening width (m, 0 closed .. 0.0854 open); absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (10 physics step(s) per control step). There is no step budget; your
  wall-clock budget is 90 min (5400 s). One control step takes about 0.9 s of wall clock here (the
  simulator keeps a full checkpoint of every physics step), so budget your experiments.
- Grippers: physical grasping only (no assisted grasping): closing on an object squeezes it with the gripper's PD force; friction holds it.
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand -> fingertips) = local [0.0, 0.0, 1.0], finger-closing axis = local [-0.0, -1.0, 0.0]. The ee_pose action, the proprio tcp pose and the IK use this frame.
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for 0.5 s; that, or one of its failure predicates,
  ends the simulated episode: later steps are recorded but no longer move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (Genesis initialises once). Do not call `s.close()` before writing every output.
