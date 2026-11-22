# DexHand · Replace the battery of a TV remote (privileged)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a table (DexHand, MuJoCo). Replace the battery of the TV remote that lies on the table: its sliding
battery door is shut and latched over a one-cell compartment holding an old gray AA cell; a new green AA cell lies on
the table and an empty receiving tray stands beside the remote. The scene is one fixed instance.
You have the full simulator to develop with; you hand in a trajectory of motor targets.

## Goal
Success: in this order: the door latch is released by pressing the door's spring-loaded thumb tab down, and the door
slid well open; the gray cell is out of the compartment, resting on the tray floor; the green cell lies seated in the
compartment slot on both cradle ribs, its + end at the gold contact; the door is slid shut and latched, the tab
released; then the hand is off everything and all of it is still for a second, the gray cell still in the tray, the
green cell seated and the door latched. Partial completion never counts. A replay ends as soon as the task is done;
later rows are not run.

The episode ends at once as a failure if a cell, the door, the remote or the tray falls below the table top, leaves the
work area or touches the floor; the remote or the tray slides or tilts; the gray cell touches the table top; the green
cell touches the table top again after it has been lifted; a cell drops (there is no grace period, and catching it later
does not undo it); the parked left arm or the left hand touches the remote, its door, the tray or a cell; or the physics
becomes unstable. Later actions cannot undo a failure.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory`
does): an archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actuator targets count: changing `s.data` or the scene while you develop changes nothing in the replay.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("remote_battery_swap")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("remote_battery_swap", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names           # selected hand, row width and exact row order
s.hold_action()                                  # current motor targets
s.model.actuator_ctrlrange                       # native target limits
s.model, s.data                                  # privileged MuJoCo model and state
s.features()                                     # door travel, tab depth, stage conditions, cell errors, contacts, failure
s.status()                                       # success, done, reason, steps, stage (latched stages), total_stages
s.step(row)                                      # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                       # RGB uint8 (480, 640, 3); also "closeup" and "top"
s.snapshot(), s.restore(snap)                    # save / restore the full simulator and task state
s.reset()                                        # exact frozen reset
s.replay(actions)                                # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
`s.features()["conditions"]` reports the four stage conditions, `s.status()["stage"]` the number of stages completed in
order and `hold_steps` the released-hold count. You may read the full simulator state and use `s.snapshot()` /
`s.restore()` while authoring; only the rows you hand in are graded.

### Actions
Each row is one 50 Hz control holding a position target for every actuator (radians), in native actuator order:

- `sharpa` (58 values): 0-6 left arm
  `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
  (actuators `<joint>_target`); 7-13 the same right-arm joints (`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave
  fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`; 36-57 the right Sharpa Wave fingers `right_thumb_CMC_FE` ...
  `right_pinky_DIP`.
- `wuji` (54 values): 0-13 the same arm targets; 14-33 the left Wuji Hand 2.2 fingers `l_wuji_l_THJ0..3`,
  `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`; 34-53 the right Wuji fingers in the
  same order (`r_wuji_r_...`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same arm pose (right hand above the
table near the robot, left arm parked); the frozen start targets of each hand are in `task.json` (`initial_targets`).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Scene
World frame: z up, metres and radians; the table top is at z = 0.30 m (the floor is at z = -0.55 m). The remote lies
flat at (0.0, 0.0, 0.32) with its long axis along world x; it is a free rigid body of 0.35 kg (a weighted handset) on
four rubber feet (shell 160 x 64 mm, battery cavity 94 x 52 mm). Its battery door slides along the remote's -x direction
on a passive slide joint (travel 0 to 0.085 m, end stops at both ends, damping 0.1 N s/m, 0.08 N friction loss) and is
latched shut: a spring-loaded thumb tab on the door (18 x 18 mm, 3 mm proud of the door, a passive slide joint pressing
down 0 to 5 mm against a 120 N/m spring) carries a hook that sits just in front of a fixed latch stop at the remote's
rear end while the door is shut. The door opens only while the tab is pressed far enough (about 2.9 to 4.5 mm) for the
hook to pass under the stop; it re-latches when it is slid fully shut and the tab is released. Under the door is a
one-cell compartment: the slot centre is at (-0.020, 0.0, -0.00244) m in the remote frame, the gray cell lies there on
two low cradle ribs with its + end toward the gold contact at the slot's +x end (the silver - contact is at the -x end;
3 mm end play). The green replacement cell (a 23 g rigid cylinder, radius 7 mm, 49 mm long, like the gray one) lies on
the table at (0.115, -0.110, 0.307) with its + end pointing 20 degrees clockwise from world +x (seen from above). The
receiving tray (free rigid body, inner 74 x 64 mm, 18 mm walls) stands at (0.16, 0.10, 0.303). Modelling scope: the
compartment holds one cell; the source's compressible negative spring is not modelled (the terminals are fixed); there
is no electrical simulation. All objects move only through contact and these passive joints.

You control a fixed Tianji Marvin robot standing at the table (stand origin at (-0.45, 0.15, -0.45), facing +x) with two
7-joint arms and a dexterous hand on each wrist; the right arm and hand do the task, the left arm hangs parked beside
the torso (keep its targets). Every arm and finger joint is a position servo inside the physics engine under native
force bounds; the arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target
sags under the arm's weight unless your targets account for it). Grasping, carrying and releasing require physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps per control.

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
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
