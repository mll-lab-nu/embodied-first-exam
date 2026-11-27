# DexJoCo · pinch_tongs (privileged)

## Task
Pick up the tongs, open them wide and squeeze them shut three times, then hold them up, a hand's width or more above the
table.

## Goal
Success: the tongs have been opened wide and squeezed shut three times, and they are then held a hand's width or more
above the table for about half a second. A replay ends as soon as the task is done; later rows are not run.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(...)`, at most 50,000 rows (1000 s of robot
time; `save_trajectory` refuses a longer one). It is replayed open-loop from the fixed start and passes if its episode
ends in success. Also leave the script that produced it at `/app/output/gen.py`. Save a first trajectory early and
overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A Franka Panda arm with a 16-joint Allegro hand (DexJoCo, MuJoCo). The scene is one fixed instance. You have the full
simulator to develop with; you hand in a trajectory of actions.

### Session
`/opt/tools/rcb_dexjoco.py`, importable as `rcb_dexjoco` (installed; run `python` from any directory):
```python
from rcb_dexjoco import Session
s = Session("pinch_tongs", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact snapshot restore)
s.objects()                        # live task objects: name -> pos, quat_wxyz (bodies) / pos (sites) / qpos (joints)
s.state()                          # DexJoCo's state dict: tcp_pose, gripper_pose (hand joints), INITIAL object poses, table height
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
p["move_ee"]("right", pos, quat_wxyz)      # straight-line + slerp motion of an arm's tcp target, then settle
p["set_hand"]("right", q16)                # interpolate the 16 Allegro joint targets
p["hold"](10); p["set_targets"](row, steps)            # keep every target / send one raw action row
p["get_ee_pose"]("right"); p["get_ee_target"]("right"); p["get_hand"]("right"); p["get_body_pose"](name)
s.render_frame("front")            # RGB uint8 (480, 640, 3); cameras: ['front', 'back', 'left', 'right', 'top0', 'handcam_rgb']; s.render_grid()
s.step(action)                     # one control step (23 values, below) = 1/50 s; returns False once the episode is over
s.record_start(); ...; actions = s.record_stop()   # (T, 23) actions, one row per control step
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'state_sha', 'info'}
s.replay(actions)                  # resets, replays open-loop until the episode ends (as the grader does), returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4", cameras=["front"])   # replays from the frozen state into a video
```
The primitives are deliberately thin (tcp target moves, hand joint targets, hold): grasping, pressing, striking and
every other skill are yours to build from them. `s.bodies()` lists every MuJoCo body for `p["get_body_pose"]`. The same
replay from the shell:
`python /opt/tools/rcb_dexjoco.py replay --task pinch_tongs --instance /app/instance.npz --traj /app/output/trajectory.npz`.

### Actions
- An action row (23): tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro joint targets (rad). The arm
  tracks the target through DexJoCo's operational-space controller, which lags a moving target and stops where contact
  blocks it. The hand joints are position-controlled. `s.hold_action()` is the no-op. At the start the tcp target is
  [-0.443, -0.0, 1.517] / [0.0, 1.0, 0.0, 0.0].
- Allegro joint order: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger = spread, 1-3 = flexion
  from the knuckle out; thumb 12 = opposition). Target ranges (rad, same for every finger slot, thumb last): low [-0.47,
  -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, 0.26, -0.1, -0.19, -0.16], high [0.47, 1.61,
  1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 1.4, 1.16, 1.64, 1.72]; the simulator clamps targets to
  them.
- Control runs at 50 Hz (10 physics substeps of 2 ms): `s.step(action)` is one control step. An episode ends at the
  first success or task failure; `s.step` then refuses further actions until `s.reset()`.

### Scene
World frame, metres; z up; the robot stands at low x and reaches towards +x. The table top is at z = 0.970. Arm base
(`link0`): link0 [-0.75, 0.0, 0.924]. Quaternions are WXYZ. `s.objects()` gives the live poses of the task objects
(`tongs`, `tongs_hinge`, `table_top`).

### Steps
- Your sessions have no step budget (about 390 control steps per second here); only the trajectory you hand in is
  capped.

## Others
- The simulation repeats exactly only for one OpenBLAS thread count: the controller's linear algebra gives slightly
  different results on 1, on 2-3 and on 4 or more threads. This container sets `OPENBLAS_NUM_THREADS=4`, as the grader's
  does; leave it as it is, or your replays will not match the grader's. (OpenBLAS never runs more threads than the CPUs
  a process may use. If the tooling warns that it runs fewer than 4, your replays here will not match the grader's.)

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 10 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
