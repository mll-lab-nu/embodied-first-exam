# DexJoCo · hammer_nail — frozen instance

You control a Franka Panda arm with a 16-DoF Allegro hand (DexJoCo on MuJoCo 3.4) via Python. **Task:** Pick up the hammer and drive the nail into the wooden block by striking its head. A strike counts only if the hammer face was moving down faster than 0.02 m/s just before it touched the nail; each counted strike drives the nail 8 mm x min(3, speed / 0.02) deeper (at most 7.26 cm). Success: the nail is at least 4 cm deep.

The hammer lies on the table at the robot's right (low y); the nail stands upright in a wooden block in front of the robot. The nail is not a free body: it only moves down when struck. `s.objects()` gives the live poses of the task objects (`hammer`, `nail`, `nail_top`, `wood_top`, `table_top`). DexJoCo's success code (from
`/opt/dexjoco/dexjoco/dexjoco/sim/envs/panda_hammer_nail_env.py`; `step()` ends the episode on success or on a task failure):
```python
def _compute_success(self):
    return float(self._nail_depth) >= self._success_depth

def _apply_hammer_nail_interaction(self) -> bool:
    if not self._hammer_geom_ids or not self._nail_geom_ids:
        return False

    hammer_set = set(self._hammer_geom_ids)
    nail_set = set(self._nail_geom_ids)
    hit = False
    ncon = int(self._data.ncon)
    for i in range(ncon):
        c = self._data.contact[i]
        g1 = int(c.geom1)
        g2 = int(c.geom2)
        if (g1 in hammer_set and g2 in nail_set) or (
            g2 in hammer_set and g1 in nail_set
        ):
            hit = True
            break

    if not hit:
        return False

    preimpact_vz = min(self._vz_buf) if self._vz_buf else 0.0
    if preimpact_vz >= -self._impact_vel_threshold:
        return True

    depth = float(self._nail_depth)
    max_depth = float(self._nail_max_depth)
    scale = min(3.0, abs(preimpact_vz) / max(self._impact_vel_threshold, 1e-6))
    delta = self._impact_insert_step * scale
    new_depth = min(max_depth, depth + delta)
    if new_depth > depth:
        self._nail_depth = new_depth
        new_pos = self._nail_init_pos.copy()
        new_pos[2] = self._nail_init_pos[2] - new_depth
        self._data.mocap_pos[self._nail_mocap_id] = new_pos
        self._data.mocap_quat[self._nail_mocap_id] = self._nail_init_quat
        mujoco.mj_forward(self._model, self._data)

    return True
```

This is a *fixed scene instance*: object poses, the table height and the robot's start pose never change between
resets. You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a
general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in a fresh process and scored 1 if its episode ends in success, else 0. Also
leave the script that produced it at `/app/output/gen.py`. A trajectory may have at most 50,000 rows
(1000 s of robot time): `save_trajectory` refuses a longer one and the verifier scores it 0. Save a
first trajectory early, improve it, and do not stop before the task is solved.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_dexjoco import Session
s = Session("hammer_nail", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
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
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4", cameras=["front"])   # replays from the frozen state into a video
```
The primitives are deliberately thin (tcp target moves, hand joint targets, hold): grasping, pressing, striking and
every other skill are yours to build from them. `s.bodies()` lists every MuJoCo body for `p["get_body_pose"]`.

CLI equivalent of the grader:
`python /opt/tools/rcb_dexjoco.py replay --task hammer_nail --instance /app/instance.npz --traj /app/output/trajectory.npz`

## Conventions
- World frame, metres; z up; the robot stands at low x and reaches towards +x. The table top is at z = 0.936. Arm base (`link0`): link0 [-0.75, 0.0, 0.924]. Quaternions are **WXYZ**.
- Action (23): tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro
  joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
  target and stops where contact blocks it); the hand joints are position-controlled. `s.hold_action()` is the no-op.
  At the start the tcp target is [-0.059, 0.008, 1.096] / [1.0, 0.0, 0.0, 0.0].
- Allegro joint order: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger =
  spread, 1-3 = flexion from the knuckle out; thumb 12 = opposition).
  Target ranges (rad, same for every finger slot, thumb last): low [-0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, 0.26, -0.1, -0.19, -0.16], high [0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 1.4, 1.16, 1.64, 1.72]; the simulator clamps
  targets to them.
- Control runs at 50 Hz (10 physics substeps of 2 ms). DexJoCo's own episode cap and real-time pacing are lifted: your
  sessions have no step budget, your wall-clock time is the limit (~400 control steps/s here); only the
  trajectory you hand in is capped (50,000 rows). An episode ends at the first success or task failure; `s.step`
  then refuses further actions until `s.reset()`.
- The simulation repeats bit for bit, for one OpenBLAS thread count: the controller's linear algebra gives slightly
  different results on 1, on 2-3 and on 4 or more threads. This container sets `OPENBLAS_NUM_THREADS=4`, as the verifier's
  does; leave it as it is, or your replays will not match the verifier's. (OpenBLAS runs no more threads than the CPUs
  a process may use: if the tooling warns that it runs fewer than 4, your replays here are not the verifier's.)

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
