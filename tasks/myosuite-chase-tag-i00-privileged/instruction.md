# MyoSuite · chase_tag — frozen instance

You control the **MyoLegs**, a free-standing musculoskeletal model of a human torso and both legs (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — 80
muscles: there is no joint-level controller.
**Task:** Tag the opponent: bring your pelvis within 0.5 m of it (horizontal distance) within 20 s of simulated time (MyoChallenge 2023 ChaseTag P1, task CHASE). Failure (the episode ends): the time limit, leaving the 13 x 13 m arena, or the pelvis below 0.5 m (fallen).

A musculoskeletal body with two legs stands in a square arena; an opponent stands somewhere in it (in this frozen instance it does not move). `s.state()` gives the task's observation dict (privileged): `internal_qpos`, `internal_qvel`, `grf`, `torso_angle`, `muscle_length`, `muscle_velocity`, `muscle_force`, `act`, `opponent_pose`, `opponent_vel`, `model_root_pos`, `model_root_vel`, `task`.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/myosuite/envs/myo/myochallenge/chasetag_v0.py`; `solved` is the goal test,
`done` the failure test):
```python
def get_reward_dict(self, obs_dict):
    """
    Rewards are computed from here, using the <self.weighted_reward_keys>.
    These weights can either be set in this file in the
    DEFAULT_RWD_KEYS_AND_WEIGHTS dict, or when registering the environment
    with gym.register in myochallenge/__init__.py
    """
    act_mag = (
        np.linalg.norm(self.obs_dict["act"], axis=-1) / self.mj_model.na
        if self.mj_model.na != 0
        else 0
    )

    # The task is entirely defined by these 3 lines
    win_cdt = self._win_condition()
    lose_cdt = self._lose_condition()
    if self.current_task.name == "CHASE":
        score = self._get_score(float(self.obs_dict["time"])) if win_cdt else 0
        self.obs_dict["time"] = self.maxTime if lose_cdt else self.obs_dict["time"]
    elif self.current_task.name == "EVADE":
        score = (
            self._get_score(float(self.obs_dict["time"]))
            if (win_cdt or lose_cdt)
            else 0
        )
    # ----------------------

    # Example reward, you should change this!
    distance = np.linalg.norm(
        obs_dict["model_root_pos"][..., :2] - obs_dict["opponent_pose"][..., :2]
    )

    rwd_dict = collections.OrderedDict(
        (
            # Perform reward tuning here --
            # Update Optional Keys section below
            # Update reward keys (DEFAULT_RWD_KEYS_AND_WEIGHTS) accordingly to update final rewards
            # Example: simple distance function
            # Optional Keys
            ("act_reg", act_mag),
            ("distance", distance),
            ("lose", lose_cdt),
            # Must keys
            ("sparse", score),
            ("solved", win_cdt),
            ("done", self._get_done()),
        )
    )
    rwd_dict["dense"] = np.sum(
        [wt * rwd_dict[key] for key, wt in self.rwd_keys_wt.items()], axis=0
    )

    # Success Indicator
    self.mj_model.site_rgba[self.success_indicator_sid, :] = (
        np.array([0, 2, 0, 0.2]) if rwd_dict["solved"] else np.array([2, 0, 0, 0])
    )
    return rwd_dict
```
`solved` is the challenge's own success event: the episode ends in success at the first control step where it holds; `done` without it (its failure conditions, its own time limit) ends it as a failure. The gym step budget (`max_episode_steps`) is lifted; the challenge's own time limit is not.

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Your time budget is 5400 s of wall clock. Save a trajectory as soon as you have one that works, improve it while
time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_myosuite import Session
s = Session("chase_tag", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # 80 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (80, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (10 ms): 80 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 80) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("topview")            # RGB uint8 (480, 640, 3); cameras: topview, opponent_view, agent_view
s.render_video(actions, "/app/output/check.mp4", cameras=["topview"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 80 real numbers per control step, one per actuator in order: 80 muscles. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity.
- Control step 10 ms (10 physics substeps). There is no step budget: your wall-clock time is the limit
  (~1200 control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
