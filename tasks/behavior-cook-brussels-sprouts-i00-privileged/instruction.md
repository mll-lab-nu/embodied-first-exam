# BEHAVIOR-1K · cook_brussels_sprouts — frozen instance

You control a simulated **R1Pro** mobile manipulator (BEHAVIOR-1K v3.9.2: OmniGibson on Isaac Sim, the 2026 BEHAVIOR
Challenge stack) via Python. **Task:** Roast the halved brussels sprouts. Four brussels sprouts are in a tupperware inside the kitchen refrigerator; a chopping board with a carving knife on it and a cookie sheet lie on the countertop, and there is an oven in the kitchen. Cut every sprout in half, cook all eight halves in the oven and leave them inside it, and close the oven and the refrigerator.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- all eight half brussels sprouts (`half__brussels_sprouts.n.01_1` to `_8`) exist (every sprout has been cut in half)
- every half is cooked and inside the oven (`oven.n.01_1`)
- the refrigerator (`electric_refrigerator.n.01_1`) and the oven are closed

The scene is `restaurant_diner`; the task objects are BDDL objects (`s.objects()`: `brussels_sprouts.n.01_1`, `brussels_sprouts.n.01_2`, `brussels_sprouts.n.01_3`, `brussels_sprouts.n.01_4`, `half__brussels_sprouts.n.01_1`, `half__brussels_sprouts.n.01_2`, `half__brussels_sprouts.n.01_3`, `half__brussels_sprouts.n.01_4`, `half__brussels_sprouts.n.01_5`, `half__brussels_sprouts.n.01_6`, `half__brussels_sprouts.n.01_7`, `half__brussels_sprouts.n.01_8`, `tupperware.n.01_1`, `carving_knife.n.01_1`, `chopping_board.n.01_1`, `cookie_sheet.n.01_1`, `oven.n.01_1`, `electric_refrigerator.n.01_1`, `countertop.n.01_1`; see
`/behavior-src/bddl3/bddl/activity_definitions/cook_brussels_sprouts/problem0.bddl`). The success predicate is the task's BDDL
goal in that file, evaluated by OmniGibson's object states; the episode ends by itself the moment it holds:
```lisp
(:goal
    (and
        (forall
            (?half__brussels_sprouts.n.01 - half__brussels_sprouts.n.01)
            (and
                (real ?half__brussels_sprouts.n.01)
                (cooked ?half__brussels_sprouts.n.01)
                (inside ?half__brussels_sprouts.n.01 oven.n.01_1)
            )
        )
        (not
            (open ?electric_refrigerator.n.01_1)
        )
        (not
            (open ?oven.n.01_1)
        )
    )
)
```
What the goal's predicates mean (OmniGibson's object states):
- `inside(A, B)`: the centre of A's axis-aligned bounding box lies within B's bounding box and within B's interior (container) volume.
- `open(A)`: at least one of A's openable joints (door, drawer, lid) is more than 5% of the way from closed to fully open; closed (`not open`) means every such joint is within 5% of closed.
- `cooked(A)`: the highest temperature A has ever reached is at least its cooking temperature (70 °C by default). Heat comes from a heat source that is on (a stove burner, an oven: 200 °C) within 0.2 m of A; once cooked, A stays cooked.
- `real(A)`: A exists in the simulation. What the BDDL problem declares `future` (halves, diced pieces, cooked food, a dish) does not exist at the start: the simulator's transition rules create it. A sliceable object touching the blade of an active slicer (a knife, an axe; after a cut the blade rests for 2 s) is replaced by its two halves, so the whole one is no longer real; a diceable half touching the blade turns into diced pieces (particles); and a recipe's ingredients, heated together in their container or vessel on or in an active heat source, turn into the cooked food or the dish.

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_behavior import Session
s = Session("cook_brussels_sprouts", instance="/app/instance.json")   # ~3 min: launches Isaac Sim and loads the scene
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
`python /opt/tools/rcb_behavior.py replay --task cook_brussels_sprouts --instance /app/instance.json --traj /app/output/trajectory.npz`

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
