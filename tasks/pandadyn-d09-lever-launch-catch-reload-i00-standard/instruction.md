# Panda Dynamic Scenes · Lever launch, catch and reload (D09) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** A ball starts in the right arm's cup. The right arm must load it into the small basket of a passive see-saw launcher and move its cup away. The left arm, holding a mallet, must strike the lever so that the ball is flung up into free flight, and the right arm must catch it in its cup. The right arm then loads the ball into the basket a second time and clears away, and the left arm launches it again. In the end the ball must come to rest inside an open box that slides back and forth on a rail, while the box is moving. The left arm's mallet must never touch the ball.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.44, -0.23, 0), yaw 0 (facing +x). Its tool is a mallet: a solid block 50 x 50 x 30 mm (along tool x, y, z), with the tool frame at its centre and axes parallel to the hand's when the hand points straight down (x forward, z up). The mallet is carried on an L-shaped side adapter of 12 mm square bars that runs forward from beside the hand, then sideways, then down onto the mallet's top near its -y edge. The mallet centre is 0.12 m ahead of the gripper TCP along tool x, 0.13 m to its tool +y side and 0.075 m below it. Start: mallet centre at (0.16, -0.11, 0.28), tool axes aligned with the world. panda-1 (right): base at (0.74, 0.23, 0), yaw pi (facing -x). Its tool is an open-top square cup: inside 0.14 x 0.14 m (2 x `tool_half`, 0.07 at this instance), walls 55 mm high and 5 mm thick on all four sides, 5 mm floor. The tool frame is the centre of the inside floor surface, z up, x pointing away from the arm's own base. With the cup level the hand points straight down and the cup's floor centre is 0.12 m ahead of the TCP along tool x and 0.04 m below it. The grey adapter enters at the middle of the cup's back (tool -x) wall: a 12 mm wide post protrudes 6 mm into the cup from the floor up to 35 mm, and a bar protrudes 12 mm into the cup between 29 and 41 mm above the floor. Start: cup floor centre at (0.12, 0.17, 0.26), level, rotated 180 deg about z (tool x = world -x). Wrist joints 5-7 of both arms use higher damping gains (24, 20, 14 instead of the default 12, 10, 7). Role labels per phase (left, right): physical_loading: cleared_striker, loader; first_launch: striker, preparing_catcher; right_catch: cleared_striker, catcher; reload_and_clear: cleared_striker, reloader; second_launch: striker, cleared_loader; moving_receptacle_retention: cleared_striker, cleared_loader.

A small orange ball (radius 18 mm) starts at rest on the floor of the right arm's cup. A passive see-saw launcher stands in the middle of the table on an orange square post (the same orange as the ball). The launcher is blue: a lever on a horizontal hinge parallel to world y. At the lever's end on the left arm's side (-x) sits a small square basket (54 mm inside, 12 mm walls). On the other side of the hinge a side arm reaches toward -y to a strike pad (36 x 50 mm), which is held a few centimetres above the lever on a spring and can be pushed down by up to 30 mm. Pushing or striking the pad side down rotates the lever and swings the basket end upward along an arc around the hinge; stops limit the lever's travel. At rest the lever lies horizontal on its lower stop, because the basket side is heavier and a weak return spring also pulls it back to that position. Beyond the launcher, on the right arm's side, a blue open box (0.15 x 0.15 m inside, 0.06 m deep) rides a straight rail along y. The box is driven back and forth along the rail in a smooth sinusoidal oscillation by itself for the whole episode: slowly, and slowest where it turns around. The table top is the world's z = 0 plane.

**Goal geometry.** Clearance point (0, 0, 0.18): in physical_loading and reload_and_clear the right cup's tool frame must finally be more than 0.16 m from it. Launch height: in first_launch and second_launch the ball centre must be above z = 0.20 m.

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. At t = 0 only the box on the rail is moving, and it keeps oscillating along the rail for the whole episode, so where it is at the second launch depends on how long the earlier phases took. The ball is visible in the right cup from the start. The launcher's post has the same orange colour as the ball.

## Success
The task has 6 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **physical_loading**: the ball rests in the launcher's basket for 0.1 s without interruption. During that time the ball touches the lever (the lever link, basket included) and does not touch the right cup, and the lever is near horizontal (|q| < 0.12 rad). In the lever's frame (origin on the hinge axis, x along the beam toward the pad side, z normal to the beam), the ball centre is within 0.021 m horizontally of the basket centre (x, y) = (-0.12, 0) and between 0.024 m and 0.044 m above the hinge plane (the basket floor is at 0.012 m, so a resting ball sits at 0.030 m). The ball also moves at less than 0.08 m/s relative to the lever's centre-of-mass velocity. This is recorded once. After that, the right cup's tool frame must be more than 0.16 m away from the clearance point (0, 0, 0.18) (the ball need not still be in the basket at that moment).
2. **first_launch**: the left mallet (any part of panda-0's tool link) touches the lever or its pad; the first such contact in this phase is recorded. After that, the ball has touched nothing for more than 0.04 s while its centre is higher than z = 0.20 m.
3. **right_catch**: the ball drops into the right cup from free flight and stays there. Measured in the cup's tool frame, its centre crosses downward through the plane 0.073 m above the cup floor (wall height 0.055 m + radius), within 0.052 m (half width - radius) of the cup centre along both x and y, after the ball has touched nothing for at least 0.025 s. After that crossing the ball must stay retained in the cup for 0.18 s without interruption. Retained means: its centre is at least 0.45 x radius inside the inner walls (|x|, |y| < 0.0619 m in the tool frame) and between 0.014 m and 0.0528 m above the cup floor; it has touched the cup within the last 25 ms; and it moves at less than 0.09 m/s relative to the cup (the cup's rigid-body velocity at the ball's position).
4. **reload_and_clear**: the same as physical_loading, counted again only within this phase. The ball rests in the basket for 0.1 s without interruption: it touches the lever and not the right cup, |q| < 0.12 rad, its centre is within 0.021 m of the basket centre and 0.024-0.044 m above the hinge plane in the lever frame, and its speed relative to the lever is < 0.08 m/s. After that, the right cup's tool frame must be more than 0.16 m from (0, 0, 0.18).
5. **second_launch**: the same as first_launch, counted again only within this phase: the left mallet touches the lever or its pad, and after that the ball has touched nothing for more than 0.04 s while its centre is higher than z = 0.20 m.
6. **moving_receptacle_retention**: the ball is inside the moving box, and the box moves along its rail faster than 0.02 m/s, for 0.7 s without interruption. Inside means: in the box's frame the ball centre is at least 0.45 x radius inside the inner walls (|x|, |y| < 0.0669 m from the box centre) and between 0.014 m and 0.0578 m above the box floor; the ball has touched the box within the last 25 ms; and it moves at less than 0.09 m/s relative to the box. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time, the ball touches the left arm's mallet tool (any part of its tool link, adapter included) (`direct_ball_hit`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The right cup (whole tool link) may touch the ball, the lever and the strike pad. The left mallet (whole tool link) may touch the lever and the pad, and by this task's rule never the ball (direct_ball_hit). Neither tool may touch the lever's base block, the orange pedestal, the moving box or its rail and base, or the table. No other robot part, the fingers included, may touch anything. The two arms and their tools may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
(`arm_arm_or_tool_collision`), an arm never touches itself (`self_collision`), no robot part touches the table or the floor
(`forbidden_collision`, `tool_table_collision`), a robot link other than an allowed one touches no object or fixture
(`forbidden_arm_object_contact`, `forbidden_arm_scene_contact`, `forbidden_arm_fixture_contact`), a tool touches only the
task's objects and the fixtures the task allows (`forbidden_tool_fixture_contact`), and no contact penetrates deeper than
4 mm (`excessive_penetration`).

**Safety limits** (the Franka Panda's own limits, checked every 1 ms on each arm; `spec["robot_spec"]["controller"]["safety_limits"]`):
measured joint positions within the joint limits (+0.002 rad); measured joint speeds at most 1.01 x (2.175, 2.175, 2.175,
2.175, 2.61, 2.61, 2.61) rad/s; finger speeds at most 0.051 m/s; the hand's TCP at most 1.01 x 1.7 m/s and 1.01 x
2.5 rad/s; joint accelerations (measured over every 20 ms window) at most 1.05 x (15, 7.5, 10, 12.5, 15, 20, 20) rad/s²
and jerks at most 1.05 x (7500, 3750, 5000, 6250, 7500, 10000, 10000) rad/s³; the TCP's acceleration (20 ms windows) at
most 1.05 x 13 m/s² and 1.05 x 25 rad/s²; motor torques at most (87, 87, 87, 87, 12, 12, 12) N m, changing at most
1000 N m/s. The servo's own reference motion is checked against the same speed, acceleration and jerk limits. A contact
(a catch, a strike) moves the arm too: what is measured counts, whatever was commanded.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, on a failure, when your time is up, or
  on a simulator error. A dropped object stays dropped.
- **No privileged state.** You see what the cameras see (RGB, and depth if you ask) plus the robot's own proprioception
  (joints, fingers, hand TCP and tool poses, velocities, motor torques, the current targets). No object poses, no success
  signal before the end.
- There is no step budget: the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]`). Actions and simulated
  time are reported as cost.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record. The episode is graded as it stands when your time is up.
- **If the service crashes**, a call fails with a connection error: the simulator restarts and resumes the SAME episode
  (never a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits
  until it answers again, then check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (the service builds the scene in a few seconds)
spec = r.spec()                               # action type, layout, joint limits, cameras, budget, robot spec, servo and safety limits

obs = r.get_obs()                             # current frames: obs.last["overview"], obs.last["closeup"] -> uint8 (480, 640, 3); no time passes
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, fingers, TCP / tool poses, velocities, torques, targets
obs.meta["cameras"]                           # per camera: intrinsic_cv / extrinsic_cv / cam2world_gl (static cameras)
obs = r.get_obs(seconds=0.2, video="frames", video_fps=50)   # hold the current targets and watch 0.2 s (at most 10 s): obs.frames[cam]

res = r.submit("joint_position", A, dt=0.01)  # A: (T, 16) rows dt seconds apart, executed at 100 Hz (hold or linear between rows)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"], res.meta["sim_time_s"]
res.frames["overview"]                        # uint8 (N, H, W, 3) at video_fps, if video="frames" | "both"; res.video[cam]: mp4 bytes
res.last["closeup"]; res.proprio              # last frame per camera; float32 (N, D) proprio at each frame; res.frame_time_s
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
r.fk(q); r.ik({"panda-0_tool": pose7}, seed=q) # stateless kinematics of the arms' own models (no physics, no simulated time)
```
Cameras (640×480 RGB, static): `overview` (the whole workspace) and `closeup` (the task's working area); z-depth on
request (`r.get_obs(depth=True)` -> `obs.last_depth[cam]` metres; `r.submit(..., depth="frames")`). `video_fps` (1..50,
default 10) sets how many frames a call returns; a call may return at most `spec["max_frames_per_call"]` images.

### Action type
- `joint_position` (16 per row): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each arm's 8 values are its 7 absolute joint-position targets
  (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at most
  0.025 m/s). Rows are `dt` apart (`0.01 ≤ dt ≤ 0.5` s, a multiple of the 0.01 s control period; any other `dt` is
  rejected, never rounded); `interpolate="linear"` (default) or `"hold"`; a chunk may cover at most 10 s; out-of-limit
  values are clipped and listed in `meta["clipped"]` (limits in the spec). The service executes the rows as float64;
  `r.submit` sends them as float32 (a float64 `actions` array part is taken as it is). `observe` with
  `seconds > 0` keeps the last targets in force.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and 5 % (jerk) of the Panda's joint
  speed, acceleration and jerk limits, and the arm tracks that reference with torque control (PD + inverse dynamics, the
  Panda's torque and torque-rate limits). A new target replans from the current reference motion, so a target far away is
  reached smoothly, not in one step. `spec["robot_spec"]["controller"]` has the exact limits and gains.
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing.

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- `spec["proprio_groups"]` names the proprio columns: `joint_pos` (per arm joint1..7, finger_left, finger_right), `tcp_pose`
  (the hand TCP, between the fingertips), `joint_vel`, `gripper_opening`, `joint_effort` (motor torques), `tool_pose` (the
  task tool's frame), `target` (the targets in force). The arms are listed panda-0 first.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
