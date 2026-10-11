# DexJoCo · bimanual_hanoi — frozen instance

You control two Franka Panda arms, each with a 16-DoF Allegro hand (DexJoCo on MuJoCo 3.4) via Python. **Task:** Tower of Hanoi with three disks on three vertical posts in a row along y: the small disk is on post A (y > 0, the left arm's side), the medium disk on post B (middle), the large disk on post C (y < 0). Build the full tower on post C: large at the bottom, then medium, then small, posts A and B empty, every disk at rest and seated on the post (horizontally within 4 cm of it, at its stacking height within 1.2 cm), held for 20 consecutive control steps. A larger disk resting on a smaller one, or a disk resting on the table, for 10 consecutive steps ends the episode as a failure.

Two arms with a hand each stand side by side facing the table (right arm at y < 0, left arm at y > 0); the wooden Hanoi base with its three posts is in front of them. Each disk has a hole and slides over a post. `s.objects()` gives the live poses of the task objects (`disk_small`, `disk_medium`, `disk_large`, `post_a`, `post_b`, `post_c`). DexJoCo's success code (from
`/opt/dexjoco/dexjoco/dexjoco/sim/envs/panda_bimanual_hanoi_env.py`; `step()` ends the episode on success or on a task failure):
```python
def _compute_success_metrics(self) -> Tuple[bool, Dict[str, Any]]:
    state = self._reconstruct_tower_state()
    towers = state["towers"]
    disk_assignment = state["disk_assignment"]
    disk_positions = state["disk_positions"]
    disk_static = state["disk_static"]
    post_positions = state["post_positions"]
    base_top_z = state["base_top_z"]

    tower_state = self._tower_state_repr(towers)
    all_disks_static = all(bool(v) for v in disk_static.values())

    illegal_candidate = False
    illegal_reason = ""

    for post_name, disks in towers.items():
        ranks = [self._disk_size_rank[disk] for disk in disks]
        if any(ranks[i] < ranks[i + 1] for i in range(len(ranks) - 1)):
            if all(disk_static[disk] for disk in disks):
                xy_error, height_error = self._tower_geometry_errors(
                    disks, post_name, disk_positions, post_positions, base_top_z
                )
                if (
                    xy_error <= self._post_assignment_tol
                    and height_error <= self._placement_height_tol
                ):
                    illegal_candidate = True
                    illegal_reason = f"illegal_stack_{post_name}"
                    break

    if not illegal_candidate and all_disks_static:
        on_table = [disk for disk, assign in disk_assignment.items() if assign == "table"]
        if on_table:
            illegal_candidate = True
            illegal_reason = "disk_on_table"

    if illegal_candidate:
        if illegal_reason == self._illegal_trigger_reason:
            self._illegal_trigger_count += 1
        else:
            self._illegal_trigger_reason = illegal_reason
            self._illegal_trigger_count = 1
    else:
        self._illegal_trigger_reason = ""
        self._illegal_trigger_count = 0

    illegal_state = self._illegal_trigger_count >= self._illegal_trigger_target

    xy_error_max = 0.0
    height_error_max = 0.0
    target_stack = ["hanoi_disk_large", "hanoi_disk_medium", "hanoi_disk_small"]

    if towers["C"] == target_stack and len(towers["A"]) == 0 and len(towers["B"]) == 0:
        xy_error_max, height_error_max = self._tower_geometry_errors(
            target_stack, "C", disk_positions, post_positions, base_top_z
        )
        geom_success = (
            xy_error_max <= self._post_assignment_tol
            and height_error_max <= self._placement_height_tol
            and all_disks_static
        )
    else:
        geom_success = False

    if geom_success and not illegal_state:
        self._success_trigger_count += 1
    else:
        self._success_trigger_count = 0

    success = self._success_trigger_count >= self._success_trigger_target

    return bool(success), {
        "tower_state": tower_state,
        "disk_assignment": dict(disk_assignment),
        "all_disks_static": bool(all_disks_static),
        "illegal_state": bool(illegal_state),
        "illegal_reason": illegal_reason,
        "xy_error_max": float(xy_error_max),
        "height_error_max": float(height_error_max),
    }

def _compute_success(self) -> bool:
    success, _ = self._compute_success_metrics()
    return bool(success)
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
s = Session("bimanual_hanoi", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact snapshot restore)
s.objects()                        # live task objects: name -> pos, quat_wxyz (bodies) / pos (sites) / qpos (joints)
s.state()                          # DexJoCo's state dict: tcp_pose, gripper_pose (hand joints), INITIAL object poses, table height
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
p["move_ee"]("right", pos, quat_wxyz)      # straight-line + slerp motion of an arm's tcp target, then settle
p["set_hand"]("right", q16)                # interpolate the 16 Allegro joint targets
p["hold"](10); p["set_targets"](row, steps)            # keep every target / send one raw action row
p["get_ee_pose"]("right"); p["get_ee_target"]("right"); p["get_hand"]("right"); p["get_body_pose"](name)
s.render_frame("front")            # RGB uint8 (480, 640, 3); cameras: ['front', 'back', 'left', 'right', 'top0', 'handcam_rgb_right', 'handcam_rgb_left']; s.render_grid()
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
`python /opt/tools/rcb_dexjoco.py replay --task bimanual_hanoi --instance /app/instance.npz --traj /app/output/trajectory.npz`

## Conventions
- World frame, metres; z up; the robots stand at low x and reach towards +x. The table top is at z = 0.942. Arm base (`link0`): link0_right [-0.75, -0.4, 0.924], link0_left [-0.75, 0.4, 0.924]. The right arm works at y < 0, the left arm at y > 0. Quaternions are **WXYZ**.
- Action (46): per arm, right first: tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro
  joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
  target and stops where contact blocks it); the hand joints are position-controlled. `s.hold_action()` is the no-op.
  At the start the tcp target is right [-0.443, -0.4, 1.517] / [0.0, -1.0, 0.0, -0.0025], left [-0.443, 0.4, 1.517] / [0.0, -1.0, 0.0, -0.0025].
- Allegro joint order (right hand): index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger =
  spread, 1-3 = flexion from the knuckle out; thumb 12 = opposition). The LEFT hand's 16 values are mirrored: ring 0-3, middle 4-7, index 8-11, thumb 12-15.
  Target ranges (rad, same for every finger slot, thumb last): low [-0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, -0.47, -0.2, -0.17, -0.23, 0.26, -0.1, -0.19, -0.16], high [0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 0.47, 1.61, 1.71, 1.62, 1.4, 1.16, 1.64, 1.72]; the simulator clamps
  targets to them.
- Control runs at 50 Hz (10 physics substeps of 2 ms). DexJoCo's own episode cap and real-time pacing are lifted: your
  sessions have no step budget, your wall-clock time is the limit (~140 control steps/s here); only the
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
