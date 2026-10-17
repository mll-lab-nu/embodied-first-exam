# DexHand: Place a two-handle pot into a shelf

A fixed dual-arm robot (two 7-joint arms, a dexterous hand on each wrist) stands at a kitchen worktop. A freely moving 1 kg two-handle stockpot (286 mm vessel diameter, 438 mm across its two loop handles) rests on the worktop; an open kitchen shelf is to the robot's left. Grasp the pot by its two handles, lift it with both hands, carry it into the shelf compartment and set it down upright on the shelf board at the target, then open both hands and withdraw them. The pot must never be dropped, tipped over, knocked against the furniture, the floor or a non-hand robot link, or leave its support while no hand carries it. Only the robot's position-controlled joint targets act on the world: there are no attachments, object actuators, scripted object motion or applied forces.

The service executes and records every row you submit, and the first failure ends the episode, so check each chunk
before you send it: a reset starts a new episode from the same start, 20 times at most, and only the last episode is
graded (see `## Episodes and resets`). Grading replays the recorded episode; there is no trajectory to hand in. Keep
working until an episode has succeeded.

## Robot, scene and control
The robot is a fixed Tianji Marvin stand with two 7-joint arms and a dexterous hand on each wrist. Every arm and finger
joint is a position servo inside MuJoCo 3.4.0 (CPU, implicitfast integrator, 2 ms physics step). Arm servos have
stiffness 700 N m/rad, damping 48 N m s/rad, the arms' own torque limits and **no gravity compensation**: a held target
sags under the arm's and the pot's weight unless your targets account for it. Every joint's range and effort limit is in
`spec()["robot_spec"]`. The pot moves only through contact and gravity.

**Control rate: one action row is one 2 ms physics step (500 Hz).** A row holds a position target for every actuator
(radians), applied for exactly one physics step. The service clips targets to the published joint limits and
reports clipping.

World frame: metres, radians, seconds; +z up, +x forward from the robot stand, +y to the robot's left; quaternions are
wxyz. Scene facts: the worktop top is at z = 0.75; the pot is upright on it with its base centre at
(0.52, -0.05, 0.75) and its two loop handles along the world y axis (handle loops 0.13 to 0.22 m from the pot axis,
0.133 to 0.187 m above the base); the open shelf's board top is at z = 0.79 and spans x from -0.14 to 1.14 and y from
0.12 to 0.84; the compartment is closed by side walls (inner faces x = -0.14 and x = 1.14), a back wall
(inner face y = 0.84) and a top board (underside z = 1.465), and opens toward -y. The target for the pot's base
centre is (0.46, 0.31, 0.79).

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); one row is one 2 ms physics step.
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`) and the exact order. The episode record names the hand, and grading replays with that hand.

Row layout, `sharpa` (58): 0-6 left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4,
WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`); 7-13 the same right-arm joints
(`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave fingers `l_hand_thumb_CMC_FE, l_hand_thumb_CMC_AA,
l_hand_thumb_MCP_FE, l_hand_thumb_MCP_AA, l_hand_thumb_IP, l_hand_index_MCP_FE, l_hand_index_MCP_AA, l_hand_index_PIP,
l_hand_index_DIP`, the same four for middle and ring, then `l_hand_pinky_CMC, l_hand_pinky_MCP_FE, l_hand_pinky_MCP_AA,
l_hand_pinky_PIP, l_hand_pinky_DIP`; 36-57 the right Sharpa Wave fingers in the same order (`r_hand_...`).
Row layout, `wuji` (54): 0-13 the same arm targets; 14-33 the left Wuji fingers `l_wuji_l_THJ0..THJ3` (thumb),
`l_wuji_l_FFJ0..FFJ3` (index), `l_wuji_l_MFJ0..MFJ3` (middle), `l_wuji_l_RFJ0..RFJ3` (ring), `l_wuji_l_LFJ0..LFJ3`
(little); 34-53 the right Wuji fingers in the same order (`r_wuji_r_...`). Both hands start open at the same arm pose.

## Success
The service evaluates the predicate after every physics step it executes, and grading replays the recorded rows.
Success needs both stages, in order:
1. **Bimanual carry**: for at least 0.5 s in total (250 steps) the pot's base is above z = 0.785 m, neither the worktop
   nor the shelf bears on it, and each hand pushes it upward with at least 0.5 N (sum of the vertical components of
   that hand's contact forces on the pot).
2. **Released on the shelf**, held for 2.0 s (1,000 consecutive steps) after stage 1, every condition at every step:
   - the pot's base centre is within 0.04 m horizontally of (0.46, 0.31) and within 0.012 m of z = 0.79;
   - upright: the angle between the pot's axis and +z is at most 0.10 rad;
   - at rest: linear speed at most 0.03 m/s and angular speed at most 0.15 rad/s;
   - resting on the shelf alone: the shelf board bears on the pot and nothing else touches it;
   - fully inside the compartment: the vessel's circular footprint (radius 0.143 m around the base centre) lies on
     the shelf board, and every part of the pot, handles included, is between the side walls, in front of the back
     wall, below the top board and at most 0.05 m in front of the board's front edge (y >= 0.07). This 50 mm
     open-front allowance exists because the 438 mm handle span lies along y: at the target the front handle
     reaches about 34 mm past the board's front edge (y = 0.12); the side walls, back wall and top board are strict;
   - both hands released and withdrawn: every hand collision surface is at least 0.04 m from the pot.

The episode ends as a success when the hold completes; the service then refuses further actions. Anything less
(pot still held, placed but not released, released outside the target, hold not completed when the episode ends) is a
failure.

## Immediate failure
These are the only early failures. The first one that occurs ends the episode as a failure; later rows cannot recover
it. "Touches" means a contact with a normal force of at least 0.02 N unless stated otherwise.
1. Fell: the pot's base (its bottom centre) is below z = 0.70 m (worktop top 0.75 m, shelf board top 0.79 m).
2. Left the workspace: the pot's base leaves the box x in [-0.10, 1.10] m, y in [-0.50, 0.85] m, z <= 1.45 m.
3. Tipped: the pot's axis is more than 0.5 rad from +z.
4. Dropped: the pot's base moves downward faster than 0.6 m/s (about a 2 cm free fall), or the pot touches nothing
   at all (no hand, worktop or shelf-board contact of any force) for more than 0.06 s (30 consecutive steps).
5. Knocked into something: the pot touches anything other than the two hands, the worktop and the shelf board (the
   floor, the cabinet side walls, back wall, top board or bases, a non-hand robot link).
6. Robot collision: a robot link touches the furniture or the floor, or two robot parts collide (contacts within one
   hand excepted).
7. Hand penetration: a hand penetrates the pot by more than 3 mm.
8. Joint limit: a robot joint exceeds its range by more than 0.005 rad.
9. Unstable physics (MuJoCo reports a bad position, velocity or acceleration).
10. Budget: 30000 physics steps (60 s of simulated time) pass without success.

Everything else is allowed and only matters through the success conditions. In particular the pot may be set back
down on the worktop (or rest on it with one side while a hand still holds the other), touch the worktop or the shelf
board again, and be regrasped any number of times, provided none of the conditions above occurs; the 0.5 s of
bimanual carry is counted over the whole episode, and the 2 s released hold must be consecutive.

## Episodes and resets
You have **20 resets** (`spec["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset
and the one episode is the run). A reset puts the robot and every object back in the same frozen starting state and
starts a new episode, either abandoning the running one or after one has ended; it takes no simulated time and
returns the start's images and proprioception:
```python
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (the 2.2 client has no reset())
res.meta["episode"], res.meta["resets_left"]
```
Once an episode has ended, `submit` raises `EpisodeOver` until you reset. **Only the last episode is graded**: an
episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up
the episode then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
`meta["resets_left"]` count the episodes (`meta["control_steps"]` is the current episode's,
`meta["control_steps_total"]` all of them).

## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own joint
positions, velocities, actuator efforts, both wrist poses and current targets. The service records every executed
step and replays the graded episode in two fresh processes. Leave your
controller at `/app/output/gen.py`; no trajectory hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()                    # spec["hand"], spec["action_types"]["joint_position"]["layout"], cameras, limits
obs = r.get_obs(cameras=["overview", "shelf"], depth=True)
obs.last["overview"]               # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]         # z-depth in metres
obs.meta["proprio"]                # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.002, interpolate="hold", video="none")
r.fk(q)                            # robot-link forward kinematics (both wrists); no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, 58)` for `sharpa` or `(T, 54)` for `wuji`, in `spec["action_types"]["joint_position"]["layout"]` order
(the row layouts above), radians. `dt` must be a multiple of 0.002 s, between 0.002 and 0.5 s; a chunk covers at most
10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target. Cameras are
overview, front (looking into the shelf compartment) and shelf, at 640 x 480. Requests can return RGB frames or mp4,
with depth `none`, `last` or `frames`; each call returns at most 1,000 camera images, counting per-frame depth.
Frames are rendered in software, about 0.6 s per camera image, and a call records `video_fps` frames per simulated
second (1 to 50, default 10) whatever `video` returns: lower it for long chunks.
`get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps; without seconds it only
observes. No IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()`
before continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps
running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
