# MyoSuite · baoding — frozen instance

You control the **MyoHand**, a musculoskeletal model of a human forearm and hand (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — 39
muscles: there is no joint-level controller.
**Task:** Baoding balls: rotate the two balls around each other in the palm so that each follows its moving target (the targets circle the palm once every 5 s). Success: both balls within 0.015 m of their targets for 200 consecutive control steps (5.0 s: one full orbit of the targets). Failure (the episode ends): a ball's height (world z) drops below 1.25 m, i.e. it falls out of the palm.

Two balls rest in the palm of the upturned hand; two small markers show where each ball should be now. `s.state()` gives the task's observation dict (privileged): `hand_pos`, `object1_pos`, `object2_pos`, `object1_velp`, `object2_velp`, `target1_pos`, `target2_pos`, `target1_err`, `target2_err`, `act`.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/myosuite/envs/myo/myochallenge/baoding_v1.py`; `solved` is the goal test,
`done` the failure test):
```python
def get_reward_dict(self, obs_dict):
    # tracking error
    target1_dist = np.linalg.norm(obs_dict["target1_err"], axis=-1)
    target2_dist = np.linalg.norm(obs_dict["target2_err"], axis=-1)
    target_dist = target1_dist + target2_dist
    act_mag = np.linalg.norm(self.obs_dict["act"], axis=-1)
    if self.mj_model.na != 0:
        act_mag = act_mag / self.mj_model.na

    # detect fall
    object1_pos = (
        obs_dict["object1_pos"][:, :, 2]
        if obs_dict["object1_pos"].ndim == 3
        else obs_dict["object1_pos"][2]
    )
    object2_pos = (
        obs_dict["object2_pos"][:, :, 2]
        if obs_dict["object2_pos"].ndim == 3
        else obs_dict["object2_pos"][2]
    )
    is_fall_1 = object1_pos < self.drop_th
    is_fall_2 = object2_pos < self.drop_th
    is_fall = np.logical_or(is_fall_1, is_fall_2)  # keep both balls up

    rwd_dict = collections.OrderedDict(
        (
            # Perform reward tuning here --
            # Update Optional Keys section below
            # Update reward keys (DEFAULT_RWD_KEYS_AND_WEIGHTS) accordingly to update final rewards
            # Examples: Env comes pre-packaged with two keys pos_dist_1 and pos_dist_2
            # Optional Keys
            ("pos_dist_1", -1.0 * target1_dist),
            ("pos_dist_2", -1.0 * target2_dist),
            # Must keys
            ("act_reg", -1.0 * act_mag),
            ("sparse", -target_dist),
            (
                "solved",
                (target1_dist < self.proximity_th)
                * (target2_dist < self.proximity_th)
                * (~is_fall),
            ),
            ("done", is_fall),
        )
    )
    rwd_dict["dense"] = np.sum(
        [wt * rwd_dict[key] for key, wt in self.rwd_keys_wt.items()], axis=0
    )

    # Sucess Indicator
    self.mj_model.geom_rgba[self.object1_gid, :2] = (
        np.array([1, 1])
        if target1_dist < self.proximity_th
        else np.array([0.5, 0.5])
    )
    self.mj_model.geom_rgba[self.object2_gid, :2] = (
        np.array([0.9, 0.7])
        if target1_dist < self.proximity_th
        else np.array([0.5, 0.5])
    )

    return rwd_dict
```
Robot Coding Bench counts the goal only when `solved` holds for 200 consecutive control steps (5.0 s); `done` ends the episode as a failure. MyoSuite's step budget is lifted.

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Save a trajectory as soon as you have one that works, improve it while time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_myosuite import Session
s = Session("baoding", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # 39 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (39, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (25 ms): 39 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 39) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("hand_top")            # RGB uint8 (480, 640, 3); cameras: side_view, front_view, hand_top, hand_bottom, hand_side_inter, hand_side_exter, plam_lookat
s.render_video(actions, "/app/output/check.mp4", cameras=["hand_top"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 39 real numbers per control step, one per actuator in order: 39 muscles. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity.
- Control step 25 ms (10 physics substeps). There is no step budget: your wall-clock time is the limit
  (~1500 control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
