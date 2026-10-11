# DexJoCo · bimanual_microwave_cook — frozen instance

You control two Franka Panda arms, each with a 16-DoF Allegro hand (DexJoCo on MuJoCo 3.4) via Python. **Task:** Open the microwave door, put the hot dog inside, close the door and press the start button. Success, at one control step: the hot dog is inside the cavity (1 cm margin), the door hinge is within 0.01 rad of closed, and the start button is in contact with something.

The microwave stands on the table with its door closed; the hot dog lies in front of it. The door has a handle and a hinge (`door_hinge`); the start and stop buttons are on the front panel. `s.objects()` gives the live poses of the task objects (`hot_dog`, `microwave`, `door_hinge`, `door_handle`, `start_button`, `stop_button`, `table_top`). DexJoCo's success code (from
`/opt/dexjoco/dexjoco/dexjoco/sim/envs/panda_bimanual_microwave_cook_env.py`; `step()` ends the episode on success or on a task failure):
```python
def _compute_success(self):
    # ---- door must be closed ----
    micro_qpos = float(self._data.joint("microjoint").qpos)
    microwave_closed = abs(micro_qpos) < 1e-2

    # ---- hot_dog must be inside interior bbox ----
    inside = self.hot_dog_inside_microwave(margin=0.01)

    contact = self._geom_in_contact("start_button")

    # Debug helpers kept nearby for local inspection when needed.
    # print("microjoint qpos:", micro_qpos)
    # print("hot_dog inside:", inside)
    # print("start button pressed:", contact)

    return inside and microwave_closed and contact

def hot_dog_inside_microwave(self, margin=0.0):
    # ---- hot_dog world position ----
    p_world = self._data.sensor("hot_dog_pos").data

    # ---- transform to microwave local frame ----
    p_local = self.world_to_body("microwave_object", p_world)

    # ---- read interior box sites (local frame) ----
    p0 = self._model.site("int_p0").pos
    px = self._model.site("int_px").pos
    py = self._model.site("int_py").pos
    pz = self._model.site("int_pz").pos

    inside_x = (p0[0] - margin) <= p_local[0] <= (px[0] + margin)
    inside_y = (p0[1] - margin) <= p_local[1] <= (py[1] + margin)
    inside_z = (p0[2] - margin) <= p_local[2] <= (pz[2] + margin)

    return inside_x and inside_y and inside_z
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
s = Session("bimanual_microwave_cook", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact snapshot restore)
s.objects()                        # live task objects: name -> pos, quat_wxyz (bodies) / pos (sites) / qpos (joints)
s.state()                          # DexJoCo's state dict: tcp_pose, gripper_pose (hand joints), INITIAL object poses, table height
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
p["move_ee"]("right", pos, quat_wxyz)      # straight-line + slerp motion of an arm's tcp target, then settle
p["set_hand"]("right", q16)                # interpolate the 16 Allegro joint targets
p["hold"](10); p["set_targets"](row, steps)            # keep every target / send one raw action row
p["get_ee_pose"]("right"); p["get_ee_target"]("right"); p["get_hand"]("right"); p["get_body_pose"](name)
s.render_frame("back")            # RGB uint8 (480, 640, 3); cameras: ['back', 'handcam_rgb_right', 'handcam_rgb_left']; s.render_grid()
s.step(action)                     # one control step (46 values, below) = 1/50 s; returns False once the episode is over
s.record_start(); ...; actions = s.record_stop()   # (T, 46) actions, one row per control step
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'state_sha', 'info'}
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4", cameras=["back"])   # replays from the frozen state into a video
```
The primitives are deliberately thin (tcp target moves, hand joint targets, hold): grasping, pressing, striking and
every other skill are yours to build from them. `s.bodies()` lists every MuJoCo body for `p["get_body_pose"]`.

CLI equivalent of the grader:
`python /opt/tools/rcb_dexjoco.py replay --task bimanual_microwave_cook --instance /app/instance.npz --traj /app/output/trajectory.npz`

## Conventions
- World frame, metres; z up; the robots stand at low x and reach towards +x. The table top is at z = 0.943. Arm base (`link0`): link0_right [-0.75, -0.4, 0.924], link0_left [-0.75, 0.4, 0.924]. The right arm works at y < 0, the left arm at y > 0. Quaternions are **WXYZ**.
- Action (46): per arm, right first: tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro
  joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
  target and stops where contact blocks it); the hand joints are position-controlled. `s.hold_action()` is the no-op.
  At the start the tcp target is right [-0.443, -0.4, 1.517] / [0.0, 1.0, 0.0, 0.0], left [-0.443, 0.4, 1.517] / [0.0, 1.0, 0.0, 0.0].
- Allegro joint order (right hand): index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger =
  spread, 1-3 = flexion from the knuckle out; thumb 12 = opposition). The LEFT hand's 16 values are mirrored: ring 0-3, middle 4-7, index 8-11, thumb 12-15.
  Target ranges (rad, same for every finger slot, thumb last): low [-0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, 0.26, -0.1, -0.19, -0.16], high [0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 1.4, 1.16, 1.64, 1.72]; the simulator clamps
  targets to them.
- Control runs at 50 Hz (10 physics substeps of 2 ms). DexJoCo's own episode cap and real-time pacing are lifted: your
  sessions have no step budget, your wall-clock time is the limit (~190 control steps/s here); only the
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
