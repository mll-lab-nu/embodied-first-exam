# TopoGym · rope_threading — frozen instance

You control a simulated robot (**two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base**; TopoGym on Genesis 1.2.1 physics, Nyx rendering) via Python.
**Task:** Thread the rope through the cyan ring, then the green ring, then the purple ring, following the rope from its material start to material end. Pass fully through each aperture without extra crossings, intersecting ring material, or damaging the rope. Keep the threaded rope still.

The scene objects are the task's entities (`s.objects()`: `rope` (deformable, fem), `R1` (fixed), `R1_stand` (fixed), `R1_base` (fixed), `R2` (fixed), `R2_stand` (fixed), `R2_base` (fixed), `R3` (fixed), `R3_stand` (fixed), `R3_base` (fixed)). The success predicate is
`RopeThreadingMediumTask.evaluate_state` (module `topogym.tasks.rope_threading.rope_threading_medium`); the task succeeds once it holds continuously for
0.5 s:
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
            radius = ring["radius_m"]-ring["tube_radius_m"]-self.layout.rope_radius_m-self.config["terminal"]["aperture_margin_m"]
            crossings, uncertain = aperture_crossings(points, center, normal, radius)
            nominal, _ = aperture_crossings(points, center, normal, ring["radius_m"]-ring["tube_radius_m"])
            thickness_ok &= len(nominal) == len(crossings)
            ambiguous |= uncertain
            for offset in (-ring["tube_radius_m"], ring["tube_radius_m"]):
                boundary, unsure = aperture_crossings(points, center+offset*normal, normal, radius)
                ambiguous |= unsure
                thickness_ok &= [h["sign"] for h in boundary] == [h["sign"] for h in crossings]
            hits.extend(dict(hit, ring=ring["name"]) for hit in crossings)
        hits.sort(key=lambda h: h["material_coordinate"])
        sequence = [(h["ring"], h["sign"]) for h in hits]
        intact = ipc_integrity(state, ("rope",))
        return (bool(sequence == expected and thickness_ok and not ambiguous and quiet and intact is True),
                "rope_volume_invalid" if intact is False else None,
                dict(crossing_sequence=sequence, ambiguous=bool(ambiguous), thickness_clear=bool(thickness_ok),
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
s.step(action)                     # one low-level action (14 entries, below) = one control step (1/40 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 14) actions, one row per control step
s.status()                         # {'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end'}
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
- Action (14): arm `left`: 6 joint targets (rad), then `left_gripper` = opening width (m, 0 closed .. 0.057378 open); arm `right`: 6 joint targets (rad), then `right_gripper` = opening width (m, 0 closed .. 0.057378 open); absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (10 physics step(s) per control step). There is no step budget; your
  wall-clock budget is 90 min (5400 s). One control step takes about 6.6 s of wall clock here (the
  simulator keeps a full checkpoint of every physics step), so budget your experiments.
- Grippers: physical grasping only (no assisted grasping): closing on an object squeezes it with the gripper's PD force; friction holds it.
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand -> fingertips) = local [1.0, 0.0, -0.023], finger-closing axis = local [0.0, 1.0, 0.011]. The ee_pose action, the proprio tcp pose and the IK use this frame.
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for 0.5 s; that, or one of its failure predicates,
  ends the simulated episode: later steps are recorded but no longer move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (Genesis initialises once). Do not call `s.close()` before writing every output.
