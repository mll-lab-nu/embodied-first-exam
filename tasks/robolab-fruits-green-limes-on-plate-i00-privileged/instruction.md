# RoboLab · fruits_green_limes_on_plate — frozen instance

You control a simulated **Franka Panda arm with a Robotiq 2F-85 gripper** (NVIDIA RoboLab's DROID setup on Isaac Lab 2.3 /
Isaac Sim 5.1, PhysX physics) via Python. **Task:** Put all the green fruit on the plate.

The scene objects are the env's rigid objects (`s.objects()`: `lemon_01`, `lemon_02`, `lime01`, `lime01_01`, `orange_01`, `orange_02`, `pomegranate01`, `pumpkinlarge`, `pumpkinsmall`, `redonion`, `serving_bowl`, `clay_plates`, `wooden_spoons`, `spatula`, `storage_box`, `table`; see
`/opt/robolab/robolab/tasks/benchmark/fruits_green_limes_on_plate.py`). RoboLab's success predicate is the `success` termination
term in that file (`object_on_top` in `/opt/robolab/robolab/core/task/conditionals.py`); it also ends the episode:
```python
class FruitsGreenLimesOnPlateTerminations:
    time_out = DoneTerm(func=mdp.time_out, time_out=True)
    success = DoneTerm(
        func=object_on_top,
        params={"object": ["lime01", "lime01_01"], "reference_object": "clay_plates", "logical": "all", "require_gripper_detached": True}
    )
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in two fresh processes and scored 1 if RoboLab's success predicate
holds in both replays (the predicate is checked after every control step and the first step where it holds ends the
episode: later rows are never executed) and both end in the same state, else 0. Also leave the script that produced it at
`/app/output/gen.py`. Save a working trajectory as soon as you have one and overwrite it as you improve it: whatever is in
`/app/output/` when the time is up is graded.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_robolab import Session
s = Session("fruits_green_limes_on_plate", instance="/app/instance.json")   # ~1-2 min: launches Isaac Sim, builds the scene, restores the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact state restore)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, bounds, size, velocity (env-local frame)
p["move_ee"](pos, quat_wxyz, speed=0.2)   # straight-line fingertip move, one differential-IK update per control step
p["move_joints"](q7); p["set_gripper"](True); p["open_gripper"](); p["hold"](10)
s.ee_pose(); s.joint_positions(); s.ik_step(pos, quat_wxyz)      # kinematics helpers (differential IK, one update per call)
s.render_frame("egocentric_mirrored_camera")   # RGB uint8 of one camera, current state (s.VIDEO_CAMERAS); s.render_grid()
s.step(action)                     # one low-level action (7 joint targets + gripper command) = one control step (1/15 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 8) actions, one row per control step
s.status()                         # {'success': bool, 'progress': float, 'sim_steps': int, 'resets': int, 'state_sha': str, 'terminated': bool}
s.replay(actions)                  # resets, replays open-loop, returns status (the first replay in a process is exact)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state, writes a tiled camera video
s.render_depth("wrist_cam")        # with Session(..., depth=True) (steps ~13 % slower): float32 (H,W) z-depth in metres (0 = no reading), pixel-aligned with render_frame(cam)
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world->camera, OpenCV axes), cam2world_gl, mount, moves
s.robot_spec(); s.proprio()        # joints + limits, gripper, gains, tool frames; measured joint pos/vel, tcp pose, opening, efforts
s.kinematics({"op": "fk", "q": q7}); s.kinematics({"op": "ik", "targets": {"tcp": pose7}, "seed": q7})   # stateless FK / IK (s.kinematics_spec())
s.gripper_angle(); s.eef_frame_pose(); s.body_pose("base_link")   # finger_joint (rad); the flange frame; any robot link's pose
p["get_object_points"](name); p["get_object_pose"](name)          # an object's surface points (N,3) / (pos, quat wxyz)
p["set_joint_targets"](a8, steps=1); p["get_joint_targets"]()     # raw 8-D targets for `steps` control steps; the targets in force
s.start_video("/app/output/try.mp4"); ...; s.stop_video()          # film the steps in between; s.state_sha(): the state's hash
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_robolab.py replay --task fruits_green_limes_on_plate --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Frame: env-local = the robot's root frame (Franka base at the origin, x forward towards the table, z up). Quaternions
  are **WXYZ**. `s.objects()["table"]["bounds"][1][2]` is the table-top height.
- Action (8): panda_joint1..7 absolute joint-position targets (rad, PD-tracked) + gripper command (0 = open, 1 = close; the
  Robotiq action is binary). `s.hold_action()` is the no-op.
- Control runs at 15 Hz (sim dt 1/120 s, decimation 8). Your wall-clock budget is 90 min (5400 s); there is no step
  budget. The episode **ends by itself the moment the success predicate holds**: after that `s.step` raises and the
  primitives become no-ops, so stop recording there.
- `s.ee_pose()` and every primitive use the **fingertip-centre tool frame**: RoboLab's `eef_frame` (the gripper flange,
  `s.eef_frame_pose()`) moved 0.162 m along the approach axis to the ends of the closed fingertips (the pads extend ~5.7 cm
  back from there, so for a low object the frame goes almost down to the table). `p["top_down_quat"](yaw)` is its
  orientation for a vertical approach whose finger-closing direction is rotated by `yaw` (rad, about z) from the reset
  pose; at yaw 0 the fingers close along `p["get_finger_closing_dir"]()` (world y at the reset pose), and
  `p["yaw_for_closing_dir"]([dx, dy])` gives the yaw for any horizontal closing direction. The Robotiq opens to 8.5 cm.
- One `Session` per process (Isaac Sim launches once, ~70 s; the scene ~30 s more). Physics is PhysX on the **CPU**
  (a live run, the first `s.replay()` in a process and a fresh-process replay of the same actions end in the same state;
  later in-process replays can differ in the last digits), rendering on the GPU; ~15 control steps/s. Do not call `s.close()` before writing every output.
