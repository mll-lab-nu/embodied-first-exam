# BEHAVIOR-1K · cook_a_brisket — frozen instance

You control a simulated **R1Pro** mobile manipulator (BEHAVIOR-1K v3.9.2: OmniGibson on Isaac Sim, the 2026 BEHAVIOR
Challenge stack) via Python. **Task:** Cook the brisket. It is raw, inside the kitchen refrigerator; a chopping board and a frying pan are on the countertop and there is an oven in the kitchen. Cook the brisket and put it on the chopping board; the frying pan must end up on the countertop.

**Success**, all at the same time, held for 1 s with no goal object in a gripper and every goal object at rest (`## Conventions`):
- the brisket (`brisket.n.01_1`) is cooked
- the brisket is on top of the chopping board (`chopping_board.n.01_1`)
- the frying pan (`frying_pan.n.01_1`) is on top of the countertop (`countertop.n.01_1`)

The scene is `house_double_floor_lower`; the task objects are BDDL objects (`s.objects()`: `chopping_board.n.01_1`, `brisket.n.01_1`, `frying_pan.n.01_1`, `countertop.n.01_1`, `electric_refrigerator.n.01_1`, `oven.n.01_1`; see
`/behavior-src/bddl3/bddl/activity_definitions/cook_a_brisket/problem0.bddl`). The success predicate is the task's BDDL
goal in that file, evaluated by OmniGibson's object states; it counts once it has held for 1 s, released and at rest (`## Conventions`):
```lisp
(:goal
    (and
        (cooked ?brisket.n.01_1)
        (ontop ?brisket.n.01_1 ?chopping_board.n.01_1)
        (ontop ?frying_pan.n.01_1 ?countertop.n.01_1)
    )
)
```
What the goal's predicates mean (OmniGibson's object states):
- `ontop(A, B)`: A touches B and B is directly below A (and not above it).
- `cooked(A)`: the highest temperature A has ever reached is at least its cooking temperature (70 °C by default). Heat comes from a heat source that is on (a stove burner, an oven: 200 °C) within 0.2 m of A; once cooked, A stays cooked.

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed (the success rule under `## Conventions`) by the end of the replay, which holds the robot still for up to
5 s after your last row, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_behavior import Session
s = Session("cook_a_brisket", instance="/app/instance.json")   # ~3 min: launches Isaac Sim and loads the scene
s.reset()                          # back to the frozen initial state (unlimited; approximate in-process, exact in a fresh process)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # task objects: BDDL name -> category, world position, orientation (xyzw)
p["move_base"](x, y, yaw)          # drive the base straight to a world pose (closed loop; no obstacle avoidance, no planning)
p["move_ee"]("left", pos, quat_xyzw)   # cuRobo IK (trunk + arm, no collision checking), then joint interpolation
p["move_joints"]({"trunk": q4, "left": q7}); p["close_gripper"]("left"); p["open_gripper"]("left"); p["hold"](10)
p["object_in_hand"]("left")        # what assisted grasping attached to that gripper; s.ik({"left": (pos, quat_xyzw)})
s.render_frame("robot_r1:zed_link:Camera:0")   # RGB of a robot camera (s.VIDEO_CAMERAS), 224x224; Session(..., cameras="tiny"): 16x16, cheaper rendering
s.render_depth("robot_r1:zed_link:Camera:0")   # z-depth (H, W) float32 in metres (0 = no reading), pixel-aligned with render_frame
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, image_size, mount
s.robot_spec(); s.robot_state()    # joints with real limits, gripper rule, drive gains, TCP, base limits; measured q/qd/effort, eef/TCP poses
s.kinematics({"op": "fk", "q": q}) # stateless FK / IK ({"op": "ik", "targets": {"left_tcp": pose}, "seed": q}), base frame; s.kinematics_spec()
p["get_robot_pose"](); p["get_eef_pose"]("left"); p["get_object_pose"](name)   # world (position, quaternion xyzw); p["top_down_quat"](yaw)
s.render_grid(); s.start_video(path); s.stop_video(); s.state_sha(); s.episode_done  # camera tiles, mp4 of what follows, state hash
s.robot, s.env, s.get_object(name) # OmniGibson robot / environment / objects (with their object states) for closed-loop control
s.step(action)                     # one low-level action (25 floats, below) = one control step; s.hold_action() holds the targets
s.record_start(); ...; actions = s.record_stop()   # (T, 25) actions, one row per control step (30 Hz)
s.status()                         # {'success', 'goal', 'goal_objects_held', 'goal_objects_moving', 'fallen', 'breakdown', 'q_score', 'sim_steps', 'state_sha', ...}
s.settle()                         # hold still up to 5 s (150 control steps), as the grader does after your last row
s.replay(actions)                  # resets, replays open-loop + settle(), returns status (the first replay in a process is exact)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # tiled robot cameras while replaying (with cameras="tiny": 16x16 tiles, upscaled)
```
The primitives are deliberately thin (joint, base, IK and gripper moves): navigation, grasping, placing and every
other skill are yours to build from them. OmniGibson itself is installed (`/behavior-src/OmniGibson`) with its own
libraries; `/behavior-src` and the tooling in `/opt/tools` are mounted read-only (the grader uses its own copies).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check; a third
replay with the challenge cameras only renders the video and never affects the score):
`python /opt/tools/rcb_behavior.py replay --task cook_a_brisket --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Coordinates are in the world frame; quaternions are **XYZW** (OmniGibson convention); yaw in radians.
- Action layout (25): base (3), trunk (4), left arm (7), left gripper (2), right arm (7), right gripper (2); indices per
  controller: `s.robot.controller_action_idx`. Trunk, arm and gripper entries are absolute joint targets (a gripper is 2
  finger targets, 0 = closed; assisted grasping holds what a closing gripper touches). The base entries are x, y, yaw
  position targets in the robot's own frame, re-applied every control step: a per-step displacement, 0 = stand still.
  `s.hold_action()` (the last command with the base at 0) is the no-op.
- Control runs at 30 Hz with 120 Hz physics. There is no step budget: the time limit (`## Time limit`) is your only budget. Only a
  runaway guard bounds an episode: it ends after 200,000 control steps (1.85 h of simulated time). **The trajectory
  you deliver has at most 40,000 rows** (22 min of simulated time; a longer one is rejected: `bad_trajectory`, score 0).
  The trajectory must be the file
  `s.save_trajectory()` writes (an `.npz` with `actions` (T, 25) and `task`): a file the grader cannot read, or with
  the wrong shape, is `bad_trajectory` too. The grader replays it twice at the simulator's own speed, each replay
  within min(28000 s, max(1 h, 20 min + 0.67 s per row)); a replay that runs out of time is reported as a grader error.
  **Success** (`s.status()["success"]`) is the goal holding for 1 s of simulated time in a row (30 control steps) with no
  goal object attached to a gripper (assisted grasping lets go only when both fingers are commanded open) and every goal
  object at rest (slower than 0.05 m/s); the episode ends there. The goal's literals being true for one frame, or with the
  object still in the hand, is not success: `s.status()["goal"]` is the bare goal, `goal_objects_held` /
  `goal_objects_moving` say what is missing (`s.goal_objects`: every object the goal names, a tool or appliance it
  names, even inside a `not`, included). After your last row the grader holds the robot still (your last command, the
  base at 0) for up to 5 s (`s.settle()`; `s.replay()` and the replay CLI do it too), so you need not record that wait.
  A simulator breakdown (a non-finite or runaway robot or goal-object state, e.g. after the robot tumbles) ends the
  episode as a failure (`s.status()["breakdown"]`). The episode also ends, as a failure, when the robot has fallen over: its base
  tilted more than 41.4° from upright (the z of its up axis below 0.75), or more than 3 cm below the floor, for 10 s of
  simulated time in a row (OmniGibson's own Falling rule; `s.status()["fallen"]`, `s.episode_done`). `s.reset()` starts
  again; the grader's replays end at the same step. While the robot moves, the cameras' frames lag the physics by 2
  control steps; `s.camera_info()` gives the pose they were rendered with.
- Primitives that take an `arm` ("left" / "right") default to the left one.
- Isaac Sim startup and scene loading take ~3 minutes per process and the simulator runs at ~7-11 steps/s: plan
  experiments accordingly. Do not call `s.close()` until you have written every output (it terminates the process).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **24 GiB of GPU memory**, **24 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
