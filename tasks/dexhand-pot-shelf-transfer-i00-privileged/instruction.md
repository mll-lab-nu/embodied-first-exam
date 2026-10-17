# DexHand: Place a two-handle pot into a shelf

A fixed dual-arm robot (two 7-joint arms, a dexterous hand on each wrist) stands at a kitchen worktop. A freely moving 1 kg two-handle stockpot (286 mm vessel diameter, 438 mm across its two loop handles) rests on the worktop; an open kitchen shelf is to the robot's left. Grasp the pot by its two handles, lift it with both hands, carry it into the shelf compartment and set it down upright on the shelf board at the target, then open both hands and withdraw them. The pot must never be dropped, tipped over, knocked against the furniture, the floor or a non-hand robot link, or leave its support while no hand carries it. Only the robot's position-controlled joint targets act on the world: there are no attachments, object actuators, scripted object motion or applied forces.

Save a valid trajectory early and keep
improving it; do not stop early.

## Robot, scene and control
The robot is a fixed Tianji Marvin stand with two 7-joint arms and a dexterous hand on each wrist. Every arm and finger
joint is a position servo inside MuJoCo 3.4.0 (CPU, implicitfast integrator, 2 ms physics step). Arm servos have
stiffness 700 N m/rad, damping 48 N m s/rad, the arms' own torque limits and **no gravity compensation**: a held target
sags under the arm's and the pot's weight unless your targets account for it. Finger servos and every joint range and
force limit are in `s.model`. The pot moves only through contact and gravity.

**Control rate: one action row is one 2 ms physics step (500 Hz).** A row holds a position target for every actuator
(radians), applied for exactly one physics step. Rows outside `s.model.actuator_ctrlrange` are rejected.

World frame: metres, radians, seconds; +z up, +x forward from the robot stand, +y to the robot's left; quaternions are
wxyz. Scene facts (all also readable from the model): the worktop top is at z = 0.75; the pot is upright on it with its
base centre at (0.52, -0.05, 0.75) and its two loop handles along the world y axis (handle loops 0.13 to 0.22 m from the
pot axis, 0.133 to 0.187 m above the base); the open shelf's board top is at z = 0.79 and spans x from -0.14 to 1.14
and y from 0.12 to 0.84; the compartment is closed by side walls (inner faces x = -0.14 and x = 1.14), a back wall
(inner face y = 0.84) and a top board (underside z = 1.465), and opens toward -y. The target for the pot's base
centre is (0.46, 0.31, 0.79).

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); one row is one 2 ms physics step.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

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
The verifier evaluates the predicate after every physics step. Success needs both stages, in order:
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

The episode ends as a success when the hold completes; later rows are not executed. Anything less (pot still held,
placed but not released, released outside the target, hold not completed when the rows end) is a failure.

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
10. Budget: 30000 rows (60 s) pass without success.

Everything else is allowed and only matters through the success conditions. In particular the pot may be set back
down on the worktop (or rest on it with one side while a hand still holds the other), touch the worktop or the shelf
board again, and be regrasped any number of times, provided none of the conditions above occurs; the 0.5 s of
bimanual carry is counted over the whole episode, and the 2 s released hold must be consecutive.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
for `wuji`, 1 <= T <= 30000, plus the `hand` member (`s.save_trajectory(actions, path)` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these rows twice in fresh processes; both replays must succeed with identical final state
hashes. Object poses, success flags, configuration overrides and pickled arrays are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("pot_shelf_transfer")          # hand="wuji" or DEXHAND_HAND=wuji for the other hand
s.actuator_names, s.joint_names    # row order (s.action_dim targets)
s.model, s.data                    # privileged MuJoCo model and state
s.hold_action()                    # current targets
s.step(row)                        # one 2 ms physics step; returns status()
s.status()                         # success, done, reason, steps, stage (0-2), carry and hold seconds
s.features()                       # pot pose/speed/tilt, hand loads and contacts, support, unmet terminal condition
s.observe()                        # joint positions/velocities/targets, wrist poses, pot pose
s.snapshot(); s.restore(snap)      # exact save/restore of physics and predicate state
s.reset()                          # exact frozen reset
s.render_frame("overview")         # RGB uint8 (480, 640, 3); cameras: overview, front, shelf; shadows=True
s.replay(actions)                  # reset, run rows until done, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The tooling is in `/opt/tools`; `task.json` (all thresholds) and `runtime.py` define the scene and the exact predicate.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
