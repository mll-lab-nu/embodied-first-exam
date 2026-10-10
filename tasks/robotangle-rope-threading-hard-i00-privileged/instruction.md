# RoboTangle (simulator package `topogym`) · rope_threading — frozen instance

You control a simulated robot (**two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base**; RoboTangle on Genesis 1.2.1 physics, Nyx rendering) via Python.
**Task:** Thread the rope through the cyan ring (R1) then green ring (R2) then purple ring (R3), in that order along the rope from material start to material end.

## Success requirements

- Required directions along that material order: cyan ring (R1): cross toward the side containing the green ring (R2); green ring (R2): cross away from the side containing the cyan ring (R1); purple ring (R3): cross away from the side containing the green ring (R2). Do not reverse the crossing directions.
- Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. Keep the full rope thickness clear of the rim, with an additional 0.1 mm radial margin; the passage must clear both sides of each ring's thickness, not just its middle plane.
- Keep every rope point at or below 10 mm/s. Holding is allowed; release is not required.
- Keep the rope intact; collapsed or inverted rope volume is not accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Invalid rope volume ends the episode in failure.

## Grader details (in addition to the requirements above)

- The rope's Young's modulus is 5000 kPa. Gripper pressure can deform it. A crushed rope volume (an inverted volume element) ends the episode only once it has lasted at least 0.25 s (7 consecutive physics ticks; while it lasts, the goal cannot be confirmed); an invalid soft-body solver state is a simulator breakdown (below). Close to about half the rope's diameter and slow down in the last centimetre.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (an invalid soft-body solver state): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- Sizes (rope radius 4 mm): R1: inner radius 50 mm, tube radius 6 mm, centreline passage radius 46.9 mm on the middle plane and 49.2 mm on the two tube-offset planes; R2: inner radius 50 mm, tube radius 6 mm, centreline passage radius 46.9 mm on the middle plane and 49.2 mm on the two tube-offset planes; R3: inner radius 50 mm, tube radius 6 mm, centreline passage radius 46.9 mm on the middle plane and 49.2 mm on the two tube-offset planes.
- Aperture check: round_ring, compression allowance 1 mm. This allowance changes the geometric passage test; the collision geometry stays as declared.
- The material start is the rope end that is farther from the rings at the start.
- Only the grippers' fingers collide with the rope and the rings: every other robot part (palms, wrists, arm links, bases) passes through them without contact, so only the fingers can push, pinch or hold the rope.
- Soft grasp patches: rope: spatial radius 14 mm, material radius 18 mm, finger proximity 6 mm, maximum material strain ratio 2, exposed patch not required. Both fingers must be near the same material patch; penetration and native constraint health checks still apply. Two hands may hold disjoint patches of one object. Material bounds, when present, restrict the admissible region.
- Grading: the verifier replays your trajectory twice in a fresh process. This family's physics runs on the GPU, which is not bit-deterministic, so a replay can differ slightly from your own run: each replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (50 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; the hold uses the thresholds above too (no tolerance for this family). Success needs both replays to succeed; each of them may complete its confirmation within that hold (whether one reached the goal with the thresholds above within your own rows is recorded, `strict_goal_reached`, not required). Nothing else changes. A recording stops at your own success, so a replay whose confirmation ends a few ticks later completes it in that hold; copies of the final row (holding still) appended before saving give it more room. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "rope_volume_invalid: <what>" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

The scene objects are the task's entities (`s.objects()`: `rope` (deformable, fem), `R1` (fixed), `R1_stand` (fixed), `R1_base` (fixed), `R2` (fixed), `R2_stand` (fixed), `R2_base` (fixed), `R3` (fixed), `R3_stand` (fixed), `R3_base` (fixed), `left_base_riser` (fixed), `right_base_riser` (fixed)).
Implementation reference: `RopeThreadingHardTask.evaluate_state` (module `topogym.tasks.rope_threading.rope_threading_hard`).
This is a partial implementation excerpt; delegated helpers, passage history and the shared release/confirmation
checks also apply. The complete public goal requirements are stated above.
```python
    def evaluate_state(self, state):
        soft = state["fem"]["rope"]
        points = sample_material_centerline(soft, *self.centerline_map)
        quiet, speed = soft_speed(soft, self.config["terminal"]["maximum_speed_m_s"])
        expected = list(self.layout.required_crossings())
        hits, ambiguous = [], False
        thickness_ok = True
        for ring in self.layout.rings():
            body = state["bodies"][ring["name"]]
            center = body_points(body, [ring["center_m"]])[0]
            q = np.asarray(body["quaternion_wxyz"])
            normal = Rotation.from_quat(q[[1, 2, 3, 0]]).apply(ring["normal"])
            radius = usable_rope_aperture_radius(ring, self.layout.rope_radius_m, self.config["terminal"], self.config["aperture_contact_allowance_m"])
            crossings, uncertain = aperture_crossings(points, center, normal, radius)
            nominal, _ = aperture_crossings(points, center, normal, ring["radius_m"]-ring["tube_radius_m"])
            thickness_ok &= len(nominal) == len(crossings)
            ambiguous |= uncertain
            for offset in (-ring["tube_radius_m"], ring["tube_radius_m"]):
                slice_radius = usable_rope_aperture_radius(ring, self.layout.rope_radius_m,
                    self.config["terminal"], self.config["aperture_contact_allowance_m"],
                    axial_offset_m=offset, profile=self.config["aperture_check_profile"])
                boundary, unsure = aperture_crossings(points, center+offset*normal, normal, slice_radius)
                ambiguous |= unsure
                thickness_ok &= [h["sign"] for h in boundary] == [h["sign"] for h in crossings]
            hits.extend(dict(hit, ring=ring["name"]) for hit in crossings)
        hits.sort(key=lambda h: h["material_coordinate"])
        sequence = [(h["ring"], h["sign"]) for h in hits]
        intact = ipc_integrity(state, ("rope",))
        return (bool(sequence == expected and thickness_ok and not ambiguous and quiet and intact is True),
                "rope_volume_invalid" if intact is False else None,
                dict(crossing_sequence=sequence, ambiguous=bool(ambiguous), thickness_clear=bool(thickness_ok),
                     aperture_contact_allowance_m=self.config["aperture_contact_allowance_m"],
                     aperture_check_profile=self.config["aperture_check_profile"],
                     quiet=quiet, **speed, evaluation_status="available" if intact is not None else "unavailable",
                     thresholds_calibrated=False, goal_evaluation_complete=bool(self.goal_complete)))
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
s = Session("rope_threading", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
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
s.step(action)                     # one low-level action (14 entries, below) = one control step (1/25 s)
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
`python /opt/tools/rcb_topogym.py replay --task rope_threading --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (-0.136, 0.000, 0.920), table top at z = 0.920, +z up. Quaternions are **WXYZ**.
- Action (14): arm `left`: 6 joint targets (rad), then `left_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); arm `right`: 6 joint targets (rad), then `right_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at 25 Hz (1 physics step(s) per control step). There is no step budget, but a trajectory may have at most
  40000 rows (26.7 min of simulated time): the verifier has to replay it twice within its own time limit, so `s.step` stops
  after that many control steps since the last reset, and a longer trajectory is rejected as invalid (reward 0). Your
  wall-clock budget is 360 min (21600 s). One control step takes about 0.36 s of wall clock here, so budget your experiments.
- Grippers: assisted grasping (ipc_soft_band_v1): closing intent and bilateral finger proximity to a material patch of rope must persist for 0.02 s, with penetration at most 6 mm and the TCP within 6 cm. The admitted patch follows through an elastic IPC attachment; the rest remains deformable. Opening by more than 0.2 % of gripper travel releases it. A hold is lost on excessive opening, material strain, invalid volume or follow error above 25 mm; a lost hand must open before reacquiring. Two hands may hold disjoint material patches of the same object; overlapping patches are rejected. Patch radii, strain limits and the exposed-patch requirement are declared in grasp_assist.targets.
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand -> fingertips) = local [1.0, 0.0, -0.023], finger-closing axis = local [0.0, 1.0, 0.008]. The ee_pose action, the proprio tcp pose and the IK use this frame.
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for 0.5 s; that, or one of its failure predicates,
  ends the simulated episode: later steps do not change the execution record or move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (Genesis initialises once). Do not call `s.close()` before writing every output.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **16 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.
