# RoboLab · clutter_plastic — frozen instance

You control a simulated **Franka Panda arm with a Robotiq 2F-85 gripper** (NVIDIA RoboLab's DROID setup on Isaac Lab 2.3 /
Isaac Sim 5.1, PhysX physics) via Python. **Task:** Put all plastic bottles away in the bin.

The scene objects are the env's rigid objects (`s.objects()`: `lemon_01`, `lemon_02`, `lime01`, `lime01_01`, `orange_01`, `orange_02`, `pomegranate01`, `pumpkinlarge`, `pumpkinsmall`, `whitepackerbottle_a01`, `avocado01`, `crabbypenholder`, `milkjug_a01`, `serving_bowl`, `utilityjug_a03`, `right_bin`, `red_onion`, `table`; see
`/opt/robolab/robolab/tasks/benchmark/clutter_plastic_task.py`). RoboLab's success predicate is the `success` termination
term in that file (`object_in_container` in `/opt/robolab/robolab/core/task/conditionals.py`); it also ends the episode:
```python
class ClutterPlasticTerminations:
    time_out = DoneTerm(func=mdp.time_out, time_out=True)
    success = DoneTerm(func=object_in_container, params={"object": [ "whitepackerbottle_a01", "milkjug_a01","utilityjug_a03"], "container": "right_bin", "logical": "all", "require_gripper_detached": True})
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in two fresh processes and scored 1 if RoboLab's success predicate
holds in both replays (the predicate is checked after every control step and the first step where it holds ends the
episode: later rows are never executed) and both end in the same state, else 0. After the last row the replay holds that
row's command for 30 more control steps (2 s) while the predicate is still checked, so a release in the last rows
completes (`s.replay` does the same); a trajectory that ends with an object in the gripper goes on holding it. "The
gripper" in the predicate (`require_gripper_detached`, `gripper_detached`, `in_contact(..., "gripper")`) is both Robotiq
fingers: an object touching either finger is held (RoboLab's DROID setup watched the left inner finger alone; this
task's tooling sets `contact_gripper` to both, with RoboLab's own alias group). Also leave the script that produced it at
`/app/output/gen.py`. Save a working trajectory as soon as you have one and overwrite it as you improve it: whatever is in
`/app/output/` when the time is up is graded. The file holds `task` and `actions`, a (T, 8) float array of at most
**100,000 rows** (one per control step, 1.9 h of robot time); anything else (another shape, NaN, more rows, a file that is
not such an npz) scores 0. Each replay has max(1800 s, 900 s + 1 s per 7.5 rows) of wall clock, about twice what a replay
takes here.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_robolab import Session
s = Session("clutter_plastic", instance="/app/instance.json")   # ~1-2 min: launches Isaac Sim, builds the scene, restores the frozen state
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
`python /opt/tools/rcb_robolab.py replay --task clutter_plastic --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Frame: env-local = the robot's root frame (Franka base at the origin, x forward towards the table, z up). Quaternions
  are **WXYZ**. `s.objects()["table"]["bounds"][1][2]` is the table-top height.
- Action (8): panda_joint1..7 absolute joint-position targets (rad, PD-tracked) + gripper command (0 = open, 1 = close; the
  Robotiq action is binary). `s.hold_action()` is the no-op.
- Control runs at 15 Hz (sim dt 1/120 s, decimation 8). There is no step budget: the time limit (`## Time limit`) is your only
  budget (a runaway guard ends an episode after 100,000 control steps, the most a trajectory may hold). The episode
  **ends by itself the moment the success predicate holds**: after that `s.step` raises and the primitives become
  no-ops, so stop recording there.
- `s.ee_pose()` and every primitive use the **fingertip-centre tool frame**: RoboLab's `eef_frame` (the gripper flange,
  `s.eef_frame_pose()`) moved 0.162 m along the approach axis to the ends of the closed fingertips (the pads extend ~5.7 cm
  back from there, so for a low object the frame goes almost down to the table). `p["top_down_quat"](yaw)` is its
  orientation for a vertical approach whose finger-closing direction is rotated by `yaw` (rad, about z) from the reset
  pose; at yaw 0 the fingers close along `p["get_finger_closing_dir"]()` (world y at the reset pose), and
  `p["yaw_for_closing_dir"]([dx, dy])` gives the yaw for any horizontal closing direction. The Robotiq opens to 8.5 cm.
- One `Session` per process (Isaac Sim launches once, ~70 s; the scene ~30 s more). Physics is PhysX on the **CPU**,
  rendering on the GPU; ~15 control steps/s. The first episode of a process (a live run before any `s.reset()`, or the
  first `s.replay()`) ends in the same state as the grader's fresh-process replay of the same actions. After `s.reset()`
  the state is restored but not every PhysX internal: a live run recorded after a reset, and later in-process replays,
  can end differently (in recorded trials a success after a few resets failed the fresh replay), so record the final
  trajectory from the first episode of a fresh process and check it with the CLI replay below, which runs in one. Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **24 GiB of GPU memory**, **24 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
