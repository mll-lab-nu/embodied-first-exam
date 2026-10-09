# YAMLab · PutPotOnCooktop-v0 — frozen instance i14

You control two simulated **I2RT YAM arms with parallel two-finger grippers** on a workstation table (YAMLab's bimanual
setup on Isaac Lab / Isaac Sim 5.1, PhysX physics) via Python. **Task:** Lift the pot with **both** arms (both grippers holding it), put it down on the cooktop, upright, and let go with both grippers.

The scene's two task objects are `pot` (YAMLab asset `Pot/pot_014`, 35.4 × 22.6 × 10.6 cm) and `cooktop` (YAMLab asset `Cooktop/cooktop_014`, 25.3 × 33.1 × 4.8 cm): `s.objects()` gives their poses, sizes (in their own frames: x × y × z, the root at the box centre) and bounding boxes, `p["get_object_points"](name)` their mesh points.

This is a *fixed scene instance*: the objects' poses and the robot's start pose never change between resets. You may
reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success (YAMLab's own check, with its evaluation thresholds)
1. **pick**: the pot's centre is more than 5 cm above its resting height (z > 0.8595 m) while **both** grippers grasp it (YAMLab's grasp detection: both fingers of that gripper touch the pot with at least 0.1 N, on their pads), for 8 consecutive control steps;
2. **place**: the pot rests on the cooktop: its centre within 0.210 m (horizontally) of the cooktop's centre, its centre's height within 2 cm of the cooktop's centre + half the cooktop's height (2.4 cm) + half the pot's height (5.3 cm), upright (its z axis within 0.2 rad of vertical), and **neither** gripper grasping it, for 30 consecutive control steps.

The stages are checked after every control step, in order (a stage is only checked once the previous one has latched),
and a latched stage stays latched. The episode **ends by itself** at the first control step where every stage has latched
(success; rows after it are never executed), or when a task object falls more than 1 cm below the table top (failure).
`s.status()` reports the stages; `s.success_params()` has the numbers above.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if the task succeeds in both replays and both
end in the same state, else 0. Also leave the script that produced it at `/app/output/gen.py`. Save a working trajectory
as soon as you have one and overwrite it as you improve it: whatever is in `/app/output/` when the time is up is graded.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_yamlab import Session
s = Session("put_pot_on_cooktop", instance="/app/instance.json")   # ~2-3 min (the first start ~10 min): launches Isaac Sim, builds the scene, restores the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact state restore)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # name -> position, orientation_wxyz, size (own frame), bounds (AABB), velocity
p["move_ee"](left=(pos, quat_wxyz), right=(pos, None), speed=0.15)   # tool frames along straight lines, both arms together (differential IK)
p["move_joints"](left=q6, right=q6); p["set_gripper"]("left", 1.0); p["open_gripper"]("right"); p["hold"](10)
s.ee_pose("left"); s.joint_positions("right"); s.ik_step("left", pos, quat_wxyz)   # kinematics helpers
s.render_frame("top")              # RGB uint8 (480, 640, 3) of "top" (static, above the table), "left_wrist" or "right_wrist"; s.render_grid()
s.step(action)                     # one low-level action (14 values) = one control step (1/30 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 14) actions, one row per control step
s.status()                         # {'success', 'stages', 'progress', 'sim_steps', 'resets', 'state_sha', 'terminated', 'end_reason'}
s.replay(actions)                  # resets, replays open-loop, returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state, writes a video (top + both wrist cameras)
s.render_depth("top")              # with Session(..., depth=True): float32 (H, W) z-depth in metres (0 = no reading), pixel-aligned with render_frame
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world->camera, OpenCV axes), cam2world_gl, mount, moves
s.robot_spec(); s.proprio()        # joints + limits, grippers, gains, tool frames; measured joints, tool poses, gripper openings, efforts
s.kinematics({"op": "fk", "q": q12}); s.kinematics({"op": "ik", "targets": {"left_tcp": pose7}, "seed": q12})   # stateless FK / IK
p["get_object_points"](name); s.body_pose("left", "link_6"); s.gripper_opening("right"); s.fallen()
s.start_video("/app/output/try.mp4"); ...; s.stop_video()   # film the steps in between; s.state_sha(): the state's hash
```
The primitives are deliberately thin (IK moves, joint moves, grippers, hold): grasping, lifting, handing over and placing
are yours to build from them. YAMLab's source is in `/opt/yamlab` (read-only reference: the task and its checks are in
`yamlab/envs/tasks/`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_yamlab.py replay --task put_pot_on_cooktop --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, x forward (from the arm bases towards the far side of the table), y to the left, z up;
  quaternions are **WXYZ**. The left arm's base is at (0.2525, 0.305, 0.76), the right arm's at (0.2525, -0.305, 0.76),
  both facing +x; the table top is at z = 0.7517.
- Action (14): `[left joint1..6, left gripper, right joint1..6, right gripper]`, YAMLab's own action. Joints: absolute
  position targets (rad) tracked by PD drives. Gripper: the position target of that arm's `left_finger` joint in metres,
  **-0.0475 = fully open .. 0.0 = closed** (YAMLab mirrors it onto `right_finger`); a closing gripper stops at whatever is
  between its fingers. `s.hold_action()` is the no-op.
- Tool frame `left_tcp` / `right_tcp` (`s.ee_pose(arm)`, `move_ee`, `ik_step`): the midpoint of the gripper's two
  fingertips, 0.1426 m from `link_6` along `link_6`'s +z axis (the approach direction), with `link_6`'s orientation. At the
  home pose (all joints 0, grippers open) both tool frames point forward (+x) at z = 0.924.
- Control runs at 30 Hz (sim dt 1/120 s, decimation 4). Your wall-clock budget is 90 min (5400 s); there is no step budget.
- One `Session` per process (Isaac Sim launches once, then the scene builds: ~1.5-3 min; the very first start in this
  container also compiles Isaac's shaders, ~10 min on a busy host). Physics is PhysX on the
  **CPU**; rendering (on the GPU) happens only when a frame is asked for and never moves anything. Stepping runs at about
  60-120 control steps/s. Do not call `s.close()` before writing every output.
