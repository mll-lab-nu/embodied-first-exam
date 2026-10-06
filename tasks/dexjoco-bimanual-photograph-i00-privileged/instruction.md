# DexJoCo · bimanual_photograph — frozen instance

You control two Franka Panda arms, each with a 16-DoF Allegro hand (DexJoCo on MuJoCo 3.4) via Python. **Task:** Hold the camera with the left hand in front of the logo and press its shutter with the right hand. Success, at one control step: the camera's view point is inside the target region (0.16 m radius, +-0.10 m height, 0.40 m in front of the logo along -x, i.e. about 0.3 m above the table), the camera's viewing axis is within 10 degrees of world +x, and the shutter button is touched by something other than the camera.

The camera lies on the table between the robots; the logo disk stands at the far side of the table. `s.objects()` gives the live poses of the task objects (`camera`, `view_point`, `shutter`, `logo`, `target_region`, `table_top`). DexJoCo's success code (from
`/opt/dexjoco/dexjoco/dexjoco/sim/envs/panda_bimanual_photograph_env.py`; `step()` ends the episode on success or on a task failure):
```python
def _compute_success(self) -> bool:
    success, _ = self._compute_success_metrics()
    return bool(success)

def _compute_success_metrics(self) -> Tuple[bool, Dict[str, Any]]:
    region_center = self._data.geom_xpos[self._target_region_geom_id].copy()
    region_rot = self._data.geom_xmat[self._target_region_geom_id].reshape(3, 3)
    view_pos = self._data.site_xpos[self._view_site_id].copy()
    delta_local = region_rot.T @ (view_pos - region_center)
    radial_dist = float(np.linalg.norm(delta_local[:2]))
    region_height_dist = float(abs(delta_local[2]))
    region_pass = radial_dist <= _TARGET_REGION_RADIUS and region_height_dist <= _TARGET_REGION_HALF_HEIGHT

    axis_z_world = self._data.geom_xmat[self._camera_axis_z_geom_id].reshape(3, 3)[:, 2].copy()
    axis_z_norm = float(np.linalg.norm(axis_z_world))
    if axis_z_norm < 1e-8:
        axis_z_world = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    else:
        axis_z_world = axis_z_world / axis_z_norm

    cos_val = float(np.clip(np.dot(axis_z_world, _WORLD_POS_X), -1.0, 1.0))
    angle_deg = float(np.degrees(np.arccos(cos_val)))
    angle_pass = angle_deg <= _TARGET_ANGLE_DEG

    shutter_pressed = False
    shutter_contact_count = 0
    ncon = int(self._data.ncon)
    for i in range(ncon):
        c = self._data.contact[i]
        g1 = int(c.geom1)
        g2 = int(c.geom2)
        if g1 == self._shutter_geom_id:
            if g2 not in self._camera_geom_ids:
                shutter_pressed = True
                shutter_contact_count += 1
        elif g2 == self._shutter_geom_id:
            if g1 not in self._camera_geom_ids:
                shutter_pressed = True
                shutter_contact_count += 1

    success = region_pass and angle_pass and shutter_pressed
    return bool(success), {
        "region_pass": bool(region_pass),
        "angle_pass": bool(angle_pass),
        "shutter_pressed": bool(shutter_pressed),
        "radial_dist": radial_dist,
        "region_height_dist": region_height_dist,
        "view_angle_deg": angle_deg,
        "shutter_contact_count": int(shutter_contact_count),
    }
```

This is a *fixed scene instance*: object poses, the table height and the robot's start pose never change between
resets. You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a
general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in a fresh process and scored 1 if its episode ends in success, else 0. Also
leave the script that produced it at `/app/output/gen.py`. You have 90 minutes of wall clock: save a
first trajectory early, improve it, and do not stop before the task is solved.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_dexjoco import Session
s = Session("bimanual_photograph", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact snapshot restore)
s.objects()                        # live task objects: name -> pos, quat_wxyz (bodies) / pos (sites) / qpos (joints)
s.state()                          # DexJoCo's state dict: tcp_pose, gripper_pose (hand joints), INITIAL object poses, table height
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
p["move_ee"]("right", pos, quat_wxyz)      # straight-line + slerp motion of an arm's tcp target, then settle
p["set_hand"]("right", q16)                # interpolate the 16 Allegro joint targets
p["hold"](10); p["set_targets"](row, steps)            # keep every target / send one raw action row
p["get_ee_pose"]("right"); p["get_ee_target"]("right"); p["get_hand"]("right"); p["get_body_pose"](name)
s.render_frame("front")            # RGB uint8 (480, 640, 3); cameras: ['front', 'back', 'left', 'right', 'top0', 'handcam_rgb_right', 'handcam_rgb_left', 'cam_pos_z']; s.render_grid()
s.step(action)                     # one control step (46 values, below) = 1/50 s; returns False once the episode is over
s.record_start(); ...; actions = s.record_stop()   # (T, 46) actions, one row per control step
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'state_sha', 'info'}
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4", cameras=["front"])   # replays from the frozen state into a video
```
The primitives are deliberately thin (tcp target moves, hand joint targets, hold): grasping, pressing, striking and
every other skill are yours to build from them. `s.bodies()` lists every MuJoCo body for `p["get_body_pose"]`.

CLI equivalent of the grader:
`python /opt/tools/rcb_dexjoco.py replay --task bimanual_photograph --instance /app/instance.npz --traj /app/output/trajectory.npz`

## Conventions
- World frame, metres; z up; the robots stand at low x and reach towards +x. The table top is at z = 0.930. Arm base (`link0`): link0_right [-0.75, -0.4, 0.924], link0_left [-0.75, 0.4, 0.924]. The right arm works at y < 0, the left arm at y > 0. Quaternions are **WXYZ**.
- Action (46): per arm, right first: tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro
  joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
  target and stops where contact blocks it); the hand joints are position-controlled. `s.hold_action()` is the no-op.
  At the start the tcp target is right [-0.443, -0.4, 1.517] / [0.0, -1.0, 0.0, -0.0025], left [-0.443, 0.4, 1.517] / [0.0, -1.0, 0.0, -0.0025].
- Allegro joint order (right hand): index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger =
  spread, 1-3 = flexion from the knuckle out; thumb 12 = opposition). The LEFT hand's 16 values are mirrored: ring 0-3, middle 4-7, index 8-11, thumb 12-15.
  Target ranges (rad, same for every finger slot, thumb last): low [-0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, 0.26, -0.1, -0.19, -0.16], high [0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 1.4, 1.16, 1.64, 1.72]; the simulator clamps
  targets to them.
- Control runs at 50 Hz (10 physics substeps of 2 ms). DexJoCo's own episode cap and real-time pacing are lifted: there
  is no step budget, your wall-clock time is the limit (~180 control steps/s here). An episode ends at the
  first success or task failure; `s.step` then refuses further actions until `s.reset()`.
