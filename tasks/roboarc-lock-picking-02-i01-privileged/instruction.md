# RoboARC (simulator package `topogym`) · lock_picking — frozen instance

You control a simulated robot (**a 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base**; RoboARC on MuJoCo 3.14.0 physics, Nyx rendering) via Python.
**Task:** Pick up the two-tab key from its rest. Insert the tabbed key through all three rotor plates and the final END plate, while respecting their slots and stops. The key's leading tab is longer than its second tab, which sits one plate spacing behind it.

## Success requirements

- Keep the finite-length shaft passing through the full thickness of all four plates at once, facing the insertion direction. Reaching END with only the shaft tip is insufficient.
- The rear edge of the leading tab must clear the outer face of END by at least 1 mm.
- Normal contact with the bore wall and a small tilt are allowed when the shaft still fits through all four bores. The radial numerical contact tolerance is 0.01 mm; do not push the shaft through solid plate material.
- Keep every tab clear of solid plate material whenever it overlaps a plate; account for the key's offset and tilt, not just its rotation about the shaft.
- Keep limited-travel rotor pins within their physical slot bounds (angular tolerance 0.5 degrees).
- You may keep holding the key. Release and zero velocity are not required; all insertion and clearance conditions must remain satisfied throughout confirmation.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- A limited-travel rotor exceeding its allowed bounds ends the episode in failure.
- The key falling more than 100 mm below the tabletop ends the episode in failure.

## Grader details (in addition to the requirements above)

- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 6 mm beyond the tool frame (TCP) along its approach axis when open and about 19 mm when closed (the Robotiq fingertips move forward as they close). Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Sizes: bore radius 7.5 mm, shaft radius 6.5 mm. At each of the 8 plate faces (three 10 mm rotor plates and END, 120 mm apart), the shaft axis' distance from the bore axis plus 6.5 mm / cos(tilt) may exceed 7.5 mm by at most 0.01 mm: about 1.01 mm of offset when the key is straight, which over the stack allows only about 0.31 degrees of tilt.
- The shaft reaches from 425 mm behind the leading tab to 15 mm in front of it; all 8 plate faces must lie within that length.
- Tabs: half-width 4 degrees; the leading tab reaches radius 36 mm and the second tab, 120 mm behind it, 22 mm. Slots: half-width 8 degrees, reaching radius 45 mm (deep) or 28 mm (shallow). A tab that overlaps a plate must sit inside one of that plate's slots that reaches beyond the tab, with an angular margin of at least asin(axis offset / tab radius) + the tilt.
- Rotor stops (from each rotor's start angle, seen from the side the key enters, looking along the key toward END; rotor 1 is the first plate the key reaches): rotor 1 2 degrees counterclockwise and 32 degrees clockwise; rotor 2 32 degrees counterclockwise and 2 degrees clockwise; rotor 3 57 degrees counterclockwise and 7 degrees clockwise. Going more than 0.5 degrees beyond a stop ends the episode.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): lock_key: radius 32 mm, on the key's handle. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- Grading: the verifier replays your trajectory twice in a fresh process. This family's physics runs on the CPU (MuJoCo, float64), so a replay reproduces your own run on the same host; the rule is kept as a margin: each replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; the hold uses the thresholds above too (no tolerance for this family). Success needs both replays to succeed AND at least one of them to reach the goal with the thresholds above within your own rows (not only in the hold; `s.replay(actions, grading=True)` reports it as `["grading"]["strict_success"]`). Nothing else changes. A recording stops at your own success, so a replay whose confirmation ends a few ticks later needs more rows: you may append copies of the final row (holding still) before saving. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "rotor_limit_exceeded", "Key fell below table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

The scene objects are the task's entities (`s.objects()`: `lock_base` (fixed), `lock_disc_0` (fixed), `lock_frame_0` (fixed), `lock_disc_1` (fixed), `lock_frame_1` (fixed), `lock_disc_2` (fixed), `lock_frame_2` (fixed), `key_tray` (fixed), `key_tray_post_0` (fixed), `key_cradle_0_0` (fixed), `key_cradle_0_1` (fixed), `key_tray_post_1` (fixed), `key_cradle_1_0` (fixed), `key_cradle_1_1` (fixed), `lock_goal_post` (fixed), `lock_goal` (fixed), `lock_key`).
Implementation reference: `LockPickingEasierTask.evaluate_state` (module `topogym.tasks.lock_picking.chain`).
This is a partial implementation excerpt; delegated helpers, passage history and the shared release/confirmation
checks also apply. The complete public goal requirements are stated above.
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
        # Tilt is constrained by passage through every finite bore, not by
        # an independent coaxiality angle.
        aligned = axis[0] > 1e-8
        offsets = []
        shaft_coordinates = []
        shaft_in_goal = False
        shaft_through_all = False
        bore_excess = None
        if aligned:
            for i in range(g.disc_count+1):
                x = g.disc_x(i)
                for face in (x-g.disc_thickness/2, x+g.disc_thickness/2):
                    coordinate = (face-p[0])/axis[0]
                    shaft_coordinates.append(float(coordinate))
                    at = p+axis*coordinate
                    offsets.append(float(np.linalg.norm(at[1:]-[g.center_y, g.axis_z])))
            # A normal resting contact need not leave a positive air gap. The
            # 10 um budget covers the 3--6 um residual in the three recorded
            # released poses; it is not a general solver penetration allowance.
            bore_excess = max(offsets) + g.shaft_radius/axis[0] - g.bore_radius
            aligned &= bore_excess <= cfg["shaft_contact_tolerance_m"]
            # write_key() authors the shaft over [-grip_offset-.02, .015].
            # Account for the oblique section's axial extent at both end caps.
            end_padding = g.shaft_radius*np.linalg.norm(axis[1:])/axis[0]
            def spans(coordinates):
                return (min(coordinates)-end_padding >= -g.grip_offset-.02
                        and max(coordinates)+end_padding <= .015)
            shaft_in_goal = spans(shaft_coordinates[-2:])
            shaft_through_all = spans(shaft_coordinates)
        # Conservative x extent of the leading tab under small residual tilt.
        tab_back = p[0]-g.tab_thickness/2*abs(axis[0])-g.tab_radius*np.linalg.norm(rotation.as_matrix()[0, 1:])
        inserted = tab_back >= g.disc_x(g.disc_count)+g.disc_thickness/2+cfg["insertion_margin_m"]
        issues = g.clearance(depth, angle, angles)
        # Expand slab tests for tilt and angular tests for the allowed offset.
        radial_error = max(offsets, default=g.bore_radius)
        angular_allowance = np.degrees(np.arcsin(min(1., radial_error/g.tab_radius)))+tilt
        for tab in range(g.tab_count):
            tab_center = p+rotation.apply([-tab*g.pitch, 0, 0])
            extent = g.tab_thickness/2*abs(axis[0])+g.tab_radius*np.linalg.norm(rotation.as_matrix()[0, 1:])
            for i in range(g.disc_count+1):
                if abs(tab_center[0]-g.disc_x(i)) <= extent+g.disc_thickness/2:
                    margin = (g.slot_margin(angle, angles[i], i, tab) if i < g.disc_count else
                              g.slot_half_deg-g.tab_half_deg-abs((angle-g.endpoint_deg+180)%360-180))
                    if margin < angular_allowance:
                        issues.append(f"tab{tab}/plate{i}/pose_clearance")
        return bool(inserted and shaft_through_all and aligned and not issues), None, dict(
            disc_angles_deg=angles, key_depth=depth, key_tilt_deg=tilt,
            coaxial=bool(aligned), shaft_bore_clear=bool(aligned),
            shaft_bore_excess_m=bore_excess,
            shaft_contact_tolerance_m=cfg["shaft_contact_tolerance_m"],
            shaft_in_goal=bool(shaft_in_goal), shaft_through_all_plates=bool(shaft_through_all),
            leading_tab_inserted=bool(inserted), clearance_issues=issues,
            physical_rotor_frames=True, rotor_mechanism_runtime_verified=False,
            evaluation_status="available", thresholds_calibrated=False,
            goal_evaluation_complete=bool(self.goal_complete))
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
s.status()                         # {'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end', 'review', 'forcing'}
s.safety()                         # since the last call: forcing / deepest contacts / rope volume / table-guard stops vs the limits
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

CLI equivalent of the grader:
`python /opt/tools/rcb_topogym.py replay --task lock_picking --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: +z up. Quaternions are **WXYZ**. The ee_pose action and the proprio TCP pose are given in this world frame.
- Action (8): arm `arm`: 7 joint targets (rad), then `arm_native_gripper` = native drive target (rad, limits 0 .. 0.8: 0 = open, 0.8 = closed, the Robotiq 2F-85's driver joint; open/closed targets in robot_spec); absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (10 physics step(s) per control step). There is no step budget, but a trajectory may have at most
  154000 rows (64.2 min of simulated time): the verifier has to replay it twice within its own time limit, so `s.step` stops
  after that many control steps since the last reset, and a longer trajectory is rejected as invalid (reward 0). The time limit
  (`## Time limit`) is your only budget. One control step takes about 0.093 s of wall clock here, so budget your experiments.
- Grippers: assisted grasping (contact_weld_v1): a gripper whose command moves towards closed takes hold of a graspable part (lock_key) once both fingers touch the same part inside its grasp region, the tool frame within 6 cm of it and the penetration at most 2 mm, for 0.05 s; the part then follows the gripper rigidly. Any command that opens the gripper (by more than 0.2 % of its travel) lets it go. A hold that breaks (the fingers open more than 15 %, the part drifts 1 cm / 0.15 rad from its held pose, the hold has to push or pull its part with more than 65 N averaged over 20 ms, or no finger has touched the part for 0.2 s) is lost, and the gripper must open before it can take hold again; that force is reached when, for example, two held parts that hook into each other are pulled apart, or a held part is pressed into another object. Two grippers never hold the same part; other objects are grasped physically (friction).
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand -> fingertips) = local [0.0, 0.0, 1.0], finger-closing axis = local [0.0, -1.0, 0.0]. The ee_pose action, the proprio tcp pose and the IK use this frame.
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for 0.5 s; that, or one of its failure predicates,
  ends the simulated episode: later steps do not change the execution record or move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (one simulator per process). Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **12 GiB of GPU memory**, **24 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 16 cores for your container; the cap only slows you down.

## Time limit
You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
