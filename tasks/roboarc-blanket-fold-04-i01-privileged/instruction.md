# RoboARC (simulator package `topogym`) · blanket_fold — frozen instance

You control a simulated robot (**two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base**; RoboARC on MuJoCo 3.14.0 physics, Nyx rendering) via Python.
**Task:** Fold the blanket into the target shape on the table, then release it and withdraw. The blanket (600 mm x 480 mm) starts folded over on itself. Fold it in half: turn the far half (the 240 mm of material along the far long edge) over onto the near half about the middle line parallel to the long edges, so that the far edge lies on the near edge and the far corners on the near corners. The folded stack is 600 mm x 240 mm, two layers, the far half upside down on top. Then dog-ear the top layer: turn the top layer's near-left corner (the blanket's original far-left corner) over onto the top layer, the top layer alone, so that its corner point (12 mm in from both edges) lands 100 mm to the right and 100 mm farther than where it lay after the half fold; the crease runs at about 45 degrees across the corner. The target images show the required final state: this is how the folded cloth must look and where it must lie; fold it like this. Near, far, left and right are as seen in the overhead camera cam_high (near = the lower side of its image).
The target images: `/app/goal/target_cam_high.png` (seen from the overhead camera cam_high) and `/app/goal/target_cam_low.png` (from the low oblique camera cam_low).

## Success requirements

- Corners: each of the blanket's four corner points (the material point 12 mm in from both edges at each corner) must lie within 55 mm, in the top view, of its place in the target fold.
- Layer order: the blanket's panels are its regions between the target's creases (the middle line and the dog-ear crease). For each point of the blanket, the panel directly beneath it (material within 8 mm horizontally and 1-20 mm below) must be the same as in the target fold for at least 88% of all points, and for at least 80% of the points that have material beneath them in the target.
- Outline: after the best rigid top-view fit of the blanket onto the target, the 20 mm grid cells it covers must overlap the target's with an intersection over union of at least 0.85.
- Flat: the folded cloth must lie flat on the tabletop, its bottom layer fully in contact with the table surface: every point of the blanket within 35 mm of its height in the target fold, and no point more than 30 mm above the target's highest point.
- Placement: placed where the target images show it, within 40 mm (the blanket's mean top-view position against the target's) and 5 degrees (the fitted rotation).
- Keep every cloth point no more than 8 mm below the tabletop. No material edge may stretch beyond 1.15 times its original length.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 30 mm/s and its displacement from the start of confirmation at most 3 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Any cloth point falling more than 100 mm below the tabletop ends the episode in failure.

## Grader details (in addition to the requirements above)

- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. Over the blanket the floor is the cloth's top: a target that would bring a gripper part other than its finger pads lower than the top of the cloth under it (less about one 1.5 mm layer) is stopped there too, so a gripper cannot crush the cloth into the table; the finger pads of a hand closing to pinch may reach about 6 mm into the cloth. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a cloth particle faster than 20 m/s): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- The blanket is 0.6 m x 0.48 m. Heights are measured at the cloth particles' centres.
- The release clearance is measured from one box around all cloth particles, grown by 8 mm: every robot collision box must stay at least 5 mm from it, i.e. at least 13 mm outside the cloth's bounding box, above its highest point too.
- Soft grasp patches: blanket: spatial radius 18 mm, material radius 18 mm, finger proximity 6 mm, maximum material strain ratio 1.5, exposed patch required. Both fingers must be near the same material patch; penetration and native constraint health checks still apply. Two hands may hold disjoint patches of one object. Material bounds, when present, restrict the admissible region.
- A failure is reported in `s.status()["episode_end"]` as "Cloth fell below the table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

The scene objects are the task's entities (`s.objects()`: `blanket` (deformable, particle)).
Implementation reference: `BlanketFoldMediumTask.evaluate_state` (module `topogym.tasks.blanket_fold.blanket_fold_medium`).
This is a partial implementation excerpt; delegated helpers, passage history and the shared release/confirmation
checks also apply. The complete public goal requirements are stated above.
```python
    def evaluate_state(self, state):
        from topogym.tasks.blanket_fold.redesign import predicate
        particle_state = state["particles"]["blanket"]
        positions = np.asarray(particle_state["position_m"])
        velocity = np.asarray(particle_state["velocity_m_s"])
        if not np.isfinite(positions).all() or not np.isfinite(velocity).all():
            return False, "Non-finite cloth particle state", {}
        heights = positions[:, 2] - self.table_height_m
        if heights.min() < -0.1:
            return False, "Cloth fell below the table", {}
        cfg = self.config
        stretch = np.linalg.norm(positions[self.particle_edges[:, 1]] - positions[self.particle_edges[:, 0]],
                                 axis=1) / self.rest_lengths
        speed = float(np.linalg.norm(velocity, axis=1).max())
        cheap = dict(above_table=float(heights.min()) >= -self.layout.particle_size_m,
                     material_intact=float(stretch.max()) <= cfg["maximum_stretch_ratio"],
                     settled=speed <= cfg["maximum_speed_m_s"])
        fold = None
        # the fold predicate (KD-tree stacking, layer maps) decides the goal only when the cheap gates hold, so it is
        # computed only then and at birth (physics step 0: the frozen instances' birth state hashes include it); a tick
        # whose cheap gates fail reports fold None (not computed), the control step's last tick included (user
        # 2026-10-12, as blanket_flatten's coverage; until then the last tick always computed it, complete_metrics)
        if all(cheap.values()) or int(state.get("physics_step", -1)) == 0:
            fold = predicate.evaluate(self.fold_uv, self.fold_target_particles, positions, self.fold_creases,
                                      th=cfg["fold_tolerances"])
        gates = dict(folded=fold is not None and fold["ok"], **cheap)
        return all(gates.values()), None, dict(
            gates=gates, fold=None if fold is None else {k: v for k, v in fold.items() if k != "thresholds"},
            maximum_height_m=float(heights.max()), maximum_speed_m_s=speed, maximum_stretch_ratio=float(stretch.max()))
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
s = Session("blanket_fold", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
s.reset()                          # back to the frozen initial state (unlimited; a restore of the first recorded state)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, euler_xyz, bounds, size, velocity
p["move_ee"]("left", pos, quat_wxyz, linear=3)   # IK on the robot's model to a TCP pose, then joint interpolation
p["move_joints"]("left", q_arm); p["set_gripper"]("left", 0.0); p["open_gripper"]("left"); p["hold"](10)
s.ee_pose("left"); s.joint_positions(); s.ik("left", pos, quat_wxyz)    # kinematics helpers (arms: ['left', 'right'])
s.render_frame("cam_high")         # RGB uint8 (480, 848, 3) from one camera (s.VIDEO_CAMERAS); s.render_grid()
s.render_depth("cam_high")         # float32 (480, 848) z-depth in metres (0 = no reading), pixel-aligned with render_frame
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.robot_spec()                     # joints (limits), grippers (the grasping rule), PD gains, tool frames ['left_tcp', 'right_tcp']
s.kinematics({"op": "fk", "q": q})   # stateless FK / IK on the robot's model; {"op": "ik", "targets": {"left_tcp": pose7}, "seed": q}
s.joint_velocities(); s.joint_efforts(); s.gripper_width("left")   # measured state in action layout (efforts: the PD drives')
s.object_pose(name); s.object_bounds(name); s.state_sha()          # one object's pose / AABB; the state hash that replays compare
p["object_in_hand"]("left"); p["set_joint_targets"](row, steps=1); p["gripper_quat"](yaw, approach)   # help(p[...])
s.step(action)                     # one low-level action (14 entries, below) = one control step (1/40 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 14) actions, one row per control step
s.status()                         # {'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end', 'review', 'forcing'}
s.safety()                         # since the last call: forcing / deepest contacts / rope volume / table-guard stops vs the limits
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

CLI equivalent of the grader:
`python /opt/tools/rcb_topogym.py replay --task blanket_fold --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: +z up. Quaternions are **WXYZ**. The ee_pose action and the proprio TCP pose are given in this world frame.
- Action (14): arm `left`: 6 joint targets (rad), then `left_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); arm `right`: 6 joint targets (rad), then `right_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (10 physics step(s) per control step). There is no step budget, but a trajectory may have at most
  37000 rows (15.4 min of simulated time): the verifier has to replay it twice within its own time limit, so `s.step` stops
  after that many control steps since the last reset, and a longer trajectory is rejected as invalid (reward 0). The time limit
  (`## Time limit`) is your only budget. One control step takes about 0.38 s of wall clock here, so budget your experiments.
- Grippers: assisted grasping (pbd_local_patch_v1): closing intent and bilateral finger proximity to a material patch of blanket must persist for 0.03 s, with penetration at most 2 mm and the TCP within 6 cm. The admitted patch follows through a local kinematic PBD attachment; the rest remains deformable. Opening by more than 0.2 % of gripper travel releases it. A hold is lost on excessive opening, material strain, invalid volume or follow error above 10 mm; a lost hand must open before reacquiring. Two hands may hold disjoint material patches of the same object; overlapping patches are rejected. Patch radii, strain limits and the exposed-patch requirement are declared in grasp_assist.targets.
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand -> fingertips) = local [1.0, 0.0, -0.023], finger-closing axis = local [0.0, 1.0, 0.008]. The ee_pose action, the proprio tcp pose and the IK use this frame.
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for 0.5 s; that, or one of its failure predicates,
  ends the simulated episode: later steps do not change the execution record or move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (one simulator per process). Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **20 GiB of GPU memory**, **24 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
