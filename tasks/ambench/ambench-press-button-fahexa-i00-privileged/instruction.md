# AM-Bench · ambench-press-button-fahexa-i00 (privileged)

## Task
A simulated aerial manipulator: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude while
hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in AM-Bench
(Isaac Lab). A wall stands in front of the hovering aerial manipulator, and a push button is mounted flat on the wall's
front face, facing the robot: a red circular plunger in a dark-grey circular housing. Press the button: push its
spring-loaded plunger into the housing, along the wall's normal. The scene is one fixed instance: it starts the same way
after every reset. You have the full simulator to develop with; you hand in one replayable trajectory of the robot's
actions.

### Scene
The ground is the world's z = 0 plane. In front of the robot stands an immovable (kinematic) wall: a slab 0.1 m thick,
2.0 m wide and 2.0 m tall with a concrete-block surface, its front face turned toward the robot. Its distance, its
sideways offset and a small tilt (the top leaning toward or away from the robot) vary between instances. On the wall's
front face sits a push button: a dark-grey circular housing, 12 mm thick, fixed flush to the wall, and in front of it a
red circular plunger, 10 mm thick, whose face stands about 2 cm proud of the wall surface. The plunger is the only
moving part: it slides along the wall's normal into the housing (10 mm of travel) and is spring-loaded, returning to its
rest position when not pushed. Where the button sits on the central part of the wall varies between instances, and so
does its face size (plunger diameter between 6 and 12 cm, housing proportionally 1.2 times wider). Nothing moves by
itself. The robot starts hovering level and motionless, facing the wall, with its arm at its zero joint configuration
(end effector a little ahead of and above the airframe) and the gripper closed.

## Goal
Success: the button is pressed: its plunger pushed into the housing at least nearly halfway (a light touch is not
enough). An episode ends by itself at the first control step where the task is done (the rows after it are never run),
or as a failure when its 20 s of simulated time run out.

Deliverable: `/app/output/trajectory.npz`, written with `Session.save_trajectory(...)`: `task` and `actions`, a (T, 8)
float array of at most 8,000 rows (one per control step); anything else (another shape, NaN, more rows, a row whose
quaternion `qw qx qy qz` has zero length, a file that is not such an npz) scores 0. It is replayed open-loop from the
same start up to 3 times and scores 1 if the task succeeds in any replay (a trajectory that only just succeeds may not
succeed again: leave a margin). Keep the script that produced it at `/app/output/gen.py`. Save a valid one early and
overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the trajectory counts: changing the simulator's state while you develop changes nothing in the grading.

## Robot Interface
### Session
`/opt/tools/rcb_ambench.py`:
```python
from rcb_ambench import Session
s = Session(instance="/app/instance.json")   # ~2-6 min: launches Isaac Sim, builds the scene, resets to the frozen instance
                                   # Session(..., cameras=True[, depth=True]) to look (see Cameras below)
s.reset()                          # back to the frozen instance (the seeded reset; as often as you like)
s.step(row)                        # one control step (1/120 s): row = 8 values (below); True once the episode is over
s.hold_action()                    # a row that keeps the current end-effector target and gripper command
s.status()                         # {'success', 'done', 'end_reason', 'control_steps', 'sim_time_s', 'episode_length_s', 'state_sha', ...}
s.state()                          # privileged: AM-Bench's own observation of the task (robot, end effector, task objects, goal)
s.objects()                        # every task object and fixture: pose (xyz + quaternion wxyz), velocities, joint state
s.proprio()                        # the robot: base and end-effector poses and velocities, gripper width, arm joints, current command
s.actions()                        # (T, 8) rows executed since the last reset: the trajectory of this episode
s.replay(actions)                  # reset, run the rows open-loop until the episode ends, return status (+ executed_rows)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("ee_camera")        # cameras=True only: RGB uint8 (384, 384, 3) at the end effector, or "base_camera" (on the airframe, looking forward)
s.render_depth("ee_camera")        # cameras=True, depth=True: float32 z-depth (m), 0 = no reading
s.camera_info()                    # cameras=True: intrinsics, world -> camera extrinsics (OpenCV axes), mounts
s.start_video("/app/output/try.mp4"); ...; s.stop_video()   # cameras=True only: film the steps in between (both cameras side by side)
s.env                              # the Isaac Lab environment itself (AM-Bench's source is in /opt/ambench: read-only reference)
```

The tooling is deliberately thin: the environment's own action, its state and its cameras. Reaching, pressing, pushing,
turning and throwing are yours to build. Isaac Sim runs once per process, and only the first episode of a process is
guaranteed to replay exactly as a new process does: after changes, check your trajectory with the replay command below.

The robot's two onboard cameras come with `Session(..., cameras=True)` (decided once per process): a second Isaac
process then draws them from the physics state (it starts with the Session and takes ~3.5 GB of GPU memory and ~12 GB of
memory), so looking never changes the physics, which stays exactly as in the replay.

Your trajectory is replayed with exactly this command (stopping at the first success), so run it to self-check:
`python /opt/tools/rcb_ambench.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`
(`... film --instance ... --traj ... --video out.mp4` films the same rows through the cameras). A process whose output
shows `PhysX error: GPU ... fail to launch` or `CUDA error: out of memory` ran short of GPU memory and its physics is
not reliable: run it again with fewer Isaac processes at once.

### Actions
- World frame: metres, z up, the ground is the plane z = 0; positions are relative to the environment's origin (the
  tooling and the actions use the same origin); quaternions are wxyz.
- Action row (8 values per control step), AM-Bench's absolute end-effector pose action: the target position of the
  end-effector link (x, y, z, m) and its target orientation (qw, qx, qy, qz, in AM-Bench's command frame of the end
  effector: `s.proprio()["command"]` and `hold_action()` give the current target in the same convention), then the
  gripper command (-1 = closed .. +1 = open). Every step, AM-Bench's floating-base inverse kinematics turns the target
  into an airframe pose and arm joint targets, its PID controller turns the airframe pose into the six rotor thrusts,
  and the arm joints track their targets.
- Control and physics run at 120 Hz (one physics step per row).

## Others
- One `Session` per process (Isaac Sim launches once, then the scene builds: ~2-6 min, the upper end on a busy host).
  Physics is PhysX on the GPU (about 10-15 control steps per second of wall time). A camera-free Session takes ~2 GiB of
  memory and ~1.2 GiB of GPU memory, one with cameras ~14 GiB and ~4.6 GiB (its render worker included): run at most two
  Sessions with cameras at once. Do not call `s.close()` before writing every output.
- Isaac Lab resets the scene inside the step that ends an episode, so after it `s.state()` and `s.objects()` show the
  start again; `s.status()` keeps the outcome and the end state's hash, and the cameras show the end.
- Exact poses, sizes and joints of everything in the scene: `s.objects()`, `s.state()` and AM-Bench's source
  (`/opt/ambench`).

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
- Resources: 8 CPUs, 34 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (16 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
