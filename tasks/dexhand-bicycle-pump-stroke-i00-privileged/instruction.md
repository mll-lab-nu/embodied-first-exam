# DexHand: Inflate a tire with a portable bicycle pump

Inflate the bicycle tire with the portable bicycle pump, using the right hand of the Tianji Marvin robot that stands at the bench (stand at the world origin, facing +x; the left arm stays parked). A mini floor pump (Topeak Mini Morph type, 154 g class, barrel 0.25 m tall) stands free on its folding foot on the bench next to a 406 (20 inch) wheel lying on the bench; as in the source scene, the pump's hose head starts disconnected from the wheel's Schrader valve and the tire is at 200.0 kPa gauge. The head (TRK-RP04 type) sits on the valve stem's axis 17.5 mm out from its seat (an 8 mm gap to the stem tip) with its thumb lock open (lever pointing up). The head moves only along the stem axis: a passive slide guided by the hose, with 2 N of friction and an end stop at the seat; pushing it 17.5 mm toward the rim seats it on the stem. The thumb lock is a passive hinge on the head (axis along world y, at the lever's foot, 0.004 N m friction) that turns 1.65 rad from up (open) to lying flat toward the wheel hub (closed). The pump's T handle rests at the top of its 0.20 m travel: the piston is a passive slide whose compressed-air spring pushes the handle back up (about 6 N at the top and 46 N at the bottom of the stroke) with viscous damping and 1 N seal friction. A stroke counts only while the head is connected (see stage 1), when the handle is pushed down to a piston depth of at least 0.18 m (90 % of the travel) and then returns to a depth of at most 0.04 m (20 %); shallower strokes never count and are not failures. The tire pressure is a checker quantity, not simulated air: every counted stroke adds 380 Pa (the mean rise per stroke of the source gas model, which reaches 210.6 kPa after its 28 strokes). Success requires, in this order: (1) the head connected: seated within 0.5 mm of its 17.5 mm travel while the thumb lock is closed to within 0.15 rad of its 1.65 rad stop (this latches; a stroke is armed and counted only while the head is seated and locked like this at that very moment); (2) at least 28 counted strokes; (3) tire pressure at least 210.6 kPa gauge; (4) the head disconnected again, as at the end of the source: the thumb lock opened to at most 0.5 rad and the head pulled at least 12.5 mm back off its seat (off the 9.5 mm stem engagement; this latches; the pressure stays, since only counted strokes change it); (5) the handle released at the top: piston depth at most 0.01 m, no contact of any robot part (hands, arms, stand) with any part of the pump or the head, pump tilt at most 0.0873 rad (5 degrees) from upright, pump centre-of-mass speed at most 0.02 m/s and handle speed at most 0.02 m/s, held continuously for 50 consecutive controls (1 s). The episode ends with success at that moment. The episode ends immediately with failure, checked after every 2 ms physics substep, when the pump tilts more than 0.2618 rad (15 degrees) from upright, when its base moves more than 0.03 m horizontally from its start or rises more than 0.02 m above it, when its centre of mass falls below the bench top (z < 0.70 m) or any pump part touches the floor, when the head, once connected and before stage 3 is reached, is pulled back more than 2 mm from its seat or its thumb lock is opened below 1.2 rad (head_disconnected), when the head is pulled back more than 2 mm from its seat while its thumb lock is still closed (at least 1.2 rad) after stage 3 (head_forced_off: open the lock first), or when the physics becomes unstable; later actions cannot undo a failure. The episode allows at most 5000 controls at 50 Hz; reaching that limit without success is a failure. Only robot actuator targets are allowed (the Marvin arm joints and the hands' finger joints); no object teleports, grasp welds, scripted object motion or direct object forces. The wheel, valve and hose are static props (the hose end at the head moves with the head, for display only); the head and its thumb lock move only through contact.

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist, standing at the bench with its base centre at the world origin, facing +x (shoulders at z = 1.121 m,
1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right arm and hand
alone. Every arm and finger joint is a position servo inside the physics engine under native force bounds; arm servos
have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held target sags under the arm's
weight and the handle's push unless your targets account for it). Pushing the pump handle requires physical contact.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and only the right arm/hand perform the task.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control and holds a position target for every actuator, in radians:

- `sharpa` (58 values): 0-6 the left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4,
  WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`; keep them at the parked start
  values), 7-13 the same right-arm joints (`..._R_J1` to `..._R_J7`), 14-35 the 22 left Sharpa Wave finger targets
  `left_thumb_CMC_FE` ... `left_pinky_DIP`, 36-57 the 22 right Sharpa Wave finger targets `right_thumb_CMC_FE` ...
  `right_pinky_DIP`.
- `wuji` (54 values): 0-13 the same arm targets, 14-33 the 20 left Wuji Hand 2.2 finger targets `l_wuji_l_THJ0..3`,
  `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, 34-53 the 20 right ones
  (`r_wuji_r_...`, same order).

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start targets of each hand are in `task.json`
(`initial_targets`): the right hand starts open, palm down, above and to the right of the pump. The right hand's frame
is the body `wrist_stage` on the right flange (fingers along its +z, palm normal +x, thumb +y), which forward
kinematics of the arm joints places in the world.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
for `wuji`, at most 5000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("bicycle_pump_stroke")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("bicycle_pump_stroke", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names           # selected hand, row width and exact row order
s.hold_action()                                  # current motor targets
s.model.actuator_ctrlrange                       # native target limits
s.model, s.data                                  # privileged MuJoCo model and state
s.features()                                     # strokes, piston depth, pressure, pump pose/speed, contacts, failure
s.status()                                       # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                      # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                       # RGB uint8 (480, 640, 3); also "closeup", "wide", "front"
s.reset()                                        # exact frozen reset
s.replay(actions)                                # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
`s.features()` and `s.status()` report `head_connected`, `head_disconnected`, `head_slide_m`, `lever_angle_rad`,
`hand_head_contacts`, `strokes`, `piston_depth_m`, `tire_gauge_pa`, `stage` (completed stages:
1 = head connected, 2 = 28 strokes, 3 = pressure target, 4 = head disconnected, 5 = released hold), `released_hold_steps`, `pump_tilt_rad`,
`pump_displacement_m`, `pump_lift_m`, `pump_speed_m_s`, `handle_speed_m_s`, `hand_pump_contacts` and, after a failure,
`failure` / `failure_detail`. Read `/opt/tools/task.json`, `scene.py`, `arm_rig.py`, `checker.py` and `runtime.py` for the
complete geometry, the robot, failure checks and predicate. The world frame has z up; lengths are in metres and angles in radians. The bench top is at z = 0.70 m; the
pump body is `pump` (free joint `pump_free`), its piston slide `piston_extension` (0.20 m = handle up, at rest) and the
T handle geom `t_handle`. The hose head is the body `pump_head` on the slide `head_slide` (0 at reset, -0.0175 m =
seated; axis (0.981, 0, 0.196), pointing from the rim toward the hub) with the thumb lock `thumb_lock` on the hinge
`lever_angle` (0 = up/open at reset, 1.65 rad = closed); at reset the lever's foot is near world (0.547, -0.129, 0.747).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
