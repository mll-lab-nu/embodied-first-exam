# RoboTangle (simulator package `topogym`) · blanket_flatten — frozen instance

You control a simulated robot (**two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base**; RoboTangle on Genesis 1.2.1 physics, Nyx rendering) via Python.
**Task:** Unfold and spread the blanket flat on the table without overlaps or excessive stretching, then release it and withdraw.

## Success requirements

- Cover at least 95% of the blanket's unfolded material area in top-down projection. Overlapping layers count only once, holes do not count, and a large outer bounding box is insufficient.
- Keep every cloth point at most 30 mm above the tabletop and no more than 8 mm below it.
- No material edge may stretch beyond 1.15 times its original length. Raised corners or pulling the blanket taut in the air do not count.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 30 mm/s and its displacement from the start of confirmation at most 3 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Any cloth point falling more than 100 mm below the tabletop ends the episode in failure.

## Grader details (in addition to the requirements above)

- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a cloth particle faster than 20 m/s): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- The blanket is 0.6 m x 0.48 m (0.288 m^2), so the coverage needs at least 0.2736 m^2 of its area in the top view. Heights are measured at the cloth particles' centres.
- The release clearance is measured from one box around all cloth particles, grown by 8 mm: every robot collision box must stay at least 5 mm from it, i.e. at least 13 mm outside the cloth's bounding box, above its highest point too.
- Soft grasp patches: blanket: spatial radius 18 mm, material radius 18 mm, finger proximity 6 mm, maximum material strain ratio 1.5, exposed patch required. Both fingers must be near the same material patch; penetration and native constraint health checks still apply. Two hands may hold disjoint patches of one object. Material bounds, when present, restrict the admissible region.
- Grading: the verifier replays your trajectory twice in a fresh process. This family's physics runs on the GPU, which is not bit-deterministic, so a replay can differ slightly from your own run: each replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; during that hold it accepts a blanket coverage of 92% instead of 95% and cloth speeds up to 80 mm/s instead of 30 mm/s (the displacement limit during the confirmation stays). Success needs both replays to succeed AND at least one of them to reach the goal with the thresholds above within your own rows (not only in the hold). Nothing else is relaxed: every other condition, the failure conditions and the confirmation time are the same. A recording stops at your own success, so a replay whose confirmation ends a few ticks later needs more rows: you may append copies of the final row (holding still) before saving. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "Cloth fell below the table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

The scene objects are the task's entities (`s.objects()`: `blanket` (deformable, particle)).
Implementation reference: `BlanketFlattenMediumTask.evaluate_state` (module `topogym.tasks.blanket_flatten.blanket_flatten_medium`).
This is a partial implementation excerpt; delegated helpers, passage history and the shared release/confirmation
checks also apply. The complete public goal requirements are stated above.
```python
    def evaluate_state(self, state):
        from topogym.evaluation.cloth_metrics import footprint_area, footprint_area_slabs, footprint_area_upper_bound

        particle_state = state["particles"]["blanket"]
        positions = np.asarray(particle_state["position_m"])
        velocity = np.asarray(particle_state["velocity_m_s"])
        if not np.isfinite(positions).all() or not np.isfinite(velocity).all():
            return False, "Non-finite cloth particle state", {}
        heights = positions[:, 2] - self.table_height_m
        if heights.min() < -0.1:
            return False, "Cloth fell below the table", {}
        cfg = self.config
        stretch = (
            np.linalg.norm(
                positions[self.particle_edges[:, 1]]
                - positions[self.particle_edges[:, 0]],
                axis=1,
            )
            / self.rest_lengths
        )
        speed = float(np.linalg.norm(velocity, axis=1).max())
        cheap = dict(
            flat=float(heights.max()) <= cfg["maximum_height_m"],
            above_table=float(heights.min()) >= -self.layout.particle_size_m,
            material_intact=float(stretch.max()) <= cfg["maximum_stretch_ratio"],
            settled=speed <= cfg["maximum_speed_m_s"],
        )
        # The footprint union is ~88 % of a control step at every 2.5 ms tick. It only decides the goal when every cheap
        # gate holds, so it is computed then, and on each control step's last tick (complete_metrics, set by Env.step) so the
        # metrics a step reports stay complete; on the other ticks the goal is false either way (identical predicate).
        coverage = None
        complete = getattr(self, "complete_metrics", True)
        if all(cheap.values()) or complete:
            area = self.layout.length_m * self.layout.width_m
            # On a tick inside the control step only the goal decision is used. When even an upper bound of the union
            # stays 1e-3 below the threshold, the goal is false whatever the union (identical decision, as for a failed
            # cheap gate), so the union is not computed; the threshold is read at this tick (a grading replay's relaxed
            # threshold included). Ticks of a confirmation window always compute it (the goal holds there).
            if complete or footprint_area_upper_bound(positions, self.particle_faces) / area >= cfg["minimum_coverage_ratio"] - 1e-3:
                coverage = footprint_area_slabs(positions, self.particle_faces) / area
        if coverage is not None:
            # The slab sum equals the union to ~1e-15 on cloth states; on extreme synthetic folds GEOS' one-shot union
            # itself drifts by up to ~3e-4 (the slab sum then agrees with a 10 nm grid union). Within 1e-3 of the
            # threshold the shipped union decides, so the gate is identical (scripts/check_blanket_coverage_slabs.py).
            if abs(coverage - cfg["minimum_coverage_ratio"]) < 1e-3:
                coverage = footprint_area(positions, self.particle_faces) / area
        gates = dict(covered=coverage is not None and coverage >= cfg["minimum_coverage_ratio"], **cheap)
        return (
            all(gates.values()),
            None,
            dict(
                gates=gates,
                coverage_ratio=None if coverage is None else float(coverage),
                maximum_height_m=float(heights.max()),
                maximum_speed_m_s=speed,
                maximum_stretch_ratio=float(stretch.max()),
            ),
        )
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
s = Session("blanket_flatten", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
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
`python /opt/tools/rcb_topogym.py replay --task blanket_flatten --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (-0.136, 0.000, 0.920), table top at z = 0.920, +z up. Quaternions are **WXYZ**.
- Action (14): arm `left`: 6 joint targets (rad), then `left_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); arm `right`: 6 joint targets (rad), then `right_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (10 physics step(s) per control step). There is no step budget; your
  wall-clock budget is 360 min (21600 s). One control step takes about 0.4 s of wall clock here, so budget your experiments.
- Grippers: assisted grasping (pbd_local_patch_v1): closing intent and bilateral finger proximity to a material patch of blanket must persist for 0.03 s, with penetration at most 2 mm and the TCP within 6 cm. The admitted patch follows through a local kinematic PBD attachment; the rest remains deformable. Opening by more than 0.2 % of gripper travel releases it. A hold is lost on excessive opening, material strain, invalid volume or follow error above 10 mm; a lost hand must open before reacquiring. Two hands may hold disjoint material patches of the same object; overlapping patches are rejected. Patch radii, strain limits and the exposed-patch requirement are declared in grasp_assist.targets.
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand -> fingertips) = local [1.0, 0.0, -0.023], finger-closing axis = local [0.0, 1.0, 0.008]. The ee_pose action, the proprio tcp pose and the IK use this frame.
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for 0.5 s; that, or one of its failure predicates,
  ends the simulated episode: later steps do not change the execution record or move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (Genesis initialises once). Do not call `s.close()` before writing every output.
