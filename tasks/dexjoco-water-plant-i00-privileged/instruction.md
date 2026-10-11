# DexJoCo · water_plant — frozen instance

You control a Franka Panda arm with a 16-DoF Allegro hand (DexJoCo on MuJoCo 3.4) via Python. **Task:** Pick up the spray bottle, point its nozzle at the potted plant and squeeze the trigger. Success: the trigger is held pulled (trigger joint > 0.34 rad; it counts as released again below 0.25 rad) while the nozzle reference point is within 0.20 m of the plant horizontally and within +-0.20 m of the plant's height AND the spray points at the plant, all three for 30 consecutive control steps (0.6 s). The spray leaves the spray head horizontally forward: perpendicular to the bottle's long axis, on the side the trigger faces (the bottle's local +z; its long axis, bottom to head, is local +y). It points at the plant when that direction is within 45 degrees of the line from the nozzle to the plant, e.g. with the bottle held upright and its trigger side facing the plant. Pulling the trigger while the nozzle is outside the zone ends the episode as a failure.

The spray bottle stands on the table to the robot's right-front, the potted plant further along +y. The trigger is a hinge on the bottle's neck that the index and middle fingers can pull back. `s.objects()` gives the live poses of the task objects (`spray_bottle`, `spray_trigger`, `spray_nozzle`, `plant`, `table_top`). DexJoCo's success code (from
`/opt/dexjoco/dexjoco/dexjoco/sim/envs/panda_water_plant_env.py`; `step()` ends the episode on success or on a task failure):
```python
def _compute_success(self):
    site_id = self._model.site("ref_point").id
    p_world = self._data.site_xpos[site_id]
    obj_world_pos = self._data.body("plant").xpos

    R = 0.2
    HALF_H = 0.2
    dx, dy, dz = p_world - obj_world_pos
    inside = (dx * dx + dy * dy <= R * R) and (-HALF_H <= dz <= HALF_H)

    failed_trigger_outside = (not inside) and self._trigger_pulled

    if inside and self._trigger_pulled:
        self._success_counter += 1
    else:
        self._success_counter = 0

    success = self._success_counter >= _SUCCESS_STEPS_REQUIRED
    return success, failed_trigger_outside
```

robot_coding_bench adds the aiming condition to DexJoCo's check: upstream's zone + trigger test alone passes with the bottle lying on the table and spraying away from the plant. The episode ends in success only when `_compute_success`'s zone + trigger condition and the aim below hold together for 30 consecutive steps (`status()['info']` reports `aim_deg` and `rcb_success_count`); DexJoCo's own `succeed` flag alone no longer ends it.
```python
WATER_AIM_MAX_DEG = 45.0

def water_aim_deg(model, data) -> float:
    """Angle (deg) between the spray direction and the direction from the nozzle reference point to the plant. The spray
    direction is the bottle body's +z axis, along which DexJoCo draws its spray cone: perpendicular to the bottle's long
    axis (+y, bottom to spray head), out of the front of the head on the side the trigger faces."""
    spray = data.body("link_2").xmat.reshape(3, 3)[:, 2]
    to_plant = data.body("plant").xpos - data.site("ref_point").xpos
    c = float(np.dot(spray, to_plant) / max(1e-9, np.linalg.norm(to_plant)))
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))
```

This is a *fixed scene instance*: object poses, the table height and the robot's start pose never change between
resets. You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a
general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in a fresh process and scored 1 if its episode ends in success, else 0. Also
leave the script that produced it at `/app/output/gen.py`. A trajectory may have at most 50,000 rows
(1000 s of robot time): `save_trajectory` refuses a longer one and the verifier scores it 0. You have
90 minutes of wall clock: save a first trajectory early, improve it, and do not stop before the task is solved.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_dexjoco import Session
s = Session("water_plant", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
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
`python /opt/tools/rcb_dexjoco.py replay --task water_plant --instance /app/instance.npz --traj /app/output/trajectory.npz`

## Conventions
- World frame, metres; z up; the robot stands at low x and reaches towards +x. The table top is at z = 0.964. Arm base (`link0`): link0 [-0.75, 0.0, 0.924]. Quaternions are **WXYZ**.
- Action (23): tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro
  joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
  target and stops where contact blocks it); the hand joints are position-controlled. `s.hold_action()` is the no-op.
  At the start the tcp target is [-0.443, -0.0, 1.517] / [0.0, -1.0, 0.0, -0.0025].
- Allegro joint order: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger =
  spread, 1-3 = flexion from the knuckle out; thumb 12 = opposition).
  Target ranges (rad, same for every finger slot, thumb last): low [-0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, 0.26, -0.1, -0.19, -0.16], high [0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 1.4, 1.16, 1.64, 1.72]; the simulator clamps
  targets to them.
- Control runs at 50 Hz (10 physics substeps of 2 ms). DexJoCo's own episode cap and real-time pacing are lifted: your
  sessions have no step budget, your wall-clock time is the limit (~390 control steps/s here); only the
  trajectory you hand in is capped (50,000 rows). An episode ends at the first success or task failure; `s.step`
  then refuses further actions until `s.reset()`.
- The simulation repeats bit for bit, for one OpenBLAS thread count: the controller's linear algebra gives slightly
  different results on 1, on 2-3 and on 4 or more threads. This container sets `OPENBLAS_NUM_THREADS=4`, as the verifier's
  does; leave it as it is, or your replays will not match the verifier's. (OpenBLAS runs no more threads than the CPUs
  a process may use: if the tooling warns that it runs fewer than 4, your replays here are not the verifier's.)

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
