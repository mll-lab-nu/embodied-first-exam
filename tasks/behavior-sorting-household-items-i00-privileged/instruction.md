# BEHAVIOR-1K · sorting_household_items — frozen instance

You control a simulated **R1Pro** mobile manipulator (BEHAVIOR-1K v3.9.2: OmniGibson on Isaac Sim, the 2026 BEHAVIOR
Challenge stack) via Python. **Task:** Sort the household items into the bathroom. Two baskets stand on the bedroom floor: one holds two bottles of detergent and a box of sanitary napkins, the other a soap dispenser, a tube of toothpaste and a toothbrush; a cup stands on the bathroom sink. Put both detergent bottles under the bathroom sink, next to each other; the box of sanitary napkins on the bathroom shelf; the soap dispenser on the sink; the toothbrush into the cup, which stays on the sink; and the toothpaste next to the cup.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- both detergent bottles (`bottle__of__detergent.n.01_1`, `_2`) are under the sink (`sink.n.01_1`) and next to each other
- the box of sanitary napkins (`box__of__sanitary_napkin.n.01_1`) is on top of the shelf (`shelf.n.01_1`)
- the soap dispenser (`soap_dispenser.n.01_1`) and the cup (`cup.n.01_1`) are on top of the sink
- the toothbrush (`toothbrush.n.01_1`) is inside the cup and the tube of toothpaste (`tube__of__toothpaste.n.01_1`) is next to the cup

The scene is `house_single_floor`; the task objects are BDDL objects (`s.objects()`: `bottle__of__detergent.n.01_1`, `bottle__of__detergent.n.01_2`, `basket.n.01_1`, `basket.n.01_2`, `box__of__sanitary_napkin.n.01_1`, `soap_dispenser.n.01_1`, `tube__of__toothpaste.n.01_1`, `toothbrush.n.01_1`, `cup.n.01_1`, `shelf.n.01_1`, `sink.n.01_1`; see
`/behavior-src/bddl3/bddl/activity_definitions/sorting_household_items/problem0.bddl`). The success predicate is the task's BDDL
goal in that file, evaluated by OmniGibson's object states; the episode ends by itself the moment it holds:
```lisp
(:goal
    (and
        (forall
            (?bottle__of__detergent.n.01 - bottle__of__detergent.n.01)
            (under ?bottle__of__detergent.n.01 ?sink.n.01_1)
        )
        (nextto ?bottle__of__detergent.n.01_1 ?bottle__of__detergent.n.01_2)
        (ontop ?box__of__sanitary_napkin.n.01_1 ?shelf.n.01_1)
        (ontop ?soap_dispenser.n.01_1 ?sink.n.01_1)
        (ontop cup.n.01_1 sink.n.01_1)
        (nextto ?tube__of__toothpaste.n.01_1 cup.n.01_1)
        (inside ?toothbrush.n.01_1 cup.n.01_1)
    )
)
```
What the goal's predicates mean (OmniGibson's object states):
- `inside(A, B)`: the centre of A's axis-aligned bounding box lies within B's bounding box and within B's interior (container) volume.
- `ontop(A, B)`: A touches B and B is directly below A (and not above it).
- `nextto(A, B)`: the gap between A's and B's axis-aligned bounding boxes is at most one sixth of the mean of their summed box dimensions, and nothing lies between them along a horizontal axis.
- `under(A, B)`: B is directly above A (and not below it).

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_behavior import Session
s = Session("sorting_household_items", instance="/app/instance.json")   # ~3 min: launches Isaac Sim and loads the scene
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
s.status()                         # {'success': bool, 'fallen': bool, 'q_score': float, 'sim_steps': int, 'resets': int, 'state_sha': str}
s.replay(actions)                  # resets, replays open-loop, returns status (the first replay in a process is exact)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # tiled robot cameras while replaying (with cameras="tiny": 16x16 tiles, upscaled)
```
The primitives are deliberately thin (joint, base, IK and gripper moves): navigation, grasping, placing and every
other skill are yours to build from them. OmniGibson itself is installed (`/behavior-src/OmniGibson`) with its own
libraries.

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_behavior.py replay --task sorting_household_items --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Coordinates are in the world frame; quaternions are **XYZW** (OmniGibson convention); yaw in radians.
- Action layout (25): base (3), trunk (4), left arm (7), left gripper (2), right arm (7), right gripper (2); indices per
  controller: `s.robot.controller_action_idx`. Trunk, arm and gripper entries are absolute joint targets (a gripper is 2
  finger targets, 0 = closed; assisted grasping holds what a closing gripper touches). The base entries are x, y, yaw
  position targets in the robot's own frame, re-applied every control step: a per-step displacement, 0 = stand still.
  `s.hold_action()` (the last command with the base at 0) is the no-op.
- Control runs at 30 Hz with 120 Hz physics. Your wall-clock budget is 4 h (14400 s); there is no step budget. The
  episode ends by itself the moment the goal holds. It also ends, as a failure, when the robot has fallen over: its base
  tilted more than 41.4° from upright (the z of its up axis below 0.75), or more than 3 cm below the floor, for 10 s of
  simulated time in a row (OmniGibson's own Falling rule; `s.status()["fallen"]`, `s.episode_done`). `s.reset()` starts
  again; the grader's replays end at the same step. While the robot moves, the cameras' frames lag the physics by 2
  control steps; `s.camera_info()` gives the pose they were rendered with.
- Primitives that take an `arm` ("left" / "right") default to the left one.
- Isaac Sim startup and scene loading take ~3 minutes per process and the simulator runs at ~7-11 steps/s: plan
  experiments accordingly. Do not call `s.close()` until you have written every output (it terminates the process).
