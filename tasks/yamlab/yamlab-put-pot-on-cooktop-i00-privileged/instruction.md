# YAMLab · PutPotOnCooktop-v0 (privileged)

## Task
Two simulated I2RT YAM arms with parallel two-finger grippers on a workstation table (YAMLab's bimanual setup on Isaac
Lab / Isaac Sim 5.1, PhysX). Lift the pot with **both** arms (both grippers holding it), put it down on the cooktop,
upright, and let go with both grippers. The scene is one fixed instance. You have the full simulator to develop with;
you hand in a trajectory of robot actions.

## Goal
Success: both grippers hold the pot between their finger pads and lift it clear of the table for a moment; then the pot
stands upright on the cooktop, resting on it, released by both grippers, for about a second. The steps count in this
order, each for good once done. An object falling off the table ends the episode as a failure. A replay ends as soon as
the task is done; later rows are not run.

Deliverable: `/app/output/trajectory.npz` with `task` and `actions`, a (T, 14) float array of at most 100,000 rows, one
per control step (1/30 s); write it with `s.save_trajectory()`. Anything else (another shape, NaN, more rows) scores 0.
Leave the script that produced it at `/app/output/gen.py`. It is replayed once from the fixed start and passes if the
task succeeds in that replay. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actions count: changing the simulator's state while you develop changes nothing in the replay.

## Robot Interface
### Session
`/opt/tools/rcb_yamlab.py`, importable as `rcb_yamlab`:
```python
from rcb_yamlab import Session
s = Session("put_pot_on_cooktop", instance="/app/instance.json")   # ~2-3 min (the first start ~10 min): launches Isaac Sim, builds the scene, restores the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact state restore)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # name -> position, orientation_wxyz, size (own frame), bounds (AABB), velocity
p["move_ee"](left=(pos, quat_wxyz), right=(pos, None), speed=0.15)   # tool frames along straight lines, both arms together (differential IK)
p["move_joints"](left=q6, right=q6); p["set_gripper"]("left", 1.0); p["open_gripper"]("right"); p["hold"](10)
s.ee_pose("left"); s.joint_positions("right"); s.ik_step("left", pos, quat_wxyz)   # kinematics helpers
s.render_frame("top")              # RGB uint8 (480, 640, 3) of "top" (static, above the table), "left_wrist" or "right_wrist"
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

The primitives are deliberately thin (IK moves, joint moves, grippers, hold): grasping, lifting, handing over and
placing are yours to build from them. One `Session` per process (Isaac Sim launches once, then the scene builds: ~1.5-3
min; the very first start in this container also compiles Isaac's shaders, ~10 min on a busy host). Physics is PhysX on
the **CPU**; rendering (on the GPU) happens only when a frame is asked for and never moves anything. Stepping runs at
about 60-120 control steps/s. Do not call `s.close()` before writing every output. YAMLab's source is in `/opt/yamlab`
(read-only). The grader replays with this command; run it to self-check (it stops at the first success):
`python /opt/tools/rcb_yamlab.py replay --task put_pot_on_cooktop --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- Action (14): `[left joint1..6, left gripper, right joint1..6, right gripper]`, YAMLab's own action. Joints: absolute
  position targets (rad) tracked by PD drives. Gripper: the position target of that arm's `left_finger` joint in metres,
  **-0.0475 = fully open .. 0.0 = closed** (YAMLab mirrors it onto `right_finger`); a closing gripper stops at whatever
  is between its fingers. `s.hold_action()` is the no-op.
- Tool frame `left_tcp` / `right_tcp` (`s.ee_pose(arm)`, `move_ee`, `ik_step`): the midpoint of the gripper's two
  fingertips, 0.1426 m from `link_6` along `link_6`'s +z axis (the approach direction), with `link_6`'s orientation. At
  the home pose (all joints 0, grippers open) both tool frames point forward (+x) at z = 0.924.
- Control runs at 30 Hz (sim dt 1/120 s, decimation 4).
- World frame: metres, x forward (from the arm bases towards the far side of the table), y to the left, z up;
  quaternions are **WXYZ**. The left arm's base is at (0.2525, 0.305, 0.76), the right arm's at (0.2525, -0.305, 0.76),
  both facing +x; the table top is at z = 0.7517.

## Others
- The two task objects: `pot` (YAMLab asset `Pot/pot_000`, 38.5 × 26.5 × 13.8 cm) and `cooktop` (YAMLab asset
  `Cooktop/cooktop_000`, 29.5 × 34.1 × 6.7 cm): `s.objects()` gives their poses, sizes (in their own frames: x × y × z,
  the root at the box centre) and bounding boxes, `p["get_object_points"](name)` their mesh points.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 29 GiB memory, 4096 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (16 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`, an exact restore of the start).
