# TopoGym · interlocked_claws — frozen instance

You control a simulated robot (**two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base**; TopoGym on Genesis 1.2.1 physics, Nyx rendering) via Python.
**Task:** Separate and place the entire brown claw piece inside the green dashed goal region. Keep the other claw piece on the puzzle/system side.

## Success requirements

- Put every part of the entire brown claw piece inside the fixed goal volume, leaving at least 1 mm inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height. It need not touch the table. The goal volume extends 404.198 mm above the tabletop.
- Keep the other claw piece, and every other remaining puzzle component, entirely on the system side of the fixed separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding the target with the gripper is allowed; release is not required.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Finger contact with a held movable piece may penetrate at most 2 mm; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand. All other task contacts, including piece-piece, table, arm and gripper-housing contacts, may penetrate at most 1 mm. Exceeding either limit ends the episode in failure.

## Grader details (in addition to the requirements above)

- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 412.2 mm x 412.2 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The other claw piece is free to move (its speed is not checked), but no point of it may cross that plane.
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step). "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active assisted grasp), the other finger is back at the 1 mm limit in the same tick.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): piece_0: radius 30 mm; piece_1: radius 30 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- A failure is reported in `s.status()["episode_end"]` as "Held finger contact penetration exceeded 2 mm", "Task contact penetration exceeded 1 mm" or "A task body fell below the table".

The scene objects are the task's entities (`s.objects()`: `piece_0`, `piece_1`, `goal_region` (fixed)).
Implementation reference: `InterlockedClawsMediumTask.evaluate_state` (module `topogym.tasks.interlocked_claws.interlocked_claws_medium`).
This is a partial implementation excerpt; delegated helpers, passage history and the shared release/confirmation
checks also apply. The complete public goal requirements are stated above.
```python
    def evaluate_state(self, state):
        return self.evaluate_placement(state)
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
s = Session("interlocked_claws", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
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
`python /opt/tools/rcb_topogym.py replay --task interlocked_claws --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (-0.136, 0.000, 0.920), table top at z = 0.920, +z up. Quaternions are **WXYZ**.
- Action (14): arm `left`: 6 joint targets (rad), then `left_gripper` = opening width (m, 0 closed .. 0.057385 open); arm `right`: 6 joint targets (rad), then `right_gripper` = opening width (m, 0 closed .. 0.057385 open); absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (10 physics step(s) per control step). There is no step budget; your
  wall-clock budget is 180 min (10800 s). One control step takes about 0.5 s of wall clock on an unloaded GPU, and up to about 0.6 s when other simulations share the GPU; the call metadata reports the time, so budget your experiments.
- Grippers: assisted grasping (contact_weld_v1): a gripper whose command moves towards closed takes hold of a graspable part (piece_0, piece_1) once both fingers touch the same part inside its grasp region, the tool frame within 6 cm of it and the penetration at most 2 mm, for 0.02 s; the part then follows the gripper rigidly. Any command that opens the gripper (by more than 0.2 % of its travel) lets it go. A hold that breaks (the fingers open more than 15 %, or the part drifts 1 cm / 0.15 rad from its held pose) is lost, and the gripper must open before it can take hold again. Two grippers never hold the same part; other objects are grasped physically (friction); the grippers start closed on their parts and may acquire after the same bilateral-contact confirmation without another close command.
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand -> fingertips) = local [1.0, 0.0, -0.023], finger-closing axis = local [0.0, 1.0, 0.003]. The ee_pose action, the proprio tcp pose and the IK use this frame.
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for 0.5 s; that, or one of its failure predicates,
  ends the simulated episode: later steps are recorded but no longer move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (Genesis initialises once). Do not call `s.close()` before writing every output.
